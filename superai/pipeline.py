"""Pipeline core — o coração do processamento GOD.

Extraído de runtime.py para reduzir GOD Object.
Handles: analysis → cache → memory → firewall → plan → tools/state/llm
"""
from __future__ import annotations

import re
import time
from typing import Any

from . import aios, executive, providers, queue as tq, resources, routing, tokens as ti
from .brain import analyze, cache_lookup, cache_store, context_pack, evaluate
from .validator import validate
from .thirdeye import criticize
from .config import ROOT, cfg
from .events import bus
from .governor import gov
from .memory_vec import vectors
from .store import store
from . import gods
from .util import now_iso, uid


def _extract_path(text: str) -> str | None:
    m = re.search(r"(/home/user[^\s]+|super-ai[^\s]*|[\w./-]+\.(py|json|yaml|md|html|csv|xml|txt))", text)
    if m:
        p = m.group(0)
        from pathlib import Path
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


def plan(task: dict) -> dict:
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
        if re.search(r"\b(l[eê]|read|cat|abre|mostra)\b", text.lower()) and _is_file(path):
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


def _is_file(path: str) -> bool:
    from pathlib import Path
    return Path(path).is_file()


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


def _extract_files(text: str) -> list[tuple[str, str]]:
    """Fences ```lang path\nbody```. Never invent a path outside the fence."""
    from pathlib import Path as PPath
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
        if path and ".." not in PPath(path).parts:
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


def _slug(text: str) -> str:
    from .tools import project_slug
    return project_slug(text)


def _record_token(task: dict, pipeline: dict, ctx: dict, *,
                  actual=None, status="ok", via="tools", provider=None,
                  cache_hit=False, quality_score=None, model=None,
                  raw_usage=None, fallback=None, retry_count=0, latency_ms=None) -> None:
    ti.record(
        task_id=task["task_id"],
        estimated=task.get("estimated_tokens"),
        actual=actual,
        model=model,
        provider=provider,
        status=status,
        raw_usage=raw_usage if isinstance(raw_usage, dict) else None,
        via=via,
        cache_hit=cache_hit,
        quality_score=quality_score,
        context_tokens=ctx.get("tokens"),
        context=pipeline.get("context"),
        route_advice=pipeline.get("route_token"),
        fallback=fallback,
        retry_count=retry_count,
        latency_ms=latency_ms,
    )


# ── Pipeline stages ─────────────────────────────────────────────────────────


def _stage_cache(text, task, pipeline, need_mem, gid, _say, _mark, _set_pipe, _broadcast, _format_result, _lock):
    """Stage 2: Cache lookup (hash + semantic)."""
    hit = cache_lookup(text, gid)
    if not hit and need_mem and cfg.get("evolution_policy", "semantic_cache", default=True) is not False and vectors.available():
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
        _record_token(task, pipeline, {}, actual=0, status="cache_hit", via="cache", cache_hit=True)
        with _lock:
            _set_pipe(pipeline)
        summ = hit["result"].get("summary") if isinstance(hit.get("result"), dict) else hit.get("result")
        if isinstance(summ, str) and summ.strip():
            _say("brain", summ)
        else:
            _say("brain", "CACHE HIT.\n\n" + _format_result(task, pipeline, [], None, None) + "\n\n" + str(summ)[:2500])
        _mark(pipeline, "cache")
        _broadcast()
        return {"ok": True, "via": "cache"}
    store.incr("cache_misses")
    bus.emit("CACHE_MISS", "INFO", task["task_id"])
    _mark(pipeline, "cache")
    return None  # no cache hit, continue


def _stage_memory(text, task, pipeline, need_mem, gid, _mark):
    """Stage 3: Memory retrieval (SQL + Qdrant)."""
    gact = gods.active()
    if (not need_mem) or gact.get("memory", True) is False:
        mem, vec_mem = [], []
    else:
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
    _mark(pipeline, "memory")
    return merged, ctx


