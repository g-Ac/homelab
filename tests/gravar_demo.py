#!/usr/bin/env python3
"""Grava um comando do terminal em asciicast v2 (formato do asciinema), só com biblioteca padrão.

Uso:
    python3 gravar_demo.py saida.cast -- python3 aceitacao_etapa1.py --fallback

Depois, o GIF: docker run --rm -v "$PWD:/d" ghcr.io/asciinema/agg /d/saida.cast /d/saida.gif --idle-time-limit 1
"""
import json
import os
import pty
import select
import sys
import time


def main():
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        sys.exit(__doc__)
    destino, comando = sys.argv[1], sys.argv[3:]
    cols, rows = 110, 32
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(COLUMNS=str(cols), LINES=str(rows), TERM="xterm-256color", PYTHONUNBUFFERED="1")
        os.execvp(comando[0], comando)
    inicio = time.monotonic()
    with open(destino, "w") as f:
        f.write(json.dumps({"version": 2, "width": cols, "height": rows, "timestamp": int(time.time()),
                            "title": " ".join(comando)}) + "\n")
        while True:
            r, _, _ = select.select([fd], [], [], 1)
            if not r:
                continue
            try:
                dados = os.read(fd, 4096)
            except OSError:
                break
            if not dados:
                break
            os.write(1, dados)
            f.write(json.dumps([round(time.monotonic() - inicio, 3), "o", dados.decode("utf-8", "replace")]) + "\n")
    _, status = os.waitpid(pid, 0)
    sys.exit(os.waitstatus_to_exitcode(status))


if __name__ == "__main__":
    main()
