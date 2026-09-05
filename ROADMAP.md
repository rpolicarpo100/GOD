# GOD — roadmap (2026-09-04)

Fonte: código em `/home/user/super-ai`.  
GitHub: [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD) `main`.  
Plane: slug `godsx` MEASURED — **não** é o núcleo.

Este é o roadmap **correcto**. Não é marketing. Fluxo = código actual.

**HEAD de código:** [`2d341e4`](https://github.com/rpolicarpo100/GOD/commit/2d341e4) · testes **162 OK** (164 total, 2 pré-existentes).

```mermaid
flowchart LR
  U[Tu] --> H[handle]
  H --> A[analyze exec_mode]
  A --> C{cache hash}
  C -->|hit| OUT[0 LLM]
  C -->|miss FAST/NORMAL| F[skip vector/mem]
  C -->|miss DEEP| M[SQL + Qdrant]
  F --> P[plan]
  M --> P
  P --> D[decide DETERMINISTIC]
  D -->|tools| SY[Governor]
  D -->|NORMAL needs_llm| L[Direct LLM]
  D -->|DEEP needs_llm| Q[fila worker]
  D -->|sem provider| NP[NO_PROVIDER]
  H -.-> MS[missão SQLite]
  Q -.-> G[job parent_id]
```

## Prioridade

| Pri | Sistema | Objectivo | Estado | Evidência |
| --- | --- | --- | --- | --- |
| 🔴 P0 | Fast Path | eliminar latência desnecessária | **FEITO** | `brain.exec_mode=FAST` → sem Qdrant/SQL. math/git/fs/parse/status |
| 🔴 P0 | Latency telemetry | descobrir onde realmente demora | **FEITO** | `runtime._mark` → `latency_ms` + `stages_ms` MEASURED |
| 🔴 P0 | Direct LLM path | não pôr chat simples sempre na queue | **FEITO** | `executive.decide` NORMAL/FAST → inline. DEEP → fila |
| 🔴 P0 | Smart memory | memória apenas quando necessária | **FEITO** | `need_mem` só DEEP ou complexity≥5 |
| 🟠 P1 | Executive Core | verdadeira decisão/orquestração | **FEITO** | `superai/executive.py` `decide()`. Sem classe Brain. `handle` mantém-se |
| 🟠 P1 | Mission Engine | objectivos persistentes | **FEITO** | `superai/mission.py` SQLite. `/api/missions`. chat `missão:` / actual / conclui |
| 🟠 P1 | Task Graph | dependências + paralelismo | **FEITO** | `queue.parent_id` + `job_is_ready`. `/api/graph`. inflight=2 (2 jobs paralelos). LLM remoto não usa CPU |
| 🟠 P1 | Model Router | qualidade/fiabilidade/latência | **FEITO** | `routing.sort_adapters` por ok_rate (fiabilidade) + latência (secundário). HARDCORE MODE → claude primary. cost UNKNOWN |
| 🟡 P2 | Agent Factory | agentes especializados | **NOT IMPLEMENTED** | Builder (`gods.py`) ≠ factory |
| 🟡 P2 | Validator | verificar trabalho | **FEITO** | `superai/validator.py` 12 check types · 10 tests |
| 🟡 P2 | Third Eye 2.0 | criticar decisões | **FEITO** | `superai/thirdeye.py` 10 checks MEASURED · 7 tests |
| 🟢 P3 | GOD Factory | criar GODs especializadas | **NOT IMPLEMENTED** | perfis no mesmo handle |
| 🟢 P3 | Compute Mesh | PC + portátil + telemóvel | **NOT IMPLEMENTED** | `pc_node` USER_DECLARED only |
| 🟢 P4 | UI Command Center | visualizar toda a operação | **FEITO** | dashboard: missão + graph + decision.path + validator + thirdeye + chips P0–P4 |
| 🔵 P1.5 | System State | consciência operacional verificável | **FEITO** | `superai/system.py` + `/api/system/state` · 5 tests |
| 🔵 P1.5 | Capability Registry | `can("memory")` etc. | **FEITO** | `superai/capabilities.py` 13 capabilities · 6 tests |
| 🔵 P1.5 | Health & Readiness | liveness + readiness + diagnostics | **FEITO** | `superai/health.py` + 4 endpoints · 5 tests |
| 🔵 P1.5 | Decision Trace | WHAT/WHY/WHEN/PATH | **FEITO** | `superai/trace.py` + 2 endpoints · 4 tests |
| 🔵 P1.5 | API Endpoints | 9 novos endpoints | **FEITO** | server.py 9 endpoints · 7 tests |
| 🔵 P1.5 | Feature Flags | 8 flags, DISABLED by default | **FEITO** | `superai/feature_flags.py` · 9 tests |
| 🔵 P1.5 | Controlled Evolution | risk classification + human-in-the-loop | **FEITO** | evolution.py `classify_risk` + `propose_with_risk` · 5 tests |
| 🔵 P1.5 | Runtime Protection | GOD Object detection | **FEITO** | `superai/runtime_protection.py` · 9 tests |

## Feito

- P0 completo (Fast Path, latency MEASURED, Direct LLM, smart memory).
- P1 Executive + Mission no código, APIs e dashboard.
- P1 Task Graph — inflight=2 (2 jobs paralelos). LLM remoto não usa CPU.
- P1 Model Router — ordenar por fiabilidade (ok_rate) + latência (secundário). HARDCORE MODE → claude primary.
- P2 Validator (`superai/validator.py`) — 12 check types, 10 tests.
- P2 Third Eye 2.0 (`superai/thirdeye.py`) — 10 criticism checks, 7 tests.
- P4 UI Command Center — dashboard interactivo com missões e grafo.
- P1.5 System State (`superai/system.py`) — consciência operacional verificável.
- P1.5 Capability Registry (`superai/capabilities.py`) — 15 capabilities, evidence-based.
- P1.5 Health & Readiness (`superai/health.py`) — liveness + readiness + diagnostics.
- P1.5 Decision Trace (`superai/trace.py`) — WHAT/WHY/WHEN/PATH per request.
- P1.5 API Endpoints — 16 novos endpoints (/api/system/*).
- P1.5 Feature Flags (`superai/feature_flags.py`) — 8 flags, DISABLED by default, risk-classified.
- P1.5 Controlled Evolution — classify_risk() + propose_with_risk() com auto-blocking para HIGH RISK.
- P1.5 Runtime Protection (`superai/runtime_protection.py`) — GOD Object detection + AST inspection.
- Refactor GOD Object — runtime.py: 1129→503 linhas, handle(): 586→53 linhas. Extracted pipeline.py + shortcuts.py.
- GitHub público + push por deploy key SSH (`3c0c8cb` e seguintes).
- Plane `godsx` / GODSX work-items MEASURED (`in_product=false`).
- Caps PC i5-4590 50%. 22€ IVA USER_STATED ≠ API UNKNOWN.

## A fazer (ordem)

1. ~~**P2 Validator**~~ — provas da tarefa, não só `evaluate()` heurístico. Sem agente QA fictício. **FEITO** (`superai/validator.py`).
2. ~~**P2 Third Eye 2.0**~~ — criticar decisões/planos com factos MEASURED. Sem LLM de crítica inventado. **FEITO** (`superai/thirdeye.py`).
3. ~~**P1 Task Graph**~~ — dependências + paralelismo. inflight=2 (2 jobs paralelos). **FEITO** (`resources.inflight_cap`, `queue.graph`).
4. ~~**P1 Model Router**~~ — ordenar por fiabilidade (ok_rate) + latência. HARDCORE MODE → claude primary. **FEITO** (`routing.sort_adapters`).
5. **P1 router €** — só com `source` verificada em `model_pricing`. Até lá cost=UNKNOWN. **BLOQUEADO:** todos os modelos são free (cost=0).
6. ~~**P4 UI**~~ — mission/graph/decision já visíveis; falta command center de missão/grafo interactivo. **FEITO** (dashboard interactivo).
7. ~~**P1.5 System Integrity**~~ — System State + Capability Registry + Health/Readiness + Decision Trace. **FEITO** (`superai/system.py`, `capabilities.py`, `health.py`, `trace.py`).
8. ~~**P1.5 Controlled Evolution**~~ — feature flags (8 flags, DISABLED by default) + risk classification (LOW/MEDIUM/HIGH). **FEITO** (`superai/feature_flags.py`, evolution.py `classify_risk` + `propose_with_risk`).
9. ~~**P1.5 Runtime Protection**~~ — GOD Object anti-pattern detection + AST-based file inspection. **FEITO** (`superai/runtime_protection.py`).
10. ~~**Refactor GOD Object**~~ — runtime.py 1129→503, handle() 586→53. Extracted `pipeline.py` + `shortcuts.py`. **FEITO**.
11. **Não** P2 Agent Factory, P3 GOD Factory, P3 mesh, Desktop, swarm, Redis/K8s por aparência.

## GitHub deploy

- Repo: https://github.com/rpolicarpo100/GOD
- Branch: `main`
- Push: SSH deploy key (nunca HTTPS PAT, nunca commitar `.env` / chave privada)
- P1: `535fcd7` · testes 113 OK

## Não agora

Desktop, swarm, marketplace, Redis/Postgres/Kafka por aparência, segundo `handle`, preços inventados, Plane como núcleo, classe ExecutiveBrain, motor DAG, Agent Factory, inflight>2 (nunca 4/4).
