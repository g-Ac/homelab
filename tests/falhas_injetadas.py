#!/usr/bin/env python3
"""Teste de falhas injetadas 0001 (pré-registro: docs/testes/0001-falhas-injetadas-prereg.md).

Roda no Pi como usuário comum (usa sudo -n e ssh srv). Só biblioteca padrão.
Uso:
    python3 tests/falhas_injetadas.py --smoke          # valida o instrumento sem injetar falha real
    python3 tests/falhas_injetadas.py --saida ARQ.json # rodada completa (única)
"""
import argparse
import json
import subprocess
import sys
import time
import unicodedata
import urllib.request

AGENTE = "http://127.0.0.1:9099/alerta"
ALERTMANAGER = "http://127.0.0.1:9093/api/v2/alerts?active=true&silenced=false&inhibited=false"
ESTADO = "/var/lib/homelab-sre"
CRITICO, ATENCAO = "🔴 CRÍTICO", "🟡 ATENÇÃO"

TERMOS_PARADO = ["inactive", "inativ", "dead", "parad", "stopped", "nao esta ativ", "desativad", "encerrad"]
CENARIOS = [
    {"id": "F1", "tipo": "sintetico", "casa": "[F1]", "gravidade": CRITICO, "acao": "🔁 Reiniciar gateway",
     "ia": True, "limite": 300,
     "termos": ["contradiz", "falso alarme", "funcionando", "se recuperou", "running", "esta no ar", "operacional"]},
    {"id": "F2", "injetar": ["ssh", "srv", "sudo -n systemctl stop crypto-analyst"],
     "desfazer": ["ssh", "srv", "sudo -n systemctl start crypto-analyst"],
     "casa": "crypto-analyst", "gravidade": CRITICO, "acao": "🔁 Reiniciar crypto-analyst", "ia": True, "limite": 300,
     "termos": TERMOS_PARADO},
    {"id": "F3", "injetar": ["sudo", "-n", "systemctl", "stop", "painel-servidor"],
     "desfazer": ["sudo", "-n", "systemctl", "start", "painel-servidor"],
     "casa": "painel-servidor", "gravidade": CRITICO, "acao": "🔁 Reiniciar painel-servidor", "ia": True, "limite": 300,
     "termos": TERMOS_PARADO},
    {"id": "F4", "injetar": ["ssh", "srv", "sudo -n systemctl stop gpu-metricas.timer"],
     "desfazer": ["ssh", "srv", "sudo -n systemctl start gpu-metricas.timer"],
     "casa": "Coleta de métricas da GPU parada", "gravidade": ATENCAO, "acao": "🔁 Reiniciar coleta da GPU", "ia": True,
     "limite": 720, "termos": ["timer", "inactive", "inativ", "dead", "desativad"]},
    {"id": "F5", "injetar": ["ssh", "srv", "sudo -n systemctl stop node_exporter"],
     "desfazer": ["ssh", "srv", "sudo -n systemctl start node_exporter"],
     "casa": "srv não responde", "gravidade": CRITICO, "acao": None, "ia": True, "limite": 300,
     "termos": ["responde", "online", "uptime", "node_exporter", "falso alarme", "contradiz", "esta no ar",
                "funcionando", "acessivel", "ativa"]},
    {"id": "F6", "injetar": ["ssh", "srv", "docker stop ollama"], "desfazer": ["ssh", "srv", "docker start ollama"],
     "casa": "ollama (srv) fora do ar", "gravidade": CRITICO, "acao": "🔁 Reiniciar Ollama", "ia": False, "limite": 300},
    {"id": "F7", "injetar": ["ssh", "srv", "docker stop bifrost"], "desfazer": ["ssh", "srv", "docker start bifrost"],
     "casa": "gateway (srv) fora do ar", "nao_casa": "[F1]", "gravidade": CRITICO, "acao": "🔁 Reiniciar gateway",
     "ia": False, "limite": 300},
]


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def ler_jsonl(nome):
    r = subprocess.run(["sudo", "-n", "cat", f"{ESTADO}/{nome}"], capture_output=True, text=True)
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]


def ts_local(s):
    return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))


def esperar(predicado, limite_s, passo=5):
    fim = time.time() + limite_s
    while time.time() < fim:
        r = predicado()
        if r:
            return r
        time.sleep(passo)
    return None


def avisos_desde(t0):
    return [a for a in ler_jsonl("avisos.jsonl") if ts_local(a["ts"]) >= int(t0)]


def casa(c, texto, resolvido=False):
    primeira = texto.splitlines()[0] if texto else ""
    if resolvido != primeira.startswith("✅ RESOLVIDO"):
        return False
    return c["casa"] in primeira and not (c.get("nao_casa") and c["nao_casa"] in primeira)


# Emenda 1 (rodada 2): só estes alertas podem ser efeito das injeções; os demais são alheios ao teste.
ALERTAS_DO_TESTE = {"MaquinaFora", "ServicoHttpFora", "ServicoSystemdParado", "MetricasGpuParadas", "GpuSemDriver"}


def alertas_ativos():
    try:
        with urllib.request.urlopen(ALERTMANAGER, timeout=10) as r:
            return [a["labels"].get("alertname") for a in json.load(r)
                    if a["labels"].get("alertname") in ALERTAS_DO_TESTE]
    except OSError:
        return ["(alertmanager inacessível)"]


