"""Health & Readiness — verificações reais de estado.

HEALTH: O processo está funcional?
READINESS: Está pronto para aceitar trabalho?
DIAGNOSTICS: Que componentes estão disponíveis? Que falhou? Porquê?
"""
from __future__ import annotations


from . import observer, providers, queue as tq, resources, routing
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

    # Providers — count as ONE component (at least 1 provider up = ok)
    health = providers.health_all()
    any_provider_up = any(p.get("available") for p in health)
    providers_up = [p["id"] for p in health if p.get("available")]
    providers_down = [p["id"] for p in health if not p.get("available")]
    components.append({
        "name": "providers",
        "status": "ok" if any_provider_up else "down",
        "weight": 30,
        "n_available": len(providers_up),
        "n_total": len(health),
        "available": providers_up,
        "down": providers_down,
        "error": None if any_provider_up else "Adiciona API keys ao ficheiro .env (GROQ_API_KEY, GEMINI_API_KEY, etc.)",
        "actionable": not any_provider_up,
    })

    # Gateway
    gw = routing.health()
    components.append({
        "name": "gateway:omniroute",
        "status": "ok" if gw["omniroute"]["available"] else "optional",
        "weight": 0,
        "optional": True,
        "error": gw["omniroute"].get("error"),
        "actionable": False,
    })
    components.append({
        "name": "gateway:direct",
        "status": "ok" if gw["direct"]["available"] else "down",
        "weight": 20,
        "error": None if gw["direct"]["available"] else "Nenhum provider disponível — verifica API keys no .env",
        "actionable": not gw["direct"]["available"],
    })

    # SQLite
    try:
        from .store import store as _store
        with _store._lock, _store._conn() as c:
            c.execute("SELECT 1")
        components.append({
            "name": "sqlite",
            "status": "ok",
            "weight": 15,
            "actionable": False,
        })
    except Exception as e:
        components.append({
            "name": "sqlite",
            "status": "down",
            "weight": 15,
            "error": str(e),
            "actionable": True,
        })

    # Embeddings
    try:
        from .embed import info as embed_info
        ei = embed_info()
        components.append({
            "name": "embeddings",
            "status": "ok",
            "weight": 10,
            "method": ei.get("method", ""),
            "neural": ei.get("neural", False),
            "actionable": False,
        })
    except Exception:
        components.append({
            "name": "embeddings",
            "status": "down",
            "weight": 10,
            "error": "Embedding system unavailable",
            "actionable": True,
        })

    # Autonomous learner
    try:
        from .autonomous_learner import status as learner_status
        ls = learner_status()
        components.append({
            "name": "learner",
            "status": "ok" if ls.get("running") else "down",
            "weight": 5,
            "cycles": ls.get("cycle_count", 0),
            "actionable": not ls.get("running"),
        })
    except Exception:
        pass

    # News connector
    try:
        from .news_connector import health as news_health
        nh = news_health()
        components.append({
            "name": "news_api",
            "status": "ok" if nh.get("available") else "down",
            "weight": 5,
            "events": nh.get("total_events", 0),
            "actionable": not nh.get("available"),
        })
    except Exception:
        pass

    # Qdrant
    qh = vectors.health()
    components.append({
        "name": "qdrant",
        "status": "ok" if qh.get("available") else "down",
        "weight": 15,
        "error": qh.get("error"),
        "actionable": not qh.get("available"),
    })

    # Workers — optional in single-process mode
    workers = tq.list_workers()
    for w in workers:
        components.append({
            "name": f"worker:{w['id']}",
            "status": "ok" if w.get("alive") else "optional",
            "weight": 5,
            "optional": True,
            "last_seen_s": w.get("last_seen_s"),
            "actionable": False,
        })

    # Observer alerts — informational only, no weight
    eye = observer.latest()
    for a in (eye.get("alerts") or []):
        components.append({
            "name": f"alert:{a['code']}",
            "status": "alert",
            "weight": 0,
            "level": a.get("level"),
            "msg": a.get("msg"),
            "actionable": False,
        })

    # Score: only count infrastructure, not alerts
    infra = [c for c in components if c["status"] != "alert"]
    # Weighted health score
    weighted_components = [c for c in components if c.get("weight", 0) > 0]
    total_weight = sum(c.get("weight", 0) for c in weighted_components)
    ok_weight = sum(c.get("weight", 0) for c in weighted_components if c["status"] == "ok")
    health_pct = round(ok_weight / max(total_weight, 1) * 100) if total_weight > 0 else 0

    # Score: only count infrastructure, not alerts
    infra = [c for c in components if c["status"] != "alert"]
    n_ok = sum(1 for c in infra if c["status"] == "ok")
    n_down = sum(1 for c in infra if c["status"] in ("down", "dead", "optional"))
    n_alert = sum(1 for c in components if c["status"] == "alert")

    return {
        "kind": "MEASURED",
        "ts": now_iso(),
        "n_components": len(components),
        "n_ok": n_ok,
        "n_down": n_down,
        "n_alert": n_alert,
        "health_pct": health_pct,
        "total_weight": total_weight,
        "ok_weight": ok_weight,
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
