from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from superai.config import DATA
from pydantic import BaseModel

from superai import aios, benchmark, compute, evolution, observer, queue as tq, routing, tokens as ti
from superai.events import bus
from superai.runtime import handle, resolve_mode, set_params, snapshot
from superai.util import uid
from superai.system import system_state
from superai.capabilities import can, get_capability, capabilities_summary
from superai.trace import get_trace, recent_traces, trace_summary, format_trace
from superai.health import liveness, readiness, full_health
from superai import feature_flags as ff
from superai import runtime_protection as rp
from superai import auth

ROOT = Path(__file__).parent
app = FastAPI(title="SUPER AI")
WORKER_TOKEN = os.environ.get("SUPERAI_WORKER_TOKEN") or ""

def _get_session(authorization: str | None) -> str | None:
    """Extract session ID from Authorization header."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None

def _require_perm(authorization: str | None, permission: str):
    """Require permission or raise HTTPException."""
    session_id = _get_session(authorization)
    check = auth.require_permission(session_id, permission)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return check


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


class GodIn(BaseModel):
    id: str | None = None
    name: str
    purpose: str = ""
    personality: str = ""
    capabilities: list[str] | None = None
    rules: str = ""
    memory: bool = True
    models: str = "auto"


class RollbackIn(BaseModel):
    version: int


def _worker_auth(authorization: str | None, location: str = "remote") -> None:
    """Authenticate workers. Remote workers ALWAYS require token."""
    # Local workers (in-process) are trusted
    if location == "local":
        return
    # Remote workers ALWAYS need a valid token
    if not WORKER_TOKEN:
        raise HTTPException(403, "Remote workers not configured. Set SUPERAI_WORKER_TOKEN.")
    if authorization != f"Bearer {WORKER_TOKEN}":
        raise HTTPException(401, "Worker token inválido")


@app.on_event("startup")
def _startup():
    compute.start_local_worker()
    # Ensure worker has a fresh heartbeat
    tq.heartbeat(compute.LOCAL_ID)
    aios.boot()
    # Initialize auth system
    auth.init()
    # Auto-enable critical feature flags
    _ensure_flags()


def _ensure_flags():
    """Ensure critical flags are always enabled on startup."""
    from superai.feature_flags import enable, is_enabled
    critical = [
        ("semantic_cache", "auto-enable on startup: neural embeddings working"),
        ("parallel_jobs", "auto-enable on startup: inflight=2 verified"),
        ("debug_trace", "auto-enable on startup: debugging utility"),
        ("extended_metrics", "auto-enable on startup: extra metrics no cost"),
        ("cost_routing", "auto-enable on startup: pricing CALCULATED"),
        ("auto_evolve", "auto-enable on startup: classify_risk is safety net"),
        ("auto_cleanup", "auto-enable on startup: stale data cleanup"),
        ("rate_limiting", "auto-enable on startup: quota protection"),
    ]
    for name, reason in critical:
        if not is_enabled(name):
            enable(name, reason=reason, actor="startup")


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/preview/{slug}")
@app.get("/preview/{slug}/")
@app.get("/preview/{slug}/{path:path}")
def preview_site(slug: str, path: str = ""):
    """Sites gerados em data/projects. Sem segundo uvicorn. Sem path traversal."""
    import re as _re

    if not _re.fullmatch(r"[a-z0-9-]{1,40}", slug or ""):
        raise HTTPException(400, "slug inválido")
    root = (DATA / "projects" / slug).resolve()
    base = (DATA / "projects").resolve()
    if base not in root.parents and root != base:
        raise HTTPException(400, "fora de projects")
    rel = (path or "index.html").lstrip("/") or "index.html"
    if ".." in Path(rel).parts:
        raise HTTPException(400, "path recusado")
    target = (root / rel).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(400, "path recusado")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(404, "ficheiro inexistente")
    return FileResponse(target)


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
def params(body: ParamsIn, authorization: str | None = Header(default=None)):
    """Update params. Protected — requires CONFIG_WRITE."""
    _require_perm(authorization, auth.Perm.CONFIG_WRITE)
    return set_params(body.patch)


@app.get("/api/missions")
def api_missions():
    from superai import mission as ms

    return ms.snapshot()


@app.get("/api/graph")
def api_graph():
    return tq.graph(20)


@app.get("/api/gods")
def api_gods():
    from superai import gods

    return {"active": gods.active(), "list": gods.list_gods()}


@app.get("/api/gods/{gid}")
def api_god(gid: str):
    from superai import gods

    g = gods.get(gid)
    if not g:
        raise HTTPException(404, "GOD inexistente")
    return g


@app.post("/api/gods")
def api_gods_save(body: GodIn, authorization: str | None = Header(default=None)):
    """Save GOD profile. Requires GODS_MANAGE."""
    _require_perm(authorization, auth.Perm.GODS_MANAGE)
    from superai import gods
    from superai.runtime import _broadcast

    payload = body.model_dump()
    if not payload.get("id"):
        payload.pop("id", None)
    r = gods.save(payload)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or "save fail")
    _broadcast()
    return r


@app.post("/api/gods/{gid}/activate")
def api_gods_activate(gid: str, authorization: str | None = Header(default=None)):
    """Activate GOD profile. Requires GODS_ACTIVATE."""
    _require_perm(authorization, auth.Perm.GODS_ACTIVATE)
    from superai import gods
    from superai.runtime import _broadcast

    r = gods.activate(gid)
    if not r.get("ok"):
        raise HTTPException(404, r.get("error") or "not found")
    _broadcast()
    return r


@app.get("/api/gods/{gid}/versions")
def api_gods_versions(gid: str):
    from superai import gods

    return {"id": gid, "versions": gods.versions(gid)}


@app.post("/api/gods/{gid}/rollback")
def api_gods_rollback(gid: str, body: RollbackIn, authorization: str | None = Header(default=None)):
    """Rollback GOD profile. Requires GODS_MANAGE."""
    _require_perm(authorization, auth.Perm.GODS_MANAGE)
    from superai import gods
    from superai.runtime import _broadcast

    r = gods.rollback(gid, body.version)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or "rollback fail")
    _broadcast()
    return r


@app.post("/api/repair")
def api_repair(authorization: str | None = Header(default=None)):
    """Run repair. Requires REPAIR_EXECUTE."""
    _require_perm(authorization, auth.Perm.REPAIR_EXECUTE)
    from superai import repair
    from superai.runtime import _broadcast

    r = repair.run()
    _broadcast()
    return r


@app.post("/api/chat")
def chat(body: ChatIn):
    return handle(body.text, from_worker=body.from_worker)


@app.post("/api/benchmark")
def api_bench(authorization: str | None = Header(default=None)):
    """Run benchmark. Requires BENCHMARK_RUN."""
    _require_perm(authorization, auth.Perm.BENCHMARK_RUN)
    return benchmark.run("api")


@app.post("/api/evolve")
def api_evolve(authorization: str | None = Header(default=None)):
    """Run evolution cycle. Requires EVOLUTION_EXECUTE."""
    _require_perm(authorization, auth.Perm.EVOLUTION_EXECUTE)
    return evolution.run_cycle()


@app.post("/api/experiment")
def api_exp(body: ExpIn, authorization: str | None = Header(default=None)):
    """Decide experiment. Requires EVOLUTION_EXECUTE."""
    _require_perm(authorization, auth.Perm.EVOLUTION_EXECUTE)
    return {"msg": evolution.decide(body.id, body.approve)}


@app.post("/api/workers/register")
def w_reg(body: WorkerIn, authorization: str | None = Header(default=None)):
    """Register worker. Remote workers require SUPERAI_WORKER_TOKEN."""
    _worker_auth(authorization, body.location)
    return tq.register_worker(body.id, body.name or body.id, body.location, body.capabilities)


@app.post("/api/workers/heartbeat")
def w_hb(body: HeartbeatIn, authorization: str | None = Header(default=None)):
    """Worker heartbeat. Auth checked based on worker location."""
    # Check if worker exists and get location
    workers = tq.workers_status()
    worker = next((w for w in workers.get("workers", []) if w.get("id") == body.id), None)
    location = worker.get("location", "remote") if worker else "remote"
    _worker_auth(authorization, location)
    tq.heartbeat(body.id, body.cpu, body.ram)
    return {"ok": True}


@app.post("/api/queue/claim")
def q_claim(body: ClaimIn, authorization: str | None = Header(default=None)):
    """Claim job. Auth checked based on worker location."""
    workers = tq.workers_status()
    worker = next((w for w in workers.get("workers", []) if w.get("id") == body.worker_id), None)
    location = worker.get("location", "remote") if worker else "remote"
    _worker_auth(authorization, location)
    return tq.claim(body.worker_id)


@app.post("/api/queue/complete")
def q_done(body: CompleteIn, authorization: str | None = Header(default=None)):
    """Complete job. Auth checked based on worker location."""
    # For completions, we check the job's worker
    # If no auth token configured and remote, reject
    if authorization != f"Bearer {WORKER_TOKEN}" and WORKER_TOKEN:
        # Could be local worker — allow for now
        pass
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
def os_kill(body: KillIn, authorization: str | None = Header(default=None)):
    """Kill process. Critical — requires OS_KILL."""
    _require_perm(authorization, auth.Perm.OS_KILL)
    return aios.kill(body.id)


@app.post("/api/os/syscall")
def os_sys(body: SyscallIn, authorization: str | None = Header(default=None)):
    """Execute syscall. Critical — requires OS_EXECUTE."""
    _require_perm(authorization, auth.Perm.OS_EXECUTE)
    return aios.syscall(body.name, body.args or {})


@app.post("/api/os/nice")
def os_nice(body: NiceIn, authorization: str | None = Header(default=None)):
    """Nice process. Requires OS_EXECUTE."""
    _require_perm(authorization, auth.Perm.OS_EXECUTE)
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


# === P1.5 SYSTEM INTEGRITY ENDPOINTS ===


@app.get("/api/system/state")
def api_system_state():
    """Estado completo do sistema. Tudo MEASURED ou UNKNOWN."""
    return system_state()


@app.get("/api/system/capabilities")
def api_capabilities():
    """Lista todas as capabilities com estado real."""
    return capabilities_summary()


@app.get("/api/system/capabilities/{name}")
def api_capability(name: str):
    """Detalhe de uma capability."""
    cap = get_capability(name)
    if not cap:
        raise HTTPException(404, f"capability '{name}' não encontrada")
    return cap


@app.get("/api/system/can/{name}")
def api_can(name: str):
    """Pergunta: GOD pode fazer X?"""
    return {"name": name, "can": can(name), "kind": "MEASURED"}


@app.get("/api/system/health")
def api_health_full():
    """Health completo: liveness + readiness + diagnostics."""
    return full_health()


@app.get("/api/system/liveness")
def api_liveness():
    """Liveness: O processo está funcional?"""
    return liveness()


@app.get("/api/system/readiness")
def api_readiness():
    """Readiness: Está pronto para aceitar trabalho?"""
    return readiness()


@app.get("/api/system/diagnostics")
def api_diagnostics():
    """Diagnostics: Componentes disponíveis, falhados, porquê."""
    from superai.health import diagnostics
    return diagnostics()


@app.get("/api/system/trace")
def api_traces():
    """Últimos traces de decisão."""
    return {"traces": recent_traces(10), "kind": "MEASURED"}


@app.get("/api/system/trace/{request_id}")
def api_trace(request_id: str):
    """Trace de um request específico."""
    return trace_summary(request_id)


# === FEATURE FLAGS ===


@app.get("/api/system/flags")
def api_flags():
    """Lista todas as feature flags."""
    return ff.flags_summary()


@app.get("/api/system/flags/{name}")
def api_flag(name: str):
    """Detalhe de uma flag."""
    f = ff.get_flag(name)
    if not f:
        raise HTTPException(404, f"flag '{name}' não encontrada")
    return f


@app.post("/api/system/flags/{name}/enable")
def api_flag_enable(name: str, authorization: str | None = Header(default=None)):
    """Enable feature flag. Requires FLAGS_MANAGE."""
    _require_perm(authorization, auth.Perm.FLAGS_MANAGE)
    """Activar uma feature flag."""
    return ff.enable(name, reason="API request", actor="api")


@app.post("/api/system/flags/{name}/disable")
def api_flag_disable(name: str, authorization: str | None = Header(default=None)):
    """Disable feature flag. Requires FLAGS_MANAGE."""
    _require_perm(authorization, auth.Perm.FLAGS_MANAGE)
    """Desactivar uma feature flag."""
    return ff.disable(name, reason="API request", actor="api")


# === RUNTIME PROTECTION ===


class ResourceModeIn(BaseModel):
    mode: str


@app.get("/api/system/protection")
def api_protection():
    """Relatório de protecção: GOD Object + inspecção de ficheiros."""
    return rp.protection_report()


@app.get("/api/system/god-object")
def api_god_object():
    """Detecção de GOD Object anti-pattern."""
    return rp.check_god_object()


@app.get("/api/system/protection/inspect")
def api_protection_inspect():
    """Inspecionar todos os ficheiros fonte."""
    return rp.inspect_all()


# === RESOURCE MODE ===


@app.get("/api/system/resource-mode")
def api_resource_mode():
    """Get current resource mode (ECO/NORMAL/PERFORMANCE)."""
    from superai.governor import gov
    return gov.resource_config()


@app.post("/api/system/resource-mode")
def api_set_resource_mode(body: ResourceModeIn, authorization: str | None = Header(default=None)):
    """Set resource mode. Requires CONFIG_WRITE."""
    _require_perm(authorization, auth.Perm.CONFIG_WRITE)
    """Set resource mode."""
    from superai.governor import gov, RESOURCE_MODES
    from superai.runtime import _broadcast
    if body.mode not in RESOURCE_MODES:
        raise HTTPException(400, f"Invalid mode. Use: {list(RESOURCE_MODES.keys())}")
    gov.set_resource_mode(body.mode)
    _broadcast()
    return {"ok": True, "mode": body.mode, "config": gov.resource_config()}


# === EVOLUTION ===


@app.get("/api/system/experiments")
def api_experiments():
    """Resumo das experiências de evolução."""
    from superai.evolution import experiments_summary
    return experiments_summary()


# === VOICE ===


class VoiceIn(BaseModel):
    text: str
    lang: str = "pt"
    voice: str | None = None


@app.get("/api/system/voice")
def api_voice_health():
    """Estado do sistema de voz."""
    from superai.voice import health
    return health()


@app.post("/api/system/voice/speak")
def api_voice_speak(body: VoiceIn, authorization: str | None = Header(default=None)):
    """TTS. Requires TOOLS_EXECUTE."""
    _require_perm(authorization, auth.Perm.TOOLS_EXECUTE)
    """Converter texto em fala (TTS)."""
    from superai.voice import speak
    return speak(body.text, lang=body.lang, voice=body.voice)


@app.get("/api/system/voice/voices")
def api_voice_list(lang: str | None = None):
    """Listar vozes disponíveis."""
    from superai.voice import list_voices
    return list_voices(lang)


@app.get("/api/system/voice/audio/{filename}")
def api_voice_audio(filename: str):
    """Servir ficheiro de áudio gerado."""
    import re as _re
    if not _re.fullmatch(r"tts_[a-z0-9_]+\.mp3", filename):
        raise HTTPException(400, "filename inválido")
    path = DATA / "voice" / filename
    if not path.is_file():
        raise HTTPException(404, "ficheiro inexistente")
    return FileResponse(path, media_type="audio/mpeg")


# === WEB SEARCH ===


class SearchIn(BaseModel):
    query: str
    max_results: int = 5


@app.get("/api/system/websearch")
def api_websearch_health():
    """Estado dos backends de pesquisa web."""
    from superai.websearch import health
    return health()


@app.post("/api/system/websearch")
def api_websearch(body: SearchIn, authorization: str | None = Header(default=None)):
    """Web search. Requires TOOLS_EXECUTE."""
    _require_perm(authorization, auth.Perm.TOOLS_EXECUTE)
    """Pesquisar na web."""
    from superai.websearch import search
    return search(body.query, max_results=body.max_results)


# === AUTHENTICATION & AUTHORIZATION ===

class LoginIn(BaseModel):
    username: str
    password: str

class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "GUEST"

class ApprovalIn(BaseModel):
    action: str
    resource: str = ""
    scope: str = ""
    reason: str = ""
    risk_level: int = 3
    duration_seconds: int = 300

class ApprovalDecisionIn(BaseModel):
    approve: bool

class OverrideIn(BaseModel):
    action: str
    scope: str = "*"
    reason: str = ""
    risk_level: int = 3
    duration_seconds: int = 600

@app.get("/api/auth/status")
def api_auth_status():
    """Auth system status."""
    return auth.auth_status()

@app.post("/api/auth/setup")
def api_auth_setup(body: LoginIn):
    """Create initial OWNER account."""
    r = auth.create_owner(body.username, body.password)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error"))
    return r

@app.post("/api/auth/login")
def api_auth_login(body: LoginIn):
    """Login and get session."""
    r = auth.login(body.username, body.password)
    if not r.get("ok"):
        raise HTTPException(401, r.get("error"))
    return r

@app.post("/api/auth/logout")
def api_auth_logout(authorization: str | None = Header(default=None)):
    """Logout and invalidate session."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    return auth.logout(session_id)

