# Thin client — extensão (não reescrita)

## CURRENT
Monólito no PC: UI + API + brain + tools + Qdrant embedded + evolution no mesmo processo.
Host auditado: 2 CPU, ~2 GB RAM, **GPU inexistente**. Sem Postgres/Redis/Docker/Ollama.

## TARGET
```
LIGHT PC (control + UI + cache SQLite)
        ↓ fila + eventos
WORKERS (compute) — 1..N, substituíveis
        ↓
DATA (hoje SQLite local; adapter para Postgres/Qdrant server depois)
```

## GAP
| Peça | Antes | Agora |
| Control plane | implícito | API + UI + registries + fila |
| Resource manager | não | CPU/RAM/GPU-optional + location |
| Task queue | inline HTTP | SQLite PENDING→…→COMPLETED |
| WorkerAdapter | não | register/heartbeat/claim + in-process worker |
| Remote worker | não | `worker.py` HTTP (não inventa cloud) |
| PC off | estado em SQLite | jobs persistem; compute remoto só se houver worker noutro host |
| TLS/RBAC | não | token opcional `SUPERAI_WORKER_TOKEN`; TLS = reverse proxy |
| Observability | logs | `/api/health` `/api/metrics` + terceiro olho (edge-triggered) |
| Fila | duplicava jobs | dedup por kind+texto; prune workers mortos; requeue órfãos; expire assigned |
| Control load | snapshot em todo o lado | health leve; SSE snapshot coalescido; probe LLM cache 2s |
| Chat sem LLM | ia à fila | só enfileira chat se `any_llm()`; senão NO_PROVIDER inline |

## MIGRAÇÃO
1. Leve (math/git/fs/json/status) **continua inline** no control plane.
2. Pesado (benchmark, evolution, LLM) **vai para a fila** se existir worker vivo.
3. Sem worker remoto: worker **in-process** no API (mesmo host, GPU não exigida).
4. Não se destrói cache, firewall, Qdrant, evolution, tools.

## NÃO INVENTADO
Cloud workers, Postgres, Redis, TLS termina no processo, GPU. `worker.py` é o contrato; neste sandbox o compute é o worker local.
