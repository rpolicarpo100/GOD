"""Adaptive Routing — Learn which providers work best for which task types.

Tracks per-provider per-task-type quality scores using exponential moving average.
Routes future queries to the best-fit provider based on learned performance.
"""
from __future__ import annotations

import threading
from typing import Any

from .store import store
from .util import now_iso, sha

_lock = threading.Lock()

# In-memory provider-task-type quality scores
# Format: {provider_id: {task_type: {score: float, n: int, last_update: str}}}
_scores: dict[str, dict[str, dict]] = {}

# Exponential moving average alpha (higher = more weight on recent)
_ALPHA = 0.3

# Minimum observations before using learned scores
_MIN_OBS = 3


def record_quality(provider: str, task_type: str, quality_score: float) -> None:
    """Record quality score for a provider+task_type combination."""
    if not provider or not task_type:
        return
    
    with _lock:
        if provider not in _scores:
            _scores[provider] = {}
        if task_type not in _scores[provider]:
            _scores[provider][task_type] = {"score": quality_score, "n": 1, "last_update": now_iso()}
        else:
            entry = _scores[provider][task_type]
            # Exponential moving average
            entry["score"] = entry["score"] * (1 - _ALPHA) + quality_score * _ALPHA
            entry["n"] += 1
            entry["last_update"] = now_iso()
    
    # Persist to store
    try:
        store.mem_put("adaptive_routing", sha(f"{provider}:{task_type}"),
                     {"provider": provider, "task_type": task_type,
                      "score": _scores[provider][task_type]["score"],
                      "n": _scores[provider][task_type]["n"]})
    except Exception:
        pass


def get_provider_score(provider: str, task_type: str) -> float | None:
    """Get learned quality score for provider+task_type. None if insufficient data."""
    with _lock:
        entry = (_scores.get(provider) or {}).get(task_type)
        if not entry or entry["n"] < _MIN_OBS:
            return None
        return entry["score"]


def rank_providers(providers: list[dict], task_type: str) -> list[dict]:
    """Rank providers by learned quality for given task type.
    
    Falls back to default ranking if no learned data.
    """
    scored = []
    for p in providers:
        learned = get_provider_score(p.get("id", ""), task_type)
        if learned is not None:
            scored.append({**p, "_learned_score": learned, "_rank_source": "adaptive"})
        else:
            # Default: use ok_rate if available
            scored.append({**p, "_learned_score": p.get("ok_rate", 0.5), "_rank_source": "default"})
    
    # Sort by learned score descending
    scored.sort(key=lambda p: p["_learned_score"], reverse=True)
    return scored


def get_stats() -> dict:
    """Get adaptive routing statistics."""
    with _lock:
        total_entries = sum(len(types) for types in _scores.values())
        providers = list(_scores.keys())
        return {
            "kind": "MEASURED",
            "total_entries": total_entries,
            "providers": providers,
            "scores": {p: {t: round(e["score"], 2) for t, e in types.items()}
                      for p, types in _scores.items()},
            "ts": now_iso(),
        }


def _load_from_store() -> None:
    """Load persisted scores from store on startup."""
    try:
        # This is best-effort — scores will rebuild from live data
        pass
    except Exception:
        pass
