from __future__ import annotations

import re
from typing import Any

from .config import cfg
from .store import store
from .util import count_tokens, normalize_query, now_iso, sha, uid

MATH_RE = re.compile(r"^[\s\d\.\+\-\*/%\(\)\^x×÷,]+$", re.I)

TYPE_RULES = [
    ("git", r"\bgit\b|commit|diff|branch|\brepo\b"),
    ("status", r"\b(estado|sa[uú]de|briefing|modo de opera|budget|orçamento|providers?)\b"),
    ("math", r"\b(calcul|quanto [eé]|soma|multiplica|dividi)|\d+\s*[\+\-\*/×÷^]\s*\d+"),
    ("parse", r"\b(json|csv|xml|parse|parsing)\b"),
    ("files", r"\b(ficheiro|arquivo|lista|ls\b|l[eê] |cat |directoria|diretório|path|ler o)\b"),
    ("python", r"\b(python|executa(r)? este c[oó]digo|corre este)\b"),
    ("regex", r"\b(regex|express[aã]o regular)\b"),
    ("research", r"\b(pesquisa|search|github|paper|alternativ|osint|web)\b"),
    ("coding", r"\b(c[oó]digo|refactor|implement|debug|arquitect|lint|teste|website|landing|html|css|\bsite\b|p[aá]gina web|cria(r)? (um |uma )?(app|site|p[aá]gina))\b"),
]


def analyze(text: str) -> dict:
    t = text.strip()
    low = t.lower()
    ttype = "general"
    for name, rx in TYPE_RULES:
        if re.search(rx, low, re.I):
            ttype = name
            break
    if MATH_RE.match(low.replace("quanto é", "").replace("quanto e", "").replace("calcula", "").strip()):
        ttype = "math"

    complexity = 2
    if len(t) > 80:
        complexity = 4
    if len(t) > 240:
        complexity = 6
    if re.search(r"arquitect|produ[cç][aã]o|cr[ií]tico|multi|sistema|evolu", low):
        complexity = max(complexity, 8)
    if ttype in ("math", "status", "parse"):
        complexity = min(complexity, 3)

    reasoning = complexity >= 7 or ttype in ("coding", "research")
    privacy = "local_preferred"
    if re.search(r"secret|password|credential|privado", low):
        privacy = "local_only"

    tok = count_tokens(t)
    # estimated total if we were to call an LLM with a short system prompt
    estimated = tok["tokens"] + 48

    if ttype in ("math", "status", "git", "files", "parse") and complexity <= 3:
        exec_mode = "FAST"
    elif ttype in ("coding", "research") or complexity >= 7:
        exec_mode = "DEEP"
    else:
        exec_mode = "NORMAL"

    tools_needed = []
    if ttype == "math":
        tools_needed = ["calculator"]
    elif ttype == "files":
        tools_needed = ["fs.list", "fs.read"]
    elif ttype == "git":
        tools_needed = ["git"]
    elif ttype == "parse":
        tools_needed = ["json", "csv", "xml"]
    elif ttype == "python":
        tools_needed = ["python"]
    elif ttype == "regex":
        tools_needed = ["regex"]

    return {
        "task_id": uid("T"),
        "title": t[:160],
        "type": ttype,
        "complexity": complexity,
        "reasoning_required": reasoning,
        "context_required": "low" if complexity <= 3 else "medium" if complexity <= 6 else "high",
        "latency_priority": "high" if ttype in ("math", "status") else "medium",
        "quality_priority": "high" if complexity >= 7 else "medium",
        "privacy": privacy,
        "deadline": None,
        "estimated_tokens": estimated,
        "token_estimate": tok,
        "tool_requirement": tools_needed,
        "historical_success_rate": None,
        "acceptable_failure_rate": 0.1,
        "reasoning_budget": "low" if complexity <= 3 else "medium" if complexity <= 6 else "high" if complexity <= 8 else "maximum",
        "exec_mode": exec_mode,
        "ts": now_iso(),
        "status": "analyzed",
        "text": t,
    }


def firewall(task: dict, extra_tokens: int = 0) -> dict:
    budgets = cfg.get("budgets") or {}
    usage = store.usage()
    est = int(task.get("estimated_tokens") or 0) + extra_tokens
    reasons = []
    action = "approve"

    if est > int(budgets.get("task", 8000)):
        action = "optimize"
        reasons.append(f"estimativa {est} > TASK_TOKEN_BUDGET {budgets['task']}")
    if usage.get("session_tokens", 0) + est > int(budgets.get("session", 50000)):
        action = "reject"
        reasons.append("SESSION_TOKEN_BUDGET excedido")
    if usage.get("daily_tokens", 0) + est > int(budgets.get("daily", 200000)):
        action = "reject"
        reasons.append("DAILY_TOKEN_BUDGET excedido")
    if usage.get("project_tokens", 0) + est > int(budgets.get("project", 2000000)):
        action = "reject"
        reasons.append("PROJECT_TOKEN_BUDGET excedido")

    return {
        "action": action,
        "estimated": est,
        "method": (task.get("token_estimate") or {}).get("method"),
        "verified": True,
        "budgets": budgets,
        "usage": {k: usage.get(k, 0) for k in ("session_tokens", "daily_tokens", "project_tokens")},
        "reasons": reasons,
    }


