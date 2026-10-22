# Varredura de segredos nos repositórios

- **Data:** 2026-10-22
- **Issue:** #2
- **Ferramenta:** gitleaks 8.30.1 (binário oficial, checksum SHA-256 conferido)

## Método

1. Clone `--bare` de **todos** os repositórios da conta (públicos e privados): 21 repositórios.
2. `gitleaks git` sobre o **histórico completo** de cada um (não só o estado atual), com `--redact`
   para que nem o relatório nem quem o lê veja o valor dos segredos.
3. **Controle positivo:** um token falso no formato de token do GitHub foi plantado num repositório
   temporário. O gitleaks detectou (`github-pat`). Isso confirma que os zeros abaixo são zeros de
   verdade, não falha silenciosa da ferramenta.
4. Relatórios brutos ficam fora de qualquer repositório e são apagados ao final.

## Resultado

| Escopo | Repositórios | Achados |
|---|---|---|
| Públicos | 8 | **0** |
| Privados | 13 | 2, ambos em um único repositório de testes, num commit de 2023 |

Os 2 achados: uma chave de API de LLM e uma chave privada de conta de serviço de nuvem.

## Tratamento

Segredo que entrou num histórico git é tratado como **comprometido**, mesmo em repositório privado.
A ordem correta é:

1. **Revogar/rotacionar** as duas chaves no painel de cada provedor. Apagar do git não invalida a chave.
2. Depois, apagar o repositório de testes ou reescrever o histórico.

## Próximos passos

- Rodar o gitleaks antes de tornar público qualquer repositório privado.
- Avaliar hook de pre-commit com gitleaks nos projetos novos.
