# ADR 0003 — Modelo local padrão: gemma4:e4b (reserva qwen3.5:4b)

- **Data:** 2026-10-22
- **Status:** aceita
- **Issue:** #5
- **Evidência:** [benchmark 0001](../benchmarks/0001-resultados.md) (pré-registro selado em `6b0c958`)

## Contexto

O gateway da Etapa 1 precisa de um modelo local para tarefas simples e privadas (classificar,
extrair). A GTX 1660 tem 6 GB de VRAM. Quatro candidatos foram testados com critério congelado antes.

## Opções consideradas

1. **gemma4:e4b** — GO; melhor qualidade (0,96 / 0,97) e velocidade (73,5 tokens/s). Errou o alerta
   de segurança mais grave do conjunto. Medida de VRAM do Ollama falha para ele (verificada à parte).
2. **qwen3.5:4b** — GO limpo; 0,96 / 0,93, 50,5 tokens/s.
3. **llama3.1:8b** e **qwen3.5:9b** — NO-GO: não cabem inteiros na GPU e ficam lentos, sem ganho de qualidade.

## Decisão

`gemma4:e4b` como padrão, pela regra pré-registrada. `qwen3.5:4b` como reserva configurada no gateway.

## Consequências

- Alertas de segurança passam por regra determinística antes do modelo; o modelo **não pode rebaixar**
  algo que a regra marcou como crítico.
- Saída do modelo é normalizada em código (datas, CNPJ), não por decodificação restrita.
- Monitorar VRAM pelo `nvidia-smi`; o `/api/ps` do Ollama não é confiável para esse modelo.
- Modelos de 8B+ ficam fora até haver GPU com mais VRAM. Trocar é uma linha de configuração (ADR 0001).
