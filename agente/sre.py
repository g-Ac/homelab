#!/usr/bin/env python3
"""Agente SRE do homelab (ADR 0006, issue #19). Só biblioteca padrão.

Recebe alertas do Alertmanager, coleta diagnóstico SOMENTE LEITURA de um catálogo fechado,
pede uma explicação à IA local pelo gateway e avisa no Telegram.

Princípios:
- A gravidade vem da regra do Prometheus; a IA nunca a altera.
- Se a IA ou o srv estiverem fora, o aviso sai montado só por regras: nunca fica em silêncio.
- O agente não executa nenhuma ação corretiva (isso é a issue #20, com aprovação humana).
"""
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # pasta do agente (root, só leitura)
import aprovacao  # noqa: E402

log = logging.getLogger("homelab-sre")

CFG = {
    "ouvir": os.environ.get("SRE_OUVIR", "127.0.0.1:9099"),
    "gateway": os.environ.get("SRE_GATEWAY", ""),          # ex.: http://<srv>:8080
    "chave_ia": os.environ.get("SRE_CHAVE_IA", ""),        # chave virtual "sre" (só modelos locais)
    "srv_ssh": os.environ.get("SRE_SRV_SSH", ""),          # ex.: gac@<srv>
    "telegram_token": os.environ.get("SRE_TELEGRAM_TOKEN", ""),
    "telegram_chat": os.environ.get("SRE_TELEGRAM_CHAT", ""),
    "estado": os.environ.get("SRE_ESTADO", "/var/lib/homelab-sre"),
}
UA = "homelab-sre/1.0 (+https://github.com/g-Ac/homelab)"

# --- Diagnóstico: catálogo fechado ------------------------------------------------------------

SERVICOS_PI = {"trade-desk", "liquidation-collector", "mesa", "radar", "painel-servidor", "mosquitto",
               "beszel-agent", "tailscaled", "ssh", "prometheus", "alertmanager", "blackbox_exporter",
               "node_exporter"}
CONTAINERS_SRV = {"ollama": "ollama", "gateway": "bifrost"}
SERVICOS_SRV = {"crypto-analyst", "canario-amostra", "docker", "containerd", "fail2ban", "tailscaled",
                "ssh", "node_exporter", "gpu-metricas"}


