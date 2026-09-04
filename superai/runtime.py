from __future__ import annotations

import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import aios, benchmark, evolution, observer, providers, queue as tq, resources, routing, tokens as ti
from .brain import analyze, cache_lookup, cache_store, context_pack, evaluate
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
        "queue": tq.stats(),
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
            "preços de modelos (cost=UNKNOWN — sem source verificada)",
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
    """LLM-last. Never invert without reason."""
    ttype = task["type"]
    text = task["text"]
    steps: list[dict] = []
    needs_llm = False
    reason = []

    if ttype == "status":
        steps.append({"tool": None, "kind": "status"})
        reason.append("estado do sistema é determinístico")
    elif ttype == "math":
        steps.append({"tool": "calculator", "args": {"expr": text}})
        reason.append("aritmética → calculator")
    elif ttype == "git":
        args = ["status"]
        if re.search(r"\blog\b", text.lower()):
            args = ["log", "-5", "--oneline"]
        elif re.search(r"\bdiff\b", text.lower()):
            args = ["diff", "--stat"]
        steps.append({"tool": "git", "args": {"args": args}})
        reason.append("git allowlist")
    elif ttype == "files":
        path = _extract_path(text) or str(ROOT)
        if re.search(r"\b(l[eê]|read|cat|abre|mostra)\b", text.lower()) and Path(path).is_file():
            steps.append({"tool": "fs.read", "args": {"path": path}})
        else:
            steps.append({"tool": "fs.list", "args": {"path": path}})
        reason.append("filesystem")
    elif ttype == "parse":
        path = _extract_path(text)
        if path and path.endswith(".json"):
            steps.append({"tool": "json", "args": {"path": path}})
        elif path and path.endswith(".csv"):
            steps.append({"tool": "csv", "args": {"path": path}})
        elif path and path.endswith(".xml"):
            steps.append({"tool": "xml", "args": {"path": path}})
        elif re.search(r"\{", text):
            m = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", text)
            steps.append({"tool": "json", "args": {"text": m.group(1) if m else text}})
        else:
            needs_llm = True
            reason.append("parse sem payload — não inventar")
        if steps:
            reason.append("parser determinístico")
    elif ttype == "python":
        code = _extract_code(text)
        if code:
            steps.append({"tool": "python", "args": {"code": code}})
            reason.append("python sandbox")
        else:
            needs_llm = True
            reason.append("pedido de código sem bloco executável")
    elif ttype == "regex":
        needs_llm = True
        reason.append("regex sem padrão explícito — não adivinhar")
    elif ttype in ("research", "coding", "general"):
        needs_llm = True
        reason.append(f"tipo {ttype} não tem ferramenta determinística suficiente")

    return {"steps": steps, "needs_llm": needs_llm, "reason": reason}


