# P1.5 — AUDITORIA INICIAL (2026-09-05)

## A. ARQUITECTURA — FLUXO REAL

```
USER (UI / API / chat)
  → server.py (FastAPI)
    → runtime.handle(text)
      → brain.analyze(text)          → intent/type/complexity/exec_mode
      → cache_lookup(hash)           → HIT → return 0 LLM
      → memory (SQL + Qdrant)        → only DEEP/cx≥5
      → tokens.gate(firewall)        → reject/optimize/approve
      → _plan(task)                  → steps/needs_llm
      → executive.decide()           → tools/queue/direct_llm/no_provider
      → [if tools] aios.syscall()    → tools.execute() → governor
      → [if llm] routing.complete()  → DirectAdapter → providers
      → validator.validate()         → type-specific checks
      → thirdeye.criticize()         → pipeline criticism
      → evaluate(scores)             → heuristic quality
      → cache_store + mem_put
      → return response
```

**Verificado:** O fluxo real corresponde ao documentado. `handle()` é o único ponto de entrada lógico.

---

## B. FUNCIONALIDADES — CLASSIFICAÇÃO VERIFICADA

| Componente | Estado | Evidência |
|------------|--------|-----------|
| `runtime.handle` | IMPLEMENTED | ~1123 linhas, orquestrador principal |
| `brain.analyze` | IMPLEMENTED | regex + complexity + exec_mode |
| `brain.cache` | IMPLEMENTED | hash + semantic Qdrant |
| `executive.decide` | IMPLEMENTED | determinístico, 53 linhas |
| `routing.sort_adapters` | IMPLEMENTED | ok_rate + latência + HARDCORE |
| `providers` (8 adapters) | IMPLEMENTED | probed, cache 5s |
| `tools` (12 tools) | IMPLEMENTED | governor-gated |
| `tokens` | IMPLEMENTED | estimate/record/firewall |
| `queue` | IMPLEMENTED | SQLite + parent_id + inflight=2 |
| `mission` | IMPLEMENTED | SQLite, CRUD, snapshot |
| `validator` | IMPLEMENTED | 12 check types |
| `thirdeye` | IMPLEMENTED | 10 criticism checks |
| `observer` | IMPLEMENTED | metrics + alerts |
| `evolution` | PARTIAL | observe/propose/decide; não muda código |
| `gods` (builder) | IMPLEMENTED | perfis JSON, overlay prompt |
| `memory_vec` | IMPLEMENTED | Qdrant embedded + HashingVectorizer |
| `aios` (kernel) | IMPLEMENTED | admit/syscall/kill/ps |
| `governor` | IMPLEMENTED | FS/python/git limits |
| `repair` | IMPLEMENTED | diagnósticos MEASURED |
| `benchmark` | IMPLEMENTED | golden-set runner |
| `plane` | PARTIAL | probe-only, workspace 401 |
| `compute` | IMPLEMENTED | in-process worker |

---

## C. TESTES

```
Comando: python3 -m unittest tests.test_core -q
Resultado: 114 tests, 113 PASS, 1 FAIL
Falha: test_subset_gates_execute (pré-existente, env-dependent)
```

**Cobertura por módulo:**
- brain: ✅ (analyzer, cache, evaluate)
- executive: ✅ (decide paths)
- routing: ✅ (sort_adapters, HARDCORE)
- providers: ✅ (health, pick_chat_model)
- tools: ✅ (calculator, json, fs, git)
- tokens: ✅ (estimate, pricing, firewall)
- queue: ✅ (claim, inflight, parent_id)
- mission: ✅ (create, status, chat commands)
- validator: ✅ (12 check types)
- thirdeye: ✅ (10 criticism checks)
- observer: ✅ (inspect, tick)
- evolution: ✅ (observe, decide)
- aios: ✅ (syscall, kill, ps)
- gods: ✅ (save, activate, rollback)
- repair: ✅ (run)
- benchmark: ✅ (golden-set)

---

## D. RISCOS ARQUITECTURAIS

1. **runtime.handle() monolítico** — ~1123 linhas. Aceitável por agora; não duplicar.
2. **Sem capability registry formal** — capabilities espalhadas por gods.py e tools.py.
3. **Sem system state centralizado** — dados espalhados por observer, tokens, resources.
4. **Sem audit trail estruturado** — events.py regista, mas sem decision trace.
5. **Evolution não integra com pipeline** — observe/propose mas sem auto-apply.
6. **Health checks incompletos** — `/api/health` existe mas sem readiness separado.

---

## E. O QUE NÃO EXISTE (verificado)

| Feature | Estado |
|---------|--------|
| System State centralizado | NOT IMPLEMENTED |
| Capability Registry | NOT IMPLEMENTED |
| Decision Trace estruturado | NOT IMPLEMENTED |
| Audit Trail estruturado | PARTIAL (events.py) |
| Health/Readiness separados | PARTIAL |
| Controlled Evolution | PARTIAL (existe mas limitado) |
| Feature Flags | NOT IMPLEMENTED |

---

## F. PLANO DE IMPLEMENTAÇÃO P1.5

### Fase 1: System State (superai/system.py)
- Criar `system_state()` que agrega dados reais de todos os módulos
- Usar git, config, providers, queue, tokens, observer, repair
- Endpoint `/api/system/state`

### Fase 2: Capability Registry (superai/capabilities.py)
- Registry centralizado de capabilities
- `can(name)` → bool com evidência
- Cada capability: name, status, enabled, verified, evidence, limitations
- Endpoint `/api/system/capabilities`

### Fase 3: Decision Trace (extensão events.py)
- Estruturar eventos como decision records
- request_id → chain de decisões
- Endpoint `/api/system/trace/{request_id}`

### Fase 4: Health/Readiness (extensão observer.py)
- Separar liveness de readiness
- Endpoint `/api/system/health` + `/api/system/readiness`

### Fase 5: Controlled Evolution (extensão evolution.py)
- Feature flags no config.yaml
- Risk classification
- Human approval para HIGH RISK

### Fase 6: Testes
- Capability registry tests
- System state tests
- Decision trace tests
- Health/readiness tests
- Evolution control tests
