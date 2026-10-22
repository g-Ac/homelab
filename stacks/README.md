# stacks

Infraestrutura como código dos serviços do srv. Cada pasta é um `docker compose` independente,
ligado à rede Docker externa `ia` (`docker network create ia`).

| Stack | O quê | Portas |
|---|---|---|
| [`ollama/`](ollama/) | Modelos locais na GPU | 11434 (localhost + Tailscale) |
| [`bifrost/`](bifrost/) | Gateway único de IA (ADR 0004) | 8080 (localhost + Tailscale) |

Regras:

- Imagens **fixadas por digest** (ADR 0004).
- Nenhum segredo no repositório: cada stack tem `.env.example`; o `.env` real fica só no servidor, com `chmod 600`.
- Portas publicadas apenas em `127.0.0.1` e no IP da Tailscale.

Observação: o Ollama foi fixado na versão que já rodava (0.40.8, publicada há menos de 72 h).
A quarentena do ADR 0004 vale para componentes que guardam segredo; o Ollama não guarda.
