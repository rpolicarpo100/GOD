"""Cache — L1 (hash) + L2 (semantic) cache system.

L1: Exact hash match (fastest, ~0.1ms)
L2: Semantic similarity via embeddings (~5ms)

Features:
- Two-level cache hierarchy
- TTL support
- Size-based eviction
- Hit/miss statistics
- Thread-safe
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import DATA
from .util import now_iso, sha

# ═══════════════════════════════
# CONFIGURATION
# ═══════════════════════════════

L1_MAX_SIZE = 500
L1_TTL_SECONDS = 3600  #1 hour
L2_TTL_SECONDS = 86400  #24 hours
CACHE_DIR = DATA / "cache"


class L1Cache:
    """L1: In-memory hash cache (exact match)."""
    
    def __init__(self, max_size: int = L1_MAX_SIZE, ttl: int = L1_TTL_SECONDS):
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._stats = {"hits": 0, "misses": 0, "stores": 0, "evictions": 0}
    
    def get(self, key: str) -> dict | None:
        """Get entry by key."""
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                self._stats["misses"] += 1
                return None
            
            # Check TTL
            if time.time() - entry["ts"] > self._ttl:
                del self._entries[key]
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            entry["last_access"] = time.time()
            return entry["value"]
    
    def put(self, key: str, value: dict, quality: float = 0):
        """Store entry."""
        with self._lock:
            self._entries[key] = {
                "value": value,
                "quality": quality,
                "ts": time.time(),
                "last_access": time.time(),
            }
            self._stats["stores"] += 1
            
            # Evict if over size
            if len(self._entries) > self._max_size:
                self._evict()
    
    def _evict(self):
        """Evict oldest entries."""
        if len(self._entries) <= self._max_size:
            return
        
        # Sort by last_access, remove oldest
        sorted_entries = sorted(
            self._entries.items(),
            key=lambda x: x[1].get("last_access", 0),
        )
        
        to_remove = len(self._entries) - self._max_size
        for key, _ in sorted_entries[:to_remove]:
            del self._entries[key]
            self._stats["evictions"] += 1
    
    def invalidate(self, key: str) -> bool:
        """Invalidate entry."""
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
            return False
    
    def clear(self):
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
    
    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                "kind": "MEASURED",
                "level": "L1",
                "size": len(self._entries),
                "max_size": self._max_size,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "stores": self._stats["stores"],
                "evictions": self._stats["evictions"],
                "hit_rate": round(self._stats["hits"] / max(total, 1), 3),
                "ttl_seconds": self._ttl,
            }


class L2Cache:
    """L2: Semantic cache via embeddings."""
    
    def __init__(self, ttl: int = L2_TTL_SECONDS):
        self._lock = threading.Lock()
        self._ttl = ttl
        self._vectors = None
        self._initialized = False
        self._stats = {"hits": 0, "misses": 0, "stores": 0}
    
    def _ensure_init(self):
        if self._initialized:
            return
        try:
            from .memory_vec import vectors
            self._vectors = vectors
        except Exception:
            pass
        self._initialized = True
    
    def available(self) -> bool:
        """Check if L2 cache is available."""
        self._ensure_init()
        return self._vectors is not None and self._vectors.available()
    
    def get(self, query: str, min_score: float = 0.75) -> dict | None:
        """Get semantically similar entry."""
        if not self.available():
            self._stats["misses"] += 1
            return None
        
        try:
            results = self._vectors.search("cache", query, k=1, min_score=min_score)
            if results:
                self._stats["hits"] += 1
                return results[0]
            self._stats["misses"] += 1
            return None
        except Exception:
            self._stats["misses"] += 1
            return None
    
    def put(self, key: str, text: str, data: dict, quality: float = 0):
        """Store entry."""
        if not self.available():
            return
        
        try:
            self._vectors.upsert("cache", key, text, {
                "result": data,
                "quality": quality,
                "ts": now_iso(),
            })
            self._stats["stores"] += 1
        except Exception:
            pass
    
    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                "kind": "MEASURED",
                "level": "L2",
                "available": self.available(),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "stores": self._stats["stores"],
                "hit_rate": round(self._stats["hits"] / max(total, 1), 3),
                "ttl_seconds": self._ttl,
            }


class CacheManager:
    """Two-level cache manager."""
    
    def __init__(self):
        self.l1 = L1Cache()
        self.l2 = L2Cache()
    
    def get(self, text: str, ns: str = "") -> dict | None:
        """Get from L1 (exact) or L2 (semantic)."""
        key = sha(text + (f"\n{ns}" if ns else ""))
        
        # L1: exact match
        result = self.l1.get(key)
        if result:
            return {"source": "L1", "result": result}
        
        # L2: semantic match
        result = self.l2.get(text)
        if result:
            # Store in L1 for faster future access
            self.l1.put(key, result, result.get("quality", 0))
            return {"source": "L2", "result": result}
        
        return None
    
    def put(self, text: str, result: dict, quality: float, ns: str = ""):
        """Store in both L1 and L2."""
        key = sha(text + (f"\n{ns}" if ns else ""))
        
        self.l1.put(key, result, quality)
        self.l2.put(key, text, result, quality)
    
    def stats(self) -> dict:
        """Get combined cache statistics."""
        return {
            "kind": "MEASURED",
            "l1": self.l1.stats(),
            "l2": self.l2.stats(),
        }
    
    def format_stats(self) -> str:
        """Format stats for display."""
        stats = self.stats()
        l1 = stats["l1"]
        l2 = stats["l2"]
        
        lines = [
            f"Cache System:",
            f"  L1 (hash): {l1['hits']} hits / {l1['misses']} misses ({l1['hit_rate']*100:.1f}% hit rate)",
            f"    Size: {l1['size']}/{l1['max_size']} entries",
            f"  L2 (semantic): {l2['hits']} hits / {l2['misses']} misses ({l2['hit_rate']*100:.1f}% hit rate)",
            f"    Available: {'Yes' if l2.get('available') else 'No'}",
        ]
        
        return "\n".join(lines)


# Global cache manager
_cache = CacheManager()


def get_cache() -> CacheManager:
    """Get the global cache manager."""
    return _cache


def cache_get(text: str, ns: str = "") -> dict | None:
    """Get from cache."""
    return _cache.get(text, ns)


def cache_put(text: str, result: dict, quality: float, ns: str = ""):
    """Store in cache."""
    _cache.put(text, result, quality, ns)


def cache_stats() -> dict:
    """Get cache statistics."""
    return _cache.stats()

