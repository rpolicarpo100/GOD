"""Distributed task queue + worker registry (SQLite). Workers are replaceable."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .events import bus
from .store import store
from .util import now_iso, uid

HEARTBEAT_TTL = 20.0
_away: list[dict] = []
_lock = threading.Lock()


def init() -> None:
    with store._conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              kind TEXT,
              status TEXT,
              text TEXT,
              payload TEXT,
              result TEXT,
              worker_id TEXT,
              location TEXT,
              error TEXT,
              ts TEXT,
              updated TEXT
            );
            CREATE TABLE IF NOT EXISTS workers (
              id TEXT PRIMARY KEY,
              name TEXT,
              location TEXT,
              capabilities TEXT,
              last_seen REAL,
              cpu TEXT,
              ram TEXT,
              status TEXT,
              meta TEXT
            );
            """
        )
        cols = [row[1] for row in c.execute("PRAGMA table_info(jobs)")]
        if "priority" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0")
        if "parent_id" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN parent_id TEXT")
        if "mission_id" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN mission_id TEXT")


init()


def enqueue(
    kind: str,
    text: str,
    payload: dict | None = None,
    location: str = "LOCAL_WORKER",
    priority: int = 0,
    parent_id: str | None = None,
    mission_id: str | None = None,
) -> dict:
    from .util import normalize_query

    norm = normalize_query(text) or text
    with store._lock, store._conn() as c:
        rows = c.execute(
            "SELECT * FROM jobs WHERE kind=? AND status IN ('queued','assigned','running')",
            (kind,),
        ).fetchall()
        found = None
        for r in rows:
            if (normalize_query(r["text"] or "") or r["text"]) == norm:
                found = _job_row(r)
                found["deduped"] = True
                break
        if found:
            job = found
        else:
            prio = max(-10, min(10, int(priority or 0)))
            job = {
                "id": uid("J"),
                "kind": kind,
                "status": "queued",
                "text": text,
                "payload": payload or {},
                "result": None,
                "worker_id": None,
                "location": location,
                "error": None,
                "ts": now_iso(),
                "updated": now_iso(),
                "priority": prio,
                "parent_id": parent_id,
                "mission_id": mission_id,
            }
            c.execute(
                "INSERT INTO jobs(id,kind,status,text,payload,result,worker_id,location,error,ts,updated,priority,parent_id,mission_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job["id"],
                    job["kind"],
                    job["status"],
                    job["text"],
                    json.dumps(job["payload"], ensure_ascii=False),
                    None,
                    None,
                    job["location"],
                    None,
                    job["ts"],
                    job["updated"],
                    job["priority"],
                    job["parent_id"],
                    job["mission_id"],
                ),
            )
    if job.get("deduped"):
        bus.emit("CACHE_HIT", "INFO", f"queue dedup {job['id']} kind={kind}")
    else:
        bus.emit("TASK_CREATED", "INFO", f"queue {job['id']} kind={kind} loc={location}")
    return job


def worker_inflight(wid: str) -> int:
    with store._conn() as c:
        n = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status IN ('assigned','running')",
            (wid,),
        ).fetchone()[0]
    return int(n)


def job_is_ready(job: dict) -> bool:
    """Filho espera o pai. Sem DAG. Sem paralelismo fingido."""
    pid = job.get("parent_id") if job else None
    if not pid:
        return True
    parent = get_job(pid)
    if not parent:
        return True
    return parent.get("status") in ("completed", "failed", "killed")


def claim(worker_id: str) -> dict | None:
    from .resources import inflight_cap

    cap = int((inflight_cap() or {}).get("applied") or 1)
    with store._lock, store._conn() as c:
        # Check inflight inside the same lock+connection to avoid WAL race
        n = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE worker_id=? AND status IN ('assigned','running')",
            (worker_id,),
        ).fetchone()[0]
        if int(n) >= cap:
            return None
        rows = c.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY COALESCE(priority,0) DESC, ts ASC LIMIT 20"
        ).fetchall()
        r = None
        for cand in rows:
            pid = cand["parent_id"] if "parent_id" in cand.keys() else None
            if pid:
                parent = c.execute("SELECT status FROM jobs WHERE id=?", (pid,)).fetchone()
                if parent and parent["status"] not in ("completed", "failed", "killed"):
                    continue
            r = cand
            break
        if not r:
            return None
        c.execute(
            "UPDATE jobs SET status='assigned', worker_id=?, updated=? WHERE id=?",
            (worker_id, now_iso(), r["id"]),
        )
    bus.emit("TASK_STARTED", "INFO", f"{r['id']} assigned {worker_id}")
    return _job_row(r, status="assigned", worker_id=worker_id)


def start_run(jid: str) -> None:
    with store._lock, store._conn() as c:
        c.execute("UPDATE jobs SET status='running', updated=? WHERE id=?", (now_iso(), jid))