def rodar(argv, timeout=20, cortar=True):
    """Executa um comando fixo (sem shell) e devolve a saída (cortada em começo + fim, salvo cortar=False)."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        saida = (r.stdout + r.stderr).strip()
        return trecho(saida, 1500, 1500) if cortar else saida
    except subprocess.TimeoutExpired:
        return f"(tempo esgotado após {timeout}s)"
    except OSError as e:
        return f"(falhou: {e})"


def diag_srv(pedido):
    if not CFG["srv_ssh"]:
        return "(acesso ao srv não configurado)"
    return rodar(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                  "-i", os.path.join(CFG["estado"], ".ssh", "id_ed25519"), CFG["srv_ssh"], pedido], timeout=30)


def diag_pi(acao, alvo=None):
    if acao == "resumo":
        top = "\n".join(rodar(["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"]).splitlines()[:6])
        return "\n".join([rodar(["uptime"]), rodar(["free", "-m"]), rodar(["df", "-h", "/"]), top])
    if acao == "servico" and alvo in SERVICOS_PI:
        return "\n".join([rodar(["systemctl", "status", "--no-pager", "--lines=0", f"{alvo}.service"]),
                          rodar(["journalctl", "-u", f"{alvo}.service", "-n", "30", "--no-pager", "-o", "short-iso"])])
    if acao == "disco":
        return "\n".join([rodar(["df", "-h", "-x", "tmpfs", "-x", "devtmpfs"]), rodar(["journalctl", "--disk-usage"])])
    if acao == "memoria":
        linhas = rodar(["ps", "-eo", "rss,pid,etime,args", "--sort=-rss", "--no-headers"], cortar=False).splitlines()[:12]
        top = [f"{int(l.split()[0]) // 1024:5d} MB  {' '.join(l.split()[1:])[:110]}" for l in linhas if l.split()[:1] and l.split()[0].isdigit()]
        return "\n".join([rodar(["free", "-m"]), "## processos que mais usam memória (MB, pid, tempo, comando)", *top])
    return "(diagnóstico fora do catálogo)"


def coletar(alerta):
    """Escolhe o diagnóstico pelo tipo de alerta. Devolve lista de (título, saída)."""
    l = alerta.get("labels", {})
    nome, maquina = l.get("alertname", ""), l.get("maquina", "")
    servico = l.get("servico") or l.get("name", "").removesuffix(".service")
    evid = []
    no_srv = maquina == "srv"
    if nome == "MaquinaFora":
        if no_srv:
            resumo = diag_srv("resumo")
            evid.append(("srv responde a SSH?", resumo))
            if "## uptime" in resumo:  # a máquina responde: o problema pode ser só o coletor (#25)
                evid.append(("coletor node_exporter", diag_srv("servico node_exporter")))
        else:
            evid.append(("coletor node_exporter", diag_pi("servico", "node_exporter")))
        evid.append(("tailscale", rodar(["tailscale", "status"])))
    elif nome in ("ServicoHttpFora", "ServicoSystemdParado"):
        if no_srv and servico in CONTAINERS_SRV:
            evid.append((f"container {CONTAINERS_SRV[servico]}", diag_srv(f"container {CONTAINERS_SRV[servico]}")))
        elif no_srv and servico in SERVICOS_SRV:
            evid.append((f"serviço {servico}", diag_srv(f"servico {servico}")))
        elif not no_srv and servico in SERVICOS_PI:
            evid.append((f"serviço {servico}", diag_pi("servico", servico)))
        evid.append(("resumo da máquina", diag_srv("resumo") if no_srv else diag_pi("resumo")))
    elif nome.startswith("Disco"):
        evid.append(("disco", diag_srv("disco") if no_srv else diag_pi("disco")))
    elif nome in ("MemoriaBaixa", "PiPertoDeTravar"):
        evid.append(("memória", diag_srv("resumo") if no_srv else diag_pi("memoria")))
    elif nome.startswith("Gpu") or nome == "MetricasGpuParadas":
        evid.append(("gpu", diag_srv("gpu")))
        if nome == "MetricasGpuParadas":
            evid.append(("timer", diag_srv("servico gpu-metricas.timer")))
    else:
        evid.append(("resumo da máquina", diag_srv("resumo") if no_srv else diag_pi("resumo")))
    return evid


# --- Redação: nada que pareça segredo sai do servidor ------------------------------------------

PADROES_SEGREDO = [
    r"sk-[A-Za-z0-9_\-]{16,}", r"gsk_[A-Za-z0-9]{20,}", r"AQ\.[A-Za-z0-9_\-]{20,}", r"AIza[0-9A-Za-z_\-]{30,}",
    r"ghp_[A-Za-z0-9]{30,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}", r"\d{8,10}:[A-Za-z0-9_\-]{30,}",
    r"(?i)(senha|password|passwd|token|secret|api[_-]?key)\s*[=:]\s*\S+",
]


def redigir(texto):
    for p in PADROES_SEGREDO:
        texto = re.sub(p, "[REDIGIDO]", texto)
    return texto


# --- IA via gateway ------------------------------------------------------------------------------

DISPONIBILIDADE = {"ServicoHttpFora", "ServicoSystemdParado", "MaquinaFora", "MetricasGpuParadas", "GpuSemDriver",
                   "ColetorLiquidacoesParado", "ColetorLiquidacoesDesconectado", "MetricasColetorParadas"}
NEGA_REGRA = ["falso alarme", "alarme falso", "contradiz", "nao confirma", "nao se confirma", "ja se resolveu",
              "ja se recuperou", "nao ha problema"]


def sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def classe_alerta(nome):
    """Disponibilidade (algo caiu) ou limiar numérico. Desconhecido conta como limiar, o mais restritivo."""
    return "disponibilidade" if nome in DISPONIBILIDADE else "limiar"


def filtrar_explicacao(classe, texto):
    """Trava determinística (#23): em alerta de limiar, a IA não pode desmentir a regra."""
    if not texto:
        return None
    if classe == "limiar" and any(t in sem_acento(texto) for t in NEGA_REGRA):
        return None
    return texto


INSTRUCAO_LIMIAR = (
    "Você é um engenheiro SRE explicando um alerta para o dono do laboratório, que NÃO é técnico. "
    "Responda em português, em no máximo 5 linhas curtas, neste formato:\n"
    "O que aconteceu: ...\nProvável causa: ...\nO que sugiro: ...\n"
    "Este é um alerta de LIMIAR NUMÉRICO. O valor medido pela regra, na descrição do alerta, é a fonte da "
    "verdade: comandos como df e free arredondam números. NUNCA diga que é falso alarme nem que a evidência "
    "contradiz o alerta. Explique o que está consumindo o recurso, com base na evidência, e o que fazer. "
    "Não invente comandos. Não opine sobre a gravidade: ela já foi definida pela regra."
)

INSTRUCAO = (
    "Você é um engenheiro SRE explicando um alerta para o dono do laboratório, que NÃO é técnico. "
    "Responda em português, em no máximo 5 linhas curtas, neste formato:\n"
    "O que aconteceu: ...\nProvável causa: ...\nO que sugiro: ...\n"
    "Use só a evidência fornecida. COMPARE a evidência com o alerta: se ela mostrar que o serviço está "
    "funcionando (por exemplo 'active (running)', 'Up', respostas 200 recentes), diga claramente que a "
    "evidência contradiz o alerta e que pode ser falso alarme ou que já se recuperou. "
    "Se a evidência não bastar, diga isso. Não invente comandos. "
    "Não opine sobre a gravidade: ela já foi definida pela regra."
)


def trecho(s, inicio, fim):
    """Começo + fim: o começo costuma ter o estado (systemctl/docker), o fim os logs recentes."""
    return s if len(s) <= inicio + fim else f"{s[:inicio]}\n[...]\n{s[-fim:]}"


def perguntar_ia(alerta, evid):
    if not (CFG["gateway"] and CFG["chave_ia"]):
        return None, "IA não configurada"
    l, a = alerta.get("labels", {}), alerta.get("annotations", {})
    contexto = f"Alerta: {l.get('alertname')} | máquina: {l.get('maquina')} | serviço: {l.get('servico') or l.get('name', '')}\n"
    contexto += f"Resumo da regra: {a.get('resumo', '')}\n{a.get('descricao', '')}\n\nEvidência coletada:\n"
    contexto += "\n".join(f"### {t}\n{trecho(s, 700, 800)}" for t, s in evid)
    classe = classe_alerta(l.get("alertname", ""))
    instrucao = INSTRUCAO if classe == "disponibilidade" else INSTRUCAO_LIMIAR
    corpo = {"model": "local", "reasoning_effort": "none", "temperature": 0, "max_tokens": 300,
             "messages": [{"role": "system", "content": instrucao}, {"role": "user", "content": redigir(contexto)}]}
    req = urllib.request.Request(f"{CFG['gateway']}/v1/chat/completions", json.dumps(corpo).encode(),
                                 {"Content-Type": "application/json", "User-Agent": UA,
                                  "Authorization": f"Bearer {CFG['chave_ia']}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        texto = filtrar_explicacao(classe, d["choices"][0]["message"]["content"].strip())
        if texto is None:
            log.warning("explicação da IA descartada: desmentia uma regra de limiar")
            return None, "explicação da IA descartada (desmentia a regra de limiar)"
        return texto, d.get("model")
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return None, f"IA indisponível ({type(e).__name__})"


# --- Mensagem e Telegram -------------------------------------------------------------------------

ICONE = {"critico": "🔴 CRÍTICO", "atencao": "🟡 ATENÇÃO"}


def montar(alerta, evid, explicacao, origem):
    l, a = alerta.get("labels", {}), alerta.get("annotations", {})
    if alerta.get("status") == "resolved":
        return f"✅ RESOLVIDO · {a.get('resumo') or l.get('alertname')}"
    cab = f"{ICONE.get(l.get('gravidade'), '⚪ ALERTA')} · {a.get('resumo') or l.get('alertname')}"
    partes = [cab, ""]
    if explicacao:
        partes += [explicacao, "", f"🤖 explicação: {origem} (IA local)"]
    else:
        partes += [a.get("descricao", ""), "", f"⚙️ {origem}; mensagem montada só pelas regras."]
    if evid:
        t, s = evid[0]
        linhas = s.strip().splitlines()
        estado = [x.strip() for x in linhas if re.search(r"Active:|\| Up |\| Exited|Main PID", x)][:2]
        if t == "memória":  # os maiores consumidores vêm logo após o cabeçalho
            i = next((n for n, x in enumerate(linhas) if x.startswith("## processos")), len(linhas))
            corpo = linhas[i + 1:i + 5]
        else:
            corpo = linhas[-4:]
        partes += ["", f"Evidência ({t}):", *(estado or []), *corpo]
    return redigir("\n".join(partes))[:3800]


def telegram(metodo, corpo, timeout=20):
    req = urllib.request.Request(f"https://api.telegram.org/bot{CFG['telegram_token']}/{metodo}",
                                 json.dumps(corpo).encode(), {"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("result")


def avisar(texto, teclado=None):
    os.makedirs(CFG["estado"], exist_ok=True)
    with open(os.path.join(CFG["estado"], "avisos.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "texto": texto}, ensure_ascii=False) + "\n")
    if not (CFG["telegram_token"] and CFG["telegram_chat"]):
        log.info("Telegram não configurado; aviso só registrado:\n%s", texto)
        return
    corpo = {"chat_id": CFG["telegram_chat"], "text": texto, "disable_web_page_preview": True}
    if teclado:
        corpo["reply_markup"] = {"inline_keyboard": teclado}
    for tentativa in range(3):
        try:
            return (telegram("sendMessage", corpo) or {}).get("message_id")
        except urllib.error.HTTPError as e:
            try:
                motivo = json.loads(e.read()).get("description", "")
            except ValueError:
                motivo = ""
            log.warning("Telegram recusou (HTTP %d): %s", e.code, motivo)
            if 400 <= e.code < 500 and e.code != 429:
                return  # erro do nosso lado (ex.: bot bloqueado): repetir não adianta
            time.sleep(3 * (tentativa + 1))
        except (urllib.error.URLError, TimeoutError) as e:
            log.warning("Telegram falhou (tentativa %d): %s", tentativa + 1, type(e).__name__)
            time.sleep(3 * (tentativa + 1))


# --- Ações aprovadas (issue #20) ---------------------------------------------------------------

pendentes = None  # criado no main() quando o Telegram está configurado


def executar(acao_id):
    onde, comando, _ = aprovacao.CATALOGO[acao_id]
    if onde == "srv":
        return rodar(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                      "-i", os.path.join(CFG["estado"], ".ssh", "id_acoes"), CFG["srv_ssh"], comando], timeout=90)
    # autorizado pelo polkit (60-homelab-sre.rules) só para os serviços do catálogo
    return rodar(["systemctl", "restart", f"{comando}.service"], timeout=90)


def conferir(acao_id, contexto):
    """Depois de agir, confere de forma independente se voltou, pelo alvo definido no catálogo (#24)."""
    time.sleep(20)
    spec = aprovacao.VERIFICACAO[acao_id]
    if spec[0] == "http":
        host = urllib.parse.urlparse(CFG["gateway"]).hostname
        url = f"http://{host}:{spec[1]}{spec[2]}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10) as r:
                return 200 <= r.status < 300, [f"checagem HTTP ({spec[2]}): {r.status}"]
        except (urllib.error.URLError, TimeoutError) as e:
            return False, [f"checagem HTTP ({spec[2]}) falhou: {type(e).__name__}"]
    unidade = spec[1]
    if spec[0] == "servico-srv":
        estado = diag_srv(f"servico {unidade}")
        linha = next((x.strip() for x in estado.splitlines() if "Active:" in x), estado.strip()[:120])
        return "active (running)" in estado or "active (waiting)" in estado, [linha]
    estado = rodar(["systemctl", "is-active", unidade]).strip()
    return estado == "active", [f"{unidade}: {estado}"]


def auditar(registro):
    with open(os.path.join(CFG["estado"], "acoes.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **registro}, ensure_ascii=False) + "\n")


def tratar_clique(cq):
    dados, quem = cq.get("data", ""), str(cq.get("from", {}).get("id", ""))
    msg = cq.get("message") or {}
    tipo, _, token = dados.partition(":")
    decisao = {"a": "aprovar", "i": "ignorar"}.get(tipo, "invalida")
    ok, motivo, acao_id = pendentes.decidir(token, quem, decisao)
    auditar({"evento": "clique", "usuario": quem, "decisao": decisao, "resultado": motivo, "acao": acao_id})
    respostas = {"aprovado": "Executando…", "ignorado": "Ok, ignorado.", "expirado": "Expirou (mais de 15 min).",
                 "usuario-nao-autorizado": "Você não pode aprovar isto."}
    try:
        telegram("answerCallbackQuery", {"callback_query_id": cq["id"],
                                         "text": respostas.get(motivo, f"Recusado: {motivo}")})
        if motivo in ("aprovado", "ignorado", "expirado") and msg:
            telegram("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                                "reply_markup": {"inline_keyboard": []}})
    except (urllib.error.URLError, TimeoutError):
        pass
    if not ok:
        if motivo == "usuario-nao-autorizado":
            log.warning("clique de usuário não autorizado (%s) recusado", quem)
        return
    contexto = pendentes.dados.get(token, {}).get("contexto", {})
    rotulo = aprovacao.CATALOGO[acao_id][2]
    log.info("ação aprovada por %s: %s", quem, acao_id)
    saida = executar(acao_id)
    voltou, linhas = conferir(acao_id, contexto)
    auditar({"evento": "execucao", "usuario": quem, "acao": acao_id, "voltou": voltou, "saida": saida[-300:]})
    icone = "✅ Resolvido" if voltou else "⚠️ Executei, mas NÃO voltou"
    avisar(redigir(f"{icone} · {rotulo}\n\n" + "\n".join(linhas) +
                   ("" if voltou else "\n\nPrecisa de olho humano: confira os logs.")))


def escutar_cliques():
    """Long polling só de callback_query. Atenção: o bot não pode ter outro programa lendo getUpdates."""
    offset = None
    while True:
        try:
            corpo = {"timeout": 25, "allowed_updates": ["callback_query"]}
            if offset is not None:
                corpo["offset"] = offset
            for u in telegram("getUpdates", corpo, timeout=35) or []:
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    threading.Thread(target=tratar_clique, args=(u["callback_query"],), daemon=True).start()
        except Exception as e:  # rede instável: espera e tenta de novo
            log.warning("escuta do Telegram: %s", type(e).__name__)
            time.sleep(10)


# --- Fila e servidor HTTP ------------------------------------------------------------------------

fila = queue.Queue(maxsize=100)


def trabalhador():
    while True:
        alerta = fila.get()
        try:
            if alerta.get("status") == "resolved":
                avisar(montar(alerta, [], None, ""))
                continue
            evid = coletar(alerta)
            explicacao, origem = perguntar_ia(alerta, evid)
            texto, teclado = montar(alerta, evid, explicacao, origem), None
            acao = aprovacao.acao_sugerida(alerta.get("labels", {}))
            if acao and pendentes is not None:
                l = alerta.get("labels", {})
                token = pendentes.propor(acao, {"alerta": l.get("alertname"), "maquina": l.get("maquina"),
                                                "alvo": l.get("alvo", ""), "resumo": alerta.get("annotations", {}).get("resumo", "")})
                rotulo = aprovacao.CATALOGO[acao][2]
                texto += f"\n\n👉 Sugestão: {rotulo}. Só executo se você aprovar (vale 15 min)."
                teclado = [[{"text": f"✅ {rotulo}", "callback_data": f"a:{token}"},
                            {"text": "Ignorar", "callback_data": f"i:{token}"}]]
            avisar(texto, teclado)
        except Exception:  # o agente nunca pode morrer por causa de um alerta
            log.exception("erro ao processar alerta")
            avisar(f"⚠️ Agente SRE falhou ao processar {alerta.get('labels', {}).get('alertname')}; ver journal.")
        finally:
            fila.task_done()


class Webhook(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/alerta":
            self.send_error(404)
            return
        try:
            tamanho = min(int(self.headers.get("Content-Length", 0)), 1_000_000)
            dados = json.loads(self.rfile.read(tamanho))
            for alerta in dados.get("alerts", []):
                fila.put_nowait(alerta)
            self.send_response(200)
        except (ValueError, queue.Full):
            self.send_response(400)
        self.end_headers()

    def do_GET(self):
        if self.path == "/saude":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"fila": fila.qsize()}).encode())
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    global pendentes
    if CFG["telegram_token"] and CFG["telegram_chat"]:
        pendentes = aprovacao.Pendentes(os.path.join(CFG["estado"], "pendentes.json"), CFG["telegram_chat"])
        pendentes.limpar()
        threading.Thread(target=escutar_cliques, daemon=True).start()
    threading.Thread(target=trabalhador, daemon=True).start()
    host, porta = CFG["ouvir"].rsplit(":", 1)
    log.info("agente SRE ouvindo em %s (Telegram %s, IA %s)", CFG["ouvir"],
             "ligado" if CFG["telegram_token"] else "desligado", "ligada" if CFG["chave_ia"] else "desligada")
    ThreadingHTTPServer((host, int(porta)), Webhook).serve_forever()


if __name__ == "__main__":
    main()
