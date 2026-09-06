"""Third Eye 2.0 — plan/decision criticism with MEASURED facts.

Not an LLM critic. Not a replacement for observer.py alerts.
Analyzes pipeline after task completion to identify inefficiencies,
suboptimal paths, and potential improvements.

Rules:
- Only facts from the pipeline, never invented
- Never blocks execution — always advisory
- Reports: what happened, was it optimal, what could improve
"""
from __future__ import annotations

import json
from typing import Any

from .events import bus
from .store import store
from .util import now_iso


def criticize(pipeline: dict, task: dict, tool_results: list[dict], scores: dict | None) -> dict:
    """Analyze pipeline after task completion. Returns structured criticism.

    Never blocks — always returns advisory findings.
    All findings are MEASURED from the pipeline, never assumed.
    """
    findings: list[dict] = []
    recommendations: list[dict] = []

    ttype = task.get("type") or "general"
    cx = int(task.get("complexity") or 0)
    exec_mode = task.get("exec_mode") or "NORMAL"
    via = task.get("via") or "unknown"
    latency_ms = pipeline.get("latency_ms")
    stages = pipeline.get("stages_ms") or {}
    decision = pipeline.get("decision") or {}
    validation = pipeline.get("validation")

    # 1. Was the path optimal?
    _check_path_optimality(findings, recommendations, task, decision, via, exec_mode)

    # 2. Was latency reasonable?
    _check_latency(findings, recommendations, latency_ms, stages, exec_mode, ttype)

    # 3. Were tools used efficiently?
    _check_tool_efficiency(findings, recommendations, tool_results, ttype)

    # 4. Was the cache used?
    _check_cache_usage(findings, recommendations, pipeline)

    # 5. Was memory needed?
    _check_memory_usage(findings, recommendations, pipeline, exec_mode)

    # 6. Was validation successful?
    _check_validation(findings, recommendations, validation)

    # 7. Were scores reasonable?
    _check_scores(findings, recommendations, scores, ttype)

    # 8. Was the router decision correct?
    _check_router(findings, recommendations, pipeline, decision)

    # 9. Token efficiency
    _check_token_efficiency(findings, recommendations, pipeline, task, scores)

    # 10. Were there unnecessary steps?
    _check_unnecessary_steps(findings, recommendations, pipeline, stages)

    n_issues = sum(1 for f in findings if f.get("severity") in ("WARNING", "CRITICAL"))
    n_ok = sum(1 for f in findings if f.get("severity") == "OK")
    n_info = sum(1 for f in findings if f.get("severity") == "INFO")

    result = {
        "kind": "MEASURED",
        "ts": now_iso(),
        "task_id": task.get("task_id"),
        "task_type": ttype,
        "exec_mode": exec_mode,
        "via": via,
        "latency_ms": latency_ms,
        "n_findings": len(findings),
        "n_issues": n_issues,
        "n_ok": n_ok,
        "n_info": n_info,
        "findings": findings,
        "recommendations": recommendations,
        "overall": "OK" if n_issues == 0 else "ISSUES",
    }

    # Emit event if there are issues
    if n_issues > 0:
        bus.emit("THIRD_EYE_FINDING", "NOTICE",
                 f"task {task.get('task_id')} {n_issues} issue(s) found")

    return result


def _check_path_optimality(findings: list, recommendations: list,
                           task: dict, decision: dict, via: str, exec_mode: str) -> None:
    """Was the execution path optimal for this task type?"""
    path = decision.get("path") or via
    ttype = task.get("type") or "general"

    # FAST task went through queue — suboptimal
    if exec_mode == "FAST" and via == "queue":
        findings.append({
            "check": "path_optimality",
            "severity": "WARNING",
            "msg": f"FAST task went through queue ({path}) — should be inline",
            "evidence": {"exec_mode": exec_mode, "via": via, "path": path},
        })
        recommendations.append({
            "type": "performance",
            "msg": "FAST tasks should avoid queue. Check if worker is blocking fast path.",
        })
    elif exec_mode == "FAST" and via in ("tools", "cache", "state"):
        findings.append({
            "check": "path_optimality",
            "severity": "OK",
            "msg": f"FAST task used optimal path: {via}",
            "evidence": {"exec_mode": exec_mode, "via": via},
        })

    # DEEP task went direct instead of queue
    if exec_mode == "DEEP" and via == "llm" and not decision.get("from_worker"):
        findings.append({
            "check": "path_optimality",
            "severity": "INFO",
            "msg": "DEEP task went direct LLM instead of queue — acceptable if no worker",
            "evidence": {"exec_mode": exec_mode, "via": via},
        })

    # Task was blocked but shouldn't have been
    if via == "blocked" and ttype in ("math", "status", "git", "files", "parse"):
        findings.append({
            "check": "path_optimality",
            "severity": "WARNING",
            "msg": f"Deterministic task ({ttype}) was blocked — should use tools",
            "evidence": {"type": ttype, "via": via},
        })
        recommendations.append({
            "type": "correctness",
            "msg": f"Task type '{ttype}' should use deterministic tools, not LLM.",
        })