def complete(jid: str, result: Any) -> None:
    with store._lock, store._conn() as c:
        c.execute(
            "UPDATE jobs SET status='completed', result=?, updated=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False, default=str)[:20000], now_iso(), jid),
        )
    bus.emit("TASK_COMPLETED", "INFO", f"queue {jid} completed")
    _note_away(jid, "completed")


def fail(jid: str, error: str) -> None:
    with store._lock, store._conn() as c:
        c.execute(
            "UPDATE jobs SET status='failed', error=?, updated=? WHERE id=?",
            (error[:2000], now_iso(), jid),
        )
    bus.emit("TASK_FAILED", "WARNING", f"queue {jid} {error[:120]}")
    _note_away(jid, "failed")


def _note_away(jid: str, status: str) -> None:
    if bus._subs:
        return
    with _lock:
        _away.append({"id": jid, "status": status, "ts": now_iso()})
        del _away[:-50]


def peek_away() -> list[dict]:
    with _lock:
        return list(_away)


def jobs(n: int = 30) -> list[dict]:
    with store._conn() as c:
        rows = c.execute("SELECT * FROM jobs ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
    return [_job_row(r) for r in rows]


def stats() -> dict:
    with store._conn() as c:
        rows = c.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
    d = {r["status"]: r["n"] for r in rows}
    return {
        "queued": d.get("queued", 0),
        "assigned": d.get("assigned", 0),
        "running": d.get("running", 0),
        "completed": d.get("completed", 0),
        "failed": d.get("failed", 0),
        "killed": d.get("killed", 0),
    }


def _job_row(r, **over) -> dict:
    def j(x):
        if not x:
            return None
        try:
            return json.loads(x)
        except Exception:
            return x

    d = {
        "id": r["id"],
        "kind": r["kind"],
        "status": r["status"],
        "text": r["text"],
        "payload": j(r["payload"]) if "payload" in r.keys() else None,
        "result": j(r["result"]) if "result" in r.keys() else None,
        "worker_id": r["worker_id"],
        "location": r["location"],
        "error": r["error"] if "error" in r.keys() else None,
        "ts": r["ts"],
        "updated": r["updated"] if "updated" in r.keys() else None,
        "priority": int(r["priority"] or 0) if "priority" in r.keys() else 0,
        "parent_id": r["parent_id"] if "parent_id" in r.keys() else None,
        "mission_id": r["mission_id"] if "mission_id" in r.keys() else None,
    }
    d.update(over)
    return d


def get_job(jid: str) -> dict | None:
    with store._conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    return _job_row(r) if r else None


def last_open(mission_id: str | None = None) -> dict | None:
    with store._conn() as c:
        if mission_id:
            r = c.execute(
                "SELECT * FROM jobs WHERE mission_id=? AND status IN ('queued','assigned','running') ORDER BY ts DESC LIMIT 1",
                (mission_id,),
            ).fetchone()
        else:
            r = c.execute(
                "SELECT * FROM jobs WHERE status IN ('queued','assigned','running') ORDER BY ts DESC LIMIT 1"
            ).fetchone()
    return _job_row(r) if r else None


def last_job() -> dict | None:
    with store._conn() as c:
        r = c.execute("SELECT * FROM jobs ORDER BY ts DESC LIMIT 1").fetchone()
    return _job_row(r) if r else None


def graph(n: int = 20) -> dict:
    items = jobs(n)
    edges = [{"from": j["parent_id"], "to": j["id"]} for j in items if j.get("parent_id")]
    from .resources import inflight_cap
    cap = inflight_cap()
    return {
        "kind": "MEASURED",
        "n": len(items),
        "edges": edges,
        "parallel": cap["applied"] > 1,
        "inflight_applied": cap["applied"],
        "note": f"parent_id no SQLite. inflight={cap['applied']}. Paralelismo limitado a {cap['applied']} jobs.",
    }


def cancel(jid: str) -> dict:
    """Kill queued/assigned only. Running has no preemption on this host."""
    with store._lock, store._conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            return {"ok": False, "reason": "pid inexistente", "id": jid}
        st = r["status"]
        if st not in ("queued", "assigned"):
            return {"ok": False, "reason": f"sem preempção para status={st}", "status": st, "id": jid}
        c.execute(
            "UPDATE jobs SET status='killed', error='killed', updated=? WHERE id=?",
            (now_iso(), jid),
        )
    bus.emit("OS_KILL", "NOTICE", f"kill {jid} was {st}")
    return {"ok": True, "id": jid, "was": st, "status": "killed"}


def set_priority(jid: str, priority: int) -> dict:
    prio = max(-10, min(10, int(priority)))
    with store._lock, store._conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            return {"ok": False, "reason": "pid inexistente", "id": jid}
        if r["status"] not in ("queued", "assigned"):
            return {"ok": False, "reason": f"já {r['status']}", "id": jid}
        c.execute("UPDATE jobs SET priority=?, updated=? WHERE id=?", (prio, now_iso(), jid))
    return {"ok": True, "id": jid, "priority": prio}


def register_worker(wid: str, name: str, location: str, capabilities: list[str], meta: dict | None = None) -> dict:
    now = time.time()
    with store._lock, store._conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO workers VALUES(?,?,?,?,?,?,?,?,?)",
            (
                wid,
                name,
                location,
                json.dumps(capabilities),
                now,
                None,
                None,
                "alive",
                json.dumps(meta or {}, default=str),
            ),
        )
    bus.emit("AGENT_STARTED", "NOTICE", f"worker {wid} {location}")
    return {"id": wid, "location": location, "capabilities": capabilities}


