#!/usr/bin/env bash
# Instala um binário oficial do projeto Prometheus com checksum conferido (ADR 0004/0006).
# Uso: sudo ./instalar.sh <projeto> <versão>      ex.: sudo ./instalar.sh node_exporter 1.12.1
set -euo pipefail
proj="${1:?projeto}"; ver="${2:?versão}"
case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) echo "arquitetura não suportada" >&2; exit 1 ;; esac
nome="$proj-$ver.linux-$arch"
base="https://github.com/prometheus/$proj/releases/download/v$ver"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$nome.tar.gz" "$base/$nome.tar.gz"
curl -fsSL -o "$tmp/sha256sums.txt" "$base/sha256sums.txt"
(cd "$tmp" && grep " $nome.tar.gz\$" sha256sums.txt | sha256sum -c --quiet -) || { echo "CHECKSUM NÃO CONFERE" >&2; exit 1; }
tar -xzf "$tmp/$nome.tar.gz" -C "$tmp"
for bin in "$tmp/$nome"/*; do
  [ -f "$bin" ] && [ -x "$bin" ] && install -m 0755 "$bin" /usr/local/bin/
done
id "$proj" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$proj"
echo "ok: $proj $ver ($arch) instalado, checksum conferido"
