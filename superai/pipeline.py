"""Pipeline core — o coração do processamento GOD.

Extraído de runtime.py para reduzir GOD Object.
Handles: security → analysis → cache → memory → firewall → plan → tools/state/llm
"""
from __future__ import annotations

import re
import time

from . import aios, executive, providers, queue as tq, routing, tokens as ti
from .brain import cache_lookup, cache_store, context_pack, evaluate
from .validator import validate
from .thirdeye import criticize
from .config import ROOT, cfg
from .events import bus
from .memory_vec import vectors
from .store import store
from . import gods
from .util import now_iso, sha
import logging

_log = logging.getLogger("superai.pipeline")
from . import sensitive, resource_limits, sandbox, adaptive_routing


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
    elif ttype == "web_search":
        # Extract search query from the text
        query = text
        for prefix in ("pesquisa na web", "pesquisa na internet", "search the web",
                       "pesquisa na web:", "pesquisa na internet:", "search the web:"):
            if prefix in query.lower():
                query = query.lower().split(prefix, 1)[1].strip()
                break
        steps.append({"tool": "web.search", "args": {"query": query or text}})
        needs_llm = True  # Also get LLM to synthesize results
        reason.append("web search + LLM synthesis")
    elif ttype == "github":
        # Try to extract owner/repo from text
        import re as _re
        gh = _re.search(r"(?:github\.com/)?(\w[\w.-]+)/(\w[\w.-]+)", text)
        if gh:
            steps.append({"tool": "github.file", "args": {"owner": gh.group(1), "repo": gh.group(2), "path": ""}})
        else:
            steps.append({"tool": "github.repos", "args": {}})
        needs_llm = True
        reason.append("github + LLM interpretation")
    elif ttype == "news":
        steps.append({"tool": "news.search", "args": {"query": text}})
        needs_llm = True
        reason.append("news intelligence + LLM synthesis")
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
    except Exception as e:
            _log.warning("pipeline error: %s", e)


def _extract_and_store_knowledge(query: str, response: str, task: dict) -> None:
    """Extract knowledge facts from interaction and store persistently.
    
    Enhanced: captures task-type + provider performance, user style preferences,
    and topic-specific knowledge for adaptive learning.
    """
    try:
        task_type = task.get("type", "general")

        # Skip trivial task types
        if task_type in ("math", "status", "git", "files", "parse"):
            return

        low = query.lower()

        # 1. User preference detection (expanded keywords)
        pref_keywords = ("prefiro", "gosto de", "quero que", "não gosto",
                        "mais curto", "mais longo", "detalhado", "resumido",
                        "em português", "em inglês", "com código", "sem código",
                        "explique", "resume", "faz um resumo")
        if any(w in low for w in pref_keywords):
            store.mem_put("knowledge", sha(f"pref:{query[:100]}"),
                         f"Utilizador: {query[:200]}")

        # 2. Style learning from response length
        if len(response) > 50:
            style = "long" if len(response) > 500 else "medium" if len(response) > 200 else "short"
            store.mem_put("style", sha(f"style:{task_type}:{style}"),
                         f"task_type={task_type} response_style={style} len={len(response)}")

        # 3. Topic knowledge extraction
        if len(query) > 20 and len(response) > 50:
            summary = f"{query[:120]} -> {response[:200]}"
            store.mem_put("knowledge", sha(f"ep:{summary}"), summary)

        # 4. Provider performance tracking (for adaptive routing)
        # This is handled in _record_token but we store task-type context here
        store.mem_put("task_pattern", sha(f"tp:{task_type}:{query[:60]}"),
                     f"type={task_type} complexity={task.get('complexity')} query_len={len(query)}")
    except Exception as e:
            _log.warning("pipeline error: %s", e)


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
        sem = vectors.search("cache", text, k=1, min_score=0.82, god_id=gid)
        pipeline["vector_cache"] = sem[:1]
        if sem and sem[0].get("key"):
            hit = store.cache_get(sem[0]["key"])
            if hit:
                pipeline["cache"] = "semantic"
    if hit:
        store.incr("cache_hits")
        try:
            from .trace import record_system_metric
            record_system_metric("cache_hits")
        except Exception:
            pass
        bus.emit("CACHE_HIT", "INFO", f"{task['task_id']} {pipeline.get('cache') or 'hash'} cache", god_core_state="ready")
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
    try:
        from .trace import record_system_metric
        record_system_metric("cache_misses")
    except Exception:
        pass
    bus.emit("CACHE_MISS", "INFO", task["task_id"], god_core_state="thinking")
    _mark(pipeline, "cache")
    return None  # no cache hit, continue


