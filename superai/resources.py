"""Resource Manager — host facts only. GPU is OPTIONAL, never required."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


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
