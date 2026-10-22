# ADR 0006 — Monitoramento e agente SRE: Prometheus no Pi, agente que falha para o lado seguro

- **Data:** 2026-10-22
- **Status:** aceita
- **Issue:** #16

## Contexto

A Etapa 2 precisa vigiar o Pi e o srv e entregar alertas investigados por um agente. Restrições:

- Quem vigia o srv **não pode** morar no srv: se ele cair, o vigia cai junto e ninguém avisa.
- O Pi não tem Docker, tem ~1,9 GB de RAM livre e o disco está em 79%.
- A IA mora no srv (gateway, Etapa 1). Se o srv cair, o alerta mais importante seria justamente
  o que fica sem IA.

## Opções consideradas

1. **Prometheus + Alertmanager + exporters** — padrão de mercado em SRE, regras como código, leve.
2. **Beszel** — já existe um hub numa VM da empresa; simples, mas mistura a infra pessoal com a da
   empresa e tem alertas limitados.
3. **Serviço gerenciado** (Grafana Cloud etc.) — tira as métricas de casa e depende de conta externa.

## Decisão

**Opção 1**, com esta divisão:

| Peça | Onde | Por quê |
|---|---|---|
| node_exporter | Pi e srv | métricas de cada máquina |
| métricas da GPU | srv, via `nvidia-smi` → textfile collector | sem dependência extra |
| Prometheus, Alertmanager, blackbox | **Pi** | o vigia fica fora do srv |
| agente SRE | **Pi** | recebe o webhook do Alertmanager |
| IA do agente | srv, via gateway, chave `sre` **só local** | logs podem conter dado interno |

**Falha para o lado seguro:** se o gateway não responder, o agente manda o alerta montado só pelas
regras, com a evidência coletada. A IA melhora a mensagem, mas nunca é condição para ela existir.

**A IA nunca rebaixa gravidade:** a gravidade vem de regra determinística. O modelo só explica e sugere.
É a lição do benchmark 0001, em que o melhor modelo classificou um login de root suspeito como ruído.

**O agente nunca age sozinho:** a coleta de contexto usa um catálogo fechado de comandos só de
leitura; qualquer ação vem de outro catálogo fechado e exige aprovação no Telegram (#20).

## Instalação

Binários oficiais com checksum conferido, serviços systemd com usuário sem privilégio, e portas
só em localhost ou na Tailscale (o Pi ainda não tem firewall; ver issue de hardening do Pi).
Mesma política de cadeia de suprimentos do ADR 0004. As versões dentro da quarentena da onda de
segurança do Go 1.27.3 ficam para a #14.

## Consequências

- O vigia sobrevive à queda do srv, que é o cenário mais provável (GPU, energia, atualização).
- Se o **Pi** cair, ninguém avisa. Mitigação futura: um *dead man's switch* externo
  (por exemplo, um cron no srv que estranha a falta de notícias do Pi).
- Mais uma carga no Pi, que já roda serviços de uso diário; retenção curta para caber no disco.
