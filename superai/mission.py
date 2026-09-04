"""Mission Engine — objectivos persistentes em SQLite.

Uma missão active de cada vez. Não é Plane. Não é um segundo handle.
"""
from __future__ import annotations

import json
from typing import Any

from .store import store
from .util import now_iso, uid

STATUSES = ("active", "paused", "done", "cancelled")


def init() -> None:
    with store._conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions (
              id TEXT PRIMARY KEY,
              title TEXT,
              goal TEXT,
              status TEXT,
              ts TEXT,
              updated TEXT,
              payload TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
            """
        )


init()


def _row(r) -> dict:
    payload = {}
    try:
        payload = json.loads(r["payload"] or "{}")
    except Exception:
        payload = {}
    return {
        "id": r["id"],
        "title": r["title"],
        "goal": r["goal"],
        "status": r["status"],
        "ts": r["ts"],
        "updated": r["updated"],
        "payload": payload,
    }


def create(goal: str, title: str | None = None) -> dict:
    g = (goal or "").strip()
    if not g:
        return {"ok": False, "error": "goal vazio"}
    t = (title or g[:80]).strip()[:160]
    mid = uid("M")
    ts = now_iso()
    with store._lock, store._conn() as c:
        c.execute("UPDATE missions SET status='paused', updated=? WHERE status='active'", (ts,))
        c.execute(
            "INSERT INTO missions(id,title,goal,status,ts,updated,payload) VALUES(?,?,?,?,?,?,?)",
            (mid, t, g[:2000], "active", ts, ts, "{}"),
        )
    store.audit("user", "mission_create", mid)
    return {"ok": True, **get(mid)}


def get(mid: str) -> dict | None:
    with store._conn() as c:
        r = c.execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
    return _row(r) if r else None


def active() -> dict | None:
    with store._conn() as c:
        r = c.execute("SELECT * FROM missions WHERE status='active' ORDER BY ts DESC LIMIT 1").fetchone()
    return _row(r) if r else None


def list_missions(n: int = 12) -> list[dict]:
    with store._conn() as c:
        rows = c.execute("SELECT * FROM missions ORDER BY ts DESC LIMIT ?", (int(n),)).fetchall()
    return [_row(r) for r in rows]


def set_status(mid: str, status: str) -> dict:
    if status not in STATUSES:
        return {"ok": False, "error": f"status inválido: {status}"}
    ts = now_iso()
    with store._lock, store._conn() as c:
        r = c.execute("SELECT id FROM missions WHERE id=?", (mid,)).fetchone()
        if not r:
            return {"ok": False, "error": "missão inexistente"}
        if status == "active":
            c.execute("UPDATE missions SET status='paused', updated=? WHERE status='active' AND id!=?", (ts, mid))
        c.execute("UPDATE missions SET status=?, updated=? WHERE id=?", (status, ts, mid))
    store.audit("user", "mission_status", f"{mid} {status}")
    m = get(mid)
    return {"ok": True, **(m or {})}


def snapshot() -> dict[str, Any]:
    a = active()
    recent = list_missions(8)
    return {
        "kind": "MEASURED",
        "active": a,
        "recent": recent,
        "n": len(recent),
        "note": "SQLite local. Não é Plane. Uma active de cada vez.",
    }
