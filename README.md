# homelab

Laboratório pessoal de **IA privada, agentes e infraestrutura**, rodando em hardware modesto em casa:
um Raspberry Pi 4 e um servidor com GPU de entrada (GTX 1660, 6 GB).

A proposta é mostrar que dá para montar uma plataforma de IA séria sem nuvem cara, com dois princípios:

- **Dado sensível não sai de casa.** Tarefas simples ou com dado privado rodam em modelo local;
  só raciocínio pesado vai para API externa (arquitetura híbrida).
- **Medir antes de construir.** Toda escolha relevante tem critério definido *antes* do teste
  e veredicto registrado depois (ver [`docs/decisoes/`](docs/decisoes/)).

> Status: Etapas 0 e 1 no ar; **Etapa 2 — agente SRE** investigando alertas e agindo só com aprovação no Telegram. O histórico completo está nas
> [issues](../../issues?q=is%3Aissue) e [milestones](../../milestones).

## Resultados até agora

| | |
|---|---|
| 🔒 **Hardening** | srv: Lynis **62 → 69** ([relatório](docs/seguranca/0001-hardening-srv.md)) · Pi: **63 → 66**, 68 atualizações de segurança e firewall onde não havia nenhum ([relatório](docs/seguranca/0003-hardening-pi.md)) |
| 🔑 **Segredos vazados** | 21 repositórios varridos no histórico completo, **0 em públicos**, com controle positivo ([relatório](docs/seguranca/0002-varredura-segredos.md)) |
| 🎮 **GPU** | Driver com Secure Boot ligado, sem acesso físico; GPU disponível em containers ([ADR 0002](docs/decisoes/0002-driver-nvidia-secure-boot.md)) |
| 🚪 **Gateway de IA** | Bifrost com chave por projeto, fallback local → nuvem gratuita, chave privada que falha fechado (auditado), orçamento e logs sem conteúdo; modelo local "sem pensar" por padrão ([ADR 0007](docs/decisoes/0007-proxy-sem-pensar.md)); 24/24 testes de aceitação; overhead de 1,0 ms. LiteLLM recusado por ataque de supply chain na véspera ([etapa 1](docs/etapa-1.md), [ADR 0004](docs/decisoes/0004-gateway-bifrost.md)) |
| 🛟 **Agente SRE** | Alerta → diagnóstico por SSH preso a *forced command* (catálogo fechado) → explicação da IA local → botão de aprovação no Telegram → ação → conferência independente. Com a IA fora, o aviso sai montado por regras ([ADR 0006](docs/decisoes/0006-monitoramento-agente-sre.md)) |
| 🧪 **Benchmark pré-registrado** | 4 modelos locais; 2 GO. Padrão `gemma4:e4b`: 96% em alertas, 97% em extração, 74 tokens/s. Modelos de 8–9B não cabem e não acertam mais ([resultados](docs/benchmarks/0001-resultados.md)) |

## Arquitetura

```mermaid
flowchart LR
    U[Gabriel / Telegram] --> PI
    subgraph Casa
        PI["Raspberry Pi 4<br/>4 GB · ARM · 24/7<br/><b>orquestração</b>"]
        SRV["srv<br/>Ryzen 5 5600 · 15 GB · GTX 1660<br/><b>estação de IA</b>"]
    end
    PI <-- rede privada (Tailscale) --> SRV
    SRV -. raciocínio pesado .-> API[(API de LLM externa)]
```

| Máquina | Papel |
|---|---|
| **Raspberry Pi 4** (4 GB, ARM) | Ligado 24/7, consumo baixo: agenda tarefas, monitora, conversa via Telegram |
| **srv** (Ryzen 5 5600, 15 GB, GTX 1660 6 GB, Ubuntu 24.04) | Estação de IA: modelos locais, processamento pesado, dados dos projetos |

Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md).

## Roadmap

| Etapa | Entrega | Status |
|---|---|---|
| **0 — Fundação** | Mapa do lab, segurança básica, GPU funcionando, benchmark de modelos locais | ✅ concluída |
| **1 — Plataforma de IA privada** | Gateway único que roteia entre modelo local e API externa, com painel de custo/uso | 🟡 local + nuvem gratuita prontos; rota paga futura |
| **2 — Agente SRE** | Agente que investiga alertas da infra e pede aprovação humana no Telegram | 🟡 monitoramento, agente e aprovação no ar; falta o teste de falhas pré-registrado |
| **3 — Solução aplicada** | Caso real de empresa em cima das etapas 1–2 | ⚪ |

Trilha paralela de **segurança defensiva**: caça a segredos vazados → hardening com nota antes/depois
→ scanner de vulnerabilidades → mini-SOC com agente explicando alertas.

## Como este repositório é usado

- Cada passo vira uma **issue** com critério de pronto; o trabalho fecha a issue por commit.
- Decisões importantes viram **ADR** em [`docs/decisoes/`](docs/decisoes/).
- Resultados de medição ficam em [`docs/benchmarks/`](docs/benchmarks/) e [`docs/seguranca/`](docs/seguranca/).
- Nenhum segredo, IP interno ou dado de terceiros entra no repositório.

## Licença

[MIT](LICENSE)
