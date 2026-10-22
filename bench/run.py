#!/usr/bin/env python3
"""Benchmark de modelos locais no Ollama (pré-registro: docs/benchmarks/0001-prereg.md).

Uso: python3 run.py MODELO [MODELO ...]
Só biblioteca padrão. Grava respostas brutas em results/<modelo>.jsonl e métricas em results/<modelo>.summary.json.
"""
import json
import re
import statistics
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
BASE = Path(__file__).parent
DATA = BASE / "data"
OUT = BASE / "results"

OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096}

PROMPT_T1 = """Você classifica alertas de infraestrutura em exatamente uma classe:
- "critico": serviço fora do ar, perda de dados em curso ou iminente, ou segurança comprometida. Exige ação imediata.
- "atencao": degradação ou tendência que vira problema em horas ou dias. Exige ação planejada.
- "ruido": informativo, esperado ou resolvido sozinho. Nenhuma ação necessária.

Alerta:
{texto}

Responda em JSON no formato {{"classe": "critico" | "atencao" | "ruido"}}."""

SCHEMA_T1 = {
    "type": "object",
    "properties": {"classe": {"type": "string", "enum": ["critico", "atencao", "ruido"]}},
    "required": ["classe"],
}

PROMPT_T2 = """Extraia do documento abaixo:
- "cnpj": CNPJ de quem recebe o pagamento (beneficiário, emitente, prestador, credor ou fornecedor). Em guia de imposto, o CNPJ do contribuinte. Só os 14 dígitos.
- "valor_total": valor a pagar na data de vencimento, como número (ex.: 1234.56).
- "vencimento": data de vencimento no formato AAAA-MM-DD.

Documento:
{texto}

Responda em JSON."""

SCHEMA_T2 = {
    "type": "object",
    "properties": {
        "cnpj": {"type": "string"},
        "valor_total": {"type": "number"},
        "vencimento": {"type": "string"},
    },
    "required": ["cnpj", "valor_total", "vencimento"],
}

PROMPT_T3 = """Resuma o log abaixo em no máximo 2 frases em português, dizendo o que aconteceu e qual o efeito.

{texto}"""


def call(model, prompt, fmt=None, keep_alive="10m"):
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": OPTIONS,
        "keep_alive": keep_alive,
    }
    if fmt is not None:
        body["format"] = fmt
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.load(r)
    resp["_wall_s"] = time.time() - t0
    return resp


def load(name):
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line.strip()]


def norm_text(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def parse_json(s):
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def norm_date(s):
    """Aceita AAAA-MM-DD, DD/MM/AAAA e DD-MM-AAAA; qualquer outra forma vira None (erro)."""
    s = str(s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s
    m = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def tps(resp):
    d = resp.get("eval_duration") or 0
    return resp.get("eval_count", 0) / (d / 1e9) if d else 0.0


def gpu_fraction(model):
    with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=30) as r:
        for m in json.load(r).get("models", []):
            if m["name"] == model or m["model"] == model:
                return m.get("size_vram", 0) / m["size"] if m.get("size") else 0.0, m.get("size", 0)
    return 0.0, 0


def run_model(model):
    OUT.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", model)
    raw = open(OUT / f"{safe}.jsonl", "w")

    def log(task, item_id, resp, extra):
        raw.write(json.dumps({
            "task": task, "id": item_id, "response": resp.get("response"),
            "eval_count": resp.get("eval_count"), "eval_duration": resp.get("eval_duration"),
            "prompt_eval_count": resp.get("prompt_eval_count"), "total_duration": resp.get("total_duration"),
            "wall_s": resp["_wall_s"], **extra,
        }, ensure_ascii=False) + "\n")

    # aquecimento: carrega o modelo, descartado
    call(model, "Responda apenas: ok")

    t1 = load("t1_alertas.jsonl")
    t1_ok = 0
    lat = []
    for it in t1:
        r = call(model, PROMPT_T1.format(texto=it["texto"]), SCHEMA_T1)
        pred = (parse_json(r.get("response")) or {}).get("classe")
        ok = pred == it["gabarito"]
        t1_ok += ok
        lat.append(r["_wall_s"])
        log("t1", it["id"], r, {"pred": pred, "gabarito": it["gabarito"], "ok": ok})

    gpu_frac, size = gpu_fraction(model)

    t2 = load("t2_documentos.jsonl")
    t2_ok = 0
    for it in t2:
        r = call(model, PROMPT_T2.format(texto=it["texto"]), SCHEMA_T2)
        p = parse_json(r.get("response")) or {}
        g = it["gabarito"]
        cnpj_ok = re.sub(r"\D", "", str(p.get("cnpj", ""))) == g["cnpj"]
        try:
            valor_ok = round(float(p.get("valor_total")), 2) == round(g["valor_total"], 2)
        except (TypeError, ValueError):
            valor_ok = False
        venc_ok = norm_date(p.get("vencimento")) == g["vencimento"]
        t2_ok += cnpj_ok + valor_ok + venc_ok
        lat.append(r["_wall_s"])
        log("t2", it["id"], r, {"pred": p, "gabarito": g, "ok": [cnpj_ok, valor_ok, venc_ok]})

    t3 = load("t3_logs.jsonl")
    t3_scores, t3_tps = [], []
    for it in t3:
        r = call(model, PROMPT_T3.format(texto=it["texto"]))
        txt = norm_text(r.get("response", ""))
        hits = [any(norm_text(k) in txt for k in group) for group in it["fatos_chave"]]
        t3_scores.append(sum(hits) / len(hits))
        t3_tps.append(tps(r))
        log("t3", it["id"], r, {"hits": hits})

    call(model, "ok", keep_alive=0)  # descarrega antes do próximo modelo
    raw.close()

    summary = {
        "model": model,
        "t1_acertos": t1_ok, "t1_total": len(t1), "t1_acuracia": round(t1_ok / len(t1), 4),
        "t2_acertos": t2_ok, "t2_total": 3 * len(t2), "t2_acuracia": round(t2_ok / (3 * len(t2)), 4),
        "t3_cobertura_media": round(statistics.mean(t3_scores), 4),
        "tokens_s_mediana_t3": round(statistics.median(t3_tps), 2),
        "latencia_mediana_t1t2_s": round(statistics.median(lat), 3),
        "fracao_na_gpu": round(gpu_frac, 4),
        "tamanho_carregado_gb": round(size / 1e9, 2),
    }
    summary["go"] = (
        summary["t1_acuracia"] >= 0.85
        and summary["t2_acuracia"] >= 0.85
        and summary["tokens_s_mediana_t3"] >= 15
        and summary["fracao_na_gpu"] >= 0.999
    )
    (OUT / f"{safe}.summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return summary


if __name__ == "__main__":
    for m in sys.argv[1:]:
        print(json.dumps(run_model(m), ensure_ascii=False), flush=True)
