#!/usr/bin/env python3
"""Teste de aceitação da Etapa 1 (gateway). Roda no srv, só biblioteca padrão.

Uso:
    python3 aceitacao_etapa1.py [--env ~/stacks/bifrost/.env] [--fallback] [--overhead]

--fallback  remove temporariamente a tag do gemma4 no Ollama para provar o fallback (restaura no fim)
--overhead  mede o tempo extra do gateway (critério na issue #12)

Saída: uma linha por verificação (PASSA / FALHA / PULADO) e código de saída 1 se algo falhar.
"""
import argparse
import base64
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

GW = "http://127.0.0.1:8080"
OLLAMA = "http://127.0.0.1:11434"
PROMPT = "Responda só: ok"

resultados = []


def registrar(nome, ok, detalhe="", pulado=False):
    estado = "PULADO" if pulado else ("PASSA" if ok else "FALHA")
    resultados.append((nome, estado))
    print(f"[{estado:6}] {nome}" + (f" — {detalhe}" if detalhe else ""), flush=True)


def ler_env(caminho):
    env = {}
    for linha in open(os.path.expanduser(caminho)):
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k] = v
    return env


def http(metodo, url, corpo=None, headers=None, timeout=120):
    req = urllib.request.Request(url, method=metodo, headers={"Content-Type": "application/json", **(headers or {})})
    dados = json.dumps(corpo).encode() if corpo is not None else None
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, dados, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}"), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}"), time.perf_counter() - t0
        except json.JSONDecodeError:
            return e.code, {}, time.perf_counter() - t0


def chat(chave, modelo, prompt=PROMPT, **extra):
    headers = {"Authorization": f"Bearer {chave}"} if chave else {}
    corpo = {"model": modelo, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "seed": 42, **extra}
    return http("POST", f"{GW}/v1/chat/completions", corpo, headers)


def ollama(*args):
    return subprocess.run(["docker", "exec", "ollama", "ollama", *args], capture_output=True, text=True)


