"""Golden-set runner. Records n, skip reasons. Never invents model scores."""
from __future__ import annotations

import time
from typing import Any, Callable

from . import providers, routing
from .events import bus
from .store import store
from .tools import execute
from .util import now_iso, uid

CaseFn = Callable[[], dict]


def _math() -> dict:
    r = execute("calculator", {"expr": "2+2*3"})
    got = (r.get("findings") or [{}])[0].get("result")
    ok = r["status"] == "success" and got == 8
    return {"passed": ok, "score": 100 if ok else 0, "detail": {"got": got, "expect": 8}, "provider": "tool:calculator"}


def _json() -> dict:
    r = execute("json", {"text": '{"a":1,"b":2}'})
    keys = (r.get("findings") or [{}])[0].get("keys")
    ok = r["status"] == "success" and keys == ["a", "b"]
    return {"passed": ok, "score": 100 if ok else 0, "detail": {"keys": keys}, "provider": "tool:json"}


def _embed_sep() -> dict:
    from .embed import cosine, embed

    a = embed("analisa arquitectura deste projecto")
    b = embed("faz uma análise da arquitectura deste projecto")
    c = embed("receita de bacalhau com natas")
    sim_pos, sim_neg = cosine(a, b), cosine(a, c)
    ok = sim_pos > sim_neg
    score = int(max(0, min(100, (sim_pos - sim_neg) * 100)))
    return {
        "passed": ok,
        "score": score,
        "detail": {"sim_paraphrase": round(sim_pos, 4), "sim_unrelated": round(sim_neg, 4)},
        "provider": "embed:hashing",
    }


def _qdrant_roundtrip() -> dict:
    from .memory_vec import vectors

    if not vectors.available():
        return {"passed": False, "score": 0, "skipped": True, "skip_reason": vectors.error or "qdrant down", "provider": "qdrant"}
    key = "bench-roundtrip"
    vectors.upsert("memory", key, "token firewall rejeita contexto demasiado grande", {"kind": "bench"})
    hits = vectors.search("memory", "firewall recusa contexto enorme", k=3, min_score=0.2)
    ok = any(h.get("key") == key or "firewall" in (h.get("text") or "") for h in hits)
    top = hits[0]["score"] if hits else 0
    return {"passed": ok, "score": int(top * 100) if ok else 0, "detail": {"hits": hits[:3]}, "provider": "qdrant-local"}


def _llm_smoke() -> dict:
    hs = providers.health_all()
    up = [h for h in hs if h["available"]]
    if not up:
        return {
            "passed": False,
            "score": None,
            "skipped": True,
            "skip_reason": "nenhum ModelAdapter available (Ollama down, Claude sem key)",
            "provider": "llm",
            "detail": [{"id": h["id"], "available": False} for h in hs],
        }
    t0 = time.perf_counter()
    res = routing.complete("Reply with the single word PONG.", max_tokens=8)
    ms = (time.perf_counter() - t0) * 1000
    ok = res.get("status") == "success" and "PONG" in (res.get("text") or "").upper()
    return {
        "passed": ok,
        "score": 100 if ok else 0,
        "provider": res.get("adapter") or "llm",
        "detail": res,
        "latency_ms": round(ms, 1),
    }


CASES: list[tuple[str, str, CaseFn]] = [
    ("tool_math", "tool", _math),
    ("tool_json", "tool", _json),
    ("embed_separation", "embed", _embed_sep),
    ("qdrant_roundtrip", "vector", _qdrant_roundtrip),
    ("llm_pong", "llm", _llm_smoke),
]


def run(trigger: str = "manual") -> dict:
    run_id = uid("B")
    rows = []
    bus.emit("EXPERIMENT_STARTED", "EVOLUTION", f"benchmark {run_id}")
    for cid, kind, fn in CASES:
        t0 = time.perf_counter()
        try:
            r = fn()
        except Exception as e:
            r = {"passed": False, "score": 0, "skipped": False, "skip_reason": None, "provider": kind, "detail": str(e)}
        ms = r.get("latency_ms")
        if ms is None:
            ms = round((time.perf_counter() - t0) * 1000, 1)
        skipped = bool(r.get("skipped"))
        row = {
            "id": uid("bc"),
            "run_id": run_id,
            "case_id": cid,
            "kind": kind,
            "provider": r.get("provider"),
            "passed": bool(r.get("passed")) and not skipped,
            "score": r.get("score"),
            "latency_ms": ms,
            "skipped": skipped,
            "skip_reason": r.get("skip_reason"),
            "detail": r.get("detail"),
            "ts": now_iso(),
        }
        store.save_benchmark(row)
        rows.append(row)
    n_model = sum(1 for r in rows if r["kind"] == "llm" and not r["skipped"])
    summary = {
        "run_id": run_id,
        "trigger": trigger,
        "n": len(rows),
        "n_llm_samples": n_model,
        "passed": sum(1 for r in rows if r["passed"]),
        "skipped": sum(1 for r in rows if r["skipped"]),
        "rows": rows,
        "ts": now_iso(),
        "note": "scores de modelos só existem se n_llm_samples>0. Aqui não se inventa qualidade Claude/Qwen.",
    }
    bus.emit("EXPERIMENT_COMPLETED", "EVOLUTION", f"benchmark {run_id} passed={summary['passed']} skipped={summary['skipped']}")
    return summary


def last() -> dict | None:
    return store.last_benchmark_run()
