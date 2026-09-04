"""Super AI OS — kernel over the existing control plane.

Does not replace Brain, Router, Governor, Memory, Evolution, Token Intel.
Syscalls go through Governor via tools.execute. Drivers are probed providers.
GPU is OPTIONAL. No preemption of running jobs on this host.
"""
from __future__ import annotations

import time

from . import observer, providers, queue as tq, resources, routing, tools
from .config import DATA, ROOT, cfg
from .events import bus
from .governor import gov
from .store import store
from .util import now_iso, uid

MEASURED = "MEASURED"
UNKNOWN = "UNKNOWN"

_boot_ts: float | None = None
_boot: dict | None = None


def init() -> None:
    with store._conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS syscalls (
              id TEXT PRIMARY KEY,
              name TEXT,
              args TEXT,
              status TEXT,
              actor TEXT,
              latency_ms REAL,
              ts TEXT,
              detail TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sys_ts ON syscalls(ts);
            """
        )


init()


def _quota(agent_id: str = "control") -> dict:
    """Agent budget vs MEASURED session actuals. Not estimated."""
    used = int(store.usage().get("session_tokens") or 0)
    limit = int(cfg.get("budgets", "agent", default=40000) or 40000)
    return {
        "agent_id": agent_id,
        "used_measured": used,
        "limit": limit,
        "ok": used < limit,
        "kind": MEASURED,
    }


def boot() -> dict:
    global _boot_ts, _boot
    if _boot is not None:
        return _boot
    t0 = time.perf_counter()
    h = resources.host()
    steps = []
    steps.append({"name": "store", "ok": store.path.exists(), "path": str(store.path)})
    steps.append({"name": "sandbox", "ok": (DATA / "sandbox").exists(), "path": str(DATA / "sandbox")})
    steps.append({"name": "governor", "ok": True, "strict": gov.strict()})
    gw = routing.health()
    steps.append(
        {
            "name": "drivers",
            "ok": True,
            "omniroute": gw["omniroute"]["available"],
            "direct": gw["direct"]["available"],
            "note": "probed — available=false não é inventado como up",
        }
    )
    steps.append({"name": "gpu", "ok": True, "required": False, "present": (h.get("gpu") or {}).get("present")})
    _boot_ts = time.time()
    _boot = {
        "kind": MEASURED,
        "ts": now_iso(),
        "uptime_s": 0,
        "boot_ms": round((time.perf_counter() - t0) * 1000, 2),
        "steps": steps,
        "gpu_required": False,
        "preempt": False,
        "sysname": "SuperAI-OS",
        "version": _os_ver(),
        "host": {k: h.get(k) for k in ("cpu_count", "ram_avail_mb", "load1", "pressure")},
    }
    bus.emit("OS_BOOT", "NOTICE", f"kernel up gpu_required=false pressure={h.get('pressure')}")
    return _boot


def _os_ver() -> str:
    from superai import __version__ as v

    return v


def uptime_s() -> float | None:
    if _boot_ts is None:
        return None
    return round(time.time() - _boot_ts, 1)


def uname() -> dict:
    h = resources.host()
    return {
        "sysname": "SuperAI-OS",
        "version": _os_ver(),
        "role": h.get("role"),
        "cpu_count": h.get("cpu_count"),
        "ram_avail_mb": h.get("ram_avail_mb"),
        "gpu_required": False,
        "gpu_present": (h.get("gpu") or {}).get("present"),
        "preempt": False,
        "kind": MEASURED,
    }


def mounts() -> dict:
    items = []
    for name, p in (
        ("root", ROOT),
        ("data", DATA),
        ("spine", DATA / "spine.db"),
        ("qdrant_data", DATA / "qdrant"),
        ("sandbox", DATA / "sandbox"),
    ):
        exists = p.exists()
        nbytes = None
        if exists and p.is_file():
            nbytes = p.stat().st_size
        items.append({"name": name, "path": str(p), "exists": exists, "bytes": nbytes, "kind": MEASURED})
    return {"kind": MEASURED, "mounts": items}


def drivers() -> list[dict]:
    out = []
    for p in providers.health_all():
        out.append(
            {
                "id": p["id"],
                "name": p["name"],
                "class": "provider",
                "available": p["available"],
                "error": p.get("error"),
                "kind": MEASURED,
            }
        )
    gw = routing.health()
    out.append(
        {
            "id": "omniroute",
            "name": "OmniRoute",
            "class": "gateway",
            "available": gw["omniroute"]["available"],
            "error": gw["omniroute"].get("error"),
            "kind": MEASURED,
        }
    )
    return out


def services() -> list[dict]:
    workers = tq.list_workers()
    eye = observer.running()
    out = []
    for w in workers:
        out.append(
            {
                "id": w["id"],
                "type": "worker",
                "alive": bool(w.get("alive")),
                "location": w.get("location"),
                "kind": MEASURED,
            }
        )
    out.append({"id": "terceiro-olho", "type": "observer", "alive": eye, "kind": MEASURED})
    return out


def ps(n: int = 24) -> dict:
    procs = []
    stmap = {
        "queued": "READY",
        "assigned": "READY",
        "running": "RUNNING",
        "completed": "ZOMBIE",
        "failed": "DEAD",
        "killed": "DEAD",
    }
    for j in tq.jobs(n):
        procs.append(
            {
                "pid": j["id"],
                "type": "job",
                "kind": j.get("kind"),
                "status": stmap.get(j.get("status") or "", j.get("status")),
                "job_status": j.get("status"),
                "priority": int(j.get("priority") or 0),
                "worker_id": j.get("worker_id"),
                "location": j.get("location"),
                "ts": j.get("ts"),
            }
        )
    for s in services():
        procs.append(
            {
                "pid": s["id"],
                "type": s["type"],
                "kind": s["type"],
                "status": "RUNNING" if s.get("alive") else "DEAD",
                "priority": 0,
                "location": s.get("location"),
            }
        )
    q = tq.stats()
    return {
        "kind": MEASURED,
        "n": len(procs),
        "ready": q.get("queued", 0),
        "running": q.get("running", 0) + q.get("assigned", 0),
        "killed": q.get("killed", 0),
        "processes": procs,
        "preempt": False,
    }


def dmesg(n: int = 40) -> list[dict]:
    names = ("OS_BOOT", "OS_KILL", "OS_ADMIT_DENY", "OS_NICE", "SYSCALL", "OS_QUOTA")
    out = [e for e in bus.history if e.get("name") in names]
    return out[:n]


def admit(kind: str, text: str, complexity: int = 8) -> dict:
    """Refuse heavy enqueue under MEASURED overload or agent quota. No inline fallback here."""
    h = resources.host()
    loc = resources.decide({"type": kind, "complexity": complexity, "job_kind": kind}, tq.list_workers())
    q = _quota()
    if not q["ok"]:
        bus.emit("OS_QUOTA", "WARNING", f"agent quota {q['used_measured']}/{q['limit']} MEASURED")
        return {
            "ok": False,
            "reason": "AGENT_QUOTA",
            "quota": q,
            "pressure": h.get("pressure"),
            "ram_avail_mb": h.get("ram_avail_mb"),
            "loc": loc,
        }
    if h.get("pressure") == "high" and loc.get("enqueue"):
        bus.emit(
            "OS_ADMIT_DENY",
            "WARNING",
            f"PC_OVERLOAD ram_avail={h.get('ram_avail_mb')} load1={h.get('load1')} kind={kind}",
        )
        return {
            "ok": False,
            "reason": "PC_OVERLOAD",
            "pressure": h.get("pressure"),
            "ram_avail_mb": h.get("ram_avail_mb"),
            "load1": h.get("load1"),
            "quota": q,
            "loc": loc,
            "kind_host": MEASURED,
        }
    return {"ok": True, "loc": loc, "quota": q, "pressure": h.get("pressure"), "ram_avail_mb": h.get("ram_avail_mb")}


def _save_syscall(name: str, args: dict, status: str, actor: str, latency_ms: float, detail: str) -> None:
    import json

    with store._lock, store._conn() as c:
        c.execute(
            "INSERT INTO syscalls VALUES(?,?,?,?,?,?,?,?)",
            (uid("sys"), name, json.dumps(args, ensure_ascii=False, default=str)[:4000], status, actor, latency_ms, now_iso(), detail[:2000]),
        )


def syscall_count() -> int:
    with store._conn() as c:
        n = c.execute("SELECT COUNT(*) FROM syscalls").fetchone()[0]
    return int(n)


def syscall(name: str, args: dict | None = None, actor: str = "user") -> dict:
    args = args or {}
    name = (name or "").strip()
    t0 = time.perf_counter()
    q = _quota()
    if not q["ok"] and name not in ("ps", "stat", "dmesg", "uname", "mounts"):
        rec = {"status": "error", "errors": ["AGENT_QUOTA"], "syscall": name, "quota": q}
        _save_syscall(name, args, "quota", actor, 0, "AGENT_QUOTA")
        bus.emit("OS_QUOTA", "WARNING", f"syscall {name} recusado")
        return rec

    builtins = {
        "ps": lambda: ps(),
        "stat": lambda: snapshot(),
        "dmesg": lambda: {"events": dmesg()},
        "uname": lambda: uname(),
        "mounts": lambda: mounts(),
        "kill": lambda: kill(str(args.get("id") or args.get("pid") or "")),
        "nice": lambda: nice(str(args.get("id") or args.get("pid") or ""), int(args.get("priority") or 0)),
    }
    if name in builtins:
        body = builtins[name]()
        ms = round((time.perf_counter() - t0) * 1000, 2)
        _save_syscall(name, args, "ok", actor, ms, "builtin")
        bus.emit("SYSCALL", "INFO", f"{name} {ms}ms actor={actor}")
        return {"status": "success", "syscall": name, "result": body, "latency_ms": ms, "kind": MEASURED}

    if name not in tools.TOOLS:
        ms = round((time.perf_counter() - t0) * 1000, 2)
        _save_syscall(name, args, "unknown", actor, ms, "unknown syscall")
        return {"status": "error", "errors": [f"syscall inexistente: {name}"], "syscall": name}

    res = tools.execute(name, args)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    st = "ok" if res.get("status") == "success" else "error"
    _save_syscall(name, args, st, actor, ms, ",".join(res.get("errors") or []) or st)
    bus.emit("SYSCALL", "INFO", f"{name} {st} {ms}ms actor={actor}")
    res = dict(res)
    res["syscall"] = name
    res["latency_ms"] = ms
    res["kind"] = MEASURED
    return res


def kill(pid: str) -> dict:
    pid = (pid or "").strip()
    if not pid:
        return {"ok": False, "reason": "pid vazio"}
    r = tq.cancel(pid)
    return r


def nice(pid: str, priority: int) -> dict:
    r = tq.set_priority(pid, priority)
    if r.get("ok"):
        bus.emit("OS_NICE", "INFO", f"{pid} priority={r.get('priority')}")
    return r


def snapshot() -> dict:
    """Light kernel view for the living dashboard. Not a documentation page."""
    b = _boot or {}
    q = tq.stats()
    h = resources.host()
    return {
        "sysname": "SuperAI-OS",
        "version": _os_ver(),
        "uptime_s": uptime_s(),
        "booted": _boot_ts is not None,
        "boot_ms": b.get("boot_ms"),
        "pressure": h.get("pressure"),
        "ram_avail_mb": h.get("ram_avail_mb"),
        "gpu_required": False,
        "preempt": False,
        "ready": q.get("queued", 0),
        "running": q.get("running", 0) + q.get("assigned", 0),
        "killed": q.get("killed", 0),
        "syscalls": syscall_count(),
        "quota": _quota(),
        "kind": MEASURED,
    }
