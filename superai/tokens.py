"""Token Intelligence — camada transversal.

Não substitui firewall, router, cache, observer, governor.
Não inventa preços, usage de provider, nem poupanças em dinheiro.
"""
from __future__ import annotations

import json
from typing import Any

from .brain import firewall as _firewall
from .config import cfg
from .events import bus
from .store import store
from .util import count_tokens, now_iso, uid

MEASURED = "MEASURED"
ESTIMATED = "ESTIMATED"
CALCULATED = "CALCULATED"
FORECAST = "FORECAST"
UNKNOWN = "UNKNOWN"


def estimate(text: str, extra: int = 0) -> dict:
    tok = count_tokens(text or "")
    total = int(tok["tokens"]) + int(extra)
    return {
        "input_tokens": tok["tokens"],
        "expected_output_tokens": extra,
        "expected_total_tokens": total,
        "kind": ESTIMATED,
        "method": tok["method"],
        "verified": tok.get("verified"),
        "estimated_cost": None,
        "cost_kind": UNKNOWN,
    }


def context_efficiency(raw: str, final: str) -> dict:
    r, f = count_tokens(raw or ""), count_tokens(final or "")
    saved = r["tokens"] - f["tokens"]
    return {
        "raw_estimated_tokens": r["tokens"],
        "final_estimated_tokens": f["tokens"],
        "tokens_saved": saved,
        "kind": ESTIMATED,
        "method": r["method"],
        "note": "poupança de contexto é ESTIMATED (tiktoken), não MEASURED no provider",
    }


def pricing(provider: str | None = None, model: str | None = None) -> dict:
    rows = store.pricing_rows(provider, model)
    if not rows:
        return {
            "kind": UNKNOWN,
            "cost": None,
            "reason": "nenhuma fonte de preço verificada neste host — não se inventa €/1M",
            "rows": [],
        }
    verified = [r for r in rows if r.get("verified") and r.get("source")]
    if not verified:
        return {"kind": UNKNOWN, "cost": None, "reason": "rows sem source verificada", "rows": rows}
    return {"kind": CALCULATED, "rows": verified}


def cost_of(tokens_in: int | None, tokens_out: int | None, provider: str | None, model: str | None) -> dict:
    p = pricing(provider, model)
    if p["kind"] != CALCULATED:
        return {"actual_cost": None, "estimated_cost": None, "kind": UNKNOWN, "currency": None, "reason": p.get("reason")}
    row = p["rows"][0]
    cin = (tokens_in or 0) / 1_000_000 * float(row["input_cost_per_1m"] or 0)
    cout = (tokens_out or 0) / 1_000_000 * float(row["output_cost_per_1m"] or 0)
    return {
        "actual_cost": round(cin + cout, 8),
        "kind": CALCULATED,
        "currency": row.get("currency") or "USD",
        "source": row.get("source"),
    }


def gate(task: dict, extra_tokens: int = 0) -> dict:
    """Reutiliza brain.firewall. Não duplica política."""
    fw = _firewall(task, extra_tokens)
    bus.emit("TOKEN_ESTIMATED", "INFO", f"est={fw.get('estimated')} action={fw.get('action')}")
    if fw.get("action") == "reject":
        bus.emit("TOKEN_BUDGET_EXCEEDED", "CRITICAL", "; ".join(fw.get("reasons") or []))
    elif fw.get("action") == "optimize":
        bus.emit("TOKEN_BUDGET_WARNING", "WARNING", "; ".join(fw.get("reasons") or []))
    return fw


