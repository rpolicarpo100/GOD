from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from superai import aios, benchmark, compute, evolution, observer, queue as tq, routing, tokens as ti
from superai.events import bus
from superai.runtime import handle, resolve_mode, set_params, snapshot
from superai.util import uid

ROOT = Path(__file__).parent
app = FastAPI(title="SUPER AI")
WORKER_TOKEN = os.environ.get("SUPERAI_WORKER_TOKEN") or ""


class ParamsIn(BaseModel):
    patch: dict


class ChatIn(BaseModel):
    text: str
    from_worker: bool = False


class ExpIn(BaseModel):
    id: str
    approve: bool


class ChatCompletion(BaseModel):
    model: str = "superai"
    messages: list[dict]
    max_tokens: int | None = None


class WorkerIn(BaseModel):
    id: str
    name: str | None = None
    location: str = "remote"
    capabilities: list[str] = []


class HeartbeatIn(BaseModel):
    id: str
    cpu: float | None = None
    ram: float | None = None


class ClaimIn(BaseModel):
    worker_id: str


class CompleteIn(BaseModel):
    id: str
    ok: bool = True
    result: dict | None = None
    error: str | None = None


class KillIn(BaseModel):
    id: str


class SyscallIn(BaseModel):
    name: str
    args: dict = {}


class NiceIn(BaseModel):
    id: str
    priority: int = 0


def _worker_auth(authorization: str | None) -> None:
    if not WORKER_TOKEN:
        return
    if authorization != f"Bearer {WORKER_TOKEN}":
        raise HTTPException(401, "worker token inválido")


@app.on_event("startup")
def _startup():
    compute.start_local_worker()
    aios.boot()


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/api/state")
def state():
    return snapshot()


@app.get("/api/health")
def health():
    """Liveness leve — sem Qdrant/snapshot. Métricas pesadas em /api/metrics."""
    eye = observer.latest()
    mode, _ = resolve_mode()
    return {
        "ok": eye.get("ok", True),
        "mode": mode,
        "workers_alive": eye.get("metrics", {}).get("workers_alive"),
        "queue_depth": eye.get("metrics", {}).get("queue_depth"),
        "alerts": [a["code"] for a in eye.get("alerts") or []],
        "gpu_required": False,
    }


@app.get("/api/metrics")
def metrics():
    return observer.inspect()


@app.get("/api/token/usage")
def token_usage():
    return ti.usage_summary()


@app.get("/api/token/cost")
def token_cost():
    return ti.pricing()


@app.get("/api/token/budget")
def token_budget():
    return ti.budget_status()


@app.get("/api/token/forecast")
def token_forecast():
    return ti.forecast()


@app.get("/api/token/anomalies")
def token_anomalies():
    return ti.anomalies()


@app.get("/api/token/efficiency")
def token_efficiency():
    return ti.efficiency()


@app.get("/api/token/report")
def token_report():
    return ti.report()


@app.get("/api/token/models")
def token_models():
    return ti.models()


@app.post("/api/params")
def params(body: ParamsIn):
    return set_params(body.patch)


@app.post("/api/chat")
def chat(body: ChatIn):
    return handle(body.text, from_worker=body.from_worker)


@app.post("/api/benchmark")
def api_bench():
    return benchmark.run("api")


@app.post("/api/evolve")
def api_evolve():
    return evolution.run_cycle()


@app.post("/api/experiment")
def api_exp(body: ExpIn):
    return {"msg": evolution.decide(body.id, body.approve)}


@app.post("/api/workers/register")
def w_reg(body: WorkerIn, authorization: str | None = Header(default=None)):
    _worker_auth(authorization)
    return tq.register_worker(body.id, body.name or body.id, body.location, body.capabilities)


@app.post("/api/workers/heartbeat")
def w_hb(body: HeartbeatIn, authorization: str | None = Header(default=None)):
    _worker_auth(authorization)
    tq.heartbeat(body.id, body.cpu, body.ram)
    return {"ok": True}


@app.post("/api/queue/claim")
def q_claim(body: ClaimIn, authorization: str | None = Header(default=None)):
    _worker_auth(authorization)
    return tq.claim(body.worker_id)


@app.post("/api/queue/complete")
def q_done(body: CompleteIn, authorization: str | None = Header(default=None)):
    _worker_auth(authorization)
    if body.ok:
        tq.complete(body.id, body.result or {})
    else:
        tq.fail(body.id, body.error or "fail")
    return {"ok": True}


@app.get("/api/os")
def os_stat():
    return aios.snapshot()


@app.get("/api/os/ps")
def os_ps():
    return aios.ps()


@app.get("/api/os/dmesg")
def os_dmesg():
    return {"events": aios.dmesg()}


@app.get("/api/os/mounts")
def os_mounts():
    return aios.mounts()


@app.get("/api/os/drivers")
def os_drivers():
    return {"drivers": aios.drivers()}


@app.post("/api/os/kill")
def os_kill(body: KillIn):
    return aios.kill(body.id)


@app.post("/api/os/syscall")
def os_sys(body: SyscallIn):
    return aios.syscall(body.name, body.args or {})


@app.post("/api/os/nice")
def os_nice(body: NiceIn):
    return aios.nice(body.id, body.priority)


@app.get("/v1/models")
def v1_models():
    gw = routing.health()
    ids = gw["omniroute"]["models"] or gw["direct"]["models"] or ["superai-offline"]
    return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": gw["active"]} for i in ids]}


@app.post("/v1/chat/completions")
def v1_chat(body: ChatCompletion):
    text = ""
    for m in body.messages:
        if m.get("role") == "user":
            text = m.get("content") or text
    handle(str(text))
    s = snapshot()
    reply = next((m["text"] for m in reversed(s.get("chat") or []) if m["role"] == "brain"), "")
    return {
        "id": uid("chatcmpl"),
        "object": "chat.completion",
        "model": body.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
    }


@app.get("/api/stream")
async def stream():
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def on_event(kind, payload):
        loop.call_soon_threadsafe(q.put_nowait, (kind, payload))

    unsub = bus.subscribe(on_event)

    async def gen():
        try:
            yield f"event: snapshot\ndata: {json.dumps(snapshot(), ensure_ascii=False)}\n\n"
            while True:
                kind, payload = await q.get()
                yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            unsub()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