def _check_latency(findings: list, recommendations: list,
                   latency_ms: float | None, stages: dict,
                   exec_mode: str, ttype: str) -> None:
    """Was latency reasonable for this task type?"""
    if latency_ms is None:
        return

    # FAST tasks should be < 100ms
    if exec_mode == "FAST" and latency_ms > 100:
        findings.append({
            "check": "latency",
            "severity": "WARNING",
            "msg": f"FAST task took {latency_ms:.0f}ms (expected < 100ms)",
            "evidence": {"latency_ms": latency_ms, "stages": stages},
        })
        # Identify slowest stage
        if stages:
            slowest = max(stages.items(), key=lambda x: x[1])
            recommendations.append({
                "type": "performance",
                "msg": f"Slowest stage: {slowest[0]} ({slowest[1]:.1f}ms). Investigate.",
            })
    elif exec_mode == "FAST" and latency_ms <= 100:
        findings.append({
            "check": "latency",
            "severity": "OK",
            "msg": f"FAST task latency {latency_ms:.0f}ms — within target",
            "evidence": {"latency_ms": latency_ms},
        })

    # Any task > 5s is suspicious
    if latency_ms > 5000:
        findings.append({
            "check": "latency",
            "severity": "WARNING",
            "msg": f"Task took {latency_ms:.0f}ms (>5s) — investigate",
            "evidence": {"latency_ms": latency_ms, "stages": stages},
        })
        recommendations.append({
            "type": "performance",
            "msg": "Task took >5s. Check for unnecessary I/O, LLM timeouts, or tool failures.",
        })

    # Cache stage should be < 10ms
    cache_ms = stages.get("cache")
    if cache_ms is not None and cache_ms > 10:
        findings.append({
            "check": "latency",
            "severity": "INFO",
            "msg": f"Cache lookup took {cache_ms:.1f}ms (expected < 10ms)",
            "evidence": {"cache_ms": cache_ms},
        })

    # Memory stage should be < 50ms
    mem_ms = stages.get("memory")
    if mem_ms is not None and mem_ms > 50:
        findings.append({
            "check": "latency",
            "severity": "INFO",
            "msg": f"Memory search took {mem_ms:.1f}ms (expected < 50ms)",
            "evidence": {"memory_ms": mem_ms},
        })


def _check_tool_efficiency(findings: list, recommendations: list,
                           tool_results: list[dict], ttype: str) -> None:
    """Were tools used efficiently?"""
    if not tool_results:
        return

    # Count tool failures
    failures = [r for r in tool_results if r.get("status") != "success"]
    if failures:
        for f in failures:
            tool = f.get("tool") or "unknown"
            errors = f.get("errors") or []
            findings.append({
                "check": "tool_efficiency",
                "severity": "WARNING",
                "msg": f"Tool '{tool}' failed: {'; '.join(errors[:2])}",
                "evidence": {"tool": tool, "errors": errors[:3]},
            })

    # Check if the right tool was used for the task type
    tools_used = [r.get("tool") for r in tool_results if r.get("tool")]
    if ttype == "math" and "calculator" not in tools_used:
        findings.append({
            "check": "tool_efficiency",
            "severity": "INFO",
            "msg": "Math task didn't use calculator tool",
            "evidence": {"type": ttype, "tools_used": tools_used},
        })
    elif ttype == "git" and "git" not in tools_used:
        findings.append({
            "check": "tool_efficiency",
            "severity": "INFO",
            "msg": "Git task didn't use git tool",
            "evidence": {"type": ttype, "tools_used": tools_used},
        })

    # Check for excessive tool calls
    if len(tool_results) > 5:
        findings.append({
            "check": "tool_efficiency",
            "severity": "INFO",
            "msg": f"{len(tool_results)} tool calls — consider if all were necessary",
            "evidence": {"n_tools": len(tool_results), "tools": tools_used},
        })