def record(
    *,
    task_id: str,
    estimated: int | None,
    actual: int | None,
    model: str | None = None,
    provider: str | None = None,
    status: str,
    cache_hit: bool = False,
    context_tokens: int | None = None,
    quality_score: float | None = None,
    raw_usage: dict | None = None,
    retry_count: int = 0,
    via: str | None = None,
    latency_ms: float | None = None,
    context: dict | None = None,
    fallback: bool | None = None,
    route_advice: dict | None = None,
) -> dict:
    usage = raw_usage or {}
    inp = usage.get("prompt_tokens") if "prompt_tokens" in usage else usage.get("input_tokens")
    out = usage.get("completion_tokens") if "completion_tokens" in usage else usage.get("output_tokens")
    cached = usage.get("cached_tokens") if "cached_tokens" in usage else None
    reasoning = usage.get("reasoning_tokens") if "reasoning_tokens" in usage else None
    total = usage.get("total_tokens")
    if actual is None and total is not None:
        actual = int(total)
    token_kind = MEASURED if actual is not None else ESTIMATED
    err = None
    if actual is not None and estimated:
        err = round((actual - estimated) / estimated * 100, 2)
    c = cost_of(inp if inp is not None else actual, out, provider, model)
    ev = {
        "id": uid("te"),
        "request_id": uid("req"),
        "task_id": task_id,
        "agent_id": None,
        "project_id": "super-ai",
        "session_id": None,
        "provider": provider,
        "model": model,
        "timestamp": now_iso(),
        "input_tokens": inp,
        "output_tokens": out,
        "cached_tokens": cached,
        "reasoning_tokens": reasoning,
        "total_tokens": total if total is not None else actual,
        "estimated_tokens": estimated,
        "actual_tokens": actual,
        "estimated_cost": None,
        "actual_cost": c.get("actual_cost"),
        "cost_kind": c.get("kind") or UNKNOWN,
        "token_kind": token_kind,
        "latency_ms": latency_ms,
        "status": status,
        "retry_count": retry_count,
        "cache_hit": cache_hit,
        "context_tokens": context_tokens,
        "system_tokens": None,
        "tool_tokens": None,
        "quality_score": quality_score,
        "confidence": None,
        "estimation_error": err,
        "via": via,
        "context": context,
        "fallback": fallback,
        "route_advice": route_advice,
    }
    store.save_token_event(ev)
    store.log_tokens(task_id, int(estimated or 0), int(actual or 0), model, bool(actual and actual > 0 and not cache_hit))
    if cache_hit:
        bus.emit("TOKEN_SAVED", "INFO", f"{task_id} cache_hit actual={actual} est={estimated} kind={token_kind}")
    elif actual and actual > 0:
        bus.emit("TOKEN_CONSUMED", "INFO", f"{task_id} actual={actual} est={estimated} model={model}")
    else:
        bus.emit("TOKEN_CONSUMED", "INFO", f"{task_id} actual=0 via={via} (sem LLM)")
    return ev


def usage_summary() -> dict:
    u = store.usage()
    log = store.token_log_stats()
    cache = store.cache_stats()
    return {
        "kind": MEASURED,
        "session_tokens": u.get("session_tokens", 0),
        "daily_tokens": u.get("daily_tokens", 0),
        "project_tokens": u.get("project_tokens", 0),
        "llm_calls": u.get("llm_calls", 0),
        "tool_calls": u.get("tool_calls", 0),
        "cache_hits": u.get("cache_hits", 0),
        "cache_misses": u.get("cache_misses", 0),
        "cache_hit_rate": cache.get("hit_rate"),
        "token_events": log.get("n", 0),
        "sum_estimated": log.get("sum_estimated", 0),
        "sum_actual": log.get("sum_actual", 0),
        "llm_rows": log.get("llm_rows", 0),
        "note": "session/daily/project só incrementam quando actual>0 (LLM MEASURED)",
    }