def _stage_firewall(task, pipeline, merged, ctx, _say, _set_pipe, _broadcast, _format_result, _lock):
    """Stage 4: Token firewall."""
    fw = ti.gate(task, extra_tokens=ctx["tokens"])
    pipeline["firewall"] = fw
    if fw["action"] == "optimize":
        slim = merged[:2]
        ctx2 = context_pack(task, slim, limit=2)
        pipeline["context_optimize"] = ti.context_efficiency(ctx["text"], ctx2["text"])
        ctx = ctx2
        merged = slim
        pipeline["context"] = pipeline["context_optimize"]
        bus.emit("TOKEN_OPTIMIZED", "INFO", f"{task['task_id']} context ESTIMATED saved={pipeline['context_optimize'].get('tokens_saved')}")
        fw = ti.gate(task, extra_tokens=ctx["tokens"])
        pipeline["firewall"] = fw
    if fw["action"] == "reject":
        pipeline["route"] = ["TOKEN_FIREWALL_REJECT"]
        task["status"] = "rejected"
        store.save_task(task)
        with _lock:
            _set_pipe(pipeline)
        _say("brain", _format_result(task, pipeline, [], None, "Firewall rejeitou a chamada. Comprime, reduz âmbito, ou sobe o budget."))
        _broadcast()
        return merged, ctx, {"ok": True, "via": "firewall"}
    return merged, ctx, None


def _stage_decide(text, task, pipeline, p, from_worker, _mark, _set_pipe, _enqueue, _lock):
    """Stage 5: Plan + executive decide + queue dispatch."""
    d = executive.decide(task, p, any_llm=providers.any_llm(), from_worker=from_worker)
    pipeline["decision"] = d
    pipeline["direct_llm"] = d["direct_llm"]
    pipeline["fast"] = d["fast"]
    pipeline["deep"] = d["deep"]

    if not from_worker and d.get("queue") and providers.any_llm():
        parent = tq.last_open(mission_id=task.get("mission_id")) if task.get("mission_id") else None
        q = _enqueue("chat", text, parent_id=(parent or {}).get("id"), mission_id=task.get("mission_id"))
        if not q.get("skip"):
            pipeline["route"].append("QUEUE:" + q.get("location", ""))
            pipeline["direct_llm"] = False
            task["status"] = "queued"
            task["via"] = "queue"
            store.save_task(task)
            _mark(pipeline, "queue")
            with _lock:
                _set_pipe(pipeline)
            return q
    if d.get("direct_llm"):
        pipeline["route"].append("DIRECT_LLM")
        pipeline["direct_llm"] = True
    return None


def _stage_tools(text, task, pipeline, p, ctx, _say, _mark, _set_pipe, _broadcast, _format_result, _lock):
    """Stage 6a: Execute deterministic tools."""
    tool_results = []
    pipeline["route"].append("DETERMINISTIC_TOOLS")
    for step in p["steps"]:
        if not step.get("tool"):
            continue
        bus.emit("TOOL_STARTED", "INFO", step["tool"])
        store.incr("tool_calls")
        res = aios.syscall(step["tool"], step.get("args") or {}, actor=task["task_id"])
        tool_results.append(res)
        if res.get("status") != "success":
            bus.emit("TOOL_FAILED", "WARNING", f"{step['tool']}: {res.get('errors')}")
    scores = evaluate(task, tool_results, llm_used=False, tokens_actual=0)
    validation = validate(task, tool_results)
    critique = criticize(pipeline, task, tool_results, scores)
    _record_token(task, pipeline, ctx, actual=0, status="ok", via="tools", quality_score=scores.get("OVERALL"))
    store.mem_put(f"episode:{gods.active_id()}", task["title"], {"task_id": task["task_id"], "type": task["type"], "overall": scores["OVERALL"]})
    cache_store(text, {"summary": tool_results, "scores": scores}, scores["OVERALL"], ns=gods.active_id())
    _index_task(task, text, scores)
    task["status"] = "done"
    task["via"] = "tools"
    task["rating"] = scores
    store.save_task(task)
    bus.emit("TASK_COMPLETED", "INFO", f"{task['task_id']} overall {scores['OVERALL']} via tools")
    pipeline["scores"] = scores
    pipeline["validation"] = validation
    pipeline["critique"] = critique
    _mark(pipeline, "tools")
    with _lock:
        _set_pipe(pipeline)
    _say("brain", _format_result(task, pipeline, tool_results, scores, None))
    _broadcast()
    return {"ok": True, "via": "tools"}


