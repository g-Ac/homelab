# Benchmark 0001 — Resultados e veredicto

- **Data:** 2026-10-22
- **Issue:** #5
- **Pré-registro:** [`0001-prereg.md`](0001-prereg.md), selado em `6b0c958` antes de rodar qualquer candidato
- **Dados brutos:** [`bench/results/`](../../bench/results/) (uma linha por chamada, com resposta, gabarito e tempos)

## Resultado

| Modelo | T1 alertas | T2 extração | tokens/s (T3) | Na GPU | Latência T1/T2 | Veredicto |
|---|---|---|---|---|---|---|
| **gemma4:e4b** | **23/24 (0,96)** | **58/60 (0,97)** | **73,5** | 100%* | 0,98 s | ✅ **GO** (ressalva*) |
| **qwen3.5:4b** | 23/24 (0,96) | 56/60 (0,93) | 50,5 | 100% | 0,94 s | ✅ **GO** |
| llama3.1:8b | 22/24 (0,92) | 53/60 (0,88) | 26,6 | 86% | 0,91 s | ❌ NO-GO (não cabe na GPU) |
| qwen3.5:9b | 23/24 (0,96) | 56/60 (0,93) | 14,0 | 63% | 2,20 s | ❌ NO-GO (não cabe; lento) |

Critério GO: T1 ≥ 0,85 · T2 ≥ 0,85 · ≥ 15 tokens/s · 100% na GPU. T3 (resumo) saturou em 1,0 para
todos, como previsto na calibração, e fica fora do veredicto.

**Modelo padrão do gateway (regra pré-registrada):** `gemma4:e4b`, maior média de T1+T2 entre os GO.
**Reserva:** `qwen3.5:4b`.

## O limite da GTX 1660, agora medido

Os dois modelos de 8–9B **acertam tanto quanto** os de 4B nessas tarefas, mas não cabem inteiros
nos 6 GB. A parte que vaza para a CPU derruba a velocidade:

| | Na GPU | tokens/s |
|---|---|---|
| qwen3.5:4b | 100% | 50,5 |
| llama3.1:8b | 86% | 26,6 |
| qwen3.5:9b | 63% | 14,0 |

Para tarefas curtas e estruturadas, **modelo maior não comprou qualidade nesta placa, só lentidão.**

## * Ressalva de medição: gemma4:e4b

O critério "cabe na GPU" foi pré-registrado como `size_vram / size` do endpoint `/api/ps` do Ollama.
Para `gemma4:e4b`, esse endpoint reporta **369 MB**, mas o arquivo tem 6,6 GB. O instrumento está
errado para essa arquitetura. O critério passou **como escrito**, mas com um instrumento que se
mostrou falho, então foi verificado de forma independente:

- `nvidia-smi`: o processo do modelo usa **4,6 GB de VRAM** (de 6 GB).
- Velocidade: **73,5 tokens/s**, a maior do teste. Os modelos que vazam para a CPU caem para 14–27.
  Não há sinal de vazamento.
- Arquitetura: os modelos "E" do Gemma foram desenhados para manter parte dos embeddings fora da
  GPU sem custo relevante de velocidade.

Conclusão: GO mantido, com a ressalva registrada. **Lição para os próximos benchmarks:** medir VRAM
pelo `nvidia-smi`, não pelo `/api/ps`.

## Onde os modelos erraram

**T1, o erro mais grave do teste:** o `gemma4:e4b` classificou como **ruído** o alerta
"login SSH ACEITO para usuário root a partir de IP desconhecido". É o alerta mais perigoso do conjunto,
e o modelo com a melhor média errou justamente ele. Os outros erros de T1 foram de gravidade menor
(pico de CPU agendado visto como "atenção", setores realocados vistos como "crítico").

> **Acurácia média esconde o custo do erro.** Errar um "crítico" de segurança não é igual a errar um
> "ruído". Consequência para a Etapa 2: alertas de segurança passam por regra determinística
> **antes** do modelo, e o modelo nunca rebaixa um alerta que a regra marcou como crítico.

**T2:** os erros se concentram nas pegadinhas de propósito:

| Documento | Pegadinha | Quem errou |
|---|---|---|
| d06 — recibo de aluguel | quem paga × quem recebe | qwen 4b, qwen 9b, llama |
| d08 — nota fiscal | emitente × destinatário | gemma4, qwen 9b, llama |
| d02 — NFS-e | valor bruto × líquido (ISS retido) | qwen 4b (CNPJ), qwen 9b, llama (valor) |
| d13 — fatura parcelada | valor do plano × valor da parcela | qwen 4b, qwen 9b |

O gabarito desses itens foi revisto depois da execução e está correto; nenhuma emenda foi necessária.
O `llama3.1:8b` foi o único a **corromper dígitos** de CNPJ (d07, d12, d19), um erro pior do que
escolher o CNPJ errado, porque produz um número que não existe.

## Veredicto

**GO para modelo local** em classificação e extração curtas, com `gemma4:e4b` como padrão e
`qwen3.5:4b` como reserva. A GTX 1660 atende essas tarefas com folga de velocidade (50–74 tokens/s).

Ver [ADR 0003](../decisoes/0003-modelo-local-padrao.md).

## Limites deste resultado

- 50 casos fictícios escritos pelo mesmo autor do critério; uma execução por modelo.
- Diz respeito a tarefas curtas e estruturadas. Raciocínio longo, uso de ferramentas e contexto
  grande ficam para a API externa até prova em contrário.
