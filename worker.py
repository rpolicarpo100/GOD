#!/usr/bin/env python3
"""Remote compute worker. Talks to the control plane over HTTP.

  SUPERAI_API=http://control-host:8000 SUPERAI_WORKER_TOKEN=... python3 worker.py

Does not open local Qdrant (control plane owns data). Executes claimed jobs
by calling back into this repo's compute.execute_job for chat/benchmark/evolution.
If you run this on the SAME host as the API, prefer the in-process worker —
embedded Qdrant cannot be opened twice.
"""
from __future__ import annotations

import os
import socket
import time

import httpx

API = os.environ.get("SUPERAI_API", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("SUPERAI_WORKER_TOKEN", "")
WID = os.environ.get("SUPERAI_WORKER_ID") or f"remote-{socket.gethostname()}"


def _h() -> dict:
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def main() -> None:
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            f"{API}/api/workers/register",
            headers=_h(),
            json={
                "id": WID,
                "name": WID,
                "location": "remote",
                "capabilities": ["chat", "benchmark", "evolution", "tools"],
            },
        )
        r.raise_for_status()
        print("registered", r.json())
        while True:
            hb = c.post(f"{API}/api/workers/heartbeat", headers=_h(), json={"id": WID})
            hb.raise_for_status()
            job = c.post(f"{API}/api/queue/claim", headers=_h(), json={"worker_id": WID}).json()
            if not job:
                time.sleep(0.8)
                continue
            print("claimed", job.get("id"), job.get("kind"))
            # Remote execution of chat still hits control handle via API to avoid
            # a second Qdrant lock. A future worker with its own MemoryAdapter
            # can run tools locally.
            if job.get("kind") == "chat":
                res = c.post(f"{API}/api/chat", headers=_h(), json={"text": job.get("text") or "", "from_worker": True})
                body = res.json() if res.is_success else {"error": res.text}
            elif job.get("kind") == "benchmark":
                body = c.post(f"{API}/api/benchmark", headers=_h()).json()
            elif job.get("kind") == "evolution":
                body = c.post(f"{API}/api/evolve", headers=_h()).json()
            else:
                body = {"error": "unknown kind"}
            c.post(
                f"{API}/api/queue/complete",
                headers=_h(),
                json={"id": job["id"], "ok": True, "result": body},
            )


if __name__ == "__main__":
    main()