def _stage_state(task, pipeline, _say, _set_pipe, _broadcast, _format_result, _lock):
    """Stage 6b: State shortcut (status queries)."""
    pipeline["route"].append("DETERMINISTIC_STATE")
    from .runtime import snapshot
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
    validation = validate(task, tool_results)
    critique = criticize(pipeline, task, tool_results, scores)
    _record_token(task, pipeline, {}, actual=0, status="ok", via="state")
    task["status"] = "done"
    task["via"] = "state"
    store.save_task(task)
    pipeline["validation"] = validation
    pipeline["critique"] = critique
    with _lock:
        _set_pipe(pipeline)
    _say("brain", _format_result(task, pipeline, tool_results, scores, None))
    _broadcast()
    return {"ok": True, "via": "state"}


def _stage_llm(text, task, pipeline, merged, ctx, *, _say, _mark, _set_pipe, _broadcast,
               _format_result, _llm_prompt, _dialogue, _lock):
    """Stage 6c: LLM routing and execution."""
    pipeline["route"].append("INTELLIGENT_ROUTER")
    gw = routing.health()
    pipeline["gateway"] = {"active": gw["active"], "omniroute": gw["omniroute"]["available"], "direct": gw["direct"]["available"]}

    # No provider available
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
        _record_token(task, pipeline, {}, actual=0, status="blocked", via="no_provider")
        task["status"] = "blocked"
        task["via"] = "no_provider"
        store.save_task(task)
        with _lock:
            _set_pipe(pipeline)
        _say("brain", _format_result(task, pipeline, [], scores, blocked))
        _broadcast()
        return {"ok": True, "via": "blocked"}

    # Call LLM
    pipeline["route"].append(gw["active"].upper())
    bus.emit("MODEL_STARTED", "INFO", gw["active"])
    max_tok = 1024 if task.get("type") == "coding" else 256
    advice = pipeline.get("route_token") or {}
    hardcore = bool(re.search(r"\b(hardcore|HARDCORE)\b", text))
    if hardcore:
        pipeline["route"].append("HARDCORE_MODE")
        pipeline["hardcore"] = True
    res = routing.complete(
        _llm_prompt(text, merged, _dialogue(4, current=text)),
        max_tokens=max_tok,
        recommendation=advice.get("recommendation"),
        hardcore=hardcore,
    )
    pipeline["llm_ms"] = res.get("latency_ms")
    pipeline["llm_adapter"] = res.get("adapter") or res.get("provider")
    _mark(pipeline, "llm")

    # LLM failed
    if res.get("status") != "success":
        bus.emit("MODEL_FAILED", "WARNING", str(res.get("error")))
        scores = evaluate(task, [], False, 0)
        _record_token(task, pipeline, {}, actual=0, status="fail", provider=gw.get("active"),
                      via="llm_fail", retry_count=int(res.get("retry_count") or 0),
                      fallback=res.get("fallback"), latency_ms=res.get("latency_ms"))
        task["status"] = "failed"
        task["via"] = "llm_fail"
        store.save_task(task)
        with _lock:
            _set_pipe(pipeline)
        _say("brain", _format_result(task, pipeline, [], scores, f"Gateway {gw['active']} falhou: {res.get('error')}"))
        _broadcast()
        return {"ok": True, "via": "llm_fail"}

    # LLM success
    store.incr("llm_calls")
    raw_tok = res.get("tokens")
    toks = int(raw_tok) if raw_tok is not None else 0
    _record_token(task, pipeline, ctx, actual=toks if raw_tok is not None else None,
                  model=res.get("model"), provider=res.get("adapter") or gw.get("active"),
                  status="ok", raw_usage=res.get("raw_usage"),
                  fallback=res.get("fallback"), retry_count=int(res.get("retry_count") or 0),
                  latency_ms=res.get("latency_ms"))
    tool_results = [{"tool": f"llm:{res.get('adapter')}", "status": "success", "confidence": 0.5, "findings": [{"text": res.get("text")}], "errors": [], "evidence": [f"adapter={res.get('adapter')} model={res.get('model')}"]}]
    scores = evaluate(task, tool_results, True, toks)
    validation = validate(task, tool_results, llm_text=str(res.get("text") or ""))
    critique = criticize(pipeline, task, tool_results, scores)
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
    pipeline["validation"] = validation
    pipeline["critique"] = critique
    with _lock:
        _set_pipe(pipeline)
    _say("brain", speech, replace_prefix="Um momento")
    _broadcast()
    return {"ok": True, "via": "llm"}


