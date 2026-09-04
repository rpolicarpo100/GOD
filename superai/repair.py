"""Repair — diagnósticos e correcções MEASURED. Não é um segundo GOD."""
from __future__ import annotations

from . import compute, gods, queue as tq
from .compute import LOCAL_ID
from .config import DATA
from .memory_vec import vectors
from .store import store
from .tools import PROJECTS
from .util import now_iso


def run() -> dict:
    actions: list[dict] = []

    n = tq.recover_local(LOCAL_ID)
    actions.append({"check": "queue_recover", "ok": True, "n": n, "kind": "MEASURED"})
    compute.start_local_worker()
    alive = any(w.get("alive") and w.get("id") == LOCAL_ID for w in tq.list_workers())
    actions.append({"check": "worker", "ok": alive, "id": LOCAL_ID, "kind": "MEASURED"})

    qh = vectors.health()
    actions.append(
        {
            "check": "qdrant",
            "ok": bool(qh.get("available")),
            "error": qh.get("error"),
            "fix": None if qh.get("available") else "lock de outro processo — não apago .lock à força",
            "kind": "MEASURED",
        }
    )

    gods.ensure()
    actions.append({"check": "gods_master", "ok": gods.get("master") is not None, "kind": "MEASURED"})

    PROJECTS.mkdir(parents=True, exist_ok=True)
    actions.append({"check": "projects", "ok": PROJECTS.is_dir(), "kind": "MEASURED"})

    try:
        u = store.usage()
        actions.append({"check": "sqlite", "ok": True, "keys": sorted(u)[:8], "kind": "MEASURED"})
    except Exception as e:
        actions.append({"check": "sqlite", "ok": False, "error": str(e)[:200], "kind": "MEASURED"})

    db = DATA / "spine.db"
    actions.append({"check": "spine_db", "ok": db.is_file(), "kind": "MEASURED"})

    ok = all(a.get("ok") for a in actions)
    return {
        "kind": "MEASURED",
        "ok": ok,
        "ts": now_iso(),
        "actions": actions,
        "note": "não repara providers remotos nem inventa SearXNG/preços",
    }
