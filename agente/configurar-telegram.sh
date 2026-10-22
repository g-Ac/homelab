#!/usr/bin/env bash
# Liga o Telegram no agente SRE. Rode num terminal seu (não cole o token em chat):
#   sudo ~/projects/homelab/agente/configurar-telegram.sh
# Antes: crie o bot com o @BotFather e mande /start para ele no Telegram.
set -euo pipefail
ENV=/etc/homelab-sre/env
[ "$(id -u)" = 0 ] || { echo "rode com sudo" >&2; exit 1; }
read -rsp "Token do bot (não aparece na tela): " token; echo
[[ "$token" =~ ^[0-9]{6,12}:[A-Za-z0-9_-]{30,}$ ]] || { echo "formato de token inválido" >&2; exit 1; }
api="https://api.telegram.org/bot$token"
nome=$(curl -fsS "$api/getMe" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['username'])") \
  || { echo "token recusado pelo Telegram" >&2; exit 1; }
echo "bot: @$nome"
chat=$(curl -fsS "$api/getUpdates" | python3 -c "
import json,sys
msgs=[u['message'] for u in json.load(sys.stdin)['result'] if 'message' in u and u['message']['chat']['type']=='private']
print(msgs[-1]['chat']['id'] if msgs else '')")
[ -n "$chat" ] || { echo "nenhuma conversa encontrada: mande /start para @$nome e rode de novo" >&2; exit 1; }
umask 077
tmp=$(mktemp)
grep -vE '^SRE_TELEGRAM_(TOKEN|CHAT)=' "$ENV" > "$tmp" || true
printf 'SRE_TELEGRAM_TOKEN=%s\nSRE_TELEGRAM_CHAT=%s\n' "$token" "$chat" >> "$tmp"
install -o root -g homelab-sre -m 0640 "$tmp" "$ENV"; rm -f "$tmp"
systemctl restart homelab-sre
curl -fsS -X POST "$api/sendMessage" -d chat_id="$chat" \
  --data-urlencode text="✅ Agente SRE do homelab conectado. Vou avisar aqui quando algo cair." >/dev/null
echo "ok: Telegram ligado (chat $chat). Confira a mensagem de teste no celular."
