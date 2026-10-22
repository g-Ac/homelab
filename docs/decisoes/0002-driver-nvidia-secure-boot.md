# ADR 0002 — Driver NVIDIA pré-assinado em vez de DKMS com Secure Boot

- **Data:** 2026-10-22
- **Status:** aceita
- **Issue:** #4

## Contexto

O srv roda com **Secure Boot ligado**. O pacote `nvidia-driver-595-open` instala o módulo do kernel via
DKMS: ele é compilado na própria máquina e assinado com uma chave local (MOK). O firmware só aceita
essa chave depois de cadastrada numa tela de boot, o que exige teclado e monitor na máquina.

Sintoma: `modprobe nvidia` → `Key was rejected by service`, e `nvidia-smi` sem comunicação com o driver.

## Opções consideradas

1. **Desligar o Secure Boot** — resolve, mas reduz a proteção do boot só para facilitar a instalação.
2. **Cadastrar a chave MOK** — mantém o Secure Boot, mas exige acesso físico e repete o problema
   a cada máquina nova.
3. **Usar os módulos pré-compilados e assinados pela Canonical**
   (`linux-modules-nvidia-595-open-generic`) — o firmware já confia na assinatura.

## Decisão

Opção 3. Instalado `linux-modules-nvidia-595-open-generic` e removido `nvidia-dkms-595-open`.
O módulo carregado mostra `signer: Canonical Ltd. Kernel Module Signing`.

## Consequências

- O Secure Boot continua ligado, sem acesso físico à máquina.
- O metapacote `-generic` acompanha as atualizações de kernel. Se um kernel novo sair antes do
  módulo correspondente, a GPU fica indisponível até o pacote chegar (o sistema sobe normalmente).
- Validado com dois reboots: driver carrega no boot, `nvidia-smi` funciona no host e dentro de
  container (`docker run --gpus all`), via NVIDIA Container Toolkit 1.20.1.

## Estado final

| Item | Valor |
|---|---|
| GPU | GeForce GTX 1660, 6144 MiB |
| Driver | 595.99.02 (open kernel module) |
| CUDA (driver) | 13.2 |
| Container Toolkit | 1.20.1, runtime configurado no Docker |