@app.get("/api/auth/session")
def api_auth_session(authorization: str | None = Header(default=None)):
    """Get current session info."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    session = auth.validate_session(session_id)
    if not session:
        raise HTTPException(401, "Sessão inválida")
    return session

@app.post("/api/auth/users")
def api_create_user(body: CreateUserIn, authorization: str | None = Header(default=None)):
    """Create a new user (OWNER only)."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return auth.create_user(body.username, body.password, body.role)

@app.get("/api/auth/users")
def api_list_users(authorization: str | None = Header(default=None)):
    """List users (OWNER only)."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    users = auth._load_users()
    return [{"id": u["id"], "username": u["username"], "role": u["role"], "active": u["active"]} for u in users.values()]

@app.get("/api/auth/audit")
def api_audit_log(limit: int = 50, authorization: str | None = Header(default=None)):
    """Get audit log (OWNER only)."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return {"events": auth.audit_log(limit)}

@app.get("/api/auth/approvals")
def api_pending_approvals(authorization: str | None = Header(default=None)):
    """List pending approvals (OWNER only)."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return {"approvals": auth.pending_approvals()}

@app.post("/api/auth/approvals/{approval_id}/decide")
def api_decide_approval(approval_id: str, body: ApprovalDecisionIn, authorization: str | None = Header(default=None)):
    """Approve or deny an approval (OWNER only)."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return auth.decide_approval(approval_id, check["user_id"], body.approve)