def _rerank_memory(memories: list[dict], query: str, task_type: str) -> list[dict]:
    """B-08: Re-rank memory results by combined relevance score.

    Scoring: vector_similarity * 0.5 + keyword_match * 0.3 + kind_bonus * 0.2
    """
    if not memories:
        return memories
    _stops = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "em", "no", "na",
              "que", "e", "é", "para", "com", "por", "se", "não", "eu", "tu", "ele",
              "the", "is", "an", "and", "or", "of", "to", "in", "for", "it"}
    query_words = set(query.lower().split()) - _stops
    if not query_words:
        return memories[:5]
    _kind_bonus = {"fine_memory": 1.0, "vector": 0.8, "knowledge": 0.6, "task_pattern": 0.5, "style": 0.4, "episode": 0.4}
    scored: list[tuple[float, dict]] = []
    for m in memories:
        vec_score = float(m.get("score") or 0.3)
        mem_text = str(m.get("value") or m.get("text") or "").lower()
        matched = sum(1 for w in query_words if w in mem_text)
        kw_score = matched / len(query_words)
        kind = m.get("kind", "episode")
        kind_score = _kind_bonus.get(kind, 0.3)
        combined = vec_score * 0.5 + kw_score * 0.3 + kind_score * 0.2
        scored.append((combined, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:5]]