def budget_status() -> dict:
    b = cfg.get("budgets") or {}
    u = store.usage()
    def row(name, used, limit):
        limit = int(limit or 0)
        used = int(used or 0)
        remaining = limit - used
        ratio = (used / limit) if limit else 0.0
        hard = used >= limit if limit else False
        return {
            "limit": limit,
            "used_measured": used,
            "remaining": remaining,
            "ratio": round(ratio, 4),
            "warn70": ratio >= 0.7,
            "warn90": ratio >= 0.9,
            "soft": ratio >= 0.9,
            "hard": hard,
        }
    return {
        "kind": MEASURED,
        "task": {"limit": int(b.get("task") or 0), "note": "enforced on ESTIMATED per call, not cumulative"},
        "session": row("session", u.get("session_tokens"), b.get("session")),
        "daily": row("daily", u.get("daily_tokens"), b.get("daily")),
        "project": row("project", u.get("project_tokens"), b.get("project")),
        "agent": {"limit": int(b.get("agent") or 0), "enforced": False, "note": "config existe; não há multi-agent neste processo"},
    }


def forecast() -> dict:
    """FORECAST only. Insufficient history → UNKNOWN, never a fake curve."""
    days = store.token_log_day_count()
    if days < 2:
        return {
            "kind": FORECAST,
            "status": UNKNOWN,
            "reason": f"histórico insuficiente ({days} dia(s) com token_log) — não se projecta",
            "tokens_day": None,
            "tokens_week": None,
            "tokens_month": None,
            "cost_day": None,
            "exhaustion_date": None,
        }
    daily = store.token_log_daily_actual()
    vals = [v for v in daily.values() if v is not None]
    if not vals:
        return {"kind": FORECAST, "status": UNKNOWN, "reason": "actual_tokens todos 0 — sem série MEASURED", "tokens_day": 0}
    avg = sum(vals) / len(vals)
    return {
        "kind": FORECAST,
        "status": FORECAST,
        "tokens_day": round(avg, 1),
        "tokens_week": round(avg * 7, 1),
        "tokens_month": round(avg * 30, 1),
        "cost_day": None,
        "cost_kind": UNKNOWN,
        "n_days": len(vals),
        "note": "média dos actual_tokens diários; custo UNKNOWN",
    }


