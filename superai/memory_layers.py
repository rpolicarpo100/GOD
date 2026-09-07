"""5-Layer Memory System for GOD.

Layers (inspired by human cognition):
1. WORKING — short-term, high-fidelity, limited capacity (7±2 items)
2. EPISODIC — events/conversations, timestamped, auto-consolidated
3. SEMANTIC — facts/knowledge, high confidence, long-term
4. PROCEDURAL — how-to knowledge, learned strategies, pattern-based
5. SELF — self-model, capabilities, limitations, introspection

Each layer has different retention, consolidation, and retrieval logic.
"""
from __future__ import annotations

import json
import time
import threading
from typing import Any
from pathlib import Path
from collections import OrderedDict

from .config import DATA

# Layer constants
WORKING = "working"
EPISODIC = "episodic"
SEMANTIC = "semantic"
PROCEDURAL = "procedural"
SELF = "self"

ALL_LAYERS = [WORKING, EPISODIC, SEMANTIC, PROCEDURAL, SELF]

# Capacity limits
WORKING_CAPACITY = 9  # 7±2 (Miller's Law)
EPISODIC_RETENTION_DAYS = 30
SEMANTIC_MIN_CONFIDENCE = 0.7
PROCEDURAL_MIN_SUCCESS_RATE = 0.6


class MemoryLayer:
    """A single memory layer with its own storage and retrieval rules."""

    def __init__(self, name: str, capacity: int = 0, min_confidence: float = 0.0):
        self.name = name
        self.capacity = capacity  # 0 = unlimited
        self.min_confidence = min_confidence
        self._store: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.RLock()

    def add(self, key: str, data: dict) -> bool:
        """Add item to this layer. Returns False if rejected."""
        with self._lock:
            if self.capacity > 0 and len(self._store) >= self.capacity:
                # Evict oldest
                self._store.popitem(last=False)
            data["_layer"] = self.name
            data["_added_at"] = time.time()
            self._store[key] = data
            return True

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._store.get(key)

    def remove(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._store.values())

    def count(self) -> int:
        with self._lock:
            return len(self._store)

    def clear(self):
        with self._lock:
            self._store.clear()


class WorkingMemory(MemoryLayer):
    """Short-term memory with limited capacity (Miller's Law: 7±2 items)."""

    def __init__(self):
        super().__init__(WORKING, capacity=WORKING_CAPACITY, min_confidence=0.0)

    def add(self, key: str, data: dict) -> bool:
        """Add to working memory, evicting oldest if full."""
        data["priority"] = data.get("priority", "normal")
        return super().add(key, data)

    def consolidate(self, episodic: "EpisodicMemory") -> list[str]:
        """Move completed items to episodic memory. Returns consolidated keys."""
        consolidated = []
        with self._lock:
            to_move = []
            for key, data in self._store.items():
                if data.get("status") == "completed" or data.get("consolidate"):
                    to_move.append(key)
            for key in to_move:
                data = self._store.pop(key)
                data.pop("priority", None)
                episodic.add(key, data)
                consolidated.append(key)
        return consolidated


