"""Compute plane: in-process worker so the control node keeps working
without a remote host. Remote workers use the same claim/complete protocol.
"""
from __future__ import annotations

import threading
import time
import traceback

from . import observer, queue as tq
from .events import bus
from .resources import host

LOCAL_ID = "control-local"
_stop = threading.Event()
_thread: threading.Thread | None = None


def start_local_worker() -> None:
    global _thread
    tq.register_worker(
        LOCAL_ID,
        "control in-process worker",
        "control",
        ["chat", "benchmark", "evolution", "tools"],
        meta={"note": "same process as API — not a second machine"},
    )
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="superai-worker", daemon=True)
    _thread.start()
    observer.start(15.0)


def _loop() -> None:
    while not _stop.is_set():
        h = host()
        tq.heartbeat(LOCAL_ID, cpu=h.get("load1"), ram=h.get("ram_avail_mb"))
        if h.get("pressure") == "high":
            time.sleep(1.2)
            continue
        job = tq.claim(LOCAL_ID)
        if not job:
            time.sleep(0.45)
            continue
        _run(job)


def _run(job: dict) -> None:
    cur = tq.get_job(job["id"])
    if not cur or cur.get("status") == "killed":
        return
    tq.start_run(job["id"])
    bus.emit("AGENT_STARTED", "INFO", f"{LOCAL_ID} running {job['id']} {job['kind']}")
    try:
        result = execute_job(job)
        tq.complete(job["id"], result if isinstance(result, dict) else {"ok": True})
    except Exception as e:
        tq.fail(job["id"], f"{e}\n{traceback.format_exc()[-800:]}")


def execute_job(job: dict) -> dict:
    kind = job.get("kind")
    text = job.get("text") or ""
    if kind == "benchmark":
        from . import benchmark
        from .runtime import _fmt_bench, _say

        s = benchmark.run("worker")
        _say("brain", f"[{LOCAL_ID}]\n" + _fmt_bench(s))
        return {"via": "benchmark", "run_id": s.get("run_id"), "passed": s.get("passed"), "skipped": s.get("skipped")}
    if kind == "evolution":
        from . import evolution
        from .runtime import _say

        cyc = evolution.run_cycle()
        exp = cyc["experiment"]
        _say(
            "brain",
            f"[{LOCAL_ID}] EVOLUTION CYCLE\n"
            f"gaps: {cyc['observe'].get('gaps')}\n"
            f"experiência {exp['id']} [{exp['status']}] {exp['title']}\n"
            "Nada entrou em produção sem ADOPT.",
        )
        return {"via": "evolution", "exp": exp["id"], "status": exp["status"]}
    if kind == "chat":
        from .runtime import handle

        return handle(text, from_worker=True)
    raise ValueError(f"kind desconhecido: {kind}")