def _index_task(task: dict, text: str, scores: dict) -> None:
    if not vectors.available():
        return
    try:
        from .util import normalize_query, sha

        gid = gods.active_id()
        vectors.upsert("memory", task["task_id"], text, {"type": task.get("type"), "overall": scores.get("OVERALL"), "god_id": gid})
        vectors.upsert("cache", sha(normalize_query(text) + f"\n{gid}"), text, {"task_id": task["task_id"], "god_id": gid})
    except Exception:
        pass


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
    """Fences ```lang path\\nbody```. Never invent a path outside the fence."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"```([^\n]*)\n([\s\S]*?)```", text or ""):
        header = (m.group(1) or "").strip().split()
        body = m.group(2) or ""
        path = None
        if len(header) >= 2:
            path = header[1].lstrip("/")
        else:
            first = body.splitlines()[0].strip() if body.splitlines() else ""
            if first.startswith(("<!-- file:", "# file:", "file:")):
                path = first.split(":", 1)[-1].replace("-->", "").strip().lstrip("/")
                body = "\n".join(body.splitlines()[1:])
        lang = (header[0] if header else "").lower()
        if not path:
            if lang in ("html", "htm") and not any(p == "index.html" for p, _ in out):
                path = "index.html"
            elif lang == "css" and not any(p.endswith(".css") for p, _ in out):
                path = "styles.css"
            elif lang in ("js", "javascript") and not any(p.endswith(".js") for p, _ in out):
                path = "app.js"
        if path and ".." not in Path(path).parts:
            out.append((path, body.strip() + "\n"))
        if len(out) >= 8:
            break
    return out


def _publish_files(title: str, files: list[tuple[str, str]]) -> dict:
    from .tools import execute as tool_exec

    slug = _slug(title)
    written = []
    errors = []
    for rel, body in files:
        r = tool_exec("fs.write", {"slug": slug, "path": rel, "text": body})
        if r.get("status") == "success":
            written.append(rel)
        else:
            errors.extend(r.get("errors") or ["write fail"])
    return {
        "slug": slug,
        "written": written,
        "errors": errors,
        "preview": f"/preview/{slug}/" if written else None,
    }


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
    lines.append("")
    via = task.get("via") or (pipeline.get("route") or ["?"])[-1]
    lines.append(f"Via {via}. Não inventei providers nem preços. Incerteza é reportada.")
    return "\n".join(lines)


def _enqueue(kind: str, text: str) -> dict:
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
    job = tq.enqueue(kind, text, None, loc.get("location") or "LOCAL_WORKER")
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


def handle(text: str, from_worker: bool = False) -> dict:
    global _last_pipeline
    text = (text or "").strip()
    if not text:
        return {"ok": False}
    if not from_worker:
        _say("user", text)

    low = text.lower()
    if gov.strict() and any(x in low for x in ("desliga o governor", "desligar o governor", "remove os limites")):
        msg = "Recusado. O Governor não se altera a si próprio a partir deste canal."
        _say("brain", msg)
        bus.emit("SECURITY_ALERT", "SECURITY", "tentativa de alterar o governor")
        return {"ok": True, "blocked": True}

    if re.search(r"economia de tokens|token intelligence|relat[oó]rio de tokens", low):
        snap = ti.snapshot()
        u, b, f, c = snap["usage"], snap["budget"], snap["forecast"], snap["cost"]
        rp = snap.get("report") or ti.report()
        cs = rp.get("cache_savings") or {}
        cx = rp.get("context_savings") or {}
        md = rp.get("models") or {}
        lines = [
            "TOKEN ECONOMY REPORT — MEASURED vs ESTIMATED vs FORECAST vs UNKNOWN.",
            f"MEASURED session={u['session_tokens']} daily={u['daily_tokens']} actual_sum={u['sum_actual']} llm_calls={u['llm_calls']}",
            f"ESTIMATED sum={u['sum_estimated']}  (tiktoken; não é consumo de provider)",
            f"COST {c['kind']}: {c.get('reason')}",
            f"BUDGET daily used={b['daily']['used_measured']}/{b['daily']['limit']} hard={b['daily']['hard']}",
            f"CACHE hits={cs.get('hits_measured')} estimated_savings={cs.get('estimated_savings')} actual_savings={cs.get('actual_savings')} ({cs.get('actual_kind')})",
            f"CONTEXT saved_est={cx.get('tokens_saved_estimated')} actual={cx.get('actual_savings')} ({cx.get('actual_kind')})",
            f"MODELS {md.get('kind')}: {md.get('reason') or md.get('models')}",
            f"FORECAST {f['kind']} status={f.get('status')} {f.get('reason') or ''}",
            f"useful_work/token {snap['efficiency'].get('useful_work_per_token')} ({snap['efficiency'].get('kind')})",
            f"Langfuse {snap['externals']['langfuse']['available']} LiteLLM {snap['externals']['litellm']['available']}",
        ]
        _say("brain", "\n".join(lines))
        _broadcast()
        return {"ok": True, "via": "tokens"}

    if re.search(r"pesquisa na (web|internet)|search the web|\bsearxng\b|\bgoogle\b.*\b(pesquisa|search)", low):
        _say(
            "brain",
            "SearXNG ausente. Pesquisa web NÃO foi feita. Não invento resultados da internet. "
            "Reformula com o que está neste repo, ou um cálculo/git/ficheiro.",
        )
        _broadcast()
        return {"ok": True, "via": "no_web", "blocked": True}

    if re.search(r"^\s*(roadmap|fluxo)\s*$", low) or re.search(r"\broadmap\b", low):
        os_s = aios.snapshot()
        llm = providers.any_llm()
        lines = [
            "Sou a GOD. Falo no feminino. Não sou um tab de documentação.",
            f"Modo {resolve_mode()[0]}. GPU required=false. OS booted={os_s.get('booted')} syscalls={os_s.get('syscalls')}.",
            "FEITO: F0 infra · F1 LLM-last · F2 memória hashing · F3 fila · F4 tokens · F5 OS.",
            f"F6 LLM vivo: {'sim' if llm else 'não'} — up={[h['id'] for h in providers.health_all() if h.get('available')]} · Ollama local={'up' if any(h['id']=='ollama' and h.get('available') for h in providers.health_all()) else 'down'}. F7 GitHub publicado. F8 Plane não no produto.",
            "Não adiciono camadas nem resultados de pesquisa fictícios. Sem provider, recuso.",
        ]
        _say("brain", "\n".join(lines))
        _broadcast()
        return {"ok": True, "via": "roadmap"}

    if re.search(r"^\s*(ps|dmesg|uname)\s*$", low) or low.strip() in ("kernel", "os", "superai os", "estado do kernel"):
        snap = aios.snapshot()
        lines = [
            f"{snap['sysname']} {snap['version']}  uptime={snap['uptime_s']}s  {snap['kind']}",
            f"pressure={snap['pressure']} ram_avail={snap['ram_avail_mb']}MB  gpu_required=false  preempt=false",
            f"ready={snap['ready']} running={snap['running']} killed={snap['killed']} syscalls={snap['syscalls']}",
            f"quota agent {snap['quota']['used_measured']}/{snap['quota']['limit']} {snap['quota']['kind']}",
        ]
        if low.strip() == "dmesg":
            evs = aios.dmesg(16)
            if not evs:
                lines.append("dmesg vazio (ainda sem SYSCALL/OS_* neste processo)")
            for e in evs:
                lines.append(f"  {e.get('name')}  {e.get('msg')}")
        else:
            for pproc in (aios.ps(16).get("processes") or []):
                lines.append(
                    f"  {(pproc.get('status') or ''):8} {pproc.get('pid')} {pproc.get('type')} {pproc.get('kind') or ''} prio={pproc.get('priority')}"
                )
        _say("brain", "\n".join(lines))
        _broadcast()
        return {"ok": True, "via": "os"}

    km = re.match(r"^\s*kill\s+(\S+)\s*$", low)
    if km:
        r = aios.kill(km.group(1))
        _say("brain", f"OS kill {km.group(1)}: ok={r.get('ok')} {r.get('status') or r.get('reason')}")
        _broadcast()
        return {"ok": True, "via": "os"}

    if re.search(r"^\s*(repara|repair|conserta)\s*$", low):
        from . import repair

        r = repair.run()
        lines = [f"REPAIR {r['kind']} ok={r['ok']}", r.get("note") or ""]
        for a in r.get("actions") or []:
            lines.append(f"  {a.get('check')} ok={a.get('ok')} {a.get('error') or a.get('fix') or ''}")
        _say("brain", "\n".join(lines))
        _broadcast()
        return {"ok": True, "via": "repair", "repair": r}

    if re.search(r"terceiro olho|olho do sistema|\bobserva sistema\b", low):
        eye = observer.tick()
        m = eye["metrics"]
        lines = [
            "TERCEIRO OLHO — só factos medidos.",
            f"ok={eye['ok']}  pressure={m.get('pressure')}  load1={m.get('cpu_load1')}  ram_avail={m.get('ram_avail_mb')}MB",
            f"fila={m.get('queue_depth')}  workers_alive={m.get('workers_alive')} dead={m.get('workers_dead')}",
            f"cache_hit={m.get('cache_hit_rate')}  tools={m.get('tool_calls')}  llm={m.get('llm_calls')}",
            f"avg_overall={m.get('avg_overall')} n={m.get('rating_n')}  useful_work/token={m.get('useful_work_per_token')}",
            f"blocked_no_provider={m.get('blocked_no_provider')}  GPU required=false present={m.get('gpu_present')}",
        ]
        if eye["alerts"]:
            lines.append("ALERTAS:")
            for a in eye["alerts"]:
                lines.append(f"  [{a['level']}] {a['code']}: {a['msg']}")
        else:
            lines.append("Sem alertas.")
        _say("brain", "\n".join(lines))
        _broadcast()
        return {"ok": True, "via": "observer"}

    if re.search(r"\b(corre|run|executa)\b.*\bbenchmark|\bbenchmark\b", low):
        if not from_worker:
            q = _enqueue("benchmark", text)
            if not q.get("skip"):
                return q
        s = benchmark.run("chat" if not from_worker else "worker")
        _say("brain", _fmt_bench(s))
        _broadcast()
        return {"ok": True, "via": "benchmark"}

    if re.search(r"\b(observa|ciclo de evolu|evolution cycle|evolu[cç][aã]o)\b", low):
        if not from_worker:
            q = _enqueue("evolution", text)
            if not q.get("skip"):
                return q
        cyc = evolution.run_cycle()
        exp = cyc["experiment"]
        _say(
            "brain",
            "EVOLUTION CYCLE\n"
            f"gaps: {cyc['observe'].get('gaps')}\n"
            f"hash paráfrases {cyc['observe']['hash_paraphrase_hits']}/{cyc['observe']['pairs']} · "
            f"semantic {cyc['observe']['semantic_paraphrase_hits']}/{cyc['observe']['pairs']}\n"
            f"benchmark {cyc['benchmark']['run_id']} passed={cyc['benchmark']['passed']} skipped={cyc['benchmark']['skipped']} n_llm={cyc['benchmark']['n_llm_samples']}\n"
            f"experiência {exp['id']} [{exp['status']}] {exp['title']}\n"
            f"{exp['hypothesis']}\n"
            "Nada entrou em produção sem ADOPT.",
        )
        _broadcast()
        return {"ok": True, "via": "evolution"}

    if re.search(r"\baprova\b", low):
        pend = evolution.pending()
        if not pend:
            _say("brain", "Não há experiências pendentes.")
            return {"ok": True, "via": "evolution"}
        _say("brain", evolution.decide(pend[0]["id"], True))
        _broadcast()
        return {"ok": True, "via": "evolution"}

    if re.search(r"\brejeita\b", low):
        pend = evolution.pending()
        if not pend:
            _say("brain", "Não há experiências pendentes.")
            return {"ok": True, "via": "evolution"}
        _say("brain", evolution.decide(pend[0]["id"], False))
        _broadcast()
        return {"ok": True, "via": "evolution"}

    # 1 analyzer
    task = analyze(text)
    task["status"] = "running"
    store.save_task(task)
    store.audit("user", "task", task["task_id"])
    bus.emit("TASK_CREATED", "INFO", f"{task['task_id']} · {task['type']} · est {task['estimated_tokens']} tok")

    pipeline = {
        "task": {k: task[k] for k in ("task_id", "type", "complexity", "reasoning_required", "estimated_tokens", "reasoning_budget", "privacy", "tool_requirement")},
        "cache": "miss",
        "memory_hits": 0,
        "firewall": None,
        "route": [],
        "providers": providers.health_all(),
    }

    # 2 cache (hash then semantic / Qdrant)
    gid = gods.active_id()
    hit = cache_lookup(text, gid)
    if not hit and cfg.get("evolution_policy", "semantic_cache", default=True) is not False and vectors.available():
        sem = vectors.search("cache", text, k=1, min_score=0.88, god_id=gid)
        pipeline["vector_cache"] = sem[:1]
        if sem and sem[0].get("key"):
            hit = store.cache_get(sem[0]["key"])
            if hit:
                pipeline["cache"] = "semantic"
    if hit:
        store.incr("cache_hits")
        bus.emit("CACHE_HIT", "INFO", f"{task['task_id']} {pipeline.get('cache') or 'hash'} cache")
        pipeline["cache"] = pipeline.get("cache") if pipeline.get("cache") == "semantic" else "hit"
        pipeline["route"] = ["CACHE"] if pipeline["cache"] != "semantic" else ["SEMANTIC_CACHE"]
        task["status"] = "done"
        task["via"] = "cache"
        store.save_task(task)
        ti.record(
            task_id=task["task_id"],
            estimated=task.get("estimated_tokens"),
            actual=0,
            status="cache_hit",
            cache_hit=True,
            via="cache",
        )
        with _lock:
            _last_pipeline = pipeline
        summ = hit["result"].get("summary") if isinstance(hit.get("result"), dict) else hit.get("result")
        if isinstance(summ, str) and summ.strip():
            _say("brain", summ)
        else:
            _say(
                "brain",
                "CACHE HIT.\n\n"
                + _format_result(task, pipeline, [], None, None)
                + "\n\n"
                + str(summ)[:2500],
            )
        _broadcast()
        return {"ok": True, "via": "cache"}

    store.incr("cache_misses")
    bus.emit("CACHE_MISS", "INFO", task["task_id"])

    # 3 memory
    gact = gods.active()
    if gact.get("memory", True) is False:
        mem, vec_mem = [], []
    else:
        gid = gods.active_id()
        kinds = ["episode", "episode:master"] if gid == "master" else [f"episode:{gid}"]
        mem = store.mem_search(text, kinds=kinds)
        vec_mem = vectors.search("memory", text, k=5, min_score=0.35, god_id=gid) if vectors.available() else []
    pipeline["memory_hits"] = len(mem)
    pipeline["vector_hits"] = vec_mem
    merged = list(mem)
    for v in vec_mem:
        merged.append({"kind": "vector", "key": v.get("key"), "value": v.get("text"), "score": v.get("score")})
    ctx = context_pack(task, merged)
    raw_ctx = (task.get("text") or "") + "\n" + "\n".join(str(m.get("value") or m.get("text") or "") for m in merged)
    pipeline["context"] = ti.context_efficiency(raw_ctx, ctx["text"])
    pipeline["route_token"] = ti.route_advice(task)

    # 4 firewall (Token Intelligence wrap — mesma política)
    fw = ti.gate(task, extra_tokens=ctx["tokens"])
    pipeline["firewall"] = fw
    if fw["action"] == "optimize":
        slim = merged[:2]
        ctx2 = context_pack(task, slim, limit=2)
        pipeline["context_optimize"] = ti.context_efficiency(ctx["text"], ctx2["text"])
        ctx = ctx2
        merged = slim
        pipeline["context"] = pipeline["context_optimize"]
        bus.emit(
            "TOKEN_OPTIMIZED",
            "INFO",
            f"{task['task_id']} context ESTIMATED saved={pipeline['context_optimize'].get('tokens_saved')}",
        )
        fw = ti.gate(task, extra_tokens=ctx["tokens"])
        pipeline["firewall"] = fw
    if fw["action"] == "reject":
        pipeline["route"] = ["TOKEN_FIREWALL_REJECT"]
        task["status"] = "rejected"
        store.save_task(task)
        with _lock:
            _last_pipeline = pipeline
        _say("brain", _format_result(task, pipeline, [], None, "Firewall rejeitou a chamada. Comprime, reduz âmbito, ou sobe o budget."))
        _broadcast()
        return {"ok": True, "via": "firewall"}

    # 5 plan (tools vs llm)
    plan = _plan(task)
    tool_results: list[dict] = []
    blocked = None

    if not from_worker and plan.get("needs_llm") and providers.any_llm():
        q = _enqueue("chat", text)
        if not q.get("skip"):
            pipeline["route"].append("QUEUE:" + q.get("location", ""))
            task["status"] = "queued"
            task["via"] = "queue"
            store.save_task(task)
            with _lock:
                _last_pipeline = pipeline
            return q

    if plan["steps"] and not (len(plan["steps"]) == 1 and plan["steps"][0].get("kind") == "status"):
        pipeline["route"].append("DETERMINISTIC_TOOLS")
        for step in plan["steps"]:
            if not step.get("tool"):
                continue
            bus.emit("TOOL_STARTED", "INFO", step["tool"])
            store.incr("tool_calls")
            res = aios.syscall(step["tool"], step.get("args") or {}, actor=task["task_id"])
            tool_results.append(res)
            if res.get("status") != "success":
                bus.emit("TOOL_FAILED", "WARNING", f"{step['tool']}: {res.get('errors')}")
        scores = evaluate(task, tool_results, llm_used=False, tokens_actual=0)
        ti.record(
            task_id=task["task_id"],
            estimated=task["estimated_tokens"],
            actual=0,
            status="ok",
            via="tools",
            quality_score=scores.get("OVERALL"),
            context_tokens=ctx.get("tokens"),
            context=pipeline.get("context"),
            route_advice=pipeline.get("route_token"),
        )
        store.mem_put(f"episode:{gods.active_id()}", task["title"], {"task_id": task["task_id"], "type": task["type"], "overall": scores["OVERALL"]})
        cache_store(text, {"summary": tool_results, "scores": scores}, scores["OVERALL"], ns=gods.active_id())
        _index_task(task, text, scores)
        task["status"] = "done"
        task["via"] = "tools"
        task["rating"] = scores
        store.save_task(task)
        bus.emit("TASK_COMPLETED", "INFO", f"{task['task_id']} overall {scores['OVERALL']} via tools")
        pipeline["scores"] = scores
        with _lock:
            _last_pipeline = pipeline
        _say("brain", _format_result(task, pipeline, tool_results, scores, None))
        _broadcast()
        return {"ok": True, "via": "tools"}

    if plan["steps"] and plan["steps"][0].get("kind") == "status":
        pipeline["route"].append("DETERMINISTIC_STATE")
        snap = snapshot()
        findings = {
            "mode": snap["mode"],
            "mode_reason": snap["mode_reason"],
            "providers": [{k: p[k] for k in ("id", "available", "error")} for p in snap["providers"]],
            "usage": snap["usage"],
            "cache": snap["cache"],
            "budgets": snap["budgets"],
        }
        tool_results = [{"tool": "state", "status": "success", "confidence": 1.0, "findings": [findings], "errors": [], "evidence": ["snapshot local"]}]
        scores = evaluate(task, tool_results, False, 0)
        ti.record(task_id=task["task_id"], estimated=0, actual=0, status="ok", via="state")
        task["status"] = "done"
        task["via"] = "state"
        store.save_task(task)
        with _lock:
            _last_pipeline = pipeline
        _say("brain", _format_result(task, pipeline, tool_results, scores, None))
        _broadcast()
        return {"ok": True, "via": "state"}

    # 6 Intelligent Router → RoutingAdapter (OmniRoute se up, senão Direct)
    pipeline["route"].append("INTELLIGENT_ROUTER")
    gw = routing.health()
    pipeline["gateway"] = {"active": gw["active"], "omniroute": gw["omniroute"]["available"], "direct": gw["direct"]["available"]}
    if not gw["omniroute"]["available"] and not gw["direct"]["available"]:
        pipeline["route"].append("NO_PROVIDER")
        bus.emit("MODEL_UNAVAILABLE", "CRITICAL", "OmniRoute down e Direct sem ModelAdapter")
        blocked = (
            "Não executei LLM.\n"
            f"Gateway activo: {gw['active']}. OmniRoute {gw['omniroute']['error']}. Direct {gw['direct']['error']}.\n"
            "Ordem: cache → memória → tools → local → OmniRoute/Direct → humano.\n"
            "SearXNG ausente: pesquisa web NÃO foi feita. Não inventei resultados."
        )
        scores = evaluate(task, [], False, 0)
        ti.record(
            task_id=task["task_id"],
            estimated=task["estimated_tokens"],
            actual=0,
            status="blocked",
            via="no_provider",
            context=pipeline.get("context"),
            route_advice=pipeline.get("route_token"),
        )
        task["status"] = "blocked"
        task["via"] = "no_provider"
        store.save_task(task)
        with _lock:
            _last_pipeline = pipeline
        _say("brain", _format_result(task, pipeline, [], scores, blocked))
        _broadcast()
        return {"ok": True, "via": "blocked"}

    pipeline["route"].append(gw["active"].upper())
    bus.emit("MODEL_STARTED", "INFO", gw["active"])
    max_tok = 1024 if task.get("type") == "coding" else 256
    res = routing.complete(_llm_prompt(text, merged, _dialogue(4, current=text)), max_tokens=max_tok)
    if res.get("status") != "success":
        bus.emit("MODEL_FAILED", "WARNING", str(res.get("error")))
        scores = evaluate(task, [], False, 0)
        ti.record(
            task_id=task["task_id"],
            estimated=task["estimated_tokens"],
            actual=0,
            status="fail",
            provider=gw.get("active"),
            via="llm_fail",
            retry_count=int(res.get("retry_count") or 0),
            fallback=res.get("fallback"),
            context=pipeline.get("context"),
            route_advice=pipeline.get("route_token"),
        )
        task["status"] = "failed"
        task["via"] = "llm_fail"
        store.save_task(task)
        with _lock:
            _last_pipeline = pipeline
        _say("brain", _format_result(task, pipeline, [], scores, f"Gateway {gw['active']} falhou: {res.get('error')}"))
        _broadcast()
        return {"ok": True, "via": "llm_fail"}

    store.incr("llm_calls")
    raw_tok = res.get("tokens")
    toks = int(raw_tok) if raw_tok is not None else 0
    ti.record(
        task_id=task["task_id"],
        estimated=task["estimated_tokens"],
        actual=toks if raw_tok is not None else None,
        model=res.get("model"),
        provider=res.get("adapter") or gw.get("active"),
        status="ok",
        raw_usage=res.get("raw_usage") if isinstance(res.get("raw_usage"), dict) else None,
        via="llm",
        context_tokens=ctx.get("tokens"),
        context=pipeline.get("context"),
        route_advice=pipeline.get("route_token"),
        fallback=res.get("fallback"),
        retry_count=int(res.get("retry_count") or 0),
    )
    tool_results = [{"tool": f"llm:{res.get('adapter')}", "status": "success", "confidence": 0.5, "findings": [{"text": res.get("text")}], "errors": [], "evidence": [f"adapter={res.get('adapter')} model={res.get('model')}"]}]
    scores = evaluate(task, tool_results, True, toks)
    speech = _format_result(task, pipeline, tool_results, scores, None)
    files = _extract_files(str(res.get("text") or ""))
    if files:
        pub = _publish_files(task.get("title") or text, files)
        if pub.get("preview"):
            speech += f"\n\nSite gravado em data/projects/{pub['slug']}/ · abre {pub['preview']}"
        if pub.get("errors"):
            speech += "\nWrite: " + "; ".join(pub["errors"][:4])
    cache_store(text, {"summary": speech, "scores": scores}, scores["OVERALL"], ns=gods.active_id())
    store.mem_put("episode", task["task_id"], f"{text[:120]} → {str(res.get('text') or '')[:240]}")
    _index_task(task, text, scores)
    task["status"] = "done"
    task["via"] = "llm"
    store.save_task(task)
    with _lock:
        _last_pipeline = pipeline
    _say("brain", speech, replace_prefix="Um momento")
    _broadcast()
    return {"ok": True, "via": "llm"}


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
