# ADR 0004 — Gateway: Bifrost, com política de cadeia de suprimentos

- **Data:** 2026-10-22
- **Status:** aceita
- **Issue:** #7

## Contexto

O gateway é o ponto único entre os projetos e os modelos (ADR 0001). Ele guarda as chaves de API
de nuvem, e por isso é o alvo mais valioso do laboratório para um ataque de cadeia de suprimentos.

No dia anterior a esta decisão, o LiteLLM, gateway mais adotado do mercado, publicou a versão
**1.107.0 com um ladrão de credenciais** embutido no pacote do PyPI e nas imagens Docker `latest`
e `main-stable` (BerriAI/litellm#47826). Foi o **segundo** incidente desse tipo no projeto em 2026
(o primeiro em março, versões 1.82.7 e 1.82.8).

## Opções consideradas

| | LiteLLM | Bifrost | Gateway próprio |
|---|---|---|---|
| Adoção | ≈62k★ | ≈9k★ | — |
| Linguagem / entrega | Python, centenas de dependências no PyPI | Go, binário único | Python, poucas dependências |
| Chaves por projeto com restrição de modelo | sim | sim | a escrever |
| Orçamento, failover, painel | sim | sim | a escrever |
| Incidentes de cadeia de suprimentos em 2026 | **2** | nenhum registrado | — |
| Licença | não declarada no GitHub | Apache-2.0 | — |

## Decisão

**Bifrost**, com uma política explícita de cadeia de suprimentos que vale para qualquer
componente que guarde segredo:

1. **Fixar por digest**, nunca por tag. Tag pode ser reescrita; digest não.
2. **Quarentena de 72 h**: só usar versão publicada há pelo menos 3 dias e sem alerta de segurança
   aberto. Os dois ataques ao LiteLLM foram descobertos em horas.
3. **Exceção à quarentena**: se a versão em uso tiver falha explorável *no nosso cenário*.
4. Ler as notas de versão antes de atualizar.

Versão inicial: **v2.3.1** (`sha256:fe323e24…5e16149`), com 73 h de publicação.

A v2.3.2 corrige uma falha de validação de certificado TLS (Go `crypto/x509`). Ela só afeta
conexões TLS com provedores externos. Como a rota inicial é só local (Ollama via HTTP na mesma
máquina), a falha não se aplica agora. A atualização para a v2.3.2 é **pré-requisito da rota de
nuvem** (#10).

## Consequências

- Menos dependências executando ao lado das chaves de API.
- Bifrost é menos conhecido que o LiteLLM; a escolha precisa ser explicada, e este ADR existe para isso.
- Atualizações ficam mais lentas por causa da quarentena, de propósito.
- Os recursos de "access profiles" do Bifrost são Enterprise; a versão aberta usa chaves virtuais,
  que atendem ao que a Etapa 1 precisa.