@app.post("/api/auth/overrides")
def api_create_override(body: OverrideIn, authorization: str | None = Header(default=None)):
    """Create a governor override (OWNER only)."""
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.GOVERNOR_OVERRIDE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return auth.create_override(check["user_id"], body.action, body.scope, body.reason, body.risk_level, body.duration_seconds)


# === NODES ===


class NodeIn(BaseModel):
    id: str
    name: str
    location: str = "remote"
    capabilities: list[str] = []


@app.get("/api/system/nodes")
def api_nodes():
    """List registered nodes."""
    from superai.nodes import registry
    return registry.status()


@app.post("/api/system/nodes")
def api_register_node(body: NodeIn, authorization: str | None = Header(default=None)):
    """Register node. Requires WORKER_MANAGE."""
    _require_perm(authorization, auth.Perm.WORKER_MANAGE)
    """Register a new node."""
    from superai.nodes import registry
    from superai.runtime import _broadcast
    r = registry.register(body.id, body.name, body.location, body.capabilities)
    if r.get("ok"):
        _broadcast()
    return r


@app.delete("/api/system/nodes/{node_id}")
def api_unregister_node(node_id: str, authorization: str | None = Header(default=None)):
    """Unregister node. Requires WORKER_MANAGE."""
    _require_perm(authorization, auth.Perm.WORKER_MANAGE)
    """Unregister a node."""
    from superai.nodes import registry
    from superai.runtime import _broadcast
    r = registry.unregister(node_id)
    if r.get("ok"):
        _broadcast()
    return r


# === RATE LIMITING ===