def heartbeat(wid: str, cpu: Any = None, ram: Any = None) -> None:
    with store._lock, store._conn() as c:
        c.execute(
            "UPDATE workers SET last_seen=?, cpu=?, ram=?, status='alive' WHERE id=?",
            (time.time(), str(cpu) if cpu is not None else None, str(ram) if ram is not None else None, wid),
        )


def unregister_worker(wid: str) -> int:
    with store._lock, store._conn() as c:
        cur = c.execute("DELETE FROM workers WHERE id=?", (wid,))
        return cur.rowcount or 0


def prune(keep: tuple[str, ...] = ("control-local",)) -> int:
    now = time.time()
    n = 0
    with store._lock, store._conn() as c:
        rows = c.execute("SELECT id, last_seen FROM workers").fetchall()
        for r in rows:
            if r["id"] in keep:
                continue
            last = float(r["last_seen"] or 0)
            if now - last > HEARTBEAT_TTL * 3:
                c.execute("DELETE FROM workers WHERE id=?", (r["id"],))
                n += 1
    return n


def list_workers() -> list[dict]:
    now = time.time()
    with store._conn() as c:
        rows = c.execute("SELECT * FROM workers").fetchall()
    out = []
    for r in rows:
        last = float(r["last_seen"] or 0)
        alive = (now - last) < HEARTBEAT_TTL
        caps = []
        try:
            caps = json.loads(r["capabilities"] or "[]")
        except Exception:
            pass
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "location": r["location"],
                "capabilities": caps,
                "alive": alive,
                "last_seen_s": round(now - last, 1),
                "cpu": r["cpu"],
                "ram": r["ram"],
            }
        )
    return out


def expire_stale(assigned_s: float = 45.0) -> int:
    """Claimed but never started → back to queued. Running só cai via requeue_orphans (worker morto)."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    n = 0
    with store._lock, store._conn() as c:
        rows = c.execute("SELECT id, updated FROM jobs WHERE status='assigned'").fetchall()
        for r in rows:
            try:
                u = datetime.fromisoformat((r["updated"] or "").replace("Z", "+00:00"))
                if u.tzinfo is None:
                    u = u.replace(tzinfo=timezone.utc)
                age = (now - u).total_seconds()
            except Exception:
                continue
            if age <= assigned_s:
                continue
            c.execute(
                "UPDATE jobs SET status='queued', worker_id=NULL, updated=? WHERE id=?",
                (now_iso(), r["id"]),
            )
            n += 1
    if n:
        bus.emit("NOTICE", "WARNING", f"expire {n} job(s) assigned sem start")
    return n


def recover_local(wid: str) -> int:
    """Boot: jobs left running/assigned on this worker id were the previous process."""
    n = 0
    with store._lock, store._conn() as c:
        rows = c.execute(
            "SELECT id FROM jobs WHERE worker_id=? AND status IN ('assigned','running')",
            (wid,),
        ).fetchall()
        for r in rows:
            c.execute(
                "UPDATE jobs SET status='queued', worker_id=NULL, updated=? WHERE id=?",
                (now_iso(), r["id"]),
            )
            n += 1
    if n:
        bus.emit("NOTICE", "WARNING", f"recover {n} job(s) do worker {wid} (processo anterior)")
    return n


def requeue_orphans() -> int:
    alive = {w["id"] for w in list_workers() if w.get("alive")}
    n = 0
    with store._lock, store._conn() as c:
        rows = c.execute("SELECT id, worker_id FROM jobs WHERE status IN ('assigned','running')").fetchall()
        for r in rows:
            wid = r["worker_id"]
            if wid and wid not in alive:
                c.execute(
                    "UPDATE jobs SET status='queued', worker_id=NULL, updated=? WHERE id=?",
                    (now_iso(), r["id"]),
                )
                n += 1
    if n:
        bus.emit("NOTICE", "WARNING", f"requeue {n} job(s) órfãos")
    return n
