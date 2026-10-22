#!/usr/bin/env bash
# Exporta o estado de energia do Raspberry Pi (vcgencmd get_throttled) para o textfile collector.
# Bits: 0 subtensão agora · 1 clock limitado agora · 2 throttling agora · 3 limite térmico agora
#       16 subtensão ocorreu · 17 clock limitado ocorreu · 18 throttling ocorreu · 19 limite térmico ocorreu
set -euo pipefail
dir=/var/lib/node_exporter/textfile; tmp="$dir/.pi-energia.prom.$$"
v=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2) || v=""
[[ "$v" =~ ^0x[0-9a-fA-F]+$ ]] || { printf '# TYPE homelab_pi_energia_up gauge\nhomelab_pi_energia_up 0\n' > "$tmp"; mv "$tmp" "$dir/pi-energia.prom"; exit 0; }
n=$((v))
bit() { echo $(( (n >> $1) & 1 )); }
{
  printf '# TYPE homelab_pi_energia_up gauge\nhomelab_pi_energia_up 1\n'
  printf '# TYPE homelab_pi_subtensao_agora gauge\nhomelab_pi_subtensao_agora %s\n' "$(bit 0)"
  printf '# TYPE homelab_pi_subtensao_desde_boot gauge\nhomelab_pi_subtensao_desde_boot %s\n' "$(bit 16)"
  printf '# TYPE homelab_pi_throttling_desde_boot gauge\nhomelab_pi_throttling_desde_boot %s\n' "$(bit 18)"
  printf '# TYPE homelab_pi_limite_termico_desde_boot gauge\nhomelab_pi_limite_termico_desde_boot %s\n' "$(bit 19)"
} > "$tmp"
mv "$tmp" "$dir/pi-energia.prom"
