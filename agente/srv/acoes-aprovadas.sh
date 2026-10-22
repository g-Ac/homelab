#!/usr/bin/env bash
# Ações APROVADAS pelo dono no Telegram (issue #20). Forced command da SEGUNDA chave do agente:
# separada da chave de diagnóstico, só executa o catálogo abaixo e registra tudo no journal.
set -euo pipefail
export LC_ALL=C.UTF-8

pedido="${SSH_ORIGINAL_COMMAND:-${*:-}}"
read -r acao alvo extra <<< "$pedido" || true

recusar() { logger -t homelab-acao "RECUSADO: '$pedido' ($1)"; echo "recusado: $1" >&2; exit 2; }
[ -z "${extra:-}" ] || recusar "argumentos demais"

case "$acao" in
  reiniciar-container)
    [[ "${alvo:-}" =~ ^(ollama|bifrost)$ ]] || recusar "container fora do catálogo"
    logger -t homelab-acao "EXECUTANDO: docker restart $alvo"
    docker restart "$alvo" >/dev/null
    docker ps --filter "name=^${alvo}\$" --format '{{.Names}} | {{.Status}}'
    ;;
  reiniciar-servico)
    [[ "${alvo:-}" =~ ^(crypto-analyst|canario-amostra|gpu-metricas\.timer)$ ]] || recusar "serviço fora do catálogo"
    unidade="$alvo"; [[ "$unidade" == *.timer ]] || unidade="$alvo.service"
    logger -t homelab-acao "EXECUTANDO: systemctl restart $unidade"
    sudo -n /usr/bin/systemctl restart "$unidade"
    systemctl is-active "$unidade"
    ;;
  *)
    recusar "ação desconhecida"
    ;;
esac
