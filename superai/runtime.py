"""Runtime — dispatcher principal da GOD.

Orquestra: security → shortcuts → pipeline.
Helpers (_say, _broadcast, etc.) ficam aqui.
Pipeline e shortcuts estão em módulos separados.
"""
from __future__ import annotations

import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import aios, benchmark, evolution, executive, mission, observer, plane, providers, queue as tq, resources, routing, tokens as ti
from .brain import analyze, cache_lookup, cache_store, context_pack, evaluate
from .validator import validate
from .thirdeye import criticize
from .config import ROOT, cfg
from .events import bus
from .governor import gov
from .memory_vec import vectors
from .store import store
from . import gods
from .tools import catalog
from .util import now_iso, uid

_chat: list[dict] = []
_lock = threading.RLock()
_last_pipeline: dict | None = None
_bcast_timer: threading.Timer | None = None


# ── Helpers (staying in runtime.py) ──────────────────────────────────────────


def _say(role: str, text: str, replace_prefix: str | None = None) -> dict:
    msg = {"id": uid("m"), "role": role, "ts": now_iso(), "text": text}
    with _lock:
        if (
            replace_prefix
            and _chat
            and _chat[-1].get("role") == role
            and str(_chat[-1].get("text") or "").startswith(replace_prefix)
        ):
            _chat[-1] = msg
        else:
            _chat.append(msg)
            del _chat[:-80]
    bus.emit("CHAT", "INFO", f"{role}: {text[:80]}")
    _broadcast()
    return msg


def _mark(p: dict, name: str) -> None:
    """Δ ms desde o último marco. MEASURED, não estimado."""
    now = time.perf_counter()
    last = p.get("_tmark")
    if last is None:
        last = p.get("t0") or now
    p.setdefault("stages_ms", {})[name] = round((now - float(last)) * 1000, 1)
    p["_tmark"] = now


def _set_pipe(p: dict) -> None:
    global _last_pipeline
    t0 = p.pop("t0", None)
    p.pop("_tmark", None)
    if t0 is not None:
        p["latency_ms"] = round((time.perf_counter() - float(t0)) * 1000, 1)
        p["latency_kind"] = "MEASURED"
    if p.get("stages_ms"):
        p["stages_kind"] = "MEASURED"
    with _lock:
        _last_pipeline = p


def _broadcast() -> None:
    """Coalesce SSE snapshots. Qualidade igual; menos CPU/RAM no control plane."""
    global _bcast_timer

    def fire() -> None:
        global _bcast_timer
        _bcast_timer = None
        bus.publish("snapshot", snapshot())

    with _lock:
        if _bcast_timer is not None:
            try:
                _bcast_timer.cancel()
            except Exception:
                pass
        t = threading.Timer(0.2, fire)
        t.daemon = True
        _bcast_timer = t
        t.start()


def resolve_mode() -> tuple[str, str]:
    wanted = cfg.get("mode") or "auto"
    llm = providers.any_llm()
    if wanted == "offline" or (wanted == "auto" and not llm):
        return "OFFLINE", "Nenhum LLM probed up. Só cache, memória e ferramentas determinísticas."
    if wanted == "auto" and llm:
        return "TOKEN_SAVER", "Há pelo menos um LLM, mas auto prefere ferramentas e local."
    return wanted.upper(), "modo forçado na config"


