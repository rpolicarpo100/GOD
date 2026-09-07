"""Knowledge Router — knowledge graph, learner, auditor, fine memory."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/knowledge-graph")
def knowledge_graph_stats():
    from superai.knowledge_graph import stats, get_user_preferences
    return {"stats": stats(), "preferences": get_user_preferences()}


@router.get("/knowledge-gaps")
def knowledge_gaps():
    from superai.evolution import knowledge_gaps_summary
    return knowledge_gaps_summary()


@router.get("/learner/status")
def learner_status():
    from superai.autonomous_learner import status
    return status()


@router.post("/learner/start")
def learner_start():
    from superai.autonomous_learner import start
    start()
    return {"ok": True, "message": "Autonomous learner started"}


@router.post("/learner/stop")
def learner_stop():
    from superai.autonomous_learner import stop
    stop()
    return {"ok": True, "message": "Autonomous learner stopped"}


@router.get("/idle-worker/status")
def idle_worker_status():
    from superai.idle_worker import status
    return status()


@router.post("/idle-worker/start")
def idle_worker_start():
    from superai.idle_worker import start
    start()
    return {"ok": True}


@router.post("/idle-worker/stop")
def idle_worker_stop():
    from superai.idle_worker import stop
    stop()
    return {"ok": True}


@router.get("/auditor/status")
def auditor_status():
    from superai.knowledge_auditor import status
    return status()


@router.post("/auditor/force")
def auditor_force():
    from superai.knowledge_auditor import force_audit
    return force_audit()


@router.get("/fine-memory")
def fine_memory_list():
    from superai.knowledge_auditor import fine_memory_list
    items = fine_memory_list(50)
    return {"count": len(items), "items": items}


@router.get("/fine-memory/search")
def fine_memory_search(q: str = ""):
    from superai.knowledge_auditor import fine_memory_search
    items = fine_memory_search(q, 10) if q else []
    return {"count": len(items), "items": items}


@router.get("/brain/status")
def brain_status():
    from superai.autonomous_learner import status as learner_status_fn
    from superai.idle_worker import status as idle_status
    from superai.knowledge_auditor import status as auditor_status_fn
    from superai.health import diagnostics
    health = diagnostics()
    learner = learner_status_fn()
    idle = idle_status()
    auditor = auditor_status_fn()
    return {
        "health_pct": health.get("health_pct", 0),
        "health_components": health.get("components", {}),
        "learner": {
            "running": learner.get("running", False),
            "facts_learned": learner.get("learned_facts", 0),
            "cycles": learner.get("cycle_count", 0),
        },
        "idle_worker": {
            "running": idle.get("running", False),
            "tasks_done": idle.get("tasks_done", 0),
            "last_task": idle.get("last_task", {}),
        },
        "auditor": {
            "running": auditor.get("running", False),
            "audits_done": auditor.get("audit_count", 0),
            "fine_memory": auditor.get("fine_memory_count", 0),
        },
    }
