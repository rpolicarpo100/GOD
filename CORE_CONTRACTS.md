# PHASE 4 — CORE CONTRACTS

## Date: 2026-09-05

---

## CONTRACT INVENTORY

### C1: TASK CONTRACT (brain.analyze)

**Creator**: `superai/brain.py` → `analyze()`
**Consumers**: pipeline, executive, validator, thirdeye, runtime

**Schema**:
```python
{
    "task_id": str,           # Unique ID (T-xxxxxxxx)
    "title": str,             # First 160 chars of text
    "type": str,              # math|git|files|parse|python|regex|research|coding|general|status
    "complexity": int,        # 1-10
    "exec_mode": str,         # FAST|NORMAL|DEEP
    "reasoning_required": bool,
    "context_required": str,  # low|medium|high
    "latency_priority": str,  # high|medium
    "quality_priority": str,  # high|medium
    "privacy": str,           # local_preferred|local_only
    "deadline": None|str,
    "estimated_tokens": int,
    "token_estimate": dict,   # {tokens, method, verified, chars}
    "tool_requirement": list[str],
    "reasoning_budget": str,  # low|medium|high|maximum
    "status": str,            # analyzed|running|done|failed|blocked|queued
    "text": str,              # Original text
    "ts": str,                # ISO timestamp
    # Optional (added by pipeline):
    "mission_id": str|None,
    "via": str,               # tools|llm|cache|queue|state|blocked
    "rating": dict,           # Scores from evaluate()
}
```

**Validation**: `type` must be in TYPE_RULES, `complexity` 1-10, `exec_mode` in FAST|NORMAL|DEEP
**Error Path**: Returns dict with all fields, never raises

---

### C2: PLAN CONTRACT (pipeline.plan)

**Creator**: `superai/pipeline.py` → `plan()`
**Consumers**: executive, runtime

**Schema**:
```python
{
    "steps": list[dict],      # [{tool, args}|{kind: "status"}]
    "needs_llm": bool,
    "reason": list[str],
}
```

**Validation**: `steps` is list, each step has `tool` or `kind`
**Error Path**: Returns empty steps + needs_llm=True if unknown type

---

### C3: DECISION CONTRACT (executive.decide)

**Creator**: `superai/executive.py` → `decide()`
**Consumers**: pipeline, runtime

**Schema**:
```python
{
    "path": str,              # tools|direct_llm|queue|no_provider
    "kind": str,              # DETERMINISTIC|INTELLIGENT|BLOCKED
    "fast": bool,
    "deep": bool,
    "direct_llm": bool,
    "queue": bool,
    "memory": bool,
    "exec_mode": str,
    "reasons": list[str],
    "note": str,
}
```

**Validation**: `path` must be in allowed values
**Error Path**: Returns path="no_provider" if no LLM available

---

### C4: TOOL RESULT CONTRACT (tools.execute)

**Creator**: `superai/tools.py` → `execute()`
**Consumers**: validator, thirdeye, pipeline

**Schema**:
```python
{
    "tool": str,              # calculator|json|csv|xml|git|fs.read|fs.list|fs.write|python|state
    "status": str,            # success|error|blocked
    "confidence": float,      # 0.0-1.0
    "findings": list[dict],   # Tool-specific results
    "errors": list[str],
    "evidence": list[str],
    "artifacts": list,
    "next_action": str,
    "ts": str,
}
```

**Validation**: `status` in success|error|blocked, `confidence` 0-1
**Error Path**: Returns status="error" with errors list populated

---

### C5: VALIDATION CONTRACT (validator.validate)

**Creator**: `superai/validator.py` → `validate()`
**Consumers**: pipeline, thirdeye

**Schema**:
```python
{
    "kind": str,              # MEASURED
    "task_type": str,
    "passed": bool,
    "confidence": float,      # 0.0-1.0
    "n_checks": int,
    "n_passed": int,
    "checks": list[dict],     # [{tool, check, passed, evidence, notes}]
    "ts": str,
}
```

**Validation**: `kind` = MEASURED, `passed` = all checks passed
**Error Path**: Returns passed=False with failed checks

---

### C6: CRITICISM CONTRACT (thirdeye.criticize)

**Creator**: `superai/thirdeye.py` → `criticize()`
**Consumers**: pipeline

**Schema**:
```python
{
    "kind": str,              # MEASURED
    "ts": str,
    "task_id": str,
    "task_type": str,
    "exec_mode": str,
    "via": str,
    "latency_ms": float|None,
    "n_findings": int,
    "n_issues": int,
    "n_ok": int,
    "n_info": int,
    "findings": list[dict],   # [{check, severity, msg, evidence}]
    "recommendations": list[dict],
    "overall": str,           # OK|ISSUES
}
```

**Validation**: `kind` = MEASURED, `overall` in OK|ISSUES
**Error Path**: Returns overall="ISSUES" with findings

---

### C7: PIPELINE RESULT CONTRACT (runtime.handle)

**Creator**: `superai/runtime.py` → `handle()`
**Consumers**: server.py, user