def anomalies() -> dict:
    rows = store.recent_token_events(40)
    actuals = [int(r["actual_tokens"]) for r in rows if r.get("actual_tokens") is not None]
    if len(actuals) < 8:
        return {"kind": MEASURED, "alerts": [], "reason": f"n={len(actuals)} < 8 — sem anomalia estatística"}
    med = sorted(actuals)[len(actuals) // 2]
    last = actuals[0]
    alerts = []
    if med > 0 and last > med * 8:
        alerts.append({"code": "TOKEN_ANOMALY", "level": "WARNING", "msg": f"último actual={last} vs mediana={med}", "kind": MEASURED})
    retries = sum(int(r.get("retry_count") or 0) for r in rows)
    if retries >= 6:
        alerts.append({"code": "RETRY_SPIKE", "level": "NOTICE", "msg": f"retries={retries} nas últimas {len(rows)}", "kind": MEASURED})
    return {"kind": MEASURED, "alerts": alerts, "median_actual": med, "last_actual": last}


def efficiency() -> dict:
    rats = store.recent_ratings(40)
    overalls = [r.get("OVERALL") for r in rats if isinstance(r.get("OVERALL"), (int, float))]
    toks = sum(int(r.get("tokens_actual") or 0) for r in rats)
    uw = None
    if toks > 0 and overalls:
        uw = round(sum(overalls) / toks, 4)
    claude_tasks = 0
    llm_tasks = store.usage().get("llm_calls", 0)
    dep = None if not llm_tasks else claude_tasks / llm_tasks
    return {
        "kind": MEASURED if toks else UNKNOWN,
        "useful_work_per_token": uw,
        "rating_n": len(overalls),
        "tokens_in_ratings": toks,
        "note": None if toks else "0 tok LLM MEASURED — useful_work/token não é ∞",
        "claude_dependency": {"claude_tasks": claude_tasks, "llm_tasks": llm_tasks, "ratio": dep, "kind": MEASURED},
    }


def adapters_status() -> dict:
    def _mod(name: str) -> dict:
        try:
            __import__(name)
            return {"available": True, "error": None}
        except Exception:
            return {"available": False, "error": f"módulo {name} não instalado — core não depende dele"}

    return {"langfuse": _mod("langfuse"), "litellm": _mod("litellm")}


def route_advice(task: dict) -> dict:
    """Dados quantitativos para o router. Não inverte LLM-last. Não inventa qualidade."""
    from . import providers

    b = budget_status()
    cache = store.cache_stats()
    llm = providers.any_llm()
    est = int(task.get("estimated_tokens") or 0)
    remaining = b["daily"]["remaining"]
    rec = "BLOCK"
    reason: list[str] = []
    if not llm:
        rec = "BLOCK"
        reason.append("nenhum LLM available — não chamar")
    elif b["daily"]["hard"] or b["session"]["hard"]:
        rec = "DEFER"
        reason.append("budget hard MEASURED")
    elif est and remaining is not None and est > remaining:
        rec = "DEFER"
        reason.append(f"estimated {est} > daily remaining {remaining}")
    elif int(task.get("complexity") or 0) >= 8:
        rec = "PREMIUM"
        reason.append("complexidade alta — se LLM, premium; tools/cache já foram tentados")
    else:
        rec = "CHEAP"
        reason.append("complexidade baixa — se LLM, barato primeiro; tools/cache já foram tentados")
    return {
        "estimated_tokens": est,
        "daily_remaining_measured": remaining,
        "cache_hit_rate": cache.get("hit_rate"),
        "any_llm": llm,
        "quality_required": task.get("quality_priority"),
        "recommendation": rec,
        "reason": reason,
        "kind": MEASURED,
        "note": "advisory. runtime continua LLM-last. sem scores de modelo (n=0).",
    }


def models() -> dict:
    """Comparação só com amostras reais. n=0 → UNKNOWN."""
    bench = store.last_benchmark_run() or {}
    n_llm = int(bench.get("n_llm_samples") or 0)
    if n_llm == 0:
        return {
            "kind": UNKNOWN,
            "reason": "n_llm_samples=0 no último benchmark — não se compara modelos",
            "models": [],
        }
    rows = store.recent_token_events(200)
    llm_rows = [r for r in rows if r.get("via") == "llm" and (r.get("actual_tokens") or 0) > 0]
    by: dict[str, dict] = {}
    for r in llm_rows:
        key = r.get("model") or r.get("provider") or "(unknown)"
        slot = by.setdefault(key, {"model": key, "n": 0, "tokens": 0, "retries": 0})
        slot["n"] += 1
        slot["tokens"] += int(r.get("actual_tokens") or 0)
        slot["retries"] += int(r.get("retry_count") or 0)
    return {"kind": MEASURED, "n_llm_samples": n_llm, "models": list(by.values())}


def context_savings() -> dict:
    rows = store.recent_token_events(200)
    saved = 0
    n = 0
    for r in rows:
        try:
            p = json.loads(r.get("payload") or "{}")
        except Exception:
            continue
        ctx = (p or {}).get("context") or {}
        if ctx.get("tokens_saved") is None:
            continue
        saved += int(ctx["tokens_saved"])
        n += 1
    return {
        "events_with_context": n,
        "tokens_saved_estimated": saved,
        "kind": ESTIMATED,
        "actual_savings": None,
        "actual_kind": UNKNOWN,
        "note": "tiktoken raw−final; não é consumo de provider",
    }


def cache_savings() -> dict:
    rows = store.recent_token_events(200)
    hits = [r for r in rows if r.get("cache_hit")]
    est = sum(int(r.get("estimated_tokens") or 0) for r in hits)
    return {
        "hits_measured": len(hits),
        "estimated_savings": est,
        "estimated_kind": ESTIMATED,
        "actual_savings": None,
        "actual_kind": UNKNOWN,
        "note": "cache hit: actual LLM = 0 MEASURED. poupança vs LLM que não correu = ESTIMATED/UNKNOWN",
    }


def retry_stats() -> dict:
    rows = store.recent_token_events(200)
    retries = sum(int(r.get("retry_count") or 0) for r in rows)
    fallbacks = 0
    for r in rows:
        try:
            p = json.loads(r.get("payload") or "{}")
        except Exception:
            p = {}
        if p.get("fallback"):
            fallbacks += 1
    return {
        "kind": MEASURED,
        "retry_count_sum": retries,
        "fallback_events": fallbacks,
        "n": len(rows),
        "note": "neste host retry_count=0 (não repetimos o mesmo prompt). fallback=OmniRoute down → Direct.",
    }


def report() -> dict:
    u = usage_summary()
    return {
        "title": "TOKEN ECONOMY REPORT",
        "period": "spine.db lifetime",
        "total_tokens": {"measured": u["sum_actual"], "estimated": u["sum_estimated"], "kind_measured": MEASURED, "kind_estimated": ESTIMATED},
        "llm_calls": {"value": u["llm_calls"], "kind": MEASURED},
        "cost": pricing(),
        "cache_savings": cache_savings(),
        "context_savings": context_savings(),
        "retries": retry_stats(),
        "forecast": forecast(),
        "efficiency": efficiency(),
        "models": models(),
        "budget": budget_status(),
        "recommendations": _recommendations(u),
    }


def _recommendations(u: dict) -> list[dict]:
    out = []
    if u.get("llm_calls", 0) == 0:
        out.append({"kind": MEASURED, "msg": "0 chamadas LLM — não há desperdício de tokens de modelo para cortar"})
    hr = u.get("cache_hit_rate")
    if hr is not None and u.get("cache_misses", 0) >= 8 and hr < 0.15:
        out.append({"kind": MEASURED, "msg": f"cache hit-rate {hr:.2f} — oportunidade de cache, não de modelo"})
    p = pricing()
    if p["kind"] == UNKNOWN:
        out.append({"kind": UNKNOWN, "msg": "sem source de preço — não se recomenda troca € sem dados"})
    return out


def cost_split() -> dict:
    """Três baldes. Subscrição ≠ API ≠ infra. Nunca somar."""
    c = cfg.get("cost") or {}
    sub = c.get("subscription") or {}
    api = c.get("api") or {}
    infra = c.get("infrastructure") or {}
    return {
        "subscription": {
            "kind": sub.get("kind") or "USER_STATED",
            "amount_eur": sub.get("amount_eur"),
            "currency": sub.get("currency") or "EUR",
            "item": sub.get("item"),
            "official_usd_monthly": sub.get("official_usd_monthly"),
            "official_usd_annual_monthly": sub.get("official_usd_annual_monthly"),
            "source": sub.get("official_source"),
            "note": sub.get("official_note"),
            "includes_vat": bool(sub.get("includes_vat")),
            "official_vat_included": bool(sub.get("official_vat_included")),
            "not_api": True,
            "not_measured_tokens": True,
        },
        "api": {
            "kind": api.get("kind") or UNKNOWN,
            "cost": None,
            "reason": "€/1M não aplicado ao usage Groq/Cerebras deste processo. Tabela Claude (claude.com/pricing) é catálogo, não factura Groq.",
        },
        "infrastructure": {
            "kind": infra.get("kind") or UNKNOWN,
            "cost": None,
            "reason": "este sandbox ≠ PC i5-4590; electricidade/disco não medidos",
        },
        "sum_eur": None,
        "sum_kind": UNKNOWN,
        "note": "não somar USER_STATED + UNKNOWN. 22€ não é consumo de tokens.",
    }


def snapshot() -> dict:
    return {
        "usage": usage_summary(),
        "budget": budget_status(),
        "cost": pricing(),
        "cost_split": cost_split(),
        "forecast": forecast(),
        "anomalies": anomalies(),
        "efficiency": efficiency(),
        "models": models(),
        "report": report(),
        "externals": adapters_status(),
        "policy": [
            "não gastar tokens se ferramenta determinística chega",
            "não inventar preços",
            "estimated ≠ actual",
            "forecast ≠ measured",
            "não optimizar tokens à custa de qualidade não medida",
        ],
    }