def _check_cache_usage(findings: list, recommendations: list, pipeline: dict) -> None:
    """Was the cache used effectively?"""
    cache = pipeline.get("cache") or "miss"
    fast = pipeline.get("fast")

    if cache in ("hit", "semantic"):
        findings.append({
            "check": "cache_usage",
            "severity": "OK",
            "msg": f"Cache {cache} — saved LLM call",
            "evidence": {"cache": cache},
        })
    elif fast and cache == "miss":
        # FAST task missed cache — might be a new query
        findings.append({
            "check": "cache_usage",
            "severity": "INFO",
            "msg": "FAST task cache miss — will be cached for next time",
            "evidence": {"cache": cache, "fast": fast},
        })


def _check_memory_usage(findings: list, recommendations: list,
                        pipeline: dict, exec_mode: str) -> None:
    """Was memory search necessary?"""
    skipped = pipeline.get("skipped_heavy") or []
    mem_hits = pipeline.get("memory_hits") or 0
    vector_hits = pipeline.get("vector_hits") or []

    if "memory" in skipped:
        findings.append({
            "check": "memory_usage",
            "severity": "OK",
            "msg": "Memory search skipped for FAST task — correct",
            "evidence": {"skipped": skipped},
        })
    elif mem_hits > 0 or len(vector_hits) > 0:
        findings.append({
            "check": "memory_usage",
            "severity": "OK",
            "msg": f"Memory used: {mem_hits} SQL hits, {len(vector_hits)} vector hits",
            "evidence": {"mem_hits": mem_hits, "vector_hits": len(vector_hits)},
        })


def _check_validation(findings: list, recommendations: list, validation: dict | None) -> None:
    """Was validation successful?"""
    if not validation:
        return

    passed = validation.get("passed")
    n_checks = validation.get("n_checks") or 0
    n_passed = validation.get("n_passed") or 0
    confidence = validation.get("confidence") or 0

    if passed:
        findings.append({
            "check": "validation",
            "severity": "OK",
            "msg": f"Validation passed: {n_passed}/{n_checks} checks (confidence {confidence:.2f})",
            "evidence": {"n_checks": n_checks, "n_passed": n_passed, "confidence": confidence},
        })
    else:
        failed_checks = [c for c in (validation.get("checks") or []) if not c.get("passed")]
        failed_msgs = [c.get("check") for c in failed_checks]
        findings.append({
            "check": "validation",
            "severity": "WARNING",
            "msg": f"Validation failed: {n_passed}/{n_checks} checks. Failed: {', '.join(failed_msgs)}",
            "evidence": {"n_checks": n_checks, "n_passed": n_passed, "failed": failed_msgs},
        })
        recommendations.append({
            "type": "correctness",
            "msg": f"Validation failed for: {', '.join(failed_msgs)}. Review result.",
        })


def _check_scores(findings: list, recommendations: list,
                  scores: dict | None, ttype: str) -> None:
    """Were scores reasonable?"""
    if not scores:
        return

    overall = scores.get("OVERALL")
    if overall is None:
        return

    if overall >= 80:
        findings.append({
            "check": "scores",
            "severity": "OK",
            "msg": f"Overall score {overall}/100 — good",
            "evidence": {"overall": overall},
        })
    elif overall >= 50:
        findings.append({
            "check": "scores",
            "severity": "INFO",
            "msg": f"Overall score {overall}/100 — acceptable",
            "evidence": {"overall": overall},
        })
    else:
        findings.append({
            "check": "scores",
            "severity": "WARNING",
            "msg": f"Overall score {overall}/100 — low quality",
            "evidence": {"overall": overall, "correctness": scores.get("CORRECTNESS")},
        })
        recommendations.append({
            "type": "quality",
            "msg": f"Low overall score ({overall}). Check correctness and completeness.",
        })

    # Check token efficiency
    token_eff = scores.get("TOKEN_EFFICIENCY")
    if token_eff is not None and token_eff < 30:
        findings.append({
            "check": "scores",
            "severity": "INFO",
            "msg": f"Token efficiency {token_eff}/100 — high token usage",
            "evidence": {"token_efficiency": token_eff, "tokens_actual": scores.get("tokens_actual")},
        })


def _check_router(findings: list, recommendations: list,
                  pipeline: dict, decision: dict) -> None:
    """Was the router decision correct?"""
    route = pipeline.get("route") or []
    gateway = pipeline.get("gateway") or {}

    # Check for fallback
    if gateway.get("fallback"):
        findings.append({
            "check": "router",
            "severity": "INFO",
            "msg": "Used fallback gateway (DirectAdapter) — OmniRoute down",
            "evidence": {"active": gateway.get("active"), "fallback": True},
        })

    # Check for no provider
    if "NO_PROVIDER" in route:
        findings.append({
            "check": "router",
            "severity": "WARNING",
            "msg": "No LLM provider available — task blocked",
            "evidence": {"route": route},
        })

    # Check for token firewall
    if "TOKEN_FIREWALL_REJECT" in route:
        findings.append({
            "check": "router",
            "severity": "WARNING",
            "msg": "Token firewall rejected task — budget exceeded",
            "evidence": {"route": route, "firewall": pipeline.get("firewall")},
        })


