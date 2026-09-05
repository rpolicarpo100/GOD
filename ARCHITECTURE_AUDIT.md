# PHASE 2 — ARCHITECTURE AUDIT

## Date: 2026-09-05

---

## P0 CRITICAL FINDINGS

### P0-001: Circular Dependency (runtime ↔ pipeline)

**Files**: `superai/runtime.py` ↔ `superai/pipeline.py`

**Issue**: 
- runtime.py imports from pipeline (run_pipeline, plan, etc.)
- pipeline.py imports from runtime (snapshot)

**Current Mitigation**: Lazy imports inside functions (not at module level)

**Risk**: LOW (currently working due to lazy imports)

**Action**: Document but do not change (working as designed)

---

## P1 HIGH FINDINGS

### P1-001: GOD Object Candidates

| File | Lines | Classes | Functions | Risk |
|------|-------|---------|-----------|------|
| auth.py | 763 | 7 | 35 | MEDIUM |
| pipeline.py | 626 | 0 | 17 | MEDIUM |
| runtime.py | 554 | 0 | 25 | MEDIUM |
| thirdeye.py | 673 | 0 | 14 | LOW |
| validator.py | 601 | 0 | 16 | LOW |
| tokens.py | 551 | 0 | 24 | LOW |
| providers.py | 553 | 5 | 19 | LOW |

**Analysis**: 
- auth.py: Has multiple classes for different auth concerns — OK
- pipeline.py: Core processing pipeline — expected to be large
- runtime.py: Main entry point — expected to be large
- Others: Well-structured, not true GOD objects

**Action**: No immediate action required

---

### P1-002: Duplicate Rate Limiters

**Files**: 
- `superai/ratelimit.py` — Provider-level rate limiting
- `superai/rate_limit.py` — Endpoint-level rate limiting

**Analysis**:
- `ratelimit.py`: Limits per LLM provider (groq, cerebras, etc.)
- `rate_limit.py`: Limits per API endpoint (/api/chat, /auth/login, etc.)

**Conclusion**: NOT duplicates — different purposes

**Action**: Add documentation to clarify distinction

---

### P1-003: Hidden Global State

**Files with global state**:
- aios.py: `_boot_ts`, `_boot`
- auth.py: `_sessions`, `_overrides`, `_approvals`
- capabilities.py: `_cache`, `_cache_ts`
- compute.py: `_thread`
- embed.py: `_neural`, `_vec`
- feature_flags.py: `_flags`, `_flag_meta`
- observer.py: `_latest`, `_started`
- plane.py: `_cache`, `_cache_t`
- providers.py: `_hcache`, `_ht`

**Risk**: MEDIUM — Thread safety depends on locks

**Action**: Verify all globals use proper locking

---

## P2 MEDIUM FINDINGS

### P2-001: Test Isolation Issues

**Affected Tests**:
- TestResourceLimits:5 tests fail due to shared state
- TestCapabilities:2 tests fail due to voice detection

**Root Cause**: Tests modify global state without cleanup

**Action**: Fix in Phase 3 (P0 Fixes)

---

### P2-002: Import Style Inconsistency

**Issue**: Mix of import styles

```python
# Style1: Relative imports
from .config import cfg

# Style 2: Absolute imports (in some files)
from superai.config import cfg
```

**Action**: Standardize in Phase 13 (Cleanup)

---

## COMPONENT CLASSIFICATION

### KEEP (Critical, Working)

| Component | Reason |
|-----------|--------|
| runtime.py | Main entry point, essential |
| pipeline.py | Core processing, essential |
| brain.py | Analysis, essential |
| store.py | Data persistence, essential |
| config.py | Configuration, essential |
| auth.py | Security, essential |
| providers.py | LLM providers, essential |
| routing.py | Request routing, essential |
| queue.py | Job queue, essential |
| tools.py | Tool execution, essential |
| validator.py | Validation, essential |
| thirdeye.py | Criticism, essential |
| executive.py | Decision making, essential |
| governor.py | Governance, essential |
| events.py | Event bus, essential |
| util.py | Utilities, essential |

### REFACTOR (Working but Could Improve)

| Component | Reason |
|-----------|--------|
| aios.py | OS abstraction, could be simplified |
| capabilities.py | Could use caching improvement |
| evolution.py | Complex but working |
| runtime_protection.py | GOD Object detection, working |
| shortcuts.py | Could be merged with runtime |

### NEW (Recently Added, Needs Validation)

| Component | Status |
|-----------|--------|
| cache.py | Needs integration testing |
| optimize.py | Needs usage validation |
| semantic_cache.py | Needs integration testing |
| cohere_rerank.py | Needs API key to test |
| evidence.py | Needs integration testing |
| sensitive.py | Integrated, needs more tests |
| sandbox.py | Integrated, needs more tests |
| resource_limits.py | Has test issues |
| rate_limit.py | Integrated, working |
| network_control.py | Integrated, working |

### DEPRECATE (Consider Removing)

| Component | Reason |
|-----------|--------|
| benchmark_reality.py | Overlaps with benchmark.py |
| plane.py | Minimal usage |

---

## DEPENDENCY MATRIX

### Core Dependencies

```
runtime → pipeline → brain → store → config
                    → validator → util
                    → thirdeye → events, store
                    → sensitive → util
                    → sandbox → util
                    → resource_limits → util
```

### Security Dependencies

```
auth → config
sensitive → util
sandbox → util
resource_limits → util
rate_limit → util
network_control → util
```

### No Critical Circular Dependencies

All circular references use lazy imports and are safe.

---

## SIDE EFFECTS ANALYSIS

### File System Writes

| Component | Writes To | Risk |
|-----------|-----------|------|
| store.py | data/spine.db | LOW |
| auth.py | data/auth/*.json | LOW |
| evidence.py | data/evidence/ | LOW |
| voice.py | data/voice/ | LOW |

### Network Calls

| Component | Calls To | Risk |
|-----------|----------|------|
| providers.py | LLM APIs | MEDIUM |
| routing.py | Provider health | LOW |
| websearch.py | SearXNG | LOW |

### Global State Modifications

| Component | Modifies | Risk |
|-----------|----------|------|
| auth.py | _sessions, _overrides, _approvals | MEDIUM |
| feature_flags.py | _flags, _flag_meta | LOW |
| observer.py | _latest | LOW |

---

## RECOMMENDATIONS

### Immediate (Phase 3)

1. Fix resource_limits test isolation
2. Fix voice capability detection
3. Document rate limiter distinction

### Short Term (Phase 4-6)

1. Validate new security module integration
2. Test cache system end-to-end
3. Verify provider normalization

### Long Term (Phase 13)

1. Standardize import style
2. Consider merging shortcuts.py with runtime.py
3. Deprecate unused components

---

## PHASE GATE

```
==================================================
PHASE GATE
==================================================

PHASE: 2

OBJECTIVE ACHIEVED: YES

COMMANDS EXECUTED:
- Dependency analysis ✓
- GOD Object detection ✓
- Duplicate detection ✓
- Hidden state analysis ✓
- Side effects analysis ✓

TESTS: N/A (no changes)

PRE-EXISTING FAILURES: 8 (from Phase 0)

NEW REGRESSIONS: NO

CRITICAL ISSUES:
- P0-001: Circular dependency (mitigated by lazy imports)

BLOCKERS: None

FILES CHANGED: ARCHITECTURE_AUDIT.md (new), PROJECT_STATE.json (updated)

EVIDENCE:
- All components classified
- Dependencies mapped
- Side effects documented
- Recommendations provided

DECISION: PROCEED → PHASE 3

==================================================
```
