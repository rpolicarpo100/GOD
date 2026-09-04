# CHANGELOG — GOD

## 2026-09-04 — P0 + P1 + P2 + P4 Complete

### Commits

| SHA | Descrição |
|-----|-----------|
| `b26b168` | Update ROADMAP: P1 completo |
| `535fcd7` | P1 Router: latência como critério secundário |
| `71a62a4` | P1: Task Graph inflight=2 + Router fiabilidade + HARDCORE |
| `6971de5` | Update ROADMAP: P2 Validator + Third Eye + P4 UI done |
| `6592c90` | P2: Validator + Third Eye 2.0 + P4 UI interactive |
| `b45cf85` | Roadmap: evidência por ficheiro, SHA P1, chips P0 completos |
| `e03a77e` | Roadmap P0–P4 alinhado ao código |
| `3c0c8cb` | P1: decide determinístico, missões SQLite, parent_id |

### P0 — Feito

- **Fast Path:** `brain.exec_mode=FAST` → sem Qdrant/SQL para math/git/fs/parse/status
- **Latency telemetry:** `runtime._mark` → `latency_ms` + `stages_ms` MEASURED
- **Direct LLM path:** `executive.decide` NORMAL/FAST → inline. DEEP → fila
- **Smart memory:** `need_mem` só DEEP ou complexity≥5

### P1 — Feito

- **Executive Core:** `superai/executive.py` `decide()`. Sem classe Brain. `handle` mantém-se
- **Mission Engine:** `superai/mission.py` SQLite. `/api/missions`. chat `missão:` / actual / conclui
- **Task Graph:** `queue.parent_id` + `job_is_ready`. inflight=2 (2 jobs paralelos). LLM remoto não usa CPU
- **Model Router:** `routing.sort_adapters` por ok_rate (fiabilidade) + latência (secundário). HARDCORE MODE → claude primary

### P2 — Feito

- **Validator:** `superai/validator.py` 12 check types, 10 tests
- **Third Eye 2.0:** `superai/thirdeye.py` 10 criticism checks, 7 tests

### P4 — Feito

- **UI Command Center:** dashboard interactivo com missões, grafo, validator, thirdeye

### Bloqueado

- **P1 Router €:** Todos os modelos são free tier (cost=0). Cost-based routing não se aplica. Só com source verificada de preços.

### Testes

```
113 PASS, 1 FAIL (pré-existente env-dependent)
```

### Ficheiros Criados/Modificados

```
superai/validator.py      — P2 Validator (NEW)
superai/thirdeye.py       — P2 Third Eye 2.0 (NEW)
superai/brain.py          — Fix regex math (MODIFIED)
superai/runtime.py        — Integração validator + thirdeye + HARDCORE MODE (MODIFIED)
superai/resources.py      — inflight=2 (MODIFIED)
superai/queue.py          — graph() reflecte paralelismo (MODIFIED)
superai/routing.py        — sort por fiabilidade + latência + HARDCORE (MODIFIED)
tests/test_core.py        — +19 testes (MODIFIED)
index.html                — Dashboard UI (MODIFIED)
PROJECT_STATE.md          — Estado do projecto (NEW)
PROJECT_STATE.json        — Estado estruturado (NEW)
CHANGELOG_AI.md           — Log de intervenções (NEW)
DECISIONS.md              — Decisões arquitecturais (NEW)
setup.bat                 — Instalação Windows (NEW)
god.bat                   — CLI utilitário (NEW)
ROADMAP.md                — Actualizado (MODIFIED)
CHANGELOG.md              — Este ficheiro (NEW)
```
