#!/usr/bin/env bash
# Exporta a saúde do coletor de liquidações (freqtrade-lab) para o textfile collector do node_exporter.
# Lê só a tabela de batimentos (um registro por minuto e conexão), do fim para trás: consulta barata.
# Roda como o dono do banco; a pasta do textfile tem ACL de escrita para esse usuário.
set -euo pipefail
db="${COLETOR_DB:-/home/gac/stacks/coletor-liquidacoes/dados/liquidacoes.db}"
dir=/var/lib/node_exporter/textfile; tmp="$dir/.coletor-liquidacoes.prom.$$"
trap 'rm -f "$tmp"' EXIT
{
  echo "# HELP homelab_coletor_liq_ultimo_batimento_segundos Hora do último batimento gravado pelo coletor."
  echo "# TYPE homelab_coletor_liq_ultimo_batimento_segundos gauge"
  echo "# HELP homelab_coletor_liq_conexoes_conectadas Conexões conectadas no último batimento, por fonte."
  echo "# TYPE homelab_coletor_liq_conexoes_conectadas gauge"
  echo "# HELP homelab_coletor_liq_conexoes_total Conexões existentes no último batimento, por fonte."
  echo "# TYPE homelab_coletor_liq_conexoes_total gauge"
  echo "# HELP homelab_coletor_liq_mensagens_1h Liquidações recebidas na última hora, por fonte."
  echo "# TYPE homelab_coletor_liq_mensagens_1h gauge"
  echo "# HELP homelab_coletor_liq_banco_bytes Tamanho do banco do coletor (com WAL)."
  echo "# TYPE homelab_coletor_liq_banco_bytes gauge"
  sqlite3 -readonly "$db" "
    WITH ult AS (SELECT * FROM batimentos ORDER BY rowid DESC LIMIT 2000),
         fim AS (SELECT fonte, MAX(ts_ms) t FROM ult GROUP BY fonte)
    SELECT 'homelab_coletor_liq_ultimo_batimento_segundos ' || (MAX(ts_ms) / 1000) FROM ult;
    WITH ult AS (SELECT * FROM batimentos ORDER BY rowid DESC LIMIT 2000),
         fim AS (SELECT fonte, MAX(ts_ms) t FROM ult GROUP BY fonte)
    SELECT 'homelab_coletor_liq_conexoes_conectadas{fonte=\"' || u.fonte || '\"} ' || SUM(u.conectado) || char(10) ||
           'homelab_coletor_liq_conexoes_total{fonte=\"' || u.fonte || '\"} ' || COUNT(*)
      FROM ult u JOIN fim f ON u.fonte = f.fonte AND u.ts_ms = f.t GROUP BY u.fonte;
    WITH ult AS (SELECT * FROM batimentos ORDER BY rowid DESC LIMIT 2000)
    SELECT 'homelab_coletor_liq_mensagens_1h{fonte=\"' || fonte || '\"} ' || SUM(msgs)
      FROM ult WHERE ts_ms > (SELECT MAX(ts_ms) FROM ult) - 3600000 GROUP BY fonte;"
  echo "homelab_coletor_liq_banco_bytes $(du -cb "$db" "$db-wal" 2>/dev/null | tail -1 | cut -f1)"
} > "$tmp"
mv "$tmp" "$dir/coletor-liquidacoes.prom"
