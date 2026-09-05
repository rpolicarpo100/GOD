# PHASE 1 — DISCOVERY REPORT

## Date: 2026-09-05

---

## COMPONENT MAP

### CORE COMPONENTS

| Component | Path | Lines | Responsibility | Depends On | Used By | Risk |
|-----------|------|-------|----------------|------------|---------|------|
| runtime | superai/runtime.py | 554 | Main entry point, handle() function | pipeline, brain, store, gods | server.py | HIGH |
| pipeline | superai/pipeline.py | 626 | Core processing pipeline | brain, validator, thirdeye, sensitive, sandbox | runtime | HIGH |
| brain | superai/brain.py | 234 | Analysis, cache, evaluation | store, util | pipeline | HIGH |
| store | superai/store.py | 488 | Data persistence (SQLite) | — | All components | HIGH |
| config | superai/config.py | 90 | Configuration management | — | All components | MEDIUM |

### SECURITY COMPONENTS (P0-P2)

| Component | Path | Lines | Responsibility | Depends On | Used By | Risk |
|-----------|------|-------|----------------|------------|---------|------|
| auth | superai/auth.py | 763 | Authentication + Authorization | config | server, pipeline | HIGH |
| evidence | superai/evidence.py | 324 | Task evidence engine | — | pipeline, validator | MEDIUM |
| sensitive | superai/sensitive.py | 278 | Sensitive data detection | util | pipeline | MEDIUM |
| sandbox | superai/sandbox.py | 378 | Sandbox protection | — | pipeline | MEDIUM |
| resource_limits | superai/resource_limits.py | 250 | Resource tracking | util | pipeline | MEDIUM |
| rate_limit | superai/rate_limit.py | 200 | Rate limiting | util | server | MEDIUM |
| network_control | superai/network_control.py | 280 | Network access control | util | server | MEDIUM |

### COGNITION COMPONENTS

| Component | Path | Lines | Responsibility | Depends On | Used By | Risk |
|-----------|------|-------|----------------|------------|---------|------|
| executive | superai/executive.py | 205 | Decision making | providers | pipeline | HIGH |
| governor | superai/governor.py | 206 | Resource governance | — | pipeline, runtime | HIGH |
| validator | superai/validator.py | 601 | Result validation | — | pipeline | MEDIUM |
| thirdeye | superai/thirdeye.py | 673 | Decision criticism | store, events | pipeline | MEDIUM |

### INFRASTRUCTURE COMPONENTS

| Component | Path | Lines | Responsibility | Depends On | Used By | Risk |
|-----------|------|-------|----------------|------------|---------|------|
| providers | superai/providers.py | 553 | LLM provider management | — | routing, pipeline | HIGH |
| routing | superai/routing.py | 190 | Request routing | providers | pipeline | MEDIUM |
| queue | superai/queue.py | 475 | Job queue | store | pipeline, compute | MEDIUM |
| tools | superai/tools.py | 434 | Tool execution | — | pipeline | MEDIUM |
| aios | superai/aios.py | 370 | OS abstraction | observer, providers | server | LOW |

### DATA COMPONENTS

| Component | Path | Lines | Responsibility | Depends On | Used By | Risk |
|-----------|------|-------|----------------|------------|---------|------|
| store | superai/store.py | 488 | SQLite persistence | — | All | HIGH |
| memory_vec | superai/memory_vec.py | 180 | Vector memory (Qdrant) | — | pipeline | MEDIUM |
| cache | superai/cache.py | 281 | L1+L2 cache system | memory_vec | pipeline | LOW |
| semantic_cache | superai/semantic_cache.py | 155 | Semantic cache | memory_vec | brain | LOW |

### EVOLUTION COMPONENTS

| Component | Path | Lines | Responsibility | Depends On | Used By | Risk |
|-----------|------|-------|----------------|------------|---------|------|
| evolution | superai/evolution.py | 323 | System evolution | store, providers | server | MEDIUM |
| mission | superai/mission.py | 155 | Mission management | store | pipeline | LOW |
| gods | superai/gods.py | 200 | GOD profiles | store | pipeline | LOW |

---

## ENTRY POINTS

### Primary Entry Points

1. **server.py** — FastAPI server
   - `POST /api/chat` → `handle()` → pipeline
   - `POST /v1/chat/completions` → OpenAI-compatible API
   - `GET /` → UI (index.html)

2. **worker.py** — Background worker
   - `if __name__ == "__main__"` → queue processing

3. **runtime.py** → `handle()` function
   - Main entry point for all requests

### Secondary Entry Points