def snapshot() -> dict:
    mode, reason = resolve_mode()
    health = providers.health_all()
    gw = routing.health()
    u = store.usage()
    llm_tasks = u.get("llm_calls", 0)
    claude_tasks = 0
    dep = None if llm_tasks == 0 else claude_tasks / llm_tasks
    bench = store.last_benchmark_run()
    exps = store.experiments(12)
    with _lock:
        chat = list(_chat)
        pipe = deepcopy(_last_pipeline)
    return {
        "mode": mode,
        "mode_reason": reason,
        "providers": health,
        "gateway": gw,
        "qdrant": vectors.health(),
        "tools": catalog(),
        "budgets": cfg.get("budgets"),
        "governor": {"strict": gov.strict(), "fs_root": str(gov.fs_root()), "python_timeout_s": gov.python_timeout()},
        "usage": u,
        "cache": store.cache_stats(),
        "memory": store.mem_counts(),
        "claude_dependency": {"claude_tasks": claude_tasks, "llm_tasks": llm_tasks, "ratio": dep},
        "tasks": store.tasks(30),
        "events": bus.history[:50],
        "last_pipeline": pipe,
        "last_rating": store.last_rating(),
        "benchmark": bench,
        "experiments": exps,
        "chat": chat,
        "host": resources.host(),
        "pc_node": resources.declared_node(),
        "layout": resources.layout(),
        "inflight": resources.inflight_cap(),
        "plane": plane.status(),
        "queue": tq.stats(),
        "mission": mission.snapshot(),
        "graph": tq.graph(12),
        "workers": tq.list_workers(),
        "jobs": tq.jobs(12),
        "away": tq.peek_away(),
        "eye": observer.latest(),
        "token": ti.snapshot(),
        "os": aios.snapshot(),
        "god": {
            "name": (gods.active() or {}).get("name") or "GOD",
            "pronoun": "ela",
            "github_url": "https://github.com/rpolicarpo100/GOD",
            "github_deployed": True,
            "github_ref": "main",
            "plane_in_product": False,
            "plane_project_id": (cfg.get("plane") or {}).get("project_id"),
            "plane_kind": (cfg.get("plane") or {}).get("kind") or "UNKNOWN",
            "active": gods.active(),
            "profiles": gods.list_gods(),
            "versions": gods.versions(gods.active_id()),
            "swarm": False,
            "desktop": False,
            "marketplace": False,
            "budget_eur": None,
            "budget_kind": "UNKNOWN",
        },
        "projects": _list_projects(),
        "unverified": [
            "embeddings neurais (em uso: HashingVectorizer, não FastEmbed/Ollama)",
            "SearXNG",
            "PostgreSQL (SQLite em uso)",
            "Redis",
            "Docker / Qdrant :6333 (embedded local sim)",
            "OmniRoute npm :20128" + (" up" if gw["omniroute"]["available"] else " down — DirectAdapter"),
            "API €/1M (cost=UNKNOWN — não aplicar tabela Claude a Groq)",
            "este processo ≠ PC i5-4590 24GB (USER_DECLARED)",
            "Langfuse / LiteLLM (ausentes; core interno)",
        ],
        "counts": {
            "agents_on": 0,
            "tasks_live": sum(1 for t in store.tasks(20) if t.get("status") in ("running", "analyzed")),
            "events": len(bus.history),
            "pending_exp": sum(1 for e in exps if e.get("status") == "pending"),
        },
    }


def _extract_path(text: str) -> str | None:
    m = re.search(r"(/home/user[^\s]+|super-ai[^\s]*|[\w./-]+\.(py|json|yaml|md|html|csv|xml|txt))", text)
    if m:
        p = m.group(0)
        cand = Path(p)
        if not cand.is_absolute():
            cand = ROOT / p if not p.startswith("super-ai") else ROOT.parent / p
            if p.startswith("super-ai"):
                cand = ROOT if p in ("super-ai", "super-ai/") else ROOT.parent / p
        return str(cand)
    if re.search(r"\b(neste (projecto|repo)|aqui|super-ai)\b", text.lower()):
        return str(ROOT)
    return None


def _extract_code(text: str) -> str | None:
    m = re.search(r"```(?:python)?\n([\s\S]+?)```", text)
    if m:
        return m.group(1)
    return None


def _plan(task: dict) -> dict:
    """LLM-last. Never invert without reason. Delegates to pipeline.plan()."""
    from .pipeline import plan
    return plan(task)