class EpisodicMemory(MemoryLayer):
    """Event/conversation memory with timestamps and auto-cleanup."""

    def __init__(self):
        super().__init__(EPISODIC, capacity=0, min_confidence=0.0)
        self._path = DATA / "memory_episodic.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                items = json.loads(self._path.read_text(encoding="utf-8"))
                for item in items:
                    key = item.get("_key", item.get("id", str(hash(json.dumps(item, sort_keys=True)))))
                    self._store[key] = item
            except Exception:
                pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(list(self._store.values()), ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def add(self, key: str, data: dict) -> bool:
        data["_key"] = key
        result = super().add(key, data)
        self._save()
        return result

    def cleanup_old(self, days: int = EPISODIC_RETENTION_DAYS) -> int:
        """Remove entries older than N days."""
        cutoff = time.time() - (days * 86400)
        removed = 0
        with self._lock:
            to_remove = [k for k, v in self._store.items() if v.get("_added_at", 0) < cutoff]
            for k in to_remove:
                del self._store[k]
                removed += 1
        if removed:
            self._save()
        return removed

    def consolidate_to_semantic(self, semantic: "SemanticMemory") -> list[str]:
        """Promote high-confidence episodic memories to semantic."""
        promoted = []
        with self._lock:
            for key, data in list(self._store.items()):
                conf = data.get("confidence", 0.5)
                access = data.get("access_count", 0)
                if conf >= SEMANTIC_MIN_CONFIDENCE and access >= 3:
                    semantic.add(key, {**data, "_promoted_from": EPISODIC})
                    promoted.append(key)
        return promoted


class SemanticMemory(MemoryLayer):
    """Facts/knowledge memory — high confidence, long-term storage."""

    def __init__(self):
        super().__init__(SEMANTIC, capacity=0, min_confidence=SEMANTIC_MIN_CONFIDENCE)
        self._path = DATA / "memory_semantic.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                items = json.loads(self._path.read_text(encoding="utf-8"))
                for item in items:
                    key = item.get("_key", item.get("id", str(hash(json.dumps(item, sort_keys=True)))))
                    self._store[key] = item
            except Exception:
                pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(list(self._store.values()), ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def add(self, key: str, data: dict) -> bool:
        conf = data.get("confidence", 0.5)
        if conf < self.min_confidence:
            return False
        data["_key"] = key
        result = super().add(key, data)
        self._save()
        return result

    def query(self, pattern: str) -> list[dict]:
        """Simple pattern-matching query."""
        results = []
        pattern_lower = pattern.lower()
        with self._lock:
            for data in self._store.values():
                text = json.dumps(data, ensure_ascii=False).lower()
                if pattern_lower in text:
                    results.append(data)
        return results


class ProceduralMemory(MemoryLayer):
    """How-to knowledge — learned strategies and patterns."""

    def __init__(self):
        super().__init__(PROCEDURAL, capacity=0, min_confidence=PROCEDURAL_MIN_SUCCESS_RATE)
        self._path = DATA / "memory_procedural.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                items = json.loads(self._path.read_text(encoding="utf-8"))
                for item in items:
                    key = item.get("_key", item.get("id", str(hash(json.dumps(item, sort_keys=True)))))
                    self._store[key] = item
            except Exception:
                pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(list(self._store.values()), ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def add(self, key: str, data: dict) -> bool:
        data["_key"] = key
        data["success_count"] = data.get("success_count", 0)
        data["failure_count"] = data.get("failure_count", 0)
        data["total_attempts"] = data["success_count"] + data["failure_count"]
        result = super().add(key, data)
        self._save()
        return result

    def record_outcome(self, key: str, success: bool) -> bool:
        """Record a success/failure for a procedure."""
        with self._lock:
            data = self._store.get(key)
            if not data:
                return False
            if success:
                data["success_count"] = data.get("success_count", 0) + 1
            else:
                data["failure_count"] = data.get("failure_count", 0) + 1
            data["total_attempts"] = data.get("success_count", 0) + data.get("failure_count", 0)
            total = data["total_attempts"]
            data["success_rate"] = data.get("success_count", 0) / total if total > 0 else 0
            data["last_outcome"] = "success" if success else "failure"
            data["last_outcome_at"] = time.time()
        self._save()
        return True

    def best_strategies(self, n: int = 5) -> list[dict]:
        """Return top N strategies by success rate (with minimum attempts)."""
        with self._lock:
            eligible = [d for d in self._store.values() if d.get("total_attempts", 0) >= 2]
            eligible.sort(key=lambda d: d.get("success_rate", 0), reverse=True)
            return eligible[:n]


class SelfMemory(MemoryLayer):
    """Self-model memory — capabilities, limitations, introspection."""

    def __init__(self):
        super().__init__(SELF, capacity=0, min_confidence=0.0)
        self._path = DATA / "memory_self.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                items = json.loads(self._path.read_text(encoding="utf-8"))
                for item in items:
                    key = item.get("_key", item.get("id", str(hash(json.dumps(item, sort_keys=True)))))
                    self._store[key] = item
            except Exception:
                pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(list(self._store.values()), ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def add(self, key: str, data: dict) -> bool:
        data["_key"] = key
        result = super().add(key, data)
        self._save()
        return result

    def get_capabilities(self) -> list[dict]:
        return [d for d in self._store.values() if d.get("type") == "capability"]

    def get_limitations(self) -> list[dict]:
        return [d for d in self._store.values() if d.get("type") == "limitation"]

    def update_self_assessment(self, assessment: dict):
        """Update self-assessment from introspection."""
        self.add("_self_assessment", {
            "type": "assessment",
            "assessment": assessment,
            "updated_at": time.time(),
        })


class MemorySystem:
    """Unified 5-layer memory system."""

    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.procedural = ProceduralMemory()
        self.self_mem = SelfMemory()
        self._consolidation_count = 0

    def remember(self, key: str, data: dict, layer: str = EPISODIC) -> bool:
        """Store in specified layer."""
        layers = {
            WORKING: self.working,
            EPISODIC: self.episodic,
            SEMANTIC: self.semantic,
            PROCEDURAL: self.procedural,
            SELF: self.self_mem,
        }
        target = layers.get(layer)
        if not target:
            return False
        return target.add(key, data)

    def recall(self, key: str, layer: str | None = None) -> dict | None:
        """Recall from specific layer or search all."""
        if layer:
            layers = {
                WORKING: self.working,
                EPISODIC: self.episodic,
                SEMANTIC: self.semantic,
                PROCEDURAL: self.procedural,
                SELF: self.self_mem,
            }
            target = layers.get(layer)
            return target.get(key) if target else None
        # Search all layers (priority: working > semantic > procedural > episodic)
        for mem in [self.working, self.semantic, self.procedural, self.episodic, self.self_mem]:
            result = mem.get(key)
            if result:
                return result
        return None

    def consolidate(self) -> dict:
        """Run consolidation cycle: working→episodic→semantic."""
        to_episodic = self.working.consolidate(self.episodic)
        self.episodic.cleanup_old()
        to_semantic = self.episodic.consolidate_to_semantic(self.semantic)
        self._consolidation_count += 1
        return {
            "working_to_episodic": len(to_episodic),
            "episodic_to_semantic": len(to_semantic),
            "consolidation_cycle": self._consolidation_count,
        }

    def learn_procedure(self, key: str, data: dict) -> bool:
        """Store a learned procedure."""
        return self.procedural.add(key, data)

    def record_procedure_outcome(self, key: str, success: bool) -> bool:
        """Record success/failure of a procedure."""
        return self.procedural.record_outcome(key, success)

    def get_strategies(self, n: int = 5) -> list[dict]:
        """Get best learned strategies."""
        return self.procedural.best_strategies(n)

    def stats(self) -> dict:
        """Memory system statistics."""
        return {
            "working": {"count": self.working.count(), "capacity": WORKING_CAPACITY},
            "episodic": {"count": self.episodic.count()},
            "semantic": {"count": self.semantic.count()},
            "procedural": {"count": self.procedural.count()},
            "self": {"count": self.self_mem.count()},
            "total": (self.working.count() + self.episodic.count() +
                      self.semantic.count() + self.procedural.count() +
                      self.self_mem.count()),
            "consolidation_cycles": self._consolidation_count,
        }


# Global singleton
_mem: MemorySystem | None = None
_init_lock = threading.Lock()


def get_memory() -> MemorySystem:
    global _mem
    if _mem is None:
        with _init_lock:
            if _mem is None:
                _mem = MemorySystem()
    return _mem
