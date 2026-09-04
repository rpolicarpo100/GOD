# GOD — roadmap (2026-09-04)

Fonte: código em `/home/user/super-ai`. GitHub: [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD) `main`. Plane: slug `godsx` MEASURED, não é o núcleo.

Este é o roadmap **correcto** (prioridade do utilizador). Não é marketing.

```mermaid
flowchart LR
  U[Tu] --> H[handle]
  H --> A[analyze exec_mode]
  A --> C{cache hash}
  C -->|hit| OUT[0 LLM]
  C -->|miss FAST/NORMAL| F[skip vector/mem]
  C -->|miss DEEP| M[SQL + Qdrant]
  F --> P{plan}
  M --> P
  P -->|tools| SY[Governor]
  P -->|NORMAL needs_llm| D[Direct LLM]
  P -->|DEEP needs_llm| Q[fila worker]
  P -->|sem provider| NP[NO_PROVIDER]
```

## Prioridade

| Pri | Sistema | Objectivo | Estado | Evidência |
| --- | --- | --- | --- | --- |
| 🔴 P0 | Fast Path | eliminar latência desnecessária | **FEITO** | `exec_mode=FAST` → sem Qdrant/SQL. math/git/fs/parse/status |
| 🔴 P0 | Latency telemetry | descobrir onde realmente demora | **FEITO** | `latency_ms` + `stages_ms` MEASURED no pipeline |
| 🔴 P0 | Direct LLM path | não pôr chat simples sempre na queue | **FEITO** | NORMAL/FAST com LLM → inline. DEEP → fila |
| 🔴 P0 | Smart memory | memória apenas quando necessária | **FEITO** | memória/vector só DEEP ou complexity≥5 |
| 🟠 P1 | Executive Core | verdadeira decisão/orquestração | PARTIAL | `runtime.handle` é o orquestrador. Sem DAG |
| 🟠 P1 | Mission Engine | objectivos persistentes | **NOT IMPLEMENTED** | — |
| 🟠 P1 | Task Graph | dependências + paralelismo | **NOT IMPLEMENTED** | inflight=1 |
| 🟠 P1 | Model Router | qualidade/latência/custo | PARTIAL | DirectAdapter ordem local→API→Claude. € UNKNOWN. n=0 scores |
| 🟡 P2 | Agent Factory | agentes especializados | **NOT IMPLEMENTED** | Builder ≠ factory |
| 🟡 P2 | Validator | verificar trabalho | PARTIAL | `evaluate()` heurístico, não testes da tarefa |
| 🟡 P2 | Third Eye 2.0 | criticar decisões | PARTIAL | observer métricas host. Sem crítica de planos |
| 🟢 P3 | GOD Factory | criar GODs especializadas | **NOT IMPLEMENTED** | perfis no mesmo handle |
| 🟢 P3 | Compute Mesh | PC + portátil + telemóvel | **NOT IMPLEMENTED** | `pc_node` USER_DECLARED only |
| 🟢 P4 | UI Command Center | visualizar toda a operação | PARTIAL | dashboard viva. Sem mission/graph |

## Não agora

Desktop, swarm, marketplace, Redis/Postgres/Kafka por aparência, segundo `handle`, preços inventados, Plane como núcleo.

## Feito à volta (não é P0–P4)

GitHub público + deploy key SSH. Plane `godsx` / GODSX work-items MEASURED. Caps PC i5-4590 50%. 22€ IVA ≠ API UNKNOWN.