def _index_task(task: dict, text: str, scores: dict) -> None:
    from .pipeline import _index_task as _it
    _it(task, text, scores)


def _fmt_bench(s: dict) -> str:
    lines = [
        f"BENCHMARK {s['run_id']}  n={s['n']}  passed={s['passed']}  skipped={s['skipped']}  n_llm_samples={s['n_llm_samples']}",
        s.get("note") or "",
    ]
    for r in s.get("rows") or []:
        st = "SKIP" if r.get("skipped") else ("PASS" if r.get("passed") else "FAIL")
        lines.append(f"  {st} {r['case_id']}  score={r.get('score')}  {r.get('provider')}  {r.get('skip_reason') or ''}  {r.get('latency_ms')}ms")
    return "\n".join(lines)


def _dialogue(n: int = 4, current: str | None = None) -> list[str]:
    """Últimos turnos do chat vivo. Sem placeholder, sem rodapé de tokens."""
    with _lock:
        msgs = list(_chat)
    cur = (current or "").strip()
    out: list[str] = []
    skipped_current = False
    for m in reversed(msgs):
        role = m.get("role")
        text = str(m.get("text") or "").strip()
        if role not in ("user", "brain") or not text:
            continue
        if text.startswith("Um momento"):
            continue
        if role == "user" and cur and text == cur and not skipped_current:
            skipped_current = True
            continue
        if role == "brain" and "\n\n— GOD ·" in text:
            text = text.split("\n\n— GOD ·", 1)[0].strip()
        who = "TU" if role == "user" else "GOD"
        out.append(f"{who}: {text[:180]}")
        if len(out) >= n:
            break
    out.reverse()
    return out


def _llm_prompt(text: str, merged: list[dict], dialogue: list[str] | None = None) -> str:
    """Pedido + diálogo curto + memória. Sem dump TASK/TYPE."""
    parts = [
        "És a GOD. Falas no feminino. Inteligência profissional, analítica, orientada a resultados. "
        "Compreende o objectivo antes de responder. Não inventes APIs, dados, ferramentas, preços, resultados nem capacidades. "
        "Se não souberes, diz. Distingue facto, estimativa, hipótese e opinião. Prefere simples e verificável. "
        "Solução primeiro; detalhes depois. Grelha Objectivo/Análise/Solução só se o pedido for complexo. "
        "Não tens pesquisa web (SearXNG ausente) nem embeddings neurais. "
        "Se criares um site, emite ficheiros em fences com path: ```html index.html … ``` "
        "Só HTML/CSS/JS em data/projects — não alteras o núcleo GOD. "
        "Usa o diálogo recente se o pedido for anafórico (isto, isso, e o CSS, continua). "
        "Prioridade: Verdade → Precisão → Segurança → Utilidade → Eficiência → Simplicidade."
    ]
    ov = gods.prompt_overlay()
    if ov:
        parts.append(ov)
    if dialogue:
        parts.append("Diálogo:\n" + "\n".join(dialogue[:4]))
    mem: list[str] = []
    for m in (merged or [])[:3]:
        v = str(m.get("value") or m.get("text") or "").strip()
        if v:
            mem.append(v[:240])
    if mem:
        parts.append("Memória:\n" + "\n".join(f"- {x}" for x in mem))
    parts.append("USER: " + text)
    return "\n\n".join(parts)