def erro(d):
    return ((d.get("error") or {}).get("message") or str(d))[:100]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="~/stacks/bifrost/.env")
    ap.add_argument("--fallback", action="store_true")
    ap.add_argument("--overhead", action="store_true")
    a = ap.parse_args()
    env = ler_env(a.env)
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    admin = "Basic " + base64.b64encode(f"{env['BIFROST_ADMIN_USERNAME']}:{env['BIFROST_ADMIN_PASSWORD']}".encode()).decode()

    # 1. Autenticação
    s, _, _ = chat(None, "local")
    registrar("inferência sem chave é recusada", s == 401, f"HTTP {s}")
    s, _, _ = chat("sk-bf-chave-falsa", "local")
    registrar("inferência com chave falsa é recusada", s == 401, f"HTTP {s}")
    s, _, _ = http("GET", f"{GW}/api/governance/virtual-keys")
    registrar("API de gestão sem login é recusada", s == 401, f"HTTP {s}")
    s, _, _ = http("GET", f"{GW}/api/governance/virtual-keys", headers={"Authorization": admin})
    registrar("API de gestão com login funciona", s == 200, f"HTTP {s}")

    # 2. Rota local e restrição de modelos
    s, d, _ = chat(env["VK_PRIVADO"], "local")
    registrar("chave 'privado' + apelido 'local' responde pelo gemma4",
              s == 200 and d.get("model") == "gemma4:e4b", f"HTTP {s}, modelo {d.get('model')}")
    s, d, _ = chat(env["VK_PRIVADO"], "ollama/llama3.1:8b")
    registrar("chave 'privado' não acessa modelo fora da lista (llama3.1:8b existe no Ollama)",
              s == 403, f"HTTP {s}: {erro(d)}")

    # Contrato de uso: tarefa simples manda reasoning_effort "none" (o qwen "pensa" por padrão)
    s, d, t = chat(env["VK_PRIVADO"], "ollama/qwen3.5:4b", reasoning_effort="none")
    saida = (d.get("usage") or {}).get("completion_tokens")
    registrar("reasoning_effort='none' desliga o 'pensar' do qwen", s == 200 and saida is not None and saida <= 10,
              f"{saida} tokens de saída em {t:.1f} s")

    # 3. Fallback real (opcional: mexe no Ollama)
    if a.fallback:
        ollama("cp", "gemma4:e4b", "aceitacao-backup/gemma4:e4b")
        ollama("rm", "gemma4:e4b")
        try:
            s, d, _ = chat(env["VK_PRIVADO"], "local")
            registrar("com o gemma4 fora, 'local' cai no qwen3.5:4b",
                      s == 200 and d.get("model") == "qwen3.5:4b", f"HTTP {s}, modelo {d.get('model')}")
        finally:
            ollama("cp", "aceitacao-backup/gemma4:e4b", "gemma4:e4b")
            ollama("rm", "aceitacao-backup/gemma4:e4b")
        s, d, _ = chat(env["VK_PRIVADO"], "local")
        registrar("gemma4 restaurado e de volta ao serviço", s == 200 and d.get("model") == "gemma4:e4b",
                  f"modelo {d.get('model')}")
    else:
        registrar("fallback gemma4 → qwen", True, "use --fallback", pulado=True)

    # 4. Limites
    codigos = [chat(env["VK_TESTE_LIMITE"], "local")[0] for _ in range(5)]
    registrar("limite de 3 req/min bloqueia com 429", 429 in codigos and codigos.count(200) <= 3, f"códigos {codigos}")
    codigos = []
    for _ in range(20):
        s, _, _ = chat(env["VK_TESTE_ORCAMENTO"], "local")
        codigos.append(s)
        if s != 200:
            break
    registrar("orçamento de US$ 0,0005/h bloqueia com 402", codigos[-1] == 402,
              f"{codigos.count(200)} chamadas aceitas antes do bloqueio")

    # 5. Privacidade dos logs
    time.sleep(2)
    s, d, _ = http("GET", f"{GW}/api/logs?limit=50", headers={"Authorization": admin})
    logs = [l for l in d.get("logs", []) if l.get("virtual_key_id") == "vk-privado"
            and l.get("status") == "success" and l.get("timestamp", "")[:19] >= inicio]
    sem_conteudo = bool(logs) and all(l.get("content_hidden") and not l.get("raw_request") for l in logs)
    registrar("logs da chave 'privado' não guardam conteúdo", sem_conteudo, f"{len(logs)} registros conferidos")
    com_custo = bool(logs) and all((l.get("cost") or 0) > 0 for l in logs)
    registrar("logs registram custo-sombra", com_custo)

    # 6. Rota de nuvem (issue #10)
    registrar("chave 'privado' recusada ao pedir modelo de nuvem", True, "aguarda #10", pulado=True)
    registrar("Ollama fora: 'privado' falha fechado, 'geral' vai para a nuvem", True, "aguarda #10", pulado=True)

    # 7. Overhead do gateway
    if a.overhead:
        direto_corpo = {"model": "gemma4:e4b", "prompt": PROMPT, "stream": False, "think": False,
                        "options": {"temperature": 0, "seed": 42}}
        http("POST", f"{OLLAMA}/api/generate", direto_corpo)  # aquecimento
        chat(env["VK_PRIVADO"], "ollama/gemma4:e4b")  # aquecimento
        difs = []
        for _ in range(30):
            _, _, t_direto = http("POST", f"{OLLAMA}/v1/chat/completions",
                                  {"model": "gemma4:e4b", "messages": [{"role": "user", "content": PROMPT}],
                                   "temperature": 0, "seed": 42})
            _, _, t_gw = chat(env["VK_PRIVADO"], "ollama/gemma4:e4b")
            difs.append((t_gw - t_direto) * 1000)
        med = statistics.median(difs)
        registrar("overhead mediano do gateway ≤ 50 ms", med <= 50,
                  f"mediana {med:.1f} ms (p10 {sorted(difs)[2]:.1f}, p90 {sorted(difs)[26]:.1f}; 30 pares)")
    else:
        registrar("overhead do gateway", True, "use --overhead", pulado=True)

    falhas = [n for n, e in resultados if e == "FALHA"]
    print(f"\n{sum(e == 'PASSA' for _, e in resultados)} passaram, {len(falhas)} falharam, "
          f"{sum(e == 'PULADO' for _, e in resultados)} pulados")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
