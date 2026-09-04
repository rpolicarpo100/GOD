# GOD — roadmap e fluxo (2026-09-04)

Ela chama-se **GOD**. Fonte: código em `/home/user/super-ai` + sondas neste host. Sem marketing.

**GitHub:** [rpolicarpo100/GOD](https://github.com/rpolicarpo100/GOD) — **publicado** `origin/main`.  
**Plane:** API `users/me` 200 (conta Ruben Policarpo). **Não há adapter no produto.** Workspaces não listados. Sem issues criadas daqui.  
**LLM:** Ollama :11434 fechado · Claude sem key · OmniRoute :20128 fechado. Modo **OFFLINE**.  
**GPU:** ausente, `required=false`.

```mermaid
flowchart LR
  U[Tu] --> H[handle]
  H --> A[analyze tiktoken]
  A --> C{cache hash / Qdrant 0.88}
  C -->|hit| OUT[resposta 0 LLM]
  C -->|miss| M[memória SQL + vectores]
  M --> FW[Token Firewall]
  FW -->|reject| OUT
  FW -->|optimize| FW
  FW --> P{plan LLM-last}
  P -->|math git fs parse py| SY[OS syscall → Governor → tools]
  SY --> OUT
  P -->|needs_llm e any_llm| Q[fila prioridade]
  Q --> W[worker in-process]
  P -->|needs_llm sem provider| NP[NO_PROVIDER — não inventa]
  W --> R[Intelligent Router]
  R -->|OmniRoute down| D[DirectAdapter]
  D -->|todos down| NP
```

```mermaid
flowchart TB
  subgraph PC["PC control — 2 CPU ~2 GB"]
    UI[dashboard GOD]
    API[FastAPI :8000]
    OS[kernel aios]
    BR[Brain runtime]
    TI[Token Intel]
    EYE[terceiro olho]
    UI --- API --- BR
    BR --- OS
    BR --- TI
    EYE --- OS
  end
  subgraph DATA["disco local"]
    SQL[(SQLite spine.db)]
    QD[(Qdrant embedded)]
  end
  subgraph COMPUTE["compute"]
    WK[control-local worker]
    Q2[jobs queued/assigned/running]
  end
  API --> SQL
  BR --> QD
  OS --> Q2 --> WK
```

## Fases — estado MEASURED

| Fase | Quê | Estado | Evidência |
|---|---|---|---|
| F0 | Infra FastAPI SQLite tools Governor | **FEITO** | `server.py` live `:8000` |
| F1 | LLM-last cache→mem→tools→router | **FEITO** | `runtime.handle` |
| F2 | Memória Qdrant embedded hashing 384 | **FEITO** | neural **não** — HashingVectorizer |
| F3 | Fila + worker in-process | **FEITO** | GPU não exigida |
| F4 | Token Intelligence | **FEITO** | cost **UNKNOWN**; 9240 actual = poluição de testes, não Claude |
| F5 | OS kernel admit/syscall/kill/ps | **FEITO** | sem preempção running |
| F6 | LLM vivo | **BLOQUEADO** | providers `available=false` |
| F7 | Deploy GitHub público | **FEITO** | `git push` origin/main https://github.com/rpolicarpo100/GOD |
| F8 | Plane no produto | **NÃO** | chave existe fora do git; código sem adapter |
| F9 | Embeddings neurais / SearXNG / Postgres | **NÃO** | ausentes |
| F10 | Preço € / Langfuse | **NÃO** | sem source |

## Terceiro olho — o que NÃO adicionar agora

- **Não** mais camadas (não duplicar Brain/Router/Governor/Firewall).
- **Não** prompts de “pesquisa” que finjam resultados. Sem SearXNG/LLM = recusar.
- **Não** preços hard-coded. cost continua UNKNOWN.
- **Não** Plane no dashboard até haver `workspace_slug` + issues **criadas pela API** (senão é teatro).
- **Não** GitHub com secrets. PAT e `plane_api_*` **nunca** no repo.
- **Não** tratar `QUALITY_DROP` como falha da GOD: é rating de tarefas `blocked` sem LLM.
- **Próximo código que vale:** (1) provider LLM real ou Ollama local; (2) `git init` + push **sem** `.env`/`data/`; (3) personalidade/UX. O resto é ruído.

## Handoff (próximo trabalhador)

- **Feito:** F0–F5 no processo `uvicorn :8000`. 47 testes na última corrida OS. Dashboard vivo + chat.
- **A fazer:** F6 provider; F7 publish GOD público; F8 Plane só depois de workspace.
- **Deploy GitHub:** **NÃO.**
- **Não reescrever** Brain / Router / Governor / Memory / Evolution.