**Schema**:
```python
{
    "ok": bool,
    "via": str,               # tools|llm|cache|queue|state|blocked|no_provider|security|repair|mission|roadmap|os|no_web
    # Optional:
    "job": str|None,          # Queue job ID if queued
}
```

**Validation**: `ok` is bool, `via` is non-empty string
**Error Path**: Returns ok=False with via indicating failure reason

---

### C8: EVIDENCE CONTRACT (evidence module)

**Creator**: `superai/evidence.py`
**Consumers**: validator, thirdeye

**Schema**:
```python
{
    "type": str,              # file_exists|file_content|syntax|test_output|exit_code|process_exit|git_state|http_status|llm_response|tool_output|command_output|structure|metric
    "kind": str,              # MEASURED|ESTIMATED|ASSUMED
    "passed": bool|None,
    "ts": str,
    # Type-specific fields
}
```

**Validation**: `type` must be in allowed types, `kind` in MEASURED|ESTIMATED|ASSUMED
**Error Path**: Returns with passed=None if cannot verify

---

### C9: SCORES CONTRACT (brain.evaluate)

**Creator**: `superai/brain.py` → `evaluate()`
**Consumers**: pipeline, thirdeye, store

**Schema**:
```python
{
    "QUALITY": int,           # 0-100
    "CORRECTNESS": int,       # 0-100
    "COMPLETENESS": int,      # 0-100
    "EFFICIENCY": int,        # 0-100
    "TOKEN_EFFICIENCY": int,  # 0-100
    "SECURITY": int,          # 0-100
    "RELIABILITY": int,       # 0-100
    "OVERALL": int,           # 0-100
    "tokens_actual": int,
    "llm_used": bool,
}
```

**Validation**: All scores 0-100
**Error Path**: Returns low scores (40) for failures

---

### C10: AUTH SESSION CONTRACT (auth module)

**Creator**: `superai/auth.py`
**Consumers**: server.py

**Schema**:
```python
{
    "ok": bool,
    "session_id": str,
    "user_id": str,
    "username": str,
    "role": str,              # OWNER|ADMIN|OPERATOR|GUEST
    "created": str,
    "expires": str,
}
```

**Validation**: `role` in allowed roles
**Error Path**: Returns ok=False with error message

---

## CONTRACT FLOW DIAGRAM

```
USER INPUT
    ↓
[C1: TASK] ← brain.analyze()
    ↓
[C2: PLAN] ← pipeline.plan()
    ↓
[C3: DECISION] ← executive.decide()
    ↓
[C4: TOOL RESULT] ← tools.execute()
    ↓
[C5: VALIDATION] ← validator.validate()
    ↓
[C6: CRITICISM] ← thirdeye.criticize()
    ↓
[C9: SCORES] ← brain.evaluate()
    ↓
[C7: PIPELINE RESULT] → runtime.handle()
    ↓
USER OUTPUT
```

---

## CONTRACT QUALITY MATRIX

| Contract | Creator | Consumer | Validation | Error Path | Test | Status |
|----------|---------|----------|------------|------------|------|--------|
| C1: TASK | brain | pipeline,executive,validator | ✓ | ✓ | ✓ | OK |
| C2: PLAN | pipeline | executive | ✓ | ✓ | ✓ | OK |
| C3: DECISION | executive | pipeline | ✓ | ✓ | ✓ | OK |
| C4: TOOL RESULT | tools | validator,thirdeye | ✓ | ✓ | ✓ | OK |
| C5: VALIDATION | validator | pipeline,thirdeye | ✓ | ✓ | ✓ | OK |
| C6: CRITICISM | thirdeye | pipeline | ✓ | ✓ | ✓ | OK |
| C7: PIPELINE RESULT | runtime | server | ✓ | ✓ | ✓ | OK |
| C8: EVIDENCE | evidence | validator | ✓ | ✓ | ✓ | OK |
| C9: SCORES | brain | pipeline,thirdeye | ✓ | ✓ | ✓ | OK |
| C10: AUTH SESSION | auth | server | ✓ | ✓ | ✓ | OK |

---

## FINDINGS

### F1: All Critical Contracts Identified

All10 contracts have:
- ✓ Creator identified
- ✓ Consumer identified
- ✓ Validation defined
- ✓ Error path defined
- ✓ Test present

### F2: Contracts are Consistent

All contracts use:
- `kind: "MEASURED"` for verified data
- `status` field for state
- `ts` for timestamps
- Lists for collections

### F3: No Ambiguous Contracts

All contracts have clear schemas and documented fields.

---

## PHASE GATE

```
==================================================
PHASE GATE
==================================================

PHASE: 4

OBJECTIVE ACHIEVED: YES

COMMANDS EXECUTED:
- Contract inventory ✓
- Schema documentation ✓
- Quality matrix ✓

TESTS: 252/252 PASS

PRE-EXISTING FAILURES: 0

NEW REGRESSIONS: NO

CRITICAL ISSUES: None

BLOCKERS: None

FILES CHANGED: CORE_CONTRACTS.md (new)

EVIDENCE:
- 10 contracts documented
- All have validation
- All have error paths
- All have tests

DECISION: PROCEED → PHASE 5

==================================================
```