def _check_token_efficiency(findings: list, recommendations: list,
                            pipeline: dict, task: dict, scores: dict | None) -> None:
    """Were tokens used efficiently?"""
    if not scores:
        return

    estimated = task.get("estimated_tokens") or 0
    actual = scores.get("tokens_actual") or 0
    llm_used = scores.get("llm_used")

    if llm_used and actual > 0 and estimated > 0:
        ratio = actual / estimated
        if ratio > 2.0:
            findings.append({
                "check": "token_efficiency",
                "severity": "INFO",
                "msg": f"Actual tokens {actual} > 2x estimated {estimated} (ratio {ratio:.1f})",
                "evidence": {"estimated": estimated, "actual": actual, "ratio": round(ratio, 2)},
            })
        elif ratio < 0.5:
            findings.append({
                "check": "token_efficiency",
                "severity": "OK",
                "msg": f"Actual tokens {actual} < estimated {estimated} — efficient",
                "evidence": {"estimated": estimated, "actual": actual, "ratio": round(ratio, 2)},
            })

    # Check context efficiency
    ctx = pipeline.get("context") or {}
    tokens_saved = ctx.get("tokens_saved") or 0
    if tokens_saved > 0:
        findings.append({
            "check": "token_efficiency",
            "severity": "OK",
            "msg": f"Context dedup saved {tokens_saved} tokens",
            "evidence": {"tokens_saved": tokens_saved},
        })


def _check_unnecessary_steps(findings: list, recommendations: list,
                             pipeline: dict, stages: dict) -> None:
    """Were there unnecessary steps in the pipeline?"""
    # Check if vector cache was searched but not needed
    vector_cache = pipeline.get("vector_cache")
    fast = pipeline.get("fast")
    if vector_cache and fast:
        findings.append({
            "check": "unnecessary_steps",
            "severity": "WARNING",
            "msg": "Vector cache searched for FAST task — unnecessary",
            "evidence": {"vector_cache": len(vector_cache), "fast": fast},
        })
        recommendations.append({
            "type": "performance",
            "msg": "Skip vector cache for FAST tasks — already handled by smart memory.",
        })

    # Check if memory was searched for simple tasks
    mem_hits = pipeline.get("memory_hits") or 0
    cx = int((pipeline.get("task") or {}).get("complexity") or 0)
    if mem_hits > 0 and cx <= 3:
        findings.append({
            "check": "unnecessary_steps",
            "severity": "INFO",
            "msg": f"Memory searched for low-complexity task (cx={cx})",
            "evidence": {"memory_hits": mem_hits, "complexity": cx},
        })


def format_criticism(critique: dict) -> str:
    """Format criticism for chat output."""
    lines = [
        f"THIRD EYE — {critique['overall']} · {critique['n_findings']} findings",
        f"Task {critique['task_id']} · {critique['task_type']} · {critique['exec_mode']} · {critique['via']}",
    ]

    if critique.get("latency_ms"):
        lines.append(f"Latency: {critique['latency_ms']:.0f}ms")

    issues = [f for f in critique.get("findings") or [] if f.get("severity") in ("WARNING", "CRITICAL")]
    oks = [f for f in critique.get("findings") or [] if f.get("severity") == "OK"]
    infos = [f for f in critique.get("findings") or [] if f.get("severity") == "INFO"]

    if issues:
        lines.append("")
        lines.append("ISSUES:")
        for f in issues:
            lines.append(f"  [{f['severity']}] {f['check']}: {f['msg']}")

    if oks:
        lines.append("")
        lines.append("OK:")
        for f in oks[:5]:  # Limit to 5 OK findings
            lines.append(f"  {f['check']}: {f['msg']}")

    if infos:
        lines.append("")
        lines.append("INFO:")
        for f in infos[:3]:  # Limit to 3 INFO findings
            lines.append(f"  {f['check']}: {f['msg']}")

    recs = critique.get("recommendations") or []
    if recs:
        lines.append("")
        lines.append("RECOMMENDATIONS:")
        for r in recs[:3]:  # Limit to 3 recommendations
            lines.append(f"  [{r['type']}] {r['msg']}")

    return "\n".join(lines)


# ═══════════════════════════════
# OUTCOME CRITICISM (Third Eye 2.0)
# ═══════════════════════════════
