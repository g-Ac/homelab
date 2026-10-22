# ADR 0005 — Rota de nuvem gratuita (Groq + Gemini) atrás do gateway

- **Data:** 2026-10-22
- **Status:** aceita
- **Issue:** #10

## Contexto

O gateway precisava de uma rota de nuvem para continuar respondendo quando o modelo local cai,
e para provar que a chave `privado` **nunca** chega à nuvem. A API paga fica para depois.

Foi avaliado o **OmniRoute** (gateway com ≈80k★ que agrega "150+ free tiers"). Recusado para este
projeto: parte da gratuidade vem de usar **assinaturas** (Claude Code, Codex, Copilot) como backend,
inclusive compartilhadas, o que viola os termos dos provedores e arrisca a conta; e ele oferece
"TLS stealth" para disfarçar o tráfego. Também concentraria os tokens de todas as contas numa
superfície grande (Node, 89 comandos, 110 ferramentas MCP), um dia depois do ataque ao LiteLLM.

A ideia de usar free tiers, porém, é boa. Ela foi implementada **no Bifrost**, com chaves oficiais.

## Termos dos provedores (lidos em 2026-10-22)

| | Groq | Gemini API (gratuito) |
|---|---|---|
| Treino com os dados | a documentação não diz; "por padrão não retém dados de inferência" | **sim**, e revisores humanos podem ler |
| Restrição de conteúdo | — | "não envie informação sensível, confidencial ou pessoal" |
| Limite gratuito | 30 req/min, 1 mil req/dia, 200 mil tokens/dia | conforme o AI Studio |

Decisão do dono do projeto: **aceitar o treino** com os dados enviados pela rota gratuita, já que o
uso é gratuito. A restrição que vem do **termo do provedor** continua valendo: dado pessoal ou
confidencial (Etapa 3) não passa pelo Gemini gratuito.

## Decisão

Cadeia do apelido `local`: **gemma4 → qwen3.5 (local) → qwen3.8-27b (Groq) → gemini-3.5-flash-lite**.

- A cadeia é única; **quem decide até onde ela vai é a chave**. `privado` só tem permissão para
  o Ollama; `geral` tem permissão para os três provedores.
- `geral` tem limite de 25 req/min, abaixo dos 30/min gratuitos da Groq.
- O modelo da Groq foi escolhido pelo **contrato `reasoning_effort: "none"`**: o `gpt-oss-20b`
  rejeita `none` (aceita só low/medium/high), e o `qwen3.8-27b` aceita e responde em ~0,3 s. O Gemini
  rejeita `none` na API dele, mas o Bifrost traduz corretamente. O qwen local só para de "pensar"
  com `none` (`low` ainda gera ~250 tokens).

## Evidência

Teste de aceitação ([`tests/aceitacao_etapa1.py`](../../tests/aceitacao_etapa1.py) `--queda`): com
o **container do Ollama parado**, a chave `geral` respondeu pelo qwen da Groq em 1,4 s e a chave
`privado` falhou com HTTP 502.

No log, a cadeia de fallback da `privado` registra tentativas na Groq e no Gemini, todas com tipo
`provider_blocked`, **nenhuma chave de provedor selecionada** e nenhum token: foram barradas pela
governança antes de qualquer chamada de rede. O teste audita isso automaticamente.

## Consequências

- O laboratório segue respondendo mesmo sem GPU, a custo zero.
- A rota gratuita é mais lenta e instável que a local (Gemini: ~6 s por resposta curta, com um caso
  de 50 s observado) e tem cota diária. É **reserva**, não caminho principal.
- **Risco aceito:** a rota foi ligada na v2.3.1 do Bifrost, antes de a v2.3.2 (correção de validação
  TLS) cumprir a quarentena de 72 h. A exploração exigiria interceptar a rede **e** ter certificado
  de uma autoridade comprometida, contra chaves gratuitas. A atualização tem issue própria.
- A Groq bloqueia (Cloudflare 1010) o User-Agent padrão do `urllib` do Python; o Bifrost não é afetado.
- API paga (Claude) entra depois, como chave/rota própria, com termos comerciais.
