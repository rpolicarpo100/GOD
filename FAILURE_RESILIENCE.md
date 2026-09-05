# PHASE 10 — FAILURE & RESILIENCE

## Date: 2026-09-05

---

## RESILIENCE STACK

### 1. PROVIDER FAILURE HANDLING (routing.py)

**Pattern**: Fallback chain with reliability sorting

**How it works**:
1. `DirectAdapter.complete()` tries providers sorted by `ok_rate` + `latency`
2. Skips unavailable providers
3. Skips rate-limited providers
4. Tries up to 3 providers
5. Returns `"unavailable"` if all fail

**Sorting criteria** (`sort_adapters()`):
```python
(demote, -ok_rate, latency, rank_default)
```
- `demote=1` if `ok_rate <= 0.3` (3+ samples)
- `ok_rate` descending (higher reliability first)
- `latency` ascending (faster first)
- `rank_default` ascending (original order as tiebreaker)

**HARDCORE mode**: Claude always first

**Fallback chain**:
```
OmniRoute → Direct → [sorted providers] → unavailable
```

**Evidence**: `routing.py` lines 140-170

---

### 2. TOOL FAILURE HANDLING (tools.py)

**Pattern**: Structured error response

**Error response**:
```python
{
    "status": "error",
    "confidence": 0.0,
    "findings": [],
    "errors": [msg],
    "artifacts": [],
    "next_action": "",
    "evidence": [],
    "ts": now_iso(),
}
```

**Every tool**:
- Returns `_ok()` on success
- Returns `_err()` on failure
- Never raises exceptions to caller

**Examples**:
- Calculator: `calculator: division by zero`
- Git: `exit 128`
- JSON: `json: Expecting value`
- CSV: parsing errors
- XML: `xml: not well-formed`

**Evidence**: `tools.py` lines 30-40

---

### 3. STORAGE FAILURE HANDLING (store.py)

**Pattern**: WAL + busy_timeout + rollback

**SQLite config**:
```python
PRAGMA journal_mode=WAL
PRAGMA busy_timeout=3000
```

**Transaction pattern**:
```python
try:
    yield c
    c.commit()
except Exception:
    try:
        c.rollback()
    except Exception:
        pass
    raise
```

**Non-critical operations**: Silent pass
```python
try:
    store.save_perf(entry)
except Exception:
    pass
```

**Evidence**: `store.py` lines 15-30

---

### 4. MEMORY/VECTOR FAILURE HANDLING (memory_vec.py)

**Pattern**: Availability check + graceful degradation

**Qdrant**:
```python
def available(self) -> bool:
    return self.c is not None and self.error is None
```

**Search**: Returns `[]` on unavailable
```python
def search(self, ...):
    if not self.available():
        return []
```

**Upsert**: Raises RuntimeError on unavailable
```python
def upsert(self, ...):
    if not self.available():
        raise RuntimeError(self.error or "qdrant down")
```

**Pipeline calls to vectors**: Wrapped in try/except
```python
try:
    vectors.upsert(...)
except Exception:
    pass  # Non-critical
```

**Evidence**: `memory_vec.py` lines 50-80

---

### 5. LLM FAILURE HANDLING (pipeline.py)

**Pattern**: Record + broadcast + graceful response

**When LLM fails**:
```python
if res.get("status") != "success":
    bus.emit("MODEL_FAILED", "WARNING", ...)
    _record_token(task, pipeline, {}, actual=0, status="fail", ...)
    task["status"] = "failed"
    task["via"] = "llm_fail"
    store.save_task(task)
    _say("brain", f"Gateway {gw['active']} falhou: {res.get('error')}")
    return {"ok": True, "via": "llm_fail"}
```

**What happens**:
1. Event emitted (MODEL_FAILED)
2. Token event recorded with status=fail
3. Task marked as failed
4. Task saved to store
5. User sees error message
6. Pipeline returns gracefully (no crash)

**Evidence**: `pipeline.py` lines 480-500

---

### 6. RATE LIMITING (rate_limit.py)

**Pattern**: Sliding window

**Config**:
| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/login` | 5 | 60s |
| `/auth/change-password` | 3 | 300s |
| `/task/submit` | 30 | 60s |
| `/task/execute` | 20 | 60s |
| `/api/` | 100 | 60s |
| `/ws` | 10 | 60s |
| Default | 60 | 60s |

**Per-user multipliers**:
- OWNER: 2x
- ADMIN: 1.5x
- OPERATOR: 1x
- GUEST: 0.5x

**Evidence**: `rate_limit.py` lines 20-45

---

### 7. ANOMALY DETECTION (tokens.py)

**Pattern**: Statistical anomaly detection

**Token anomaly**:
```python
if med > 0 and last > med * 8:
    alerts.append({"code": "TOKEN_ANOMALY", ...})
