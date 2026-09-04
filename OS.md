# Super AI OS — auditoria (extensão, não rewrite)

Fonte: código em `/home/user/super-ai` em 2026-09-04. Host: 2 CPU, ~2 GB RAM, GPU ausente/`required=false`.

## CURRENT

Peças de SO já existem **dispersas**, não como kernel:

| Função OS | Onde | Lacuna |
|---|---|---|
| Processos | `queue.jobs` + `store.tasks` | sem tabela unificada, sem `kill` |
| Scheduler | `claim` FIFO `ORDER BY ts` | sem prioridade |
| Admissão | `resources.decide` | enfileira pesado mesmo com `pressure=high` |
| Syscalls | `tools.execute` | sem log de kernel; runtime chama direto |
| Drivers | `providers` + `routing` | probed — não inventar up |
| Segurança | `governor` | intacto; não se auto-altera |
| Serviços | worker in-process + terceiro olho | sem `ps` de daemons |
| Quota agent | `config.budgets.agent` | **não enforced** (TOKEN.md) |
| Preempção | nenhuma | running não se interrompe — honesto |

Não há `/proc`, `dmesg`, nem cancelamento de jobs `queued`/`assigned`.

## TARGET

```
USER / API / chat
  → kernel (aios.py)  admit / syscall / kill / ps / nice
       ↓ não substitui
  Brain · Router · Governor · Memory · Evolution · Token Intel · Observer
       ↓ usa
  queue (prioridade) · tools · providers (drivers) · store (disco)
```

PC = control + UI + cache. REMOTE = worker se existir. GPU = OPTIONAL.

## NÃO INVENTAR

Ollama/OmniRoute/Langfuse/preços/cloud workers. Drivers `available=false` se a sonda falhar.
Sem tab de documentação. Sem duplicar firewall/cache/router.
Running jobs: **sem preempção** neste host (não matamos threads).
