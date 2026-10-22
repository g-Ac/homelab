# Hardening do Pi — rodada 1

- **Data:** 2026-10-22
- **Issue:** #22
- **Ferramenta:** Lynis 3.1.4

## Resultado

| Medida | Antes | Depois |
|---|---|---|
| Hardening index | **63** | **66** |
| Warnings | 2 | 1 (falso positivo, ver abaixo) |
| Sugestões | 49 | 43 |
| Atualizações de segurança pendentes | **68** | 0 |
| Firewall | nenhum (`policy accept`) | ativo, nega entrada por padrão |

## Achados

- **Sem firewall de entrada** e com **IPv6 global**: SSH, MQTT (1883) e o painel trade-desk (5000, com
  rotas POST sem autenticação) aceitavam conexão de qualquer rede que alcançasse o Pi.
- **68 atualizações de segurança pendentes**, incluindo `ca-certificates` (remoção das autoridades
  comprometidas na onda de 20–21/10), `curl` e `libexpat`.
- **Login por senha** em uso real (4 de 154 logins em 7 dias), então não foi desligado sem decisão do dono.
- O aviso restante do Lynis ("sem repositório de segurança") é falso positivo: o Pi usa o formato
  `.sources` (deb822) do apt, que o Lynis não lê; `trixie-security` está configurado.

## O que foi feito

**Atualizações:** só os 68 pacotes de segurança (não os 235 disponíveis), sem reiniciar serviços.

**Firewall (ufw)**, aplicado com trava de rollback de 5 minutos, cancelada após validar o acesso:

| Entrada permitida | Origem |
|---|---|
| tudo | interface da Tailscale |
| SSH (22) | rede local |
| MQTT (1883), usado no trabalho de Redes, com senha | rede local |
| mDNS (5353/udp) | rede local |
| Tailscale (41641/udp) | qualquer |

Roteamento negado (o Pi não é subnet router nem exit node). O trade-desk passa a ser acessível só pela Tailscale.

**SSH** (conservador, sem risco de trancar o dono): sem login de root, sem X11, 30 s para autenticar.
`MaxAuthTries` mantido em 6, porque o cliente SSH do Windows pode oferecer várias chaves antes da senha.

**fail2ban:** jail `sshd`, 5 falhas → 1 h de bloqueio; rede local e Tailscale como exceção.

**Kernel/sistema:** mesmos ajustes do srv (protocolos sem uso desativados, sem core dumps,
`sysctl` de rede e de kernel), mais aviso legal no `issue.net`.

## Validação

- A partir do srv, pela Tailscale: SSH, trade-desk (HTTP 200), Prometheus e painel acessíveis.
- As 3 sessões SSH ativas do dono continuaram abertas durante todas as mudanças.
- Prometheus continuou coletando 8 de 8 alvos; os 8 serviços de uso diário seguiram ativos.

## Pendente (decisão do dono)

| Item | Recomendação |
|---|---|
| Login SSH por senha | Desligar depois de garantir chave em todos os aparelhos usados |
| Tailscale Funnel publicando o `localhost:5173` inteiro (desenvolvimento do WhatsApp) | Publicar só o caminho do webhook (`/webhook/whatsapp`) |
| ~5 GB em versões antigas do Hermes, cópias do `bot.db` e navegadores de automação | Limpar o que não for usado |
