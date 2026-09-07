"""Sandbox for GOD Experiments — test changes safely before deployment.

Provides:
- Experiment sandbox: isolate changes, measure impact, auto-rollback
- Canary deployment: gradual rollout with monitoring
- A/B testing: compare old vs new behavior
"""
from __future__ import annotations

import time
import threading
from typing import Any, Callable
from collections import defaultdict

from .config import cfg
from .events import bus
from .store import store
from .util import now_iso, sha


class ExperimentSandbox:
    """Sandbox for running experiments safely."""

    def __init__(self):
        self._active: dict[str, dict] = {}
        self._results: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.RLock()

    def create_experiment(self, name: str, description: str,
                          old_behavior: str, new_behavior: str,
                          metric: str = "quality") -> dict:
        """Create a new experiment in the sandbox."""
        xid = sha(f"exp:{name}:{time.time()}")
        exp = {
            "id": xid,
            "name": name,
            "description": description,
            "old_behavior": old_behavior,
            "new_behavior": new_behavior,
            "metric": metric,
            "status": "created",
            "created_at": now_iso(),
            "samples": {"old": [], "new": []},
            "canary_pct": 0,
            "max_canary_pct": 50,
        }
        with self._lock:
            self._active[xid] = exp
        store.save_experiment(exp)
        bus.emit("EXPERIMENT_CREATED", "INFO", f"{name}: {description}")
        return exp

    def run_trial(self, xid: str, variant: str, input_data: Any,
                  output_data: Any, quality_score: float) -> dict:
        """Record a trial result for old or new behavior."""
        with self._lock:
            exp = self._active.get(xid)
            if not exp:
                return {"ok": False, "error": "experiment not found"}
            trial = {
                "input": str(input_data)[:200],
                "output": str(output_data)[:200],
                "quality": quality_score,
                "ts": time.time(),
            }
            exp["samples"][variant].append(trial)
            self._results[xid].append({**trial, "variant": variant})
        return {"ok": True, "variant": variant, "quality": quality_score}

    def evaluate(self, xid: str) -> dict:
        """Evaluate experiment results — is new better than old?"""
        with self._lock:
            exp = self._active.get(xid)
            if not exp:
                return {"ok": False, "error": "experiment not found"}
            old_scores = [s["quality"] for s in exp["samples"]["old"]]
            new_scores = [s["quality"] for s in exp["samples"]["new"]]

        if not old_scores or not new_scores:
            return {"ok": True, "status": "insufficient_data",
                    "old_samples": len(old_scores), "new_samples": len(new_scores)}

        old_avg = sum(old_scores) / len(old_scores)
        new_avg = sum(new_scores) / len(new_scores)
        improvement = new_avg - old_avg
        improvement_pct = (improvement / old_avg * 100) if old_avg > 0 else 0

        # Statistical significance (simple: need at least 5 samples each)
        sufficient = len(old_scores) >= 5 and len(new_scores) >= 5
        significant = sufficient and abs(improvement_pct) > 5  # 5% threshold

        recommendation = "keep_old"
        if significant and improvement > 0:
            recommendation = "adopt_new"
        elif significant and improvement < 0:
            recommendation = "rollback"
        elif sufficient:
            recommendation = "inconclusive"

        result = {
            "ok": True,
            "status": "evaluated",
            "old_avg": round(old_avg, 2),
            "new_avg": round(new_avg, 2),
            "improvement": round(improvement, 2),
            "improvement_pct": round(improvement_pct, 1),
            "old_samples": len(old_scores),
            "new_samples": len(new_scores),
            "sufficient": sufficient,
            "significant": significant,
            "recommendation": recommendation,
        }

        exp["evaluation"] = result
        store.save_experiment(exp)
        return result

    def canary_deploy(self, xid: str, pct: int) -> dict:
        """Set canary deployment percentage (0-100)."""
        with self._lock:
            exp = self._active.get(xid)
            if not exp:
                return {"ok": False, "error": "experiment not found"}
            exp["canary_pct"] = min(pct, exp["max_canary_pct"])
            exp["status"] = "canary"
            store.save_experiment(exp)
        return {"ok": True, "canary_pct": exp["canary_pct"]}

    def should_use_new(self, xid: str) -> bool:
        """Decide whether to use new behavior based on canary percentage."""
        import random
        with self._lock:
            exp = self._active.get(xid)
            if not exp:
                return False
            return random.randint(1, 100) <= exp.get("canary_pct", 0)

    def adopt(self, xid: str) -> dict:
        """Fully adopt the new behavior."""
        with self._lock:
            exp = self._active.get(xid)
            if not exp:
                return {"ok": False, "error": "experiment not found"}
            exp["status"] = "adopted"
            exp["canary_pct"] = 100
            store.save_experiment(exp)
        bus.emit("EXPERIMENT_ADOPTED", "INFO", exp["name"])
        return {"ok": True, "status": "adopted"}

    def rollback(self, xid: str, reason: str = "") -> dict:
        """Rollback to old behavior."""
        with self._lock:
            exp = self._active.get(xid)
            if not exp:
                return {"ok": False, "error": "experiment not found"}
            exp["status"] = "rolled_back"
            exp["canary_pct"] = 0
            exp["rollback_reason"] = reason
            store.save_experiment(exp)
        bus.emit("EXPERIMENT_ROLLED_BACK", "INFO", f"{exp['name']}: {reason}")
        return {"ok": True, "status": "rolled_back"}

    def list_experiments(self) -> list[dict]:
        """List all active experiments."""
        with self._lock:
            return list(self._active.values())

    def get_experiment(self, xid: str) -> dict | None:
        with self._lock:
            return self._active.get(xid)


# Global singleton
_sandbox: ExperimentSandbox | None = None
_init_lock = threading.Lock()


def get_sandbox() -> ExperimentSandbox:
    global _sandbox
    if _sandbox is None:
        with _init_lock:
            if _sandbox is None:
                _sandbox = ExperimentSandbox()
    return _sandbox
