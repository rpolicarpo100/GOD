"""Autonomous Missions — GOD self-initiates learning tasks.

Detects opportunities and creates missions:
- Knowledge gaps (repeated low-quality topics)
- Skill improvements (procedures with low success rate)
- Optimization targets (high-latency or high-token patterns)
- Memory consolidation needs
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any

from .config import DATA
from .store import store
from .events import bus
from .util import now_iso, sha
import logging

_log = logging.getLogger("superai.missions")


class Mission:
    """A self-initiated learning mission."""

    def __init__(self, mission_type: str, target: str, reason: str, priority: int = 5):
        self.id = sha(f"mission:{mission_type}:{target}:{time.time()}")
        self.type = mission_type  # knowledge_gap, skill_improve, optimize, consolidate
        self.target = target
        self.reason = reason
        self.priority = priority  # 1=highest, 10=lowest
        self.status = "pending"  # pending, running, completed, failed, abandoned
        self.created_at = now_iso()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.result: dict | None = None
        self.attempts = 0
        self.max_attempts = 3

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "target": self.target,
            "reason": self.reason, "priority": self.priority,
            "status": self.status, "created_at": self.created_at,
            "started_at": self.started_at, "completed_at": self.completed_at,
            "result": self.result, "attempts": self.attempts,
        }


class MissionControl:
    """Autonomous mission controller."""

    def __init__(self):
        self._missions: dict[str, Mission] = {}
        self._completed: list[dict] = []
        self._lock = threading.RLock()
        self._path = DATA / "missions_history.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._completed = data.get("completed", [])
            except Exception:
                pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({
                "completed": self._completed[-100:],  # keep last 100
            }, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def detect_opportunities(self) -> list[Mission]:
        """Scan system state for improvement opportunities."""
        missions = []

        # 1. Knowledge gaps: repeated low-quality topics
        try:
            gaps = store.mem_search("", kinds=["knowledge_gap"])
            for gap in (gaps or []):
                val = gap.get("value", {})
                if isinstance(val, dict) and val.get("count", 0) >= 3:
                    m = Mission(
                        mission_type="knowledge_gap",
                        target=val.get("topic", "unknown")[:100],
                        reason=f"Low quality repeated {val.get('count', 0)}x (score {val.get('last_score', 0)})",
                        priority=3,
                    )
                    missions.append(m)
        except Exception:
            pass

        # 2. Memory consolidation needed
        try:
            from .memory_layers import get_memory
            mem = get_memory()
            stats = mem.stats()
            if stats["working"]["count"] >= stats["working"]["capacity"] * 0.8:
                missions.append(Mission(
                    mission_type="consolidate",
                    target="working_memory",
                    reason=f"Working memory at {stats['working']['count']}/{stats['working']['capacity']}",
                    priority=2,
                ))
        except Exception:
            pass

        # 3. Provider optimization: check for slow providers
        try:
            from .trace import all_provider_scores
            scores = all_provider_scores()
            for provider, data in (scores or {}).items():
                if isinstance(data, dict) and data.get("p95_ms", 0) > 10000:
                    missions.append(Mission(
                        mission_type="optimize",
                        target=f"provider:{provider}",
                        reason=f"P95 latency {data['p95_ms']:.0f}ms > 10s threshold",
                        priority=5,
                    ))
        except Exception:
            pass

        # 4. Strategy learning: check for unexplored task types
        try:
            from .strategy_learner import get_learner
            summary = get_learner().get_strategy_summary()
            if summary.get("total_samples", 0) < 10:
                missions.append(Mission(
                    mission_type="skill_improve",
                    target="general",
                    reason=f"Only {summary['total_samples']} samples — need more data",
                    priority=6,
                ))
        except Exception:
            pass

        return missions

    def create_mission(self, mission_type: str, target: str, reason: str, priority: int = 5) -> Mission:
        """Create a new mission."""
        m = Mission(mission_type, target, reason, priority)
        with self._lock:
            self._missions[m.id] = m
        bus.emit("MISSION_CREATED", "INFO", f"{mission_type}: {target}")
        return m

    def start_mission(self, mission_id: str) -> dict:
        """Start executing a mission."""
        with self._lock:
            m = self._missions.get(mission_id)
            if not m:
                return {"ok": False, "error": "mission not found"}
            if m.status not in ("pending", "failed"):
                return {"ok": False, "error": f"cannot start mission in status '{m.status}'"}
            m.status = "running"
            m.started_at = now_iso()
            m.attempts += 1
        bus.emit("MISSION_STARTED", "INFO", f"{m.type}: {m.target}")
        return {"ok": True, "mission": m.to_dict()}

    def complete_mission(self, mission_id: str, result: dict) -> dict:
        """Mark mission as completed."""
        with self._lock:
            m = self._missions.get(mission_id)
            if not m:
                return {"ok": False, "error": "mission not found"}
            m.status = "completed"
            m.completed_at = now_iso()
            m.result = result
            self._completed.append(m.to_dict())
            del self._missions[m.id]
        self._save()
        bus.emit("MISSION_COMPLETED", "INFO", f"{m.type}: {m.target}")
        # Record telemetry
        try:
            from .trace import record_system_metric
            record_system_metric("missions_completed")
        except Exception:
            pass
        return {"ok": True, "mission": m.to_dict()}

    def fail_mission(self, mission_id: str, reason: str) -> dict:
        """Mark mission as failed."""
        with self._lock:
            m = self._missions.get(mission_id)
            if not m:
                return {"ok": False, "error": "mission not found"}
            if m.attempts >= m.max_attempts:
                m.status = "abandoned"
                m.result = {"error": reason, "abandoned": True}
                self._completed.append(m.to_dict())
                del self._missions[m.id]
            else:
                m.status = "failed"
                m.result = {"error": reason}
        self._save()
        bus.emit("MISSION_FAILED", "WARNING", f"{m.type}: {m.target}: {reason}")
        return {"ok": True, "mission": m.to_dict()}

    def get_pending(self) -> list[dict]:
        """Get pending missions sorted by priority."""
        with self._lock:
            pending = [m for m in self._missions.values() if m.status == "pending"]
            pending.sort(key=lambda m: m.priority)
            return [m.to_dict() for m in pending]

    def get_active(self) -> list[dict]:
        """Get running missions."""
        with self._lock:
            return [m.to_dict() for m in self._missions.values() if m.status == "running"]

    def get_history(self, n: int = 20) -> list[dict]:
        """Get completed mission history."""
        return self._completed[-n:]

    def auto_detect_and_create(self) -> list[dict]:
        """Auto-detect opportunities and create missions."""
        opportunities = self.detect_opportunities()
        created = []
        for m in opportunities:
            # Avoid duplicates
            existing = [x for x in self._missions.values()
                       if x.type == m.type and x.target == m.target and x.status in ("pending", "running")]
            if not existing:
                with self._lock:
                    self._missions[m.id] = m
                created.append(m.to_dict())
                bus.emit("MISSION_CREATED", "INFO", f"Auto: {m.type}: {m.target}")
        return created

    def stats(self) -> dict:
        """Mission control statistics."""
        with self._lock:
            by_status = {}
            for m in self._missions.values():
                by_status[m.status] = by_status.get(m.status, 0) + 1
            return {
                "active": len(self._missions),
                "by_status": by_status,
                "completed_total": len(self._completed),
                "completed_recent": self._completed[-5:],
            }


# Global singleton
_mc: MissionControl | None = None
_init_lock = threading.Lock()


def get_mission_control() -> MissionControl:
    global _mc
    if _mc is None:
        with _init_lock:
            if _mc is None:
                _mc = MissionControl()
    return _mc