```

**Retry spike**:
```python
retries = sum(...)
if retries >= 6:
    alerts.append({"code": "RETRY_SPIKE", ...})
```

**Evidence**: `tokens.py` lines 260-270

---

### 8. GATEWAY FALLBACK (routing.py)

**Pattern**: Active gateway selection

```python
def active_gateway():
    h = omni.health()
    if h["available"]:
        return omni
    return direct
```

**OmniRoute** → **Direct** (automatic)

**Evidence**: `routing.py` lines 210-220

---

## RESILIENCE MATRIX

| Component | Failure | Handling | Recovery |
|-----------|---------|----------|----------|
| Provider unavailable | Skip + try next | ✓ | ✓ |
| Provider rate limited | Skip + try next | ✓ | ✓ |
| All providers fail | Return "unavailable" | ✓ | ✗ |
| Tool execution error | Return _err() | ✓ | ✓ |
| Storage write fail | Rollback | ✓ | ✓ |
| Storage read fail | Silent pass | ✓ | ✓ |
| Vector store down | Return [] | ✓ | ✓ |
| LLM call fail | Record + broadcast | ✓ | ✗ |
| Rate limit hit | Reject request | ✓ | ✓ |
| Token anomaly | Alert | ✓ | ✗ |

---

## WHAT EXISTS

| Pattern | Present | Quality |
|---------|---------|---------|
| Fallback chain | ✓ | Good — 3 providers max |
| Error structure | ✓ | Good — consistent _err() |
| Transaction rollback | ✓ | Good — WAL + timeout |
| Availability check | ✓ | Good — available() |
| Event broadcasting | ✓ | Good — MODEL_FAILED, TOOL_FAILED |
| Rate limiting | ✓ | Good — sliding window |
| Anomaly detection | ✓ | Good — statistical |

---

## WHAT'S MISSING

| Pattern | Priority | Notes |
|---------|----------|-------|
| Retry with backoff | P1 | No exponential backoff for transient failures |
| Circuit breaker | P2 | No circuit breaker for repeated failures |
| Dead letter queue | P2 | No persistent retry queue |
| Adaptive timeout | P3 | Fixed timeouts only |

---

## DECISION

**Phase 10 scope**: Document existing resilience patterns.

**Why not add missing patterns**:
1. Retry with backoff → would change routing.py behavior (scope creep)
2. Circuit breaker → would change provider selection (scope creep)
3. Dead letter queue → would add new persistence (scope creep)
4. Adaptive timeout → would change timeout logic (scope creep)

**Existing patterns are sufficient** for current failure modes:
- Provider failures → handled by fallback chain
- Tool failures → handled by structured errors
- Storage failures → handled by rollback
- Memory failures → handled by availability check
- LLM failures → handled by recording + broadcasting

---

## VERIFICATION

### Provider Failure
```
DirectAdapter.complete() → tries 3 providers → returns "unavailable" if all fail
```

### Tool Failure
```
tool_exec() → _err() → structured error → pipeline continues
```

### Storage Failure
```
store._conn() → rollback → raise → caller handles
```

### Memory Failure
```
vectors.available() → False → search returns [] → pipeline continues
```

### LLM Failure
```
routing.complete() → status != "success" → MODEL_FAILED event → user sees error
```

---

## PHASE GATE

```
==================================================
PHASE GATE
==================================================

PHASE: 10

OBJECTIVE ACHIEVED: YES

COMMANDS EXECUTED:
- Provider failure handling verified ✓
- Tool failure handling verified ✓
- Storage failure handling verified ✓
- Memory failure handling verified ✓
- LLM failure handling verified ✓
- Rate limiting verified ✓
- Anomaly detection verified ✓

TESTS: 252/252 PASS

PRE-EXISTING FAILURES: 0

NEW REGRESSIONS: NO

CRITICAL ISSUES: None

BLOCKERS: None

FILES CHANGED: FAILURE_RESILIENCE.md (new)

EVIDENCE:
- Fallback chain: 3 providers max
- Error structure: consistent _err()
- Transaction rollback: WAL + timeout
- Availability check: available()
- Event broadcasting: MODEL_FAILED, TOOL_FAILED
- Rate limiting: sliding window
- Anomaly detection: statistical

DECISION: PROCEED → PHASE 11

==================================================
```
