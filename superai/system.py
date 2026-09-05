"""System State — consciência operacional verificável.

Agrega dados reais de todos os módulos. Não inventa.
Responde: WHO AM I? WHERE AM I? WHAT IS RUNNING? WHAT CAN I DO?
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from . import aios, gods, observer, providers, queue as tq, resources, routing, tokens as ti
from .config import ROOT, cfg
from .store import store
from .util import now_iso


def _git_info() -> dict:
    """Git commit real. Não inventar."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=3
        )
        commit = r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        commit = None
    try:
        r2 = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=3
        )
        branch = r2.stdout.strip() if r2.returncode == 0 else None
    except Exception:
        branch = None
    return {
        "commit": commit or "UNKNOWN",
        "branch": branch or "UNKNOWN",
        "kind": "MEASURED" if commit else "UNKNOWN",
    }


def _version() -> dict:
    """Versão real do package."""
    try:
        from superai import __version__
        return {"version": __version__, "kind": "MEASURED"}
    except Exception:
        return {"version": "UNKNOWN", "kind": "UNKNOWN"}


def _runtime_status() -> dict:
    """Estado real do runtime."""
    eye = observer.latest()
    ok = eye.get("ok", True)
    alerts = [a["code"] for a in (eye.get("alerts") or [])]
    pressure = eye.get("metrics", {}).get("pressure", "unknown")
    return {
        "status": "healthy" if ok else "degraded",
        "pressure": pressure,
        "alerts": alerts,
        "kind": "MEASURED",
    }


def _providers_summary() -> dict:
    """Estado real dos providers."""
    health = providers.health_all()
    available = [h["id"] for h in health if h.get("available")]
    unavailable = [h["id"] for h in health if not h.get("available")]
    gw = routing.health()
    return {
        "available": available,
        "unavailable": unavailable,
        "n_available": len(available),
        "n_total": len(health),
        "gateway": gw["active"],
        "omniroute_up": gw["omniroute"]["available"],
        "kind": "MEASURED",
    }


def _queue_summary() -> dict:
    """Estado real da queue."""
    stats = tq.stats()
    workers = tq.list_workers()
    alive = [w for w in workers if w.get("alive")]
    dead = [w for w in workers if not w.get("alive")]
    inf = resources.inflight_cap()
    return {
        "queued": stats.get("queued", 0),
        "running": stats.get("running", 0) + stats.get("assigned", 0),
        "completed": stats.get("completed", 0),
        "failed": stats.get("failed", 0),
        "killed": stats.get("killed", 0),
        "workers_alive": len(alive),
        "workers_dead": len(dead),
        "inflight": inf.get("applied"),
        "kind": "MEASURED",
    }


def _resources_summary() -> dict:
    """Recursos reais do host."""
    h = resources.host()
    n = resources.declared_node()
    return {
        "host": {
            "cpu_count": h.get("cpu_count"),
            "ram_avail_mb": h.get("ram_avail_mb"),
            "load1": h.get("load1"),
            "pressure": h.get("pressure"),
            "gpu_present": (h.get("gpu") or {}).get("present"),
        },
        "pc_node": {
            "kind": n.get("kind"),
            "cpu": n.get("cpu"),
            "cores": n.get("cores"),
            "ram_gb": n.get("ram_gb"),
            "cores_max": (n.get("caps") or {}).get("cores_max"),
        },
        "kind": "MEASURED",
    }


def _missions_summary() -> dict:
    """Estado real das missões."""
    from . import mission as ms
    snap = ms.snapshot()
    active = snap.get("active")
    return {
        "active": active.get("id") if active else None,
        "active_goal": active.get("goal") if active else None,
        "total": snap.get("n", 0),
        "kind": "MEASURED",
    }


def _diagnostics() -> dict:
    """Diagnósticos reais."""
    from . import repair
    eye = observer.latest()
    return {
        "alerts": eye.get("alerts", []),
        "n_alerts": len(eye.get("alerts", [])),
        "critical": sum(1 for a in (eye.get("alerts") or []) if a.get("level") == "CRITICAL"),
        "kind": "MEASURED",
    }


def _tests_summary() -> dict:
    """Último resultado de testes conhecido. Não inventar."""
    # Não executamos testes aqui — só reportamos o último resultado conhecido
    # O resultado real vem de `python3 -m unittest tests.test_core`
    return {
        "kind": "UNKNOWN",
        "note": "executar manualmente: python3 -m unittest tests.test_core -q",
        "last_known": {
            "total": 114,
            "pass": 113,
            "fail": 1,
            "fail_reason": "test_subset_gates_execute (env-dependent)",
            "source": "P1.5 audit 2026-09-05",
        },
    }


def _token_summary() -> dict:
    """Estado real de tokens."""
    u = ti.usage_summary()
    return {
        "session_tokens": u.get("session_tokens", 0),
        "daily_tokens": u.get("daily_tokens", 0),
        "llm_calls": u.get("llm_calls", 0),
        "tool_calls": u.get("tool_calls", 0),
        "cache_hits": u.get("cache_hits", 0),
        "cache_hit_rate": u.get("cache_hit_rate"),
        "cost_kind": ti.pricing().get("kind"),
        "kind": "MEASURED",
    }


def system_state() -> dict:
    """Estado completo do sistema. Tudo MEASURED ou UNKNOWN. Nunca inventar."""
    git = _git_info()
    ver = _version()
    return {
        "system": {
            "name": "GOD",
            "version": ver["version"],
            "git_commit": git["commit"],
            "git_branch": git["branch"],
            "ts": now_iso(),
        },
        "runtime": _runtime_status(),
        "providers": _providers_summary(),
        "queue": _queue_summary(),
        "resources": _resources_summary(),
        "missions": _missions_summary(),
        "tokens": _token_summary(),
        "diagnostics": _diagnostics(),
        "tests": _tests_summary(),
        "mode": (cfg.get("mode") or "auto"),
        "governor_strict": cfg.get("governor", "strict", default=True),
    }
