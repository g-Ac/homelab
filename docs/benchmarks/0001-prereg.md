# Benchmark 0001 — Pré-registro

- **Data:** 2026-10-22
- **Issue:** #5
- **Status:** 🔒 congelado — o commit que contém este arquivo é o selo. Nada abaixo muda depois de ver resultado.

## Pergunta

Quais modelos locais a GTX 1660 (6 GB) roda com qualidade e velocidade suficientes para entrar no
gateway da Etapa 1 como opção para tarefas simples e privadas?

## Candidatos (lista fechada)

| Modelo | Por quê |
|---|---|
| `qwen3.5:4b` | Pequeno e recente |
| `qwen3.5:9b` | O maior que talvez caiba: testa o limite da placa |
| `gemma4:e4b` | Família pensada para hardware modesto |
| `llama3.1:8b` | Referência clássica do mercado |

Quantização padrão do Ollama de cada tag. Ollama 0.40.8, driver 595.99.02.

## Configuração (igual para todos)

- `temperature 0`, `seed 42`, `num_ctx 4096`, `think: false`.
- T1 e T2 com saída estruturada (JSON schema, sem restrição de padrão nos campos).
- 1 chamada de aquecimento descartada por modelo; modelo descarregado antes do próximo.
- Código: [`bench/run.py`](../../bench/run.py); dados: [`bench/data/`](../../bench/data/).

## Tarefas

Todos os dados são **fictícios**, escritos antes de qualquer execução de candidato, com gabarito.

| Tarefa | Casos | Métrica |
|---|---|---|
| **T1** — classificar alertas de infra (crítico / atenção / ruído) | 24 (8 por classe) | acurácia |
| **T2** — extrair CNPJ, valor a pagar e vencimento de documentos financeiros | 20 docs × 3 campos = 60 | acurácia por campo |
| **T3** — resumir log em até 2 frases | 6 | cobertura de fatos-chave (**só descritiva**) |

Normalização da T2: CNPJ só dígitos; valor arredondado a 2 casas; data aceita `AAAA-MM-DD`,
`DD/MM/AAAA` ou `DD-MM-AAAA`, qualquer outra forma é erro.

## Critério GO (por modelo)

Um modelo é **GO** se cumprir **todos**:

1. T1: acurácia ≥ **0,85** (≥ 21 de 24)
2. T2: acurácia por campo ≥ **0,85** (≥ 51 de 60)
3. Velocidade: mediana de tokens/s na T3 ≥ **15**
4. Cabe na GPU: 100% do modelo carregado em VRAM (`size_vram / size ≥ 0,999` no `/api/ps`)

**Modelo padrão do gateway:** entre os GO, maior média de T1 e T2; empate desempata pela velocidade.

**Se nenhum for GO:** veredicto NO-GO para modelo local nessas tarefas; o gateway da Etapa 1 nasce
roteando tudo para API externa, e o limite fica documentado.

## Regras de emenda

- Erro de **gabarito** descoberto depois pode ser corrigido, desde que documentado aqui com data
  e aplicado igualmente a todos os modelos.
- Limiares, lista de candidatos e configuração **não mudam**.
- Cada candidato roda **uma vez**. Sem "rodar de novo para ver se melhora".

## Calibração do aparato (antes do selo, com modelo que não é candidato)

O script foi validado com `qwen3.5:0.8b`, fora da lista de candidatos, para testar a ferramenta sem
ver resultado de nenhum concorrente.

| Rodada | Mudança | T1 | T2 | Observação |
|---|---|---|---|---|
| 1 | — | 0,42 | 0,73 | Erros de T2 eram, em maioria, formato de data (`15-10-2026`) |
| 2 | Padrão regex forçado no JSON schema | 0,42 | 0,70 | **Piorou**: o modelo passou a embaralhar datas e inventar dígitos de CNPJ para caber no padrão |
| 3 | Sem padrão; normalização de data no código | 0,42 | 0,90 | Configuração final |

Aprendizados da calibração:

- **Forçar formato via decodificação restrita pode piorar modelos pequenos.** Melhor deixar o
  modelo responder e normalizar no código.
- **T1 discrimina** (0,42 no modelo minúsculo, perto do acaso de 0,33). **T2 é mais fácil** do que
  o esperado. Os limiares foram mantidos como propostos *antes* da calibração.
- **T3 satura** (cobertura 1,0 mesmo com resumos contendo erros factuais). Confirmado como só
  descritiva; fora do critério.

## Limitações conhecidas

- Os dados foram escritos pelo mesmo autor do critério; o conjunto é pequeno (50 casos).
- Uma execução por modelo, `temperature 0`: mede o comportamento típico, não a variância.
- Mede tarefas curtas; não diz nada sobre raciocínio longo ou uso de ferramentas.
