#!/usr/bin/env bash
# Grava um segredo no .env do Bifrost sem que ele apareça na tela, no histórico ou em logs.
# Uso (de um terminal seu, NUNCA colando a chave em chat):
#   ssh -t srv ~/stacks/bifrost/adicionar-segredo.sh GROQ_API_KEY
set -euo pipefail
nome="${1:?informe o nome da variável, ex.: GROQ_API_KEY}"
[[ "$nome" =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "nome inválido: $nome" >&2; exit 1; }
env_file="$(dirname "$(readlink -f "$0")")/.env"
read -rsp "Cole o valor de $nome (não aparece na tela) e tecle Enter: " valor; echo
[[ -n "$valor" ]] || { echo "valor vazio, nada gravado" >&2; exit 1; }
umask 077
tmp="$(mktemp "$env_file.XXXX")"
grep -v "^$nome=" "$env_file" > "$tmp" || true
printf '%s=%s\n' "$nome" "$valor" >> "$tmp"
mv "$tmp" "$env_file"
chmod 600 "$env_file"
echo "ok: $nome gravado em $env_file (${#valor} caracteres)"
