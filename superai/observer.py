"""Terceiro olho — métricas e alertas reais. Edge-triggered. Sem invenção."""
from __future__ import annotations

import json
import threading
import time

from . import queue as tq, tokens as ti
from .events import bus
from .resources import host
from .store import store
from .util import now_iso

_lock = threading.Lock()
_last_codes: set[str] = set()
_latest: dict = {"ok": True, "alerts": [], "metrics": {}, "ts": None}


def _ratings(n: int = 40) -> list[dict]:
    with store._conn() as c:
        rows = c.execute("SELECT scores FROM ratings ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["scores"]))
        except Exception:
            pass
    return out


def inspect() -> dict:
    h = host()
    q = tq.stats()
    workers = tq.list_workers()
    dead = [w for w in workers if not w.get("alive")]
    alive = [w for w in workers if w.get("alive")]
    cache = store.cache_stats()
    usage = store.usage()
    tasks = store.tasks(80)
    blocked = sum(1 for t in tasks if t.get("via") == "no_provider")
    queued_n = q.get("queued", 0) + q.get("assigned", 0) + q.get("running", 0)
    failed = q.get("failed", 0)
    done = q.get("completed", 0)
    rats = _ratings()
    overalls = [r.get("OVERALL") for r in rats if isinstance(r.get("OVERALL"), (int, float))]
    toks = sum(int(r.get("tokens_actual") or 0) for r in rats)
    avg_q = round(sum(overalls) / len(overalls), 1) if overalls else None
    uwpt = None
    if toks > 0 and overalls:
        uwpt = round(sum(overalls) / toks, 4)
    elif toks == 0 and overalls:
        uwpt = None  # trabalho útil sem tokens LLM — correcto, não é ∞ inventado

    alerts = []
    if h.get("pressure") == "high":
        alerts.append({"level": "WARNING", "code": "PC_OVERLOAD", "msg": "pressão de CPU/RAM no control plane", "evidence": h})
    if queued_n >= 8:
        alerts.append({"level": "WARNING", "code": "QUEUE_BACKUP", "msg": f"fila profunda ({queued_n})", "evidence": q})
    if dead:
        alerts.append({"level": "NOTICE", "code": "DEAD_WORKER", "msg": f"{len(dead)} worker(s) sem heartbeat", "evidence": [w["id"] for w in dead]})
    if not alive:
        alerts.append({"level": "CRITICAL", "code": "NO_WORKER", "msg": "nenhum worker vivo", "evidence": []})
    hr = cache.get("hit_rate")
    if hr is not None and cache.get("misses", 0) >= 8 and hr < 0.15:
        alerts.append({"level": "NOTICE", "code": "CACHE_COLD", "msg": f"hit-rate {hr:.2f} com {cache['misses']} misses", "evidence": cache})
    if blocked >= 3:
        alerts.append({"level": "NOTICE", "code": "PROVIDER_GAP", "msg": f"{blocked} tarefas bloqueadas sem LLM — gap de provider, não de qualidade de código", "evidence": {"blocked": blocked}})
    if avg_q is not None and avg_q < 50 and len(overalls) >= 5:
        alerts.append({"level": "WARNING", "code": "QUALITY_DROP", "msg": f"overall médio {avg_q} nas últimas {len(overalls)}", "evidence": {"n": len(overalls)}})
    if failed >= 3 and done and failed / max(1, failed + done) > 0.3:
        alerts.append({"level": "WARNING", "code": "FAIL_RATE", "msg": f"falhas de fila {failed}/{failed+done}", "evidence": q})
    bud = ti.budget_status()
    if bud["daily"]["hard"] or bud["session"]["hard"]:
        alerts.append({"level": "CRITICAL", "code": "TOKEN_BUDGET_EXCEEDED", "msg": "budget hard MEASURED", "evidence": bud})
    elif bud["daily"]["soft"] or bud["session"]["soft"]:
        alerts.append({"level": "WARNING", "code": "TOKEN_BUDGET_WARNING", "msg": "budget ≥80% MEASURED", "evidence": {"daily": bud["daily"], "session": bud["session"]}})

    ok = not any(a["level"] in ("CRITICAL", "SECURITY") for a in alerts)
    metrics = {
        "cpu_load1": h.get("load1"),
        "ram_avail_mb": h.get("ram_avail_mb"),
        "pressure": h.get("pressure"),
        "gpu_required": False,
        "gpu_present": (h.get("gpu") or {}).get("present"),
        "queue_depth": queued_n,
        "workers_alive": len(alive),
        "workers_dead": len(dead),
        "cache_hit_rate": hr,
        "llm_calls": usage.get("llm_calls", 0),
        "tool_calls": usage.get("tool_calls", 0),
        "blocked_no_provider": blocked,
        "avg_overall": avg_q,
        "rating_n": len(overalls),
        "tokens_in_ratings": toks,
        "useful_work_per_token": uwpt,
        "claude_dependency": None if not usage.get("llm_calls") else 0.0,
        "token_actual_sum": ti.usage_summary().get("sum_actual"),
        "token_cost_kind": ti.pricing().get("kind"),
        "token_forecast": ti.forecast().get("status"),
    }
    for a in (ti.anomalies().get("alerts") or []):
        alerts.append({"level": a.get("level") or "WARNING", "code": a["code"], "msg": a["msg"], "evidence": a})
    return {"ok": ok, "alerts": alerts, "metrics": metrics, "ts": now_iso()}


def tick() -> dict:
    """Edge-triggered: só emite evento quando o conjunto de códigos muda."""
    global _latest
    snap = inspect()
    codes = {a["code"] for a in snap["alerts"]}
    with _lock:
        appeared = codes - _last_codes
        cleared = _last_codes - codes
        _last_codes.clear()
        _last_codes.update(codes)
        _latest = snap
    for a in snap["alerts"]:
        if a["code"] in appeared:
            bus.emit(a["code"], a["level"], a["msg"])
    if cleared:
        bus.emit("QUALITY_IMPROVEMENT", "INFO", f"alertas resolvidos: {sorted(cleared)}")
    return snap


def latest() -> dict:
    with _lock:
        return dict(_latest) if _latest.get("ts") else inspect()


_started = False


def running() -> bool:
    return _started


def start(interval: float = 15.0) -> None:
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                tq.prune()
                tq.requeue_orphans()
                tq.expire_stale()
                tick()
            except Exception:
                pass
            time.sleep(interval)

    threading.Thread(target=loop, name="superai-eye", daemon=True).start()