def _list_projects() -> list[dict]:
    from .tools import PROJECTS

    out = []
    if PROJECTS.exists():
        for d in sorted(PROJECTS.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                out.append({"slug": d.name, "index": (d / "index.html").is_file(), "preview": f"/preview/{d.name}/"})
    return out[:20]


def _slug(text: str) -> str:
    from .tools import project_slug
    return project_slug(text)


def _extract_files(text: str) -> list[tuple[str, str]]:
    """Fences ```lang path\nbody```. Delegates to pipeline."""
    from .pipeline import _extract_files as _ef
    return _ef(text)


def _publish_files(title: str, files: list[tuple[str, str]]) -> dict:
    from .pipeline import _publish_files as _pf
    return _pf(title, files)


def _llm_text(tool_results: list[dict]) -> str | None:
    for r in tool_results:
        if not str(r.get("tool") or "").startswith("llm:"):
            continue
        f0 = (r.get("findings") or [None])[0]
        if isinstance(f0, dict) and f0.get("text"):
            return str(f0["text"]).strip()
        if isinstance(f0, str) and f0.strip():
            return f0.strip()
    return None


def _format_result(task: dict, pipeline: dict, tool_results: list[dict], scores: dict | None, blocked: str | None) -> str:
    speech = None if blocked else _llm_text(tool_results)
    if speech:
        ev = ""
        for r in tool_results:
            if r.get("evidence"):
                ev = str(r["evidence"][0])
                break
        toks = scores.get("tokens_actual") if scores else None
        kind = "MEASURED" if toks else "UNKNOWN"
        return f"{speech}\n\n— GOD · {ev or 'llm'} · tokens {toks} {kind} · cost UNKNOWN"

    fw = pipeline.get("firewall") or {}
    lines = [
        f"Tarefa {task['task_id']} · tipo {task['type']} · complexidade {task['complexity']}/10",
        f"reasoning_budget={task['reasoning_budget']} · est. {task['estimated_tokens']} tokens (tiktoken)",
        f"Firewall: {fw.get('action') or 'n/a'}" + (f" · {'; '.join(fw['reasons'])}" if fw.get("reasons") else ""),
        f"Cache: {pipeline.get('cache')}",
        f"Decisão: {' → '.join(pipeline.get('route') or [])}",
    ]
    if blocked:
        lines += ["", blocked]
    for r in tool_results:
        lines.append("")
        lines.append(f"[{r.get('tool')}] status={r.get('status')} confiança={r.get('confidence')}")
        for e in r.get("evidence") or []:
            lines.append(f"  evidência: {e}")
        for f in (r.get("findings") or [])[:12]:
            lines.append(f"  {f}")
        for err in r.get("errors") or []:
            lines.append(f"  erro: {err}")
    if scores:
        lines.append("")
        lines.append(
            f"QUALITY {scores['QUALITY']}  CORRECTNESS {scores['CORRECTNESS']}  "
            f"TOKEN_EFF {scores['TOKEN_EFFICIENCY']}  OVERALL {scores['OVERALL']}/100"
        )
        lines.append(f"LLM usado: {scores['llm_used']} · tokens LLM: {scores['tokens_actual']}")
    val = pipeline.get("validation")
    if val:
        vc = val.get("n_passed", 0)
        vt = val.get("n_checks", 0)
        lines.append(f"Validator: {vc}/{vt} checks passed (confidence {val.get('confidence', 0)})")
    crit = pipeline.get("critique")
    if crit:
        ci = crit.get("n_issues", 0)
        ct = crit.get("n_findings", 0)
        lines.append(f"Third Eye: {crit.get('overall', '?')} · {ct} findings, {ci} issues")
    lines.append("")
    via = task.get("via") or (pipeline.get("route") or ["?"])[-1]
    lines.append(f"Via {via}. Não inventei providers nem preços. Incerteza é reportada.")
    return "\n".join(lines)


def _enqueue(kind: str, text: str, parent_id: str | None = None, mission_id: str | None = None) -> dict:
    adm = aios.admit(kind, text)
    if not adm.get("ok"):
        _say(
            "brain",
            "OS recusou admissão (MEASURED).\n"
            f"reason={adm.get('reason')} pressure={adm.get('pressure')} ram_avail={adm.get('ram_avail_mb')}MB",
        )
        _broadcast()
        return {"ok": True, "via": "os_admit", "admitted": False, "reason": adm.get("reason")}
    loc = adm["loc"]
    if not loc.get("enqueue"):
        return {"skip": True, "loc": loc}
    job = tq.enqueue(
        kind,
        text,
        None,
        loc.get("location") or "LOCAL_WORKER",
        parent_id=parent_id,
        mission_id=mission_id,
    )
    note = "dedup — já na fila, não duplico." if job.get("deduped") else "O PC não executa isto no pedido HTTP. A fila e o worker tratam. Eventos chegam por SSE."
    if kind == "chat":
        _say("brain", f"Um momento — a pensar ({loc['location']}, job {job['id']}).")
    else:
        _say(
            "brain",
            f"CONTROL → COMPUTE\n{loc['reason']}\njob {job['id']} · {kind} · {loc['location']}\n{note}",
        )
    _broadcast()
    return {"ok": True, "via": "queue", "job": job["id"], "location": loc["location"]}


# ── Main dispatcher ─────────────────────────────────────────────────────────


def handle(text: str, from_worker: bool = False) -> dict:
    """Dispatcher: security → shortcuts → pipeline.
    
    Reduzido de586 linhas para ~40 linhas.
    Shortcuts em superai/shortcuts.py. Pipeline em superai/pipeline.py.
    """
    global _last_pipeline
    text = (text or "").strip()
    if not text:
        return {"ok": False}
    if not from_worker:
        _say("user", text)

    low = text.lower()

    # Security check
    if gov.strict() and any(x in low for x in ("desliga o governor", "desligar o governor", "remove os limites")):
        msg = "Recusado. O Governor não se altera a si próprio a partir deste canal."
        _say("brain", msg)
        bus.emit("SECURITY_ALERT", "SECURITY", "tentativa de alterar o governor")
        return {"ok": True, "blocked": True}

    # Shortcuts (token, web, roadmap, OS, repair, missions, observer, benchmark, evolution)
    from .shortcuts import try_shortcuts
    handled, result = try_shortcuts(
        text, low, from_worker,
        _say=_say, _broadcast=_broadcast, _last_pipeline=_last_pipeline,
        _fmt_bench=_fmt_bench, _enqueue=_enqueue, resolve_mode=resolve_mode,
    )
    if handled:
        return result

    # "depois" command chaining
    dm = re.match(r"^\s*(depois|em seguida)\s*[:.\-]\s+(.+)$", text, re.I | re.S)
    if dm:
        body = dm.group(2).strip()
        last = tq.last_open() or tq.last_job()
        mid = (mission.active() or {}).get("id")
        if last and last.get("status") in ("queued", "assigned", "running"):
            q = _enqueue("chat", body, parent_id=last.get("id"), mission_id=mid)
            if not q.get("skip"):
                return q
        text = body
        low = text.lower()

    # Core pipeline
    from .pipeline import run_pipeline
    task = analyze(text)
    return run_pipeline(
        text, task, from_worker,
        _say=_say, _mark=_mark, _set_pipe=_set_pipe, _broadcast=_broadcast,
        _format_result=_format_result, _llm_prompt=_llm_prompt,
        _dialogue=_dialogue, _enqueue=_enqueue, _lock=_lock,
    )


def set_params(patch: dict) -> dict:
    out = cfg.patch(patch)
    store.audit("human", "config", str(patch)[:500])
    bus.emit("NOTICE", "NOTICE", f"config patch {list(patch)}")
    _broadcast()
    return out


def boot() -> None:
    gods.ensure()
    if not _chat:
        mode, reason = resolve_mode()
        _say(
            "brain",
            "Sou a GOD. Estou online. Constituição: verdade primeiro. Não invento.\n\n"
            f"Modo {mode}. {reason}\n"
            "LLM last. OS: admit/syscall/kill/ps. Terceiro olho a observar.\n"
            "Leve corre aqui. Pesado vai ao worker. Sem provider, eu digo que não há.\n"
            "Fala comigo no chat. Sites que eu gravar abrem em /preview neste servidor — não na cloud.",
        )


boot()
