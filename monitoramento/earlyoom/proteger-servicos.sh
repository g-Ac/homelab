#!/usr/bin/env bash
# Marca serviços como "último a ser morto" por falta de memória (OOMScoreAdjust=-900).
# Aplica na hora (processos já rodando) e grava drop-in do systemd para os próximos starts. Não reinicia nada.
set -euo pipefail
SERVICOS=(trade-desk liquidation-collector mesa radar painel-servidor mosquitto tailscaled beszel-agent
          prometheus alertmanager blackbox_exporter node_exporter homelab-sre)
for s in "${SERVICOS[@]}"; do
  systemctl cat "$s.service" >/dev/null 2>&1 || { echo "  (pulado: $s não existe)"; continue; }
  install -d "/etc/systemd/system/$s.service.d"
  printf '[Service]\nOOMScoreAdjust=-900\n' > "/etc/systemd/system/$s.service.d/homelab-oom.conf"
  procs="/sys/fs/cgroup/system.slice/$s.service/cgroup.procs"
  n=0; if [ -r "$procs" ]; then while read -r pid; do echo -900 > "/proc/$pid/oom_score_adj" 2>/dev/null && n=$((n+1)); done < "$procs"; fi
  echo "  $s: protegido ($n processos)"
done
systemctl daemon-reload
