"""Health & Readiness — verificações reais de estado.

HEALTH: O processo está funcional?
READINESS: Está pronto para aceitar trabalho?
DIAGNOSTICS: Que componentes estão disponíveis? Que falhou? Porquê?
"""
from __future__ import annotations

from typing import Any

from . import aios, observer, providers, queue as tq, resources, routing
from .events import bus
from .memory_vec import vectors
from .store import store
from .util import now_iso


def liveness() -> dict:
    """HEALTH: O processo está funcional?"""
    eye = observer.latest()
    ok = eye.get("ok", True)
    h = resources.host()
    return {
        "status": "healthy" if ok else "unhealthy",
        "ok": ok,
        "ts": now_iso(),
        "kind": "MEASURED",
    }


def readiness() -> dict:
    """READINESS: Está pronto para aceitar trabalho?"""
    checks = []
    all_ok = True

    # 1. SQLite
    try:
        store.usage()
        checks.append({"name": "sqlite", "ok": True})
    except Exception as e:
        checks.append({"name": "sqlite", "ok": False, "error": str(e)[:100]})
        all_ok = False

    # 2. Worker
    workers = tq.list_workers()
    alive = [w for w in workers if w.get("alive")]
    worker_ok = len(alive) > 0
    checks.append({"name": "worker", "ok": worker_ok, "n_alive": len(alive)})
    if not worker_ok:
        all_ok = False

    # 3. Queue capacity
    stats = tq.stats()
    queued = stats.get("queued", 0) + stats.get("assigned", 0) + stats.get("running", 0)
    cap_ok = queued < 20  # não aceitar mais se fila > 20
    checks.append({"name": "queue_capacity", "ok": cap_ok, "queued": queued})
    if not cap_ok:
        all_ok = False

    # 4. Memory pressure
    h = resources.host()
    pressure_ok = h.get("pressure") != "high"
    checks.append({"name": "memory_pressure", "ok": pressure_ok, "pressure": h.get("pressure")})
    if not pressure_ok:
        all_ok = False

    return {
        "status": "ready" if all_ok else "not_ready",
        "ok": all_ok,
        "checks": checks,
        "ts": now_iso(),
        "kind": "MEASURED",
    }


def diagnostics() -> dict:
    """DIAGNOSTICS: Componentes disponíveis, falhados, porquê."""
    components = []

    # Providers
    health = providers.health_all()
    for p in health:
        components.append({
            "name": f"provider:{p['id']}",
            "status": "ok" if p.get("available") else "down",
            "error": p.get("error"),
        })

    # Gateway
    gw = routing.health()
    components.append({
        "name": "gateway:omniroute",
        "status": "ok" if gw["omniroute"]["available"] else "down",
        "error": gw["omniroute"].get("error"),
    })
    components.append({
        "name": "gateway:direct",
        "status": "ok" if gw["direct"]["available"] else "down",
        "error": gw["direct"].get("error"),
    })

    # Qdrant
    qh = vectors.health()
    components.append({
        "name": "qdrant",
        "status": "ok" if qh.get("available") else "down",
        "error": qh.get("error"),
    })

    # Workers
    workers = tq.list_workers()
    for w in workers:
        components.append({
            "name": f"worker:{w['id']}",
            "status": "ok" if w.get("alive") else "dead",
            "last_seen_s": w.get("last_seen_s"),
        })

    # Observer
    eye = observer.latest()
    for a in (eye.get("alerts") or []):
        components.append({
            "name": f"alert:{a['code']}",
            "status": "alert",
            "level": a.get("level"),
            "msg": a.get("msg"),
        })

    n_ok = sum(1 for c in components if c["status"] == "ok")
    n_down = sum(1 for c in components if c["status"] in ("down", "dead"))
    n_alert = sum(1 for c in components if c["status"] == "alert")

    return {
        "kind": "MEASURED",
        "ts": now_iso(),
        "n_components": len(components),
        "n_ok": n_ok,
        "n_down": n_down,
        "n_alert": n_alert,
        "components": components,
    }


def full_health() -> dict:
    """Health completo para API."""
    return {
        "liveness": liveness(),
        "readiness": readiness(),
        "diagnostics": diagnostics(),
        "ts": now_iso(),
    }
