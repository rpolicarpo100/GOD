"""Strategy Learner — learn from past experiences to improve future performance.

Learns:
- Which tools work best for which task types
- Which providers give best quality for which task types
- Optimal complexity routing
- Common failure patterns to avoid
"""
from __future__ import annotations

import json
import time
import threading
from collections import defaultdict
from pathlib import Path

from .config import DATA
from .store import store
from .util import now_iso


class StrategyLearner:
    """Learn strategies from task history."""

    def __init__(self):
        self._path = DATA / "learned_strategies.json"
        self._strategies: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._strategies = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._strategies = {}

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._strategies, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def record_task_outcome(self, task_type: str, via: str, provider: str,
                            quality: float, latency_ms: float, tools_used: list[str]):
        """Record outcome of a task for learning."""
        with self._lock:
            # Learn tool effectiveness per task type
            for tool in tools_used:
                key = f"tool:{task_type}:{tool}"
                s = self._strategies.setdefault(key, {
                    "type": "tool_effectiveness",
                    "task_type": task_type,
                    "tool": tool,
                    "samples": 0,
                    "avg_quality": 0,
                    "avg_latency": 0,
                })
                n = s["samples"]
                s["avg_quality"] = (s["avg_quality"] * n + quality) / (n + 1)
                s["avg_latency"] = (s["avg_latency"] * n + latency_ms) / (n + 1)
                s["samples"] = n + 1
                s["last_used"] = now_iso()

            # Learn provider effectiveness per task type
            if provider:
                key = f"provider:{task_type}:{provider}"
                s = self._strategies.setdefault(key, {
                    "type": "provider_effectiveness",
                    "task_type": task_type,
                    "provider": provider,
                    "samples": 0,
                    "avg_quality": 0,
                    "avg_latency": 0,
                })
                n = s["samples"]
                s["avg_quality"] = (s["avg_quality"] * n + quality) / (n + 1)
                s["avg_latency"] = (s["avg_latency"] * n + latency_ms) / (n + 1)
                s["samples"] = n + 1
                s["last_used"] = now_iso()

            # Learn routing effectiveness
            key = f"route:{task_type}:{via}"
            s = self._strategies.setdefault(key, {
                "type": "routing_effectiveness",
                "task_type": task_type,
                "via": via,
                "samples": 0,
                "avg_quality": 0,
            })
            n = s["samples"]
            s["avg_quality"] = (s["avg_quality"] * n + quality) / (n + 1)
            s["samples"] = n + 1

        self._save()

    def get_best_tool(self, task_type: str) -> str | None:
        """Get best tool for a task type."""
        with self._lock:
            candidates = [
                s for s in self._strategies.values()
                if s.get("type") == "tool_effectiveness"
                and s.get("task_type") == task_type
                and s.get("samples", 0) >= 3
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda s: s.get("avg_quality", 0))["tool"]

    def get_best_provider(self, task_type: str) -> str | None:
        """Get best provider for a task type."""
        with self._lock:
            candidates = [
                s for s in self._strategies.values()
                if s.get("type") == "provider_effectiveness"
                and s.get("task_type") == task_type
                and s.get("samples", 0) >= 3
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda s: s.get("avg_quality", 0))["provider"]

    def get_strategy_summary(self) -> dict:
        """Get summary of learned strategies."""
        with self._lock:
            by_type = defaultdict(list)
            for s in self._strategies.values():
                by_type[s.get("type", "unknown")].append(s)

            summary = {}
            for stype, items in by_type.items():
                if stype == "tool_effectiveness":
                    best = sorted(items, key=lambda x: x.get("avg_quality", 0), reverse=True)[:5]
                    summary["best_tools"] = [{
                        "task_type": i["task_type"],
                        "tool": i["tool"],
                        "quality": round(i["avg_quality"], 2),
                        "samples": i["samples"],
                    } for i in best]
                elif stype == "provider_effectiveness":
                    best = sorted(items, key=lambda x: x.get("avg_quality", 0), reverse=True)[:5]
                    summary["best_providers"] = [{
                        "task_type": i["task_type"],
                        "provider": i["provider"],
                        "quality": round(i["avg_quality"], 2),
                        "samples": i["samples"],
                    } for i in best]
                elif stype == "routing_effectiveness":
                    best = sorted(items, key=lambda x: x.get("avg_quality", 0), reverse=True)[:5]
                    summary["best_routes"] = [{
                        "task_type": i["task_type"],
                        "via": i["via"],
                        "quality": round(i["avg_quality"], 2),
                        "samples": i["samples"],
                    } for i in best]

            summary["total_strategies"] = len(self._strategies)
            summary["total_samples"] = sum(s.get("samples", 0) for s in self._strategies.values())
            return summary


# Global singleton
_learner: StrategyLearner | None = None
_init_lock = threading.Lock()


def get_learner() -> StrategyLearner:
    global _learner
    if _learner is None:
        with _init_lock:
            if _learner is None:
                _learner = StrategyLearner()
    return _learner
