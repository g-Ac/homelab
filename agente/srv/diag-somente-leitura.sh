#!/usr/bin/env bash
# Diagnóstico SOMENTE LEITURA para o agente SRE (ADR 0006, issue #19).
# Instalado como "forced command" no authorized_keys do srv: a chave do agente só consegue rodar ESTE script,
# e o script só aceita os pedidos do catálogo abaixo. Qualquer outra coisa é recusada e registrada.
set -euo pipefail
export LC_ALL=C.UTF-8

pedido="${SSH_ORIGINAL_COMMAND:-${*:-}}"
read -r acao alvo extra <<< "$pedido" || true

recusar() { logger -t homelab-diag "RECUSADO: '$pedido' ($1)"; echo "recusado: $1" >&2; exit 2; }
[ -z "${extra:-}" ] || recusar "argumentos demais"

SERVICOS='^(crypto-analyst|canario-amostra|docker|containerd|fail2ban|tailscaled|ssh|node_exporter|gpu-metricas)(\.service|\.timer)?$'
CONTAINERS='^(ollama|bifrost)$'

case "$acao" in
  resumo)
    [ -z "${alvo:-}" ] || recusar "resumo não aceita alvo"
    echo "## uptime"; uptime
    echo "## memória (MB)"; free -m
    echo "## disco /"; df -h /
    echo "## 5 processos com mais CPU"; ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu | head -6
    ;;
  servico)
    [[ "${alvo:-}" =~ $SERVICOS ]] || recusar "serviço fora do catálogo"
    echo "## systemctl status $alvo"; systemctl status --no-pager --lines=0 "$alvo" || true
    echo "## últimas 30 linhas do journal"; journalctl -u "$alvo" -n 30 --no-pager --output=short-iso 2>&1 || true
    ;;
  container)
    [[ "${alvo:-}" =~ $CONTAINERS ]] || recusar "container fora do catálogo"
    echo "## estado"; docker ps -a --filter "name=^${alvo}\$" --format '{{.Names}} | {{.Status}} | {{.Image}}'
    echo "## últimas 30 linhas do log"; docker logs --tail 30 --timestamps "$alvo" 2>&1 || true
    ;;
  gpu)
    [ -z "${alvo:-}" ] || recusar "gpu não aceita alvo"
    nvidia-smi --query-gpu=name,driver_version,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,fan.speed --format=csv 2>&1 || echo "nvidia-smi falhou"
    echo "## processos na GPU"; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>&1 || true
    ;;
  disco)
    [ -z "${alvo:-}" ] || recusar "disco não aceita alvo"
    df -h -x tmpfs -x overlay -x devtmpfs
    echo "## journal"; journalctl --disk-usage 2>&1 || true
    echo "## docker"; docker system df 2>&1 || true
    ;;
  *)
    recusar "ação desconhecida"
    ;;
esac
