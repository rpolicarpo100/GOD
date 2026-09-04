# GOD — roadmap (2026-09-04)

Fonte: código em `/home/user/super-ai`.  
GitHub: [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD) `main`.  
Plane: slug `godsx` MEASURED — **não** é o núcleo.

Este é o roadmap **correcto**. Não é marketing. Fluxo = código actual.

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
| 🔴 P0 | Fast Path | eliminar latência desnecessária | **FEITO** | `exec_mode=FAST` → sem Qdrant/SQL. math/git/fs/parse/status |
| 🔴 P0 | Latency telemetry | descobrir onde realmente demora | **FEITO** | `latency_ms` + `stages_ms` MEASURED no pipeline |
| 🔴 P0 | Direct LLM path | não pôr chat simples sempre na queue | **FEITO** | NORMAL/FAST com LLM → inline. DEEP → fila |
| 🔴 P0 | Smart memory | memória apenas quando necessária | **FEITO** | memória/vector só DEEP ou complexity≥5 |
| 🟠 P1 | Executive Core | verdadeira decisão/orquestração | **FEITO** | `executive.decide()` DETERMINISTIC. Sem classe Brain. `handle` mantém-se |
| 🟠 P1 | Mission Engine | objectivos persistentes | **FEITO** | SQLite `missions`. chat `missão:` / actual / conclui. Uma active |
| 🟠 P1 | Task Graph | dependências + paralelismo | PARTIAL | `jobs.parent_id`. claim espera o pai. inflight=1. Sem DAG. Sem paralelo |
| 🟠 P1 | Model Router | qualidade/latência/custo | PARTIAL | stats MEASURED n≥3 reordenam. PREMIUM→claude se probed. cost UNKNOWN |
| 🟡 P2 | Agent Factory | agentes especializados | **NOT IMPLEMENTED** | Builder ≠ factory |
| 🟡 P2 | Validator | verificar trabalho | PARTIAL | `evaluate()` heurístico, não testes da tarefa |
| 🟡 P2 | Third Eye 2.0 | criticar decisões | PARTIAL | observer métricas host. Sem crítica de planos |
| 🟢 P3 | GOD Factory | criar GODs especializadas | **NOT IMPLEMENTED** | perfis no mesmo handle |
| 🟢 P3 | Compute Mesh | PC + portátil + telemóvel | **NOT IMPLEMENTED** | `pc_node` USER_DECLARED only |
| 🟢 P4 | UI Command Center | visualizar toda a operação | PARTIAL | dashboard: missão + graph + decision.path · chips P0–P4 |

## Feito

- P0 completo (Fast Path, latency MEASURED, Direct LLM, smart memory).
- P1 Executive + Mission no código e no dashboard.
- GitHub público + push por deploy key SSH.
- Plane `godsx` / GODSX work-items MEASURED (`in_product=false`).
- Caps PC i5-4590 50%. 22€ IVA USER_STATED ≠ API UNKNOWN.

## A fazer (ordem)

1. **P2 Validator** — provas da tarefa, não só `evaluate()` heurístico. Sem agente QA fictício.
2. **P2 Third Eye 2.0** — criticar decisões/planos com factos MEASURED. Sem LLM de crítica inventado.
3. **P1 graph** — fica PARTIAL de propósito: inflight=1 neste host; paralelo só no PC com cap de cores, nunca 4/4.
4. **P1 router €** — só com `source` verificada em `model_pricing`. Até lá cost=UNKNOWN.
5. **P4 UI** — mission/graph/decision já visíveis; falta command center de missão/grafo interactivo.
6. **Não** P2 Agent Factory, P3 GOD Factory, P3/P4 mesh, Desktop, swarm, Redis/K8s por aparência.

## GitHub deploy

- Repo: https://github.com/rpolicarpo100/GOD
- Branch: `main`
- Push: SSH deploy key (nunca HTTPS PAT, nunca commitar `.env` / chave privada)
- Testes no último P1: 89 OK

## Não agora

Desktop, swarm, marketplace, Redis/Postgres/Kafka por aparência, segundo `handle`, preços inventados, Plane como núcleo, classe ExecutiveBrain, motor DAG, Agent Factory.