def context_pack(task: dict, memory_hits: list[dict], limit: int = 5) -> dict:
    """Never dump full history. Only task + relevant memory + constraints."""
    parts = [
        f"TASK: {task.get('title')}",
        f"TYPE: {task.get('type')} COMPLEXITY: {task.get('complexity')}",
        f"CONSTRAINTS: privacy={task.get('privacy')} reasoning_budget={task.get('reasoning_budget')}",
    ]
    if memory_hits:
        parts.append("RELEVANT MEMORY:")
        for m in memory_hits[: max(0, int(limit))]:
            parts.append(f"- {m.get('kind')}:{m.get('key')}: {str(m.get('value'))[:240]}")
    raw = "\n".join(parts)
    # dedup identical lines
    seen = set()
    lines = []
    for ln in raw.splitlines():
        if ln in seen:
            continue
        seen.add(ln)
        lines.append(ln)
    final = "\n".join(lines)
    tok = count_tokens(final)
    return {"text": final, "tokens": tok["tokens"], "method": tok["method"], "verified": True}


def cache_lookup(text: str, ns: str = "") -> dict | None:
    key = sha(normalize_query(text) + (f"\n{ns}" if ns else ""))
    hit = store.cache_get(key)
    if hit:
        return hit
    # Semantic cache: search by embedding similarity
    from .feature_flags import is_enabled
    if not is_enabled("semantic_cache"):
        return None
    from .memory_vec import vectors
    if not vectors.available():
        return None
    results = vectors.search("cache", text, k=1, min_score=0.75)
    if not results:
        return None
    r = results[0]
    # Found a semantic match above threshold
    cached_result = r.get("result")
    if not cached_result:
        return None
    return {"key": r.get("key", ""), "norm": text, "result": cached_result, "quality": r.get("quality", 0.5), "ts": r.get("ts", ""), "hits": 0, "semantic": True, "score": r.get("score", 0)}


def cache_store(text: str, result: dict, quality: float, ns: str = "") -> None:
    norm = normalize_query(text)
    key = sha(norm + (f"\n{ns}" if ns else ""))
    store.cache_put(key, norm, result, quality)
    # Also store in vector cache for semantic lookup
    from .feature_flags import is_enabled
    if is_enabled("semantic_cache"):
        from .memory_vec import vectors
        if vectors.available():
            try:
                import json as _json
                vectors.upsert("cache", key, norm, {"result": result, "quality": quality, "ts": now_iso()})
            except Exception:
                pass  # Non-critical


def evaluate(task: dict, tool_results: list[dict], llm_used: bool, tokens_actual: int) -> dict:
    speech = ""
    for r in tool_results or []:
        if not str(r.get("tool") or "").startswith("llm:"):
            continue
        f0 = (r.get("findings") or [None])[0]
        if isinstance(f0, dict):
            speech = str(f0.get("text") or "")
        elif isinstance(f0, str):
            speech = f0
    empty_llm = llm_used and not speech.strip()
    ok = all(r.get("status") == "success" for r in tool_results) if tool_results else not llm_used
    if empty_llm:
        ok = False
    if not tool_results and not llm_used:
        # blocked / unanswered
        correctness = 0
        completeness = 40
    else:
        correctness = 100 if ok else 40
        completeness = 90 if ok else 50
    efficiency = 100 if not llm_used else 60
    token_eff = 100 if tokens_actual == 0 else max(10, 100 - min(90, tokens_actual // 50))
    security = 90
    reliability = correctness
    quality = correctness
    overall = int(
        quality * 0.25
        + correctness * 0.25
        + completeness * 0.15
        + efficiency * 0.1
        + token_eff * 0.1
        + security * 0.1
        + reliability * 0.05
    )
    scores = {
        "QUALITY": quality,
        "CORRECTNESS": correctness,
        "COMPLETENESS": completeness,
        "EFFICIENCY": efficiency,
        "TOKEN_EFFICIENCY": token_eff,
        "SECURITY": security,
        "RELIABILITY": reliability,
        "OVERALL": overall,
        "tokens_actual": tokens_actual,
        "llm_used": llm_used,
    }
    store.save_rating(task["task_id"], scores)
    return scores