def _stage_memory(text, task, pipeline, need_mem, gid, _mark):
    """Stage 3: Context-aware memory retrieval (SQL + Qdrant).
    
    Enhanced: augments query with task type + dialogue context for better recall.
    Weights recent episodes higher. Deduplicates across SQL and vector results.
    """
    gact = gods.active()
    if (not need_mem) or gact.get("memory", True) is False:
        mem, vec_mem = [], []
    else:
        # Context-aware query augmentation
        task_type = task.get("type", "general")
        augmented_query = text
        # Add task type context for better semantic matching
        if task_type and task_type != "general":
            augmented_query = f"[{task_type}] {text}"

        kinds = ["episode", "episode:master"] if gid == "master" else [f"episode:{gid}"]
        mem = store.mem_search(augmented_query, kinds=kinds)

        # Also search knowledge and style memories for context
        knowledge = store.mem_search(text, kinds=["knowledge", "task_pattern", "style"])
        if knowledge:
            pipeline["knowledge_hits"] = len(knowledge)

        # Vector search with augmented query
        vec_mem = vectors.search("memory", augmented_query, k=5, min_score=0.35, god_id=gid) if vectors.available() else []

        # Deduplicate: prefer vector results (higher quality) over SQL
        seen_texts = set()
        deduped_mem = []
        for m in mem:
            val = str(m.get("value") or m.get("text") or "")[:100]
            if val not in seen_texts:
                seen_texts.add(val)
                deduped_mem.append(m)
        mem = deduped_mem

        # Add knowledge to merged results (lower priority)
        for k in (knowledge or [])[:3]:
            mem.append({"kind": "knowledge", "key": k.get("key"), "value": k.get("value")})

        # Add fine memory (audited, curated knowledge — highest priority)
        try:
            fine = store.mem_search(text, kinds=["fine_memory"])
            for f in (fine or [])[:3]:
                mem.insert(0, {"kind": "fine_memory", "key": f.get("key"), "value": f.get("value")})
        except Exception as e:
            bus.emit("PIPELINE_ERROR", "WARNING", str(e)[:100])

    pipeline["memory_hits"] = len(mem)
    pipeline["vector_hits"] = vec_mem
    merged = list(mem)
    for v in vec_mem:
        merged.append({"kind": "vector", "key": v.get("key"), "value": v.get("text"), "score": v.get("score")})
    # B-08: Re-rank by combined relevance score
    merged = _rerank_memory(merged, text, task.get("type", "general"))
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
        bus.emit("TOKEN_OPTIMIZED", "INFO", f"{task['task_id']} context ESTIMATED saved={pipeline['context_optimize'].get('tokens_saved')}", god_core_state="thinking")
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

    # Check resource limits before tools (P2.2)
    resource_check = resource_limits.check_limits(task["task_id"])
    if not resource_check.get("ok"):
        bus.emit("RESOURCE_LIMIT", "WARNING", f"Resource limits exceeded: {resource_check.get('violations')}")

    for step in p["steps"]:
        if not step.get("tool"):
            continue

        # Sandbox check for file operations (P2.4)
        args = step.get("args") or {}
        if step["tool"] in ("fs.read", "fs.list", "fs.write"):
            path = args.get("path", "")
            if path:
                path_check = sandbox.check_path(path, "write" if step["tool"] == "fs.write" else "read")
                if not path_check.get("ok"):
                    tool_results.append({
                        "tool": step["tool"],
                        "status": "blocked",
                        "confidence": 1.0,
                        "findings": [],
                        "errors": [f"Sandbox: {path_check.get('reason')}"],
                        "evidence": ["sandbox_block"],
                    })
                    continue

        # Sandbox check for python execution (P2.4)
        if step["tool"] == "python":
            code = args.get("code", "")
            if code:
                # Check for blocked imports
                import re as _re
                imports = _re.findall(r'import\s+(\w+)|from\s+(\w+)\s+import', code)
                for mod in imports:
                    mod_name = mod[0] or mod[1]
                    import_check = sandbox.check_import(mod_name)
                    if not import_check.get("ok"):
                        tool_results.append({
                            "tool": "python",
                            "status": "blocked",
                            "confidence": 1.0,
                            "findings": [],
                            "errors": [f"Sandbox: {import_check.get('reason')}"],
                            "evidence": ["sandbox_block"],
                        })
                        continue

        bus.emit("TOOL_STARTED", "INFO", step["tool"], god_core_state="tools")
        store.incr("tool_calls")
        res = aios.syscall(step["tool"], step.get("args") or {}, actor=task["task_id"])

        # Record tool call for resource tracking (P2.2)
        resource_limits.get_tracker().record_tool_call(task["task_id"], step["tool"])

        tool_results.append(res)
        # Record telemetry
        try:
            from .trace import record_system_metric
            record_system_metric("tool_calls_total")
            if res.get("status") == "success":
                record_system_metric("tool_calls_success")
        except Exception:
            pass
        if res.get("status") != "success":
            bus.emit("TOOL_FAILED", "WARNING", f"{step['tool']}: {res.get('errors')}", god_core_state="error")
    scores = evaluate(task, tool_results, llm_used=False, tokens_actual=0)
    validation = validate(task, tool_results)
    critique = criticize(pipeline, task, tool_results, scores)
    # Adversarial check: try to prove result wrong
    try:
        from .thirdeye import adversarial_check
        pipeline["adversarial"] = adversarial_check(pipeline, task, tool_results, scores)
    except Exception:
        pass
    # Evidence engine: validate claims from tool results
    try:
        from .evidence import validate_claim_from_tools
        evidence_result = validate_claim_from_tools(task.get("title", ""), tool_results)
        pipeline["evidence"] = evidence_result
    except Exception:
        pass
    _record_token(task, pipeline, ctx, actual=0, status="ok", via="tools", quality_score=scores.get("OVERALL"))
    store.mem_put(f"episode:{gods.active_id()}", task["title"], {"task_id": task["task_id"], "type": task["type"], "overall": scores["OVERALL"]})
    # Only cache if at least one tool succeeded
    any_success = any(r.get("status") == "success" for r in tool_results)
    if any_success:
        cache_store(text, {"summary": tool_results, "scores": scores}, scores["OVERALL"], ns=gods.active_id())
    _index_task(task, text, scores)
    task["status"] = "done"
    task["via"] = "tools"
    task["rating"] = scores
    store.save_task(task)
    bus.emit("TASK_COMPLETED", "INFO", f"{task['task_id']} overall {scores['OVERALL']} via tools", god_core_state="ready")

    # End resource tracking (P2.2)
    resource_limits.end_tracking(task["task_id"])
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
        bus.emit("MODEL_UNAVAILABLE", "CRITICAL", "OmniRoute down e Direct sem ModelAdapter", god_core_state="error")
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
    bus.emit("MODEL_STARTED", "INFO", gw["active"], god_core_state="thinking")
    # Multi-model strategy: token budget by task type and complexity
    task_type = task.get("type", "general")
    cx = int(task.get("complexity") or 0)
    if task_type == "coding":
        max_tok = 2048 if cx >= 7 else 1024
    elif task_type == "research":
        max_tok = 1536 if cx >= 5 else 768
    elif task_type in ("math", "status"):
        max_tok = 512
    else:
        max_tok = 768 if cx >= 5 else 512
    advice = pipeline.get("route_token") or {}
    hardcore = bool(re.search(r"\b(hardcore|HARDCORE)\b", text))
    if hardcore:
        pipeline["route"].append("HARDCORE_MODE")
        pipeline["hardcore"] = True
    # R-01: Pipeline timeout — 30s safety net (providers have their own timeouts)
    import concurrent.futures
    _llm_prompt_text = _llm_prompt(text, merged, _dialogue(4, current=text), task_type=task_type)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _llm_pool:
        _llm_future = _llm_pool.submit(
            routing.complete,
            _llm_prompt_text,
            max_tokens=max_tok,
            recommendation=advice.get("recommendation"),
            hardcore=hardcore,
        )
        try:
            res = _llm_future.result(timeout=30.0)
        except concurrent.futures.TimeoutError:
            _llm_future.cancel()
            res = {"status": "error", "error": "LLM timeout (30s)", "adapter": "timeout"}
            bus.emit("LLM_TIMEOUT", "WARNING", "LLM call exceeded 30s", god_core_state="error")
    pipeline["llm_ms"] = res.get("latency_ms")
    pipeline["llm_adapter"] = res.get("adapter") or res.get("provider")
    _mark(pipeline, "llm")

    # Record LLM telemetry
    try:
        from .trace import record_system_metric
        record_system_metric("llm_calls_total")
    except Exception:
        pass

    # LLM failed
    if res.get("status") != "success":
        bus.emit("MODEL_FAILED", "WARNING", str(res.get("error")), god_core_state="error")
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
    try:
        from .trace import record_system_metric
        record_system_metric("llm_calls_success")
    except Exception:
        pass
    raw_tok = res.get("tokens")
    toks = int(raw_tok) if raw_tok is not None else 0

    # Record adaptive routing quality (async, non-blocking)
    try:
        provider_id = res.get("adapter") or gw.get("active", "")
        task_type = task.get("type", "general")
        # We'll record quality after scoring below
        _adaptive_provider = provider_id
        _adaptive_task_type = task_type
    except Exception:
        _adaptive_provider = None
        _adaptive_task_type = None
    _record_token(task, pipeline, ctx, actual=toks if raw_tok is not None else None,
                  model=res.get("model"), provider=res.get("adapter") or gw.get("active"),
                  status="ok", raw_usage=res.get("raw_usage"),
                  fallback=res.get("fallback"), retry_count=int(res.get("retry_count") or 0),
                  latency_ms=res.get("latency_ms"))
    tool_results = [{"tool": f"llm:{res.get('adapter')}", "status": "success", "confidence": 0.5, "findings": [{"text": res.get("text")}], "errors": [], "evidence": [f"adapter={res.get('adapter')} model={res.get('model')}"]}]
    scores = evaluate(task, tool_results, True, toks)
    # Record adaptive routing quality
    try:
        if _adaptive_provider and _adaptive_task_type:
            adaptive_routing.record_quality(
                _adaptive_provider, _adaptive_task_type,
                (scores.get("OVERALL", 50) or 50) / 100.0
            )
    except Exception as e:
            _log.warning("pipeline error: %s", e)
    # Knowledge gap detection: log repeated low-quality topics
    try:
        if scores.get("OVERALL", 50) < 50:
            gap_key = sha(f"gap:{task_type}:{text[:60]}")
            gap_entry = store.mem_search(gap_key, kinds=["knowledge_gap"])
            count = len(gap_entry) + 1
            store.mem_put("knowledge_gap", gap_key, {
                "topic": text[:120], "type": task_type,
                "count": count, "last_score": scores.get("OVERALL"), "ts": now_iso(),
            })
            if count >= 3:
                bus.emit("KNOWLEDGE_GAP", "NOTICE",
                         f"Repeated low quality on \'{text[:60]}\' ({count}x)", god_core_state="learning")
    except Exception as e:
            _log.warning("pipeline error: %s", e)

    # Self-reflection: if quality is low and we haven't retried, re-prompt
    if scores.get("OVERALL", 1.0) < 0.5 and not pipeline.get("_reflected"):
        pipeline["_reflected"] = True
        pipeline["route"].append("SELF_REFLECTION")
        bus.emit("REFLECTION", "INFO", f"score {scores['OVERALL']:.2f} < 0.5 -- re-prompting", god_core_state="thinking")
        original_text = str(res.get("text") or "")
        improved_prompt = (
            f"A resposta anterior teve qualidade baixa (score {scores['OVERALL']:.2f}).\n"
            f"Resposta anterior: {original_text[:300]}\n\n"
            f"Melhora agora. Responde de novo ao pedido original:\n{text}"
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ref_pool:
            _ref_future = _ref_pool.submit(routing.complete, improved_prompt, max_tokens=max_tok, hardcore=hardcore)
            try:
                res2 = _ref_future.result(timeout=30.0)
            except concurrent.futures.TimeoutError:
                _ref_future.cancel()
                res2 = {"status": "error", "error": "Reflection timeout"}
        if res2.get("status") == "success" and res2.get("text"):
            res = res2
            toks = int(res2.get("tokens") or 0)
            tool_results = [{"tool": f"llm:{res2.get('adapter')}", "status": "success", "confidence": 0.5, "findings": [{"text": res2.get("text")}], "errors": [], "evidence": [f"adapter={res2.get('adapter')} model={res2.get('model')} reflection=true"]}]
            scores = evaluate(task, tool_results, True, toks)
            speech = _format_result(task, pipeline, tool_results, scores, None)

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
    store.mem_put("episode", task["task_id"], f"{text[:120]} -> {str(res.get('text') or '')[:240]}")
    # Knowledge persistence: extract facts from interaction
    _extract_and_store_knowledge(text, str(res.get("text") or ""), task)
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
    """Core pipeline: security → analysis → cache → memory → firewall → plan → tools/state/llm.
    
    Returns result dict. All _say/_broadcast/etc passed as callbacks to avoid circular imports.
    """
    # 0 SECURITY SCAN (P2.1)
    sensitive_scan = sensitive.scan_task_content(task)
    if sensitive_scan.get("has_sensitive"):
        risk_score = sensitive_scan.get("risk_score", 0)
        if risk_score >= 5:
            # High risk: block
            bus.emit("SECURITY_BLOCK", "CRITICAL", f"Sensitive data detected (risk={risk_score})", god_core_state="error")
            _say("brain", f"⚠ BLOCKED: Sensitive data detected in request (risk level {risk_score}/5).\n\n{sensitive.format_detections(sensitive_scan)}\n\nRemove sensitive data and try again.")
            return {"ok": False, "via": "security", "reason": "sensitive_data", "risk": risk_score}
        elif risk_score >= 3:
            # Medium risk: warn but continue
            bus.emit("SECURITY_WARNING", "WARNING", f"Sensitive data detected (risk={risk_score})", god_core_state="thinking")
            task["security_warning"] = sensitive.format_detections(sensitive_scan)

    # 1 analyzer
    act_m = __import__('superai.mission', fromlist=['active']).active()
    if act_m:
        task["mission_id"] = act_m["id"]
    task["status"] = "running"
    store.save_task(task)
    store.audit("user", "task", task["task_id"])
    bus.emit("TASK_CREATED", "INFO", f"{task['task_id']} · {task['type']} · est {task['estimated_tokens']} tok", god_core_state="thinking")

    # Start resource tracking (P2.2)
    resource_tracker = resource_limits.get_tracker()
    resource_tracker.start_task(task["task_id"])

    pipeline = {
        "task": {k: task[k] for k in ("task_id", "type", "complexity", "exec_mode", "reasoning_required", "estimated_tokens", "reasoning_budget", "privacy", "tool_requirement", "classify_method", "classify_confidence")},
        "cache": "miss",
        "memory_hits": 0,
        "firewall": None,
        "route": [],
        "providers": providers.health_all(),
        "t0": time.perf_counter(),
        "stage_times": {},
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

    # 2+3 parallel: cache + memory (independent stages)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        cache_f = pool.submit(_stage_cache, text, task, pipeline, need_mem, gid, _say, _mark, _set_pipe, _broadcast, _format_result, _lock)
        memory_f = pool.submit(_stage_memory, text, task, pipeline, need_mem, gid, _mark)
        cache_result = cache_f.result()
        if cache_result:
            memory_f.cancel()
            return cache_result
        merged, ctx = memory_f.result()

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