4. **god.sh / god.bat** — Startup scripts
5. **tests/** — Test entry points

---

## MAIN FLOW

```
USER INPUT
    ↓
server.py (POST /api/chat)
    ↓
runtime.handle()
    ↓
pipeline.run_pipeline()
    ↓
┌─────────────────────────────────────────────────────────┐
│ SECURITY SCAN (sensitive.py)                            │
│ - Block if risk≥5                                       │
│ - Warn if risk≥3                                        │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ ANALYSIS (brain.analyze)                                │
│ - Task type detection                                   │
│ - Complexity estimation                                 │
│ - Exec mode (FAST/NORMAL/DEEP)                          │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ CACHE LOOKUP (cache.py)                                 │
│ - L1: Hash match                                        │
│ - L2: Semantic match                                    │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ MEMORY RETRIEVAL (store + memory_vec)                   │
│ - SQL episodes                                          │
│ - Vector similarity                                     │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ TOKEN FIREWALL (tokens.py)                              │
│ - Budget check                                          │
│ - Optimization if needed                                │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ PLAN + DECIDE (executive.py)                            │
│ - Tool selection                                        │
│ - LLM routing                                           │
│ - Queue dispatch                                        │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ EXECUTION                                               │
│ - Tools (sandbox.py)                                    │
│ - State query                                           │
│ - LLM (routing.py)                                      │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ VALIDATION (validator.py)                               │
│ - Type-specific checks                                  │
│ - Evidence collection                                   │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ CRITICISM (thirdeye.py)                                 │
│ - Path optimality                                       │
│ - Latency analysis                                      │
│ - Recommendations                                       │
└─────────────────────────────────────────────────────────┘
    ↓
RESULT + AUDIT
```

---

## DEPENDENCY GRAPH

```
server.py
    ├── runtime.py
    │   ├── pipeline.py
    │   │   ├── brain.py
    │   │   ├── validator.py
    │   │   ├── thirdeye.py
    │   │   ├── sensitive.py
    │   │   ├── sandbox.py
    │   │   ├── resource_limits.py
    │   │   └── cache.py
    │   ├── gods.py
    │   └── shortcuts.py
    ├── auth.py
    ├── rate_limit.py
    └── network_control.py

pipeline.py
    ├── brain.py
    │   ├── store.py
    │   └── util.py
    ├── executive.py
    │   └── providers.py
    ├── validator.py
    ├── thirdeye.py
    ├── sensitive.py
    ├── sandbox.py
    ├── resource_limits.py
    ├── cache.py
    └── routing.py
        └── providers.py

store.py (SQLite)
    └── config.py
```

---

## CIRCULAR DEPENDENCIES

### Detected

1. **runtime.py ↔ pipeline.py**
   - runtime imports pipeline
   - pipeline imports runtime (snapshot)
   - **Risk**: LOW (one-way actual dependency)

2. **pipeline.py ↔ brain.py**
   - pipeline imports brain functions
   - brain imports store (not pipeline)
   - **Risk**: NONE

### No Circular Dependencies Found

All other dependencies are acyclic.

---

## COMPONENT CLASSIFICATION

### KEEP (Critical, Working)

- runtime.py — Main entry point
- pipeline.py — Core processing
- brain.py — Analysis
- store.py — Data persistence
- config.py — Configuration
- auth.py — Security
- providers.py — LLM providers
- routing.py — Request routing
- queue.py — Job queue
- tools.py — Tool execution
- validator.py — Validation
- thirdeye.py — Criticism
- executive.py — Decision making
- governor.py — Governance

### REFACTOR (Working but Needs Improvement)

- aios.py — OS abstraction (370 lines)
- capabilities.py — Capability detection (419 lines)
- evolution.py — Evolution system (323 lines)
- runtime_protection.py — GOD Object detection (323 lines)

### NEW (Recently Added, Needs Integration Validation)

- cache.py — L1+L2 cache system
- optimize.py — Optimization utilities
- semantic_cache.py — Semantic cache
- cohere_rerank.py — Cohere rerank
- evidence.py — Evidence engine
- sensitive.py — Sensitive data detection
- sandbox.py — Sandbox protection
- resource_limits.py — Resource limits
- rate_limit.py — Rate limiting
- network_control.py — Network control

### DEPRECATE (Consider Removing)

- ratelimit.py — Duplicate of rate_limit.py?
- benchmark_reality.py — Superseded by benchmark.py?

---

## CRITICAL FINDINGS

### F1: Duplicate Rate Limiters

**Files**: `superai/ratelimit.py` vs `superai/rate_limit.py`

**Issue**: Two rate limiter implementations exist.

**Risk**: MEDIUM

**Action**: Investigate and merge/remove.

### F2: Resource Limits Test Failures

**Issue**:5 tests in `test_security_p2.py` fail due to shared state.

**Root Cause**: Tests modify global tracker without cleanup.

**Risk**: LOW (test issue, not production)

**Action**: Fix test isolation.

### F3: Voice Capability Not Detected

**Issue**: `can("voice")` returns False even though voice.py exists.

**Root Cause**: Capability detection not recognizing voice module.

**Risk**: LOW

**Action**: Update capability detection.

---

## NEXT STEPS

1. Resolve F1: Investigate duplicate rate limiters
2. Resolve F2: Fix test isolation for resource limits
3. Resolve F3: Update capability detection
4. Proceed to Phase 2: Architecture Audit

---

## PHASE GATE

```
==================================================
PHASE GATE
==================================================

PHASE: 1

OBJECTIVE ACHIEVED: YES

COMMANDS EXECUTED:
- git ls-files ✓
- grep -R imports ✓
- grep -R entry points ✓
- grep -R components ✓
- Component analysis ✓

TESTS: N/A (no changes)

PRE-EXISTING FAILURES: 8 (from Phase 0)

NEW REGRESSIONS: NO

CRITICAL ISSUES:
- Duplicate rate limiters (ratelimit.py vs rate_limit.py)
- Resource limits test isolation
- Voice capability detection

BLOCKERS: None

FILES CHANGED: DISCOVERY.md (new)

EVIDENCE:
- Component map created
- Dependency graph mapped
- Entry points identified
- Critical findings documented

DECISION: PROCEED → PHASE 2

==================================================
```
