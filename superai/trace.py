"""Decision Trace — registo estruturo de decisões operacionais.

Não é um log gigante. É uma cadeia de decisões por request.
Permite reconstruir: WHAT HAPPENED? WHY? WHEN? WHICH PATH?
"""
from __future__ import annotations

import threading
from typing import Any

from .events import bus
from .store import store
from .util import now_iso, uid

_lock = threading.Lock()
_traces: dict[str, list[dict]] = {}  # request_id → [decisions]
_MAX_TRACES = 100
_MAX_DECISIONS_PER_TRACE = 20


def start_trace(request_id: str | None = None) -> str:
    """Inicia um novo trace. Retorna request_id."""
    rid = request_id or uid("req")
    with _lock:
        _traces[rid] = []
        # Evitar crescimento infinito
        if len(_traces) > _MAX_TRACES:
            oldest = sorted(_traces.keys())[:len(_traces) - _MAX_TRACES]
            for k in oldest:
                _traces.pop(k, None)
    return rid


def record_decision(
    request_id: str,
    component: str,
    decision: str,
    reason: str,
    result: str = "pending",
    evidence: dict | None = None,
) -> dict:
    """Regista uma decisão no trace."""
    rec = {
        "id": uid("dec"),
        "request_id": request_id,
        "ts": now_iso(),
        "component": component,
        "decision": decision,
        "reason": reason,
        "result": result,
        "evidence": evidence or {},
    }
    with _lock:
        if request_id not in _traces:
            _traces[request_id] = []
        trace = _traces[request_id]
        if len(trace) < _MAX_DECISIONS_PER_TRACE:
            trace.append(rec)
    # Emitir evento
    bus.emit("DECISION", "INFO", f"{component}: {decision} ({reason})")
    return rec


def get_trace(request_id: str) -> list[dict]:
    """Obtém o trace de um request."""
    with _lock:
        return list(_traces.get(request_id, []))


def recent_traces(n: int = 10) -> list[dict]:
    """Últimos traces."""
    with _lock:
        keys = sorted(_traces.keys(), reverse=True)[:n]
        return [{"request_id": k, "decisions": list(_traces[k])} for k in keys]


def trace_summary(request_id: str) -> dict:
    """Resumo do trace para API."""
    trace = get_trace(request_id)
    if not trace:
        return {
            "request_id": request_id,
            "found": False,
            "kind": "UNKNOWN",
        }
    components = list({d["component"] for d in trace})
    decisions = [{"component": d["component"], "decision": d["decision"], "result": d["result"]} for d in trace]
    return {
        "request_id": request_id,
        "found": True,
        "kind": "MEASURED",
        "n_decisions": len(trace),
        "components": components,
        "decisions": decisions,
        "ts": trace[0]["ts"] if trace else None,
    }


def format_trace(request_id: str) -> str:
    """Formato legível do trace."""
    trace = get_trace(request_id)
    if not trace:
        return f"Trace {request_id}: not found"
    lines = [f"TRACE {request_id}"]
    for d in trace:
        lines.append(f"  {d['ts']} [{d['component']}] {d['decision']} → {d['result']}")
        if d.get("reason"):
            lines.append(f"    reason: {d['reason']}")
    return "\n".join(lines)


# ═══════════════════════════════
# UNIFIED TRACE (P1.5)
# ═══════════════════════════════

def record_auth(
    request_id: str,
    user_id: str | None,
    session_id: str | None,
    action: str,
    permission: str | None = None,
    result: str = "allowed",
    reason: str = "",
) -> dict:
    """Record an authentication/authorization event in trace."""
    return record_decision(
        request_id=request_id,
        component="auth",
        decision=action,
        reason=reason or f"user={user_id} session={session_id}",
        result=result,
        evidence={
            "user_id": user_id,
            "session_id": session_id,
            "permission": permission,
        },
    )


def record_approval(
    request_id: str,
    approval_id: str | None,
    action: str,
    risk_level: int = 0,
    result: str = "pending",
    reason: str = "",
) -> dict:
    """Record an approval event in trace."""
    return record_decision(
        request_id=request_id,
        component="approval",
        decision=action,
        reason=reason or f"risk={risk_level}",
        result=result,
        evidence={
            "approval_id": approval_id,
            "risk_level": risk_level,
        },
    )


def record_evidence(
    request_id: str,
    task_id: str,
    evidence_type: str,
    passed: bool,
    kind: str = "MEASURED",
    details: dict | None = None,
) -> dict:
    """Record an evidence event in trace."""
    return record_decision(
        request_id=request_id,
        component="evidence",
        decision=evidence_type,
        reason=f"task={task_id}",
        result="passed" if passed else "failed",
        evidence={
            "task_id": task_id,
            "evidence_type": evidence_type,
            "passed": passed,
            "kind": kind,
            **(details or {}),
        },
    )


def record_outcome(
    request_id: str,
    task_id: str,
    state: str,
    success: bool,
    confidence: float = 0.0,
    verification: dict | None = None,
) -> dict:
    """Record a task outcome in trace."""
    return record_decision(
        request_id=request_id,
        component="outcome",
        decision="complete" if success else "failed",
        reason=f"state={state} confidence={confidence:.2f}",
        result="verified" if state == "VERIFIED" else state,
        evidence={
            "task_id": task_id,
            "state": state,
            "success": success,
            "confidence": confidence,
            "verification": verification or {},
        },
    )


def full_trace_summary(request_id: str) -> dict:
    """Full trace summary including auth, approval, evidence, outcome."""
    trace = get_trace(request_id)
    if not trace:
        return {"request_id": request_id, "found": False, "kind": "UNKNOWN"}
    
    auth_events = [d for d in trace if d.get("component") == "auth"]
    approval_events = [d for d in trace if d.get("component") == "approval"]
    evidence_events = [d for d in trace if d.get("component") == "evidence"]
    outcome_events = [d for d in trace if d.get("component") == "outcome"]
    
    return {
        "request_id": request_id,
        "found": True,
        "kind": "MEASURED",
        "n_decisions": len(trace),
        "auth": auth_events,
        "approvals": approval_events,
        "evidence": evidence_events,
        "outcomes": outcome_events,
        "ts": trace[0]["ts"] if trace else None,
    }
