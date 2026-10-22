#!/usr/bin/env bash
# Exporta métricas da GPU NVIDIA para o textfile collector do node_exporter (sem exporter extra).
set -euo pipefail
dir=/var/lib/node_exporter/textfile
tmp="$dir/.gpu.prom.$$"
campos=(temperatura_celsius utilizacao_pct memoria_usada_mib memoria_total_mib potencia_watts ventoinha_pct)

num() { local v; v=$(echo "$1" | tr -d ' '); [[ "$v" =~ ^[0-9.]+$ ]] && echo "$v" || echo "NaN"; }

if ! out=$(nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,fan.speed \
             --format=csv,noheader,nounits 2>/dev/null); then
  printf '# HELP homelab_gpu_up nvidia-smi respondeu\n# TYPE homelab_gpu_up gauge\nhomelab_gpu_up 0\n' > "$tmp"
  mv "$tmp" "$dir/gpu.prom"
  exit 0
fi

mapfile -t linhas <<< "$out"
{
  printf '# HELP homelab_gpu_up nvidia-smi respondeu\n# TYPE homelab_gpu_up gauge\nhomelab_gpu_up 1\n'
  for i in "${!campos[@]}"; do
    echo "# TYPE homelab_gpu_${campos[$i]} gauge"
    for linha in "${linhas[@]}"; do
      IFS=',' read -r -a v <<< "$linha"
      echo "homelab_gpu_${campos[$i]}{gpu=\"$(echo "${v[0]}" | xargs)\",nome=\"$(echo "${v[1]}" | xargs)\"} $(num "${v[$((i + 2))]}")"
    done
  done
} > "$tmp"
mv "$tmp" "$dir/gpu.prom"
