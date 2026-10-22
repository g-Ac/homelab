"""Aprovação humana de ações do agente SRE (issue #20). Lógica pura, sem rede, para ser testável.

Regras:
- Só ações do CATALOGO podem ser propostas.
- Cada proposta gera um token aleatório de uso único, válido por VALIDADE_S segundos.
- Só o dono (id do Telegram configurado) pode aprovar.
- Um token aprovado, ignorado ou expirado nunca mais executa nada.
"""
import json
import os
import secrets
import threading
import time

VALIDADE_S = 15 * 60

# acao_id -> (onde roda, comando enviado ao executor, texto do botão)
CATALOGO = {
    "reiniciar-container-ollama": ("srv", "reiniciar-container ollama", "🔁 Reiniciar Ollama"),
    "reiniciar-container-bifrost": ("srv", "reiniciar-container bifrost", "🔁 Reiniciar gateway"),
    "reiniciar-servico-crypto-analyst": ("srv", "reiniciar-servico crypto-analyst", "🔁 Reiniciar crypto-analyst"),
    "reiniciar-servico-canario-amostra": ("srv", "reiniciar-servico canario-amostra", "🔁 Reiniciar canário"),
    "reiniciar-servico-gpu-metricas": ("srv", "reiniciar-servico gpu-metricas.timer", "🔁 Reiniciar coleta da GPU"),
    **{f"reiniciar-servico-{s}": ("pi", s, f"🔁 Reiniciar {s}")
       for s in ("trade-desk", "liquidation-collector", "mesa", "radar", "painel-servidor", "mosquitto")},
}


def acao_sugerida(labels):
    """Mapeia o alerta para no máximo UMA ação do catálogo (ou None)."""
    nome = labels.get("alertname", "")
    maquina = labels.get("maquina", "")
    alvo = labels.get("servico") or labels.get("name", "").removesuffix(".service").removesuffix(".timer")
    if nome not in ("ServicoHttpFora", "ServicoSystemdParado", "MetricasGpuParadas"):
        return None
    if nome == "MetricasGpuParadas":
        return "reiniciar-servico-gpu-metricas"
    if maquina == "srv" and alvo == "ollama":
        return "reiniciar-container-ollama"
    if maquina == "srv" and alvo == "gateway":
        return "reiniciar-container-bifrost"
    candidato = f"reiniciar-servico-{alvo}"
    if candidato in CATALOGO and CATALOGO[candidato][0] == maquina:
        return candidato
    return None


class Pendentes:
    """Propostas aguardando decisão, persistidas em JSON (sobrevive a reinício do agente)."""

    def __init__(self, caminho, dono_id, relogio=time.time):
        self.caminho = caminho
        self.dono_id = str(dono_id)
        self.relogio = relogio
        self.trava = threading.Lock()
        self.dados = {}
        if os.path.exists(caminho):
            with open(caminho) as f:
                self.dados = json.load(f)

    def _salvar(self):
        tmp = self.caminho + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.dados, f)
        os.replace(tmp, self.caminho)

    def propor(self, acao_id, contexto):
        if acao_id not in CATALOGO:
            raise ValueError(f"ação fora do catálogo: {acao_id}")
        token = secrets.token_urlsafe(12)
        with self.trava:
            self.dados[token] = {"acao": acao_id, "contexto": contexto, "criado": self.relogio(), "estado": "pendente"}
            self._salvar()
        return token

    def decidir(self, token, usuario_id, decisao):
        """Devolve (ok, motivo, acao_id). Só devolve ok=True uma vez por token, e só para o dono."""
        with self.trava:
            p = self.dados.get(token)
            if p is None:
                return False, "desconhecido", None
            if str(usuario_id) != self.dono_id:
                return False, "usuario-nao-autorizado", None
            if p["estado"] != "pendente":
                return False, f"ja-{p['estado']}", None
            if self.relogio() - p["criado"] > VALIDADE_S:
                p["estado"] = "expirado"
                self._salvar()
                return False, "expirado", None
            if decisao not in ("aprovar", "ignorar"):
                return False, "decisao-invalida", None
            p["estado"] = "aprovado" if decisao == "aprovar" else "ignorado"
            p["decidido"] = self.relogio()
            self._salvar()
            return decisao == "aprovar", p["estado"], p["acao"]

    def limpar(self, idade_max_s=7 * 24 * 3600):
        with self.trava:
            agora = self.relogio()
            self.dados = {t: p for t, p in self.dados.items() if agora - p["criado"] < idade_max_s}
            self._salvar()
