# ADR 0007 — "Sem pensar" por padrão nos modelos locais: proxy entre o Bifrost e o Ollama

- **Data:** 2026-10-23
- **Status:** aceita
- **Issue:** #13

## Contexto

O `qwen3.5:4b`, segundo modelo da cadeia `local`, liga o modo "pensar" por padrão. Medido no
Ollama 0.40.8 (temperature 0, seed 42, "Responda só: ok"):

| modelo | `reasoning_effort` | tokens de saída | tempo |
|---|---|---|---|
| qwen3.5:4b | ausente | 238 | 4,8–10,7 s |
| qwen3.5:4b | `none` | 2 | 0,17 s |
| qwen3.5:4b | `high` | 238 | 4,8 s |
| gemma4:e4b | ausente / `none` / `high` | 2 | — |

Até aqui `reasoning_effort: "none"` era **contrato de uso**: documentado e verificado no teste de
aceitação, mas dependente de cada projeto lembrar. Quem esquecesse veria o fallback, que já é o
caminho degradado, ficar 20–30× mais lento.

O que não serve:

- `think: false`, parâmetro nativo do Ollama, **não atravessa** o Bifrost, que fala com o Ollama
  pela rota OpenAI `/v1/chat/completions`.
- O Ollama não aceita `PARAMETER think` no Modelfile.
- Plugin do Bifrost: o plugin Go (`.so`) precisa ser recompilado a cada troca de digest da imagem
  (toda atualização, ver #14), e o plugin WASM está marcado como *deprecated* na documentação.
- Esperar suporte nativo no upstream não tem prazo.

## Decisão

Um **proxy mínimo entre o Bifrost e o Ollama**, [`stacks/bifrost/sem-pensar/`](../../stacks/bifrost/sem-pensar/),
na rede Docker `ia`. O Bifrost passa a apontar para `http://sem-pensar:11434` em vez de `http://ollama:11434`.

Regra única: em `POST /v1/chat/completions`, se o corpo não traz `reasoning_effort` nem
`reasoning`, o proxy injeta `reasoning_effort: "none"`. **Qualquer valor que o cliente mandar é
preservado byte a byte.** Todo o resto (outros caminhos, cabeçalhos, streaming) passa intacto.

Por que assim:

- **Vale também no fallback.** O pedido que cai no qwen por falha do gemma4 passa pelo mesmo proxy.
- **Não faz mal ao gemma4**, que aceita `none` sem erro e já não pensava.
- **Independente da versão do Bifrost**: é um container à parte, sem recompilar nada ao atualizar o gateway.
- **Pequeno e auditável**: ~100 linhas de Go só com biblioteca padrão (`httputil.ReverseProxy`,
  streaming sem buffer), 7 testes unitários rodados no próprio build da imagem.
- **Sem segredo e sem conteúdo no log**: registra só "injetado" e o nome do modelo.
- Imagem final `scratch` (sem shell), usuário sem root, read-only, sem capabilities, **nenhuma
  porta publicada** (só a rede `ia`).

Cadeia de suprimentos: a imagem de build é `golang:1.27.3-alpine`, fixada por digest, da biblioteca
oficial do Docker. O Go 1.27.3 traz as correções de `net/http` e `crypto/tls` de 20/10 (#14), que
importam para um proxy HTTP. A imagem foi publicada em 22/10, dentro das 72 h de quarentena do
ADR 0004. **Risco aceito**, com dois motivos: a quarentena do ADR vale para componentes que guardam
segredo, e o proxy não guarda nenhum; e a alternativa (1.27.2, fora da quarentena) é a versão
**com** as falhas corrigidas. O que o proxy vê, e que pesa contra, é o conteúdo de toda chamada
local: por isso ele não publica porta, roda em `scratch` sem shell e tem o código inteiro no repositório.

## Evidência

Teste de aceitação ([`tests/aceitacao_etapa1.py`](../../tests/aceitacao_etapa1.py)), rodado no srv em 2026-10-23:

```text
[PASSA ] reasoning_effort='none' desliga o 'pensar' do qwen — 2 tokens de saída em 4.5 s
[PASSA ] sem reasoning_effort, o gateway impõe 'none' ao qwen (#13) — 2 tokens de saída em 0.1 s
[PASSA ] reasoning_effort='high' do cliente é preservado (qwen continua pensando) — 237 tokens de saída em 4.8 s
[PASSA ] com o gemma4 fora, 'local' cai no qwen3.5:4b — HTTP 200, modelo qwen3.5:4b
[PASSA ] overhead mediano do gateway ≤ 50 ms — mediana 1.0 ms (p10 0.3, p90 1.6; 30 pares)
```

O critério da issue ("uma chamada sem `reasoning_effort` ao qwen sai com ≤ 10 tokens") passou com
2 tokens; a chamada com `high` continuou pensando (237 tokens). O salto extra custou ~0,3 ms de
mediana (0,7 → 1,0 ms), dentro do critério de 50 ms congelado na #12.

## Consequências

- `reasoning_effort: "none"` deixa de ser contrato e vira **padrão** nos modelos locais. Quem quiser
  o modelo pensando pede `high` explicitamente.
- O proxy fica só na frente do Ollama. Na rota de nuvem gratuita (chave `geral`), o `qwen3.8-27b`
  da Groq ainda pensa se o pedido não trouxer `reasoning_effort`; mandar `none` continua sendo a
  recomendação para tarefas simples.
- O proxy entra na lista de componentes a atualizar quando sai correção no Go (digest no `Dockerfile`).
- O Bifrost **não relê** `config.json` em `compose up -d` (o conteúdo do bind mount não muda o
  container); mudar a URL do provedor exige `compose restart bifrost`.
