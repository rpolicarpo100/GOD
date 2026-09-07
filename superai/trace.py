"""Decision Trace — registo estruturo de decisões operacionais.

Não é um log gigante. É uma cadeia de decisões por request.
Permite reconstruir: WHAT HAPPENED? WHY? WHEN? WHICH PATH?
"""
from __future__ import annotations

import threading

from .events import bus
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
# PROVIDER TELEMETRY (P0)
# ═══════════════════════════════

_metrics_lock = threading.Lock()
_provider_metrics: dict[str, dict] = {}
_system_metrics: dict[str, int] = {
    "requests_total": 0, "requests_success": 0, "requests_error": 0,
    "cache_hits": 0, "cache_misses": 0,
    "tool_calls_total": 0, "tool_calls_success": 0,
    "llm_calls_total": 0, "llm_calls_success": 0,
    "evolution_cycles": 0, "evolution_applied": 0, "evolution_rolled_back": 0,
}


def record_provider_call(
    provider_id: str,
    model: str,
    success: bool,
    latency_ms: float,
    tokens: int = 0,
    error: str | None = None,
    task_type: str = "unknown",
) -> None:
    """Record a provider call for adaptive scoring."""
    with _metrics_lock:
        if provider_id not in _provider_metrics:
            _provider_metrics[provider_id] = {
                "calls": 0, "successes": 0, "failures": 0,
                "latencies": [], "tokens_total": 0, "errors": [],
                "by_task_type": {},
            }
        m = _provider_metrics[provider_id]
        m["calls"] += 1
        if success:
            m["successes"] += 1
        else:
            m["failures"] += 1
            if error:
                m["errors"].append({"ts": now_iso(), "error": error[:200]})
                m["errors"] = m["errors"][-20:]
        m["latencies"].append(latency_ms)
        m["latencies"] = m["latencies"][-100:]
        m["tokens_total"] += tokens
        if task_type not in m["by_task_type"]:
            m["by_task_type"][task_type] = {"calls": 0, "successes": 0, "latencies": []}
        tt = m["by_task_type"][task_type]
        tt["calls"] += 1
        if success:
            tt["successes"] += 1
        tt["latencies"].append(latency_ms)
        tt["latencies"] = tt["latencies"][-50:]
    try:
        from .store import store
        store.mem_put("provider_metrics", provider_id, _provider_metrics[provider_id])
    except Exception:
        pass


def get_provider_score(provider_id: str) -> dict:
    """Get adaptive score for a provider (0-1)."""
    with _metrics_lock:
        m = _provider_metrics.get(provider_id)
    if not m:
        try:
            from .store import store
            stored = store.mem_get("provider_metrics", provider_id)
            if stored:
                with _metrics_lock:
                    _provider_metrics[provider_id] = stored
                m = stored
        except Exception:
            pass
    if not m or m["calls"] == 0:
        return {"score": 0.5, "confidence": 0, "calls": 0, "reason": "no data"}
    sr = m["successes"] / m["calls"]
    lats = m["latencies"]
    p50 = sorted(lats)[len(lats) // 2] if lats else 0
    p95 = sorted(lats)[int(len(lats) * 0.95)] if lats else 0
    score = sr * 0.6 + max(0, 1.0 - (p50 / 10000)) * 0.2
    if len(lats) > 2:
        mean = sum(lats) / len(lats)
        var = sum((l - mean) ** 2 for l in lats) / len(lats)
        score += max(0, 1.0 - (var / 1000000)) * 0.2
    else:
        score += 0.1
    return {
        "score": round(score, 3), "confidence": round(min(m["calls"] / 10, 1.0), 2),
        "calls": m["calls"], "success_rate": round(sr, 3),
        "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
        "tokens_total": m["tokens_total"],
    }


def all_provider_scores() -> dict:
    """Get scores for all known providers."""
    with _metrics_lock:
        ids = list(_provider_metrics.keys())
    scores = {}
    for pid in ids:
        scores[pid] = get_provider_score(pid)
    return scores


def record_system_metric(name: str, value: int = 1) -> None:
    """Increment a system metric."""
    with _metrics_lock:
        _system_metrics[name] = _system_metrics.get(name, 0) + value


def get_system_metrics() -> dict:
    """Get all system metrics."""
    with _metrics_lock:
        return dict(_system_metrics)
