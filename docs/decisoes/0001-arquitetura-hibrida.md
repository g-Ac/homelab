# ADR 0001 — Arquitetura híbrida: modelo local + API externa

- **Data:** 2026-10-22
- **Status:** aceita

## Contexto

O laboratório tem uma GPU de entrada (GTX 1660, 6 GB). Ela não roda modelos grandes, mas roda bem
modelos pequenos quantizados. Ao mesmo tempo, parte das tarefas envolve dado que não deve sair de casa,
e parte exige raciocínio que só modelos grandes entregam.

## Opções consideradas

1. **Só API externa** — melhor qualidade, mas todo dado sai de casa e o custo cresce com o uso.
2. **Só modelo local** — privado e sem custo por chamada, mas a 1660 não sustenta tarefas complexas.
3. **Híbrido com gateway** — um ponto único recebe os pedidos e roteia por sensibilidade e dificuldade.

## Decisão

Opção 3. Tarefas simples, repetitivas ou com dado sensível vão para o modelo local; raciocínio pesado
vai para a API externa. Os projetos chamam sempre o gateway, nunca um modelo diretamente.

## Consequências

- Trocar a GPU no futuro muda só a configuração do gateway, não os projetos.
- É preciso medir o que o modelo local aguenta antes de decidir o roteamento (benchmark da Etapa 0).
- O gateway passa a ser peça crítica e precisa de observabilidade (custo, latência, uso por projeto).
