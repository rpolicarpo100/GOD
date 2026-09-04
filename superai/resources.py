"""Resource Manager — host facts only. GPU is OPTIONAL, never required."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import cfg


def _mem() -> dict:
    tot = avail = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                tot = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) // 1024
    except Exception:
        pass
    return {"ram_mb": tot, "ram_avail_mb": avail}


def _load() -> dict:
    try:
        a, b, c, *_ = Path("/proc/loadavg").read_text().split()
        return {"load1": float(a), "load5": float(b), "load15": float(c)}
    except Exception:
        return {"load1": None, "load5": None, "load15": None}


def _gpu() -> dict:
    if shutil.which("nvidia-smi"):
        return {"present": True, "required": False, "note": "nvidia-smi found — optional"}
    return {"present": False, "required": False, "note": "sem GPU — arquitectura não exige"}


def _disk() -> dict:
    """Disco DESTE processo. Não é o ADATA do PC i5-4590."""
    try:
        u = shutil.disk_usage("/")
        return {
            "disk_total_mb": u.total // (1024 * 1024),
            "disk_free_mb": u.free // (1024 * 1024),
            "disk_kind": "MEASURED",
            "disk_note": "filesystem deste sandbox, não o disco do PC USER_DECLARED",
        }
    except Exception:
        return {"disk_total_mb": None, "disk_free_mb": None, "disk_kind": "UNKNOWN"}


def declared_node() -> dict:
    """PC do utilizador (foto). Nunca confundir com host() deste processo."""
    n = cfg.get("pc_node") or {}
    if not n:
        return {"kind": "UNKNOWN", "reason": "sem pc_node na config"}
    ram_gb = n.get("ram_gb")
    cores = n.get("cores")
    caps = n.get("caps") or {}
    rf = float(caps.get("ram_fraction_max") or 0.5)
    cf = float(caps.get("cpu_fraction_max") or 0.5)
    return {
        "kind": n.get("kind") or "USER_DECLARED",
        "cpu": n.get("cpu"),
        "cores": cores,
        "ram_gb": ram_gb,
        "gpu": n.get("gpu"),
        "gpu_required": False,
        "board": n.get("board"),
        "nic": n.get("nic"),
        "disk": n.get("disk"),
        "caps": {
            "ram_gb_max": round(ram_gb * rf, 1) if ram_gb else None,
            "cores_max": max(1, int(cores * cf)) if cores else None,
            "ram_fraction_max": rf,
            "cpu_fraction_max": cf,
            "gpu_for_llm": bool(caps.get("gpu_for_llm")),
            "note": caps.get("note") or "nunca a totalidade",
        },
        "this_process_is_not_that_pc": True,
        "local_llm": False,
        "local_llm_reason": "GT 1030 não para LLM; Ollama ausente neste host",
    }


def host() -> dict:
    m, l = _mem(), _load()
    cpu = os.cpu_count() or 1
    load1 = l.get("load1") or 0
    pressure = "high" if (m.get("ram_avail_mb") or 9999) < 256 or load1 > cpu else "low"
    return {
        "role": "control",
        "cpu_count": cpu,
        "gpu": _gpu(),
        **m,
        **l,
        "pressure": pressure,
        "thin_client": True,
        **_disk(),
    }


def layout() -> dict:
    """Split físico alvo no PC do utilizador. applied_here=False neste sandbox."""
    n = declared_node()
    caps = n.get("caps") or {}
    return {
        "kind": "USER_DECLARED",
        "applied_here": False,
        "this_host_kind": "MEASURED",
        "pc": {
            "role": "interface + control + local cache",
            "cpu": n.get("cpu"),
            "cores_total": n.get("cores"),
            "cores_god_max": caps.get("cores_max"),
            "ram_gb_total": n.get("ram_gb"),
            "ram_gb_god_max": caps.get("ram_gb_max"),
            "gpu": n.get("gpu"),
            "gpu_for_llm": False,
            "gpu_required": False,
            "disk": n.get("disk"),
            "never_totality": True,
        },
        "remote": {
            "role": "heavy compute (LLM APIs)",
            "note": "Groq/Cerebras/Claude via DirectAdapter. OmniRoute :20128 down.",
        },
        "database": {
            "role": "persistent state",
            "engine": "SQLite + Qdrant embedded on disk",
        },
        "workers": {
            "role": "execution",
            "this_process": "1 in-process thread (control-local)",
            "declared_pc_cores_max": caps.get("cores_max"),
        },
        "local_llm": {
            "allowed": False,
            "reason": "GT 1030 não para LLM; Ollama :11434 fechado neste host",
        },
        "cache": {"prefer": "disk", "reason": "RAM capped 50%; disco 'muito' (GB UNKNOWN)"},
    }


def inflight_cap() -> dict:
    """Jobs simultâneos. Este sandbox = 1. Alvo no PC = cores_max (nunca 4/4)."""
    n = declared_node()
    target = (n.get("caps") or {}).get("cores_max") or 1
    return {
        "applied": 1,
        "applied_kind": "MEASURED",
        "applied_reason": "1 worker in-process; este host ≠ PC i5-4590 24GB",
        "declared_pc_target": int(target),
        "declared_kind": "USER_DECLARED",
    }


def decide(task: dict, workers: list[dict]) -> dict:
    """Where to run. Light work stays on control. Heavy work prefers a worker."""
    ttype = task.get("type") or ""
    complexity = int(task.get("complexity") or 0)
    heavy_type = ttype in ("research", "coding", "evolution") or complexity >= 7
    kind = task.get("job_kind")
    if kind in ("benchmark", "evolution"):
        heavy_type = True
    live = [w for w in workers if w.get("alive")]
    remote = [w for w in live if w.get("location") == "remote"]
    local_w = [w for w in live if w.get("location") in ("local", "control")]
    if not heavy_type:
        return {
            "plane": "control",
            "location": "LOCAL",
            "enqueue": False,
            "reason": "tarefa leve — control plane (thin client)",
        }
    if remote:
        return {
            "plane": "compute",
            "location": "REMOTE",
            "enqueue": True,
            "worker": remote[0]["id"],
            "reason": "tarefa pesada — worker remoto",
        }
    if local_w:
        return {
            "plane": "compute",
            "location": "LOCAL_WORKER",
            "enqueue": True,
            "worker": None,
            "reason": "tarefa pesada — fila; worker local in-process (nenhum remoto registado)",
        }
    h = host()
    return {
        "plane": "control",
        "location": "LOCAL_FALLBACK",
        "enqueue": False,
        "reason": f"sem workers vivos; fallback inline (pressure={h['pressure']})",
    }
