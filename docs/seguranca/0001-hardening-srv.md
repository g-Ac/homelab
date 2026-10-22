# Hardening do srv — rodada 1

- **Data:** 2026-10-22
- **Issue:** #3
- **Ferramenta:** Lynis 3.0.9 (`lynis audit system`)

## Resultado

| Medida | Antes | Depois |
|---|---|---|
| Hardening index | **62** | **69** |
| Warnings | 0 | 0 |
| Sugestões | 49 | 38 |
| Firewall | inativo | ativo, nega entrada por padrão |
| SSH | todas as interfaces, sem filtro | só Tailscale + rede local |

## Achado principal

O servidor tinha **IPv6 global** e o SSH escutava em todas as interfaces, sem firewall.
Dependendo do roteador, isso deixa a porta 22 alcançável pela internet. A autenticação já era
só por chave, mas a exposição era desnecessária.

## O que foi feito

**Firewall (ufw)**
- Entrada negada por padrão (IPv4 e IPv6), saída liberada.
- Liberado: tudo na interface da Tailscale; SSH a partir da rede local (acesso de emergência);
  UDP da Tailscale para conexão direta.
- Aplicado com **trava de rollback**: um timer desativaria o firewall em 5 minutos caso o acesso
  se perdesse. A trava só foi cancelada depois de reconectar numa sessão nova.

**SSH** (`/etc/ssh/sshd_config.d/10-homelab-hardening.conf`)
- Sem login de root, sem senha, sem X11, sem agent forwarding.
- Máximo de 3 tentativas por conexão, 30 s para autenticar.
- Configuração validada com `sshd -t` antes do reload.

**fail2ban**
- Jail `sshd` com backend systemd, 5 falhas → bloqueio de 1 h.
- Redes confiáveis (Tailscale, rede local) na lista de exceção.

**Kernel e sistema**
- Protocolos de rede sem uso desativados (`dccp`, `sctp`, `rds`, `tipc`).
- Core dumps desativados.
- `sysctl`: restrição de `dmesg` e ponteiros do kernel, log de pacotes "marcianos",
  sem aceitar/enviar redirects ICMP.
- Pacotes de auditoria: `debsums`, `apt-show-versions`, `libpam-tmpdir`, `sysstat` ativo.
- Aviso legal no login.

## Validação

- Reconexão SSH testada após cada mudança.
- Dois reboots completos: firewall, fail2ban e todos os serviços voltaram sozinhos.

## Fica para depois (com motivo)

| Sugestão | Por que não agora |
|---|---|
| Partições separadas para `/home`, `/tmp`, `/var` | Exige reinstalar ou reparticionar |
| Senha no GRUB | Máquina em casa; risco de trancar o boot sem ganho real |
| `auditd` + verificador de integridade (AIDE) | Bom candidato para a trilha de segurança (mini-SOC) |
| Política de expiração de senha | Conta usa só chave SSH |
| Mais ajustes de SSH (`SSH-7408`) | Rodada 2, junto com revisão de algoritmos |