# ── Main orchestrator ───────────────────────────────────────────────────────


def run_pipeline(text: str, task: dict, from_worker: bool, *,
                 _say, _mark, _set_pipe, _broadcast, _format_result,
                 _llm_prompt, _dialogue, _enqueue, _lock) -> dict:
    """Core pipeline: analysis → cache → memory → firewall → plan → tools/state/llm.
    
    Returns result dict. All _say/_broadcast/etc passed as callbacks to avoid circular imports.
    """
    # 1 analyzer
    act_m = __import__('superai.mission', fromlist=['active']).active()
    if act_m:
        task["mission_id"] = act_m["id"]
    task["status"] = "running"
    store.save_task(task)
    store.audit("user", "task", task["task_id"])
    bus.emit("TASK_CREATED", "INFO", f"{task['task_id']} · {task['type']} · est {task['estimated_tokens']} tok")

    pipeline = {
        "task": {k: task[k] for k in ("task_id", "type", "complexity", "exec_mode", "reasoning_required", "estimated_tokens", "reasoning_budget", "privacy", "tool_requirement")},
        "cache": "miss",
        "memory_hits": 0,
        "firewall": None,
        "route": [],
        "providers": providers.health_all(),
        "t0": time.perf_counter(),
    }
    fast = (task.get("exec_mode") or "") == "FAST"
    deep = (task.get("exec_mode") or "") == "DEEP"
    need_mem = deep or int(task.get("complexity") or 0) >= 5
    pipeline["fast"] = fast
    pipeline["deep"] = deep
    pipeline["direct_llm"] = False
    pipeline["mission_id"] = task.get("mission_id")
    pipeline["skipped_heavy"] = ["vector", "memory"] if not need_mem else []

    gid = gods.active_id()

    # 2 cache
    cache_result = _stage_cache(text, task, pipeline, need_mem, gid, _say, _mark, _set_pipe, _broadcast, _format_result, _lock)
    if cache_result:
        return cache_result

    # 3 memory
    merged, ctx = _stage_memory(text, task, pipeline, need_mem, gid, _mark)

    # 4 firewall
    merged, ctx, fw_result = _stage_firewall(task, pipeline, merged, ctx, _say, _set_pipe, _broadcast, _format_result, _lock)
    if fw_result:
        return fw_result

    # 5 plan + decide
    p = plan(task)
    decide_result = _stage_decide(text, task, pipeline, p, from_worker, _mark, _set_pipe, _enqueue, _lock)
    if decide_result:
        return decide_result

    # 6a tools
    if p["steps"] and not (len(p["steps"]) == 1 and p["steps"][0].get("kind") == "status"):
        return _stage_tools(text, task, pipeline, p, ctx, _say, _mark, _set_pipe, _broadcast, _format_result, _lock)

    # 6b state
    if p["steps"] and p["steps"][0].get("kind") == "status":
        return _stage_state(task, pipeline, _say, _set_pipe, _broadcast, _format_result, _lock)

    # 6c llm
    return _stage_llm(text, task, pipeline, merged, ctx,
                      _say=_say, _mark=_mark, _set_pipe=_set_pipe, _broadcast=_broadcast,
                      _format_result=_format_result, _llm_prompt=_llm_prompt,
                      _dialogue=_dialogue, _lock=_lock)