def explicacao(texto):
    """Só o trecho escrito pela IA: entre o cabeçalho e a linha '🤖 explicação'."""
    linhas = texto.splitlines()
    fim = next((i for i, l in enumerate(linhas) if l.startswith("🤖 explicação")), None)
    return None if fim is None else "\n".join(linhas[1:fim]).strip()


def avaliar(c, aviso, t0):
    texto = aviso["texto"]
    r = {"segundos_ate_aviso": round(ts_local(aviso["ts"]) - t0), "texto": texto}
    r["M1"] = r["segundos_ate_aviso"] <= c["limite"]
    r["M2"] = texto.startswith(c["gravidade"])
    exp = explicacao(texto)
    if c["ia"]:
        r["M3"] = bool(exp) and any(t in sem_acento(exp) for t in c["termos"])
    else:
        r["M4"] = "montada só pelas regras" in texto
    sugerida = next((l.split("Sugestão: ", 1)[1].split(". Só executo")[0] for l in texto.splitlines()
                     if "👉 Sugestão:" in l), None)
    r["acao_sugerida"] = sugerida
    r["M5"] = sugerida == c["acao"]
    return r


def rodar_cenario(c):
    print(f"\n=== {c['id']} ===", flush=True)
    ativos = esperar(lambda: not alertas_ativos() or None, 900, 15)
    if ativos is None:
        return {"id": c["id"], "invalido": f"alertas pendentes antes de começar: {alertas_ativos()}"}
    t0 = time.time()
    if c.get("tipo") == "sintetico":
        corpo = {"alerts": [{"status": "firing", "labels": {"alertname": "ServicoHttpFora", "maquina": "srv",
                 "servico": "gateway", "gravidade": "critico", "alvo": "http://127.0.0.1:1/"},
                 "annotations": {"resumo": "[F1] gateway (srv) fora do ar",
                                 "descricao": "Cenário de controle: o gateway está saudável."}}]}
        req = urllib.request.Request(AGENTE, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    else:
        p = subprocess.run(c["injetar"], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return {"id": c["id"], "invalido": f"injeção falhou: {p.stderr.strip()[:200]}"}
    print(f"injetado às {time.strftime('%H:%M:%S')}", flush=True)
    aviso = esperar(lambda: next((a for a in avisos_desde(t0) if casa(c, a["texto"])), None), c["limite"] + 300)
    if c.get("desfazer"):
        subprocess.run(c["desfazer"], capture_output=True, text=True, timeout=120)
        print(f"desfeito às {time.strftime('%H:%M:%S')}", flush=True)
    t_desfez = time.time()
    if aviso is None:
        return {"id": c["id"], "M1": False, "erro": "nenhum aviso dentro do prazo + 5 min de folga"}
    r = {"id": c["id"], **avaliar(c, aviso, t0)}
    if c.get("desfazer"):
        res = esperar(lambda: next((a for a in avisos_desde(t_desfez) if casa(c, a["texto"], resolvido=True)), None),
                      900)
        r["segundos_ate_resolvido"] = round(ts_local(res["ts"]) - t_desfez) if res else None
        r["M7"] = bool(res) and r["segundos_ate_resolvido"] <= 600
    print({k: v for k, v in r.items() if k != "texto"}, flush=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--saida")
    ap.add_argument("--cenarios", help="lista separada por vírgula (emenda 1: rodada 2 só com F5,F6,F7)")
    a = ap.parse_args()
    if a.smoke:  # valida leitura de avisos, casamento e avaliação, sem falha real
        t0 = time.time()
        corpo = {"alerts": [{"status": "firing", "labels": {"alertname": "SmokeInstrumento", "maquina": "pi",
                 "gravidade": "atencao"}, "annotations": {"resumo": "[SMOKE] teste do instrumento"}}]}
        urllib.request.urlopen(urllib.request.Request(AGENTE, json.dumps(corpo).encode(),
                                                      {"Content-Type": "application/json"}), timeout=10).read()
        c = {"id": "SMOKE", "casa": "[SMOKE]", "gravidade": ATENCAO, "acao": None, "ia": True, "limite": 300,
             "termos": ["smoke", "teste", "instrumento"]}
        aviso = esperar(lambda: next((x for x in avisos_desde(t0) if casa(c, x["texto"])), None), 180)
        print("aviso encontrado:", bool(aviso))
        if aviso:
            r = avaliar(c, aviso, t0)
            print({k: v for k, v in r.items() if k != "texto"})
            print("explicação extraída:", repr((explicacao(aviso["texto"]) or "")[:160]))
        print("alertas ativos no Alertmanager:", alertas_ativos())
        print("execuções registradas até agora:", sum(1 for x in ler_jsonl("acoes.jsonl") if x.get("evento") == "execucao"))
        return
    exec_antes = sum(1 for x in ler_jsonl("acoes.jsonl") if x.get("evento") == "execucao")
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S")
    escolhidos = set(a.cenarios.split(",")) if a.cenarios else {c["id"] for c in CENARIOS}
    resultados = [rodar_cenario(c) for c in CENARIOS if c["id"] in escolhidos]
    exec_depois = sum(1 for x in ler_jsonl("acoes.jsonl") if x.get("evento") == "execucao")
    final = {"inicio": inicio, "fim": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "M6_execucoes_durante_teste": exec_depois - exec_antes, "cenarios": resultados}
    with open(a.saida, "w") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print("\nresultado salvo em", a.saida)


if __name__ == "__main__":
    sys.exit(main())
