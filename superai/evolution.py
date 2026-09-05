"""Evolution Engine — observe, hypothesise, experiment, compare, wait for Governor.

Does not invent GitHub tools. Does not auto-modify production code.
"""
from __future__ import annotations

from typing import Any

from . import benchmark
from .config import cfg
from .embed import cosine, embed
from .events import bus
from .governor import gov
from .store import store
from .util import now_iso, uid

# Controlled paraphrase set — used as a real A/B, not as web research.
PAIRS = [
    ("Analisa a arquitectura deste projecto.", "Faz uma análise da arquitectura deste projecto."),
    ("calcula 2+2*3", "quanto é 2+2*3"),
    ("lista ficheiros em super-ai", "mostra os ficheiros do super-ai"),
]


def _hash_hit(a: str, b: str) -> bool:
    from .util import normalize_query

    return normalize_query(a) == normalize_query(b)


def observe() -> dict:
    from . import tokens as ti

    u = store.usage()
    cache = store.cache_stats()
    tok = ti.usage_summary()
    # retrieval experiment (real numbers)
    hash_hits = sum(1 for a, b in PAIRS if _hash_hit(a, b))
    sem_hits = sum(1 for a, b in PAIRS if cosine(embed(a), embed(b)) >= 0.5)
    n = len(PAIRS)
    gaps = []
    if (cache.get("hit_rate") or 0) < 0.25 and (u.get("cache_misses") or 0) >= 3:
        gaps.append("cache hit-rate baixa")
    if (tok.get("llm_calls") or 0) == 0 and store.tasks(5):
        blocked = sum(1 for t in store.tasks(30) if t.get("via") == "no_provider")
        if blocked:
            gaps.append(f"{blocked} tarefas bloqueadas sem LLM — gap de provider, não de código")
        gaps.append("0 LLM MEASURED — evolução de routing de modelos não aplicável")
    if sem_hits > hash_hits:
        gaps.append("embeddings recuperam paráfrases que o hash cache não colapsa")
    cost = ti.pricing()
    if cost.get("kind") == "UNKNOWN":
        gaps.append("preço de modelos UNKNOWN — não se experimenta troca € sem source")

    snapshot = {
        "usage": u,
        "cache": cache,
        "token": {"llm_calls": tok.get("llm_calls"), "kind": tok.get("kind"), "sum_actual": tok.get("sum_actual")},
        "hash_paraphrase_hits": hash_hits,
        "semantic_paraphrase_hits": sem_hits,
        "pairs": n,
        "gaps": gaps,
        "governor_strict": gov.strict(),
        "ts": now_iso(),
    }
    bus.emit("NOTICE", "EVOLUTION", f"observe gaps={gaps or 'none'}")
    return snapshot


def propose_from_observe(obs: dict | None = None) -> dict:
    obs = obs or observe()
    hash_n = obs["hash_paraphrase_hits"]
    sem_n = obs["semantic_paraphrase_hits"]
    n = obs["pairs"]
    if sem_n <= hash_n:
        exp = {
            "id": uid("X"),
            "title": "Sem promoção — hash já cobre as paráfrases medidas",
            "hypothesis": "Semantic cache não melhora recall neste conjunto.",
            "status": "completed",
            "metric": "paraphrase_hits",
            "before": {"hash": hash_n, "n": n},
            "after": {"semantic": sem_n, "n": n},
            "risk": "low",
            "payload": {"obs": obs, "decision": "no-op"},
            "ts": now_iso(),
        }
        store.save_experiment(exp)
        bus.emit("VERSION_REJECTED", "EVOLUTION", exp["title"])
        return exp

    exp = {
        "id": uid("X"),
        "title": "Promover semantic cache (Qdrant) à frente do hash em paráfrases",
        "hypothesis": f"Embeddings hashing+Qdrant acertam {sem_n}/{n} vs hash {hash_n}/{n}.",
        "status": "pending",
        "metric": "paraphrase_hits",
        "before": {"hash": hash_n, "n": n},
        "after": {"semantic": sem_n, "n": n},
        "risk": "low",
        "payload": {
            "change": "runtime already searches Qdrant cache after hash miss — adopt = keep; reject = disable semantic cache",
            "obs": obs,
        },
        "ts": now_iso(),
    }
    store.save_experiment(exp)
    bus.emit("VERSION_PROPOSED", "EVOLUTION", exp["title"])
    return exp


def decide(xid: str, approve: bool) -> str:
    exp = store.get_experiment(xid)
    if not exp:
        return "experiência não encontrada"
    if exp["status"] not in ("pending",):
        return f"já está {exp['status']}"
    if approve and gov.strict() and exp.get("risk") == "high":
        return "Governor: risco alto exige canal humano fora da AI."
    if approve:
        # Semantic cache is already in the pipeline; adoption is a recorded policy flag.
        cfg.patch({"evolution_policy": {"semantic_cache": True}})
        store.set_experiment_status(xid, "adopted")
        bus.emit("VERSION_ADOPTED", "EVOLUTION", exp["title"])
        store.mem_put("strategic", exp["title"], {"id": xid, "after": exp.get("after")})
        return f"ADOPT {xid}. {exp['title']}\nEvidência: {exp.get('before')} → {exp.get('after')}. Rollback: reject futuro + semantic_cache false."
    store.set_experiment_status(xid, "rejected")
    cfg.patch({"evolution_policy": {"semantic_cache": False}})
    bus.emit("VERSION_REJECTED", "EVOLUTION", exp["title"])
    return f"REJECT {xid}. Semantic cache policy=false. Hash cache mantém-se."


def classify_risk(proposal: dict) -> dict:
    """Classifica o risco de uma proposta de evolução.

    Critérios:
    - LOW: cache/embedding/read-only changes
    - MEDIUM: routing/priority/queue changes
    - HIGH: security/governor/code modification/auto-apply
    """
    title = (proposal.get("title") or "").lower()
    hypothesis = (proposal.get("hypothesis") or "").lower()
    payload = proposal.get("payload") or {}
    change = (payload.get("change") or "").lower()
    text = f"{title} {hypothesis} {change}"

    # HIGH RISK indicators
    high_risk_keywords = [
        "governor", "security", "strict", "auto-apply", "auto_apply",
        "code modification", "refactor", "deploy", "production",
        "disable", "remove limit", "permissão",
    ]
    if any(kw in text for kw in high_risk_keywords):
        return {
            "risk": "high",
            "reason": "contém keywords de segurança/governance",
            "requires_human": True,
            "kind": "MEASURED",
        }

    # MEDIUM RISK indicators
    medium_risk_keywords = [
        "routing", "priority", "queue", "inflight", "provider",
        "model", "adapter", "worker", "threshold",
    ]
    if any(kw in text for kw in medium_risk_keywords):
        return {
            "risk": "medium",
            "reason": "afecta routing/queue/providers",
            "requires_human": gov.strict(),
            "kind": "MEASURED",
        }

    # LOW RISK (default for cache/embedding)
    return {
        "risk": "low",
        "reason": "cache/embedding/read-only",
        "requires_human": False,
        "kind": "MEASURED",
    }


def propose_with_risk(title: str, hypothesis: str, change: str, metric: str,
                      before: dict, after: dict, obs: dict | None = None) -> dict:
    """Propor experimento com classificação de risco automática."""
    proposal = {
        "title": title,
        "hypothesis": hypothesis,
        "payload": {"change": change, "obs": obs},
    }
    risk_info = classify_risk(proposal)

    exp = {
        "id": uid("X"),
        "title": title,
        "hypothesis": hypothesis,
        "status": "pending",
        "metric": metric,
        "before": before,
        "after": after,
        "risk": risk_info["risk"],
        "risk_info": risk_info,
        "requires_human": risk_info["requires_human"],
        "payload": {
            "change": change,
            "obs": obs,
        },
        "ts": now_iso(),
    }

    # Auto-reject HIGH RISK in strict mode (never auto-apply)
    if risk_info["risk"] == "high" and gov.strict():
        exp["status"] = "blocked"
        exp["blocked_reason"] = "Governor strict: HIGH RISK requires human approval outside AI"
        store.save_experiment(exp)
        bus.emit("VERSION_REJECTED", "EVOLUTION", f"BLOCKED: {title}")
        return exp

    store.save_experiment(exp)
    bus.emit("VERSION_PROPOSED", "EVOLUTION", exp["title"])
    return exp


def run_cycle() -> dict:
    obs = observe()
    bench = benchmark.run(trigger="evolution")
    exp = propose_from_observe(obs)
    bus.emit("EXPERIMENT_COMPLETED", "EVOLUTION", f"cycle {exp['id']} + bench {bench['run_id']}")
    return {"observe": obs, "benchmark": bench, "experiment": exp}


def pending() -> list[dict]:
    return [e for e in store.experiments(20) if e.get("status") == "pending"]
