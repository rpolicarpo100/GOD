"""Semantic Cache — cache por similaridade semântica.

Não é um LLM critic. É um cache que encontra respostas
semanticamente similares usando embeddings.

Features:
- FastEmbed embeddings (local, sem API calls)
- Qdrant vector store
- Similarity threshold configurable
- Cache invalidation por qualidade
- Stats de hit/miss
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import cfg, DATA
from .util import now_iso, sha

# ═══════════════════════════════
# CONFIGURATION
# ═══════════════════════════════

DEFAULT_SIMILARITY_THRESHOLD = 0.75
HIGH_SIMILARITY_THRESHOLD = 0.88
MAX_CACHE_ENTRIES = 1000
CACHE_DIR = DATA / "semantic_cache"


class SemanticCache:
    """Semantic cache using embeddings."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "stores": 0,
            "evictions": 0,
        }
        self._vectors = None
        self._initialized = False
    
    def _ensure_init(self):
        """Lazy initialization."""
        if self._initialized:
            return
        
        try:
            from .memory_vec import vectors
            self._vectors = vectors
            self._initialized = True
        except Exception:
            self._initialized = True
    
    def available(self) -> bool:
        """Check if semantic cache is available."""
        self._ensure_init()
        return self._vectors is not None and self._vectors.available()
    
    def lookup(
        self,
        text: str,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ns: str = "",
    ) -> dict | None:
        """Look up semantically similar cached result.
        
        Returns: {result, quality, score, key} or None
        """
        if not self.available():
            self._stats["misses"] += 1
            return None
        
        try:
            # Search in Qdrant
            results = self._vectors.search(
                "cache",
                text,
                k=1,
                min_score=threshold,
            )
            
            if not results:
                self._stats["misses"] += 1
                return None
            
            r = results[0]
            score = r.get("score", 0)
            
            # High confidence: use directly
            if score >= HIGH_SIMILARITY_THRESHOLD:
                self._stats["hits"] += 1
                return {
                    "result": r.get("result"),
                    "quality": r.get("quality", 0.5),
                    "score": score,
                    "key": r.get("key", ""),
                    "confidence": "high",
                }
            
            # Medium confidence: use but flag
            if score >= threshold:
                self._stats["hits"] += 1
                return {
                    "result": r.get("result"),
                    "quality": r.get("quality", 0.5),
                    "score": score,
                    "key": r.get("key", ""),
                    "confidence": "medium",
                }
            
            self._stats["misses"] += 1
            return None
            
        except Exception:
            self._stats["misses"] += 1
            return None
    
    def store(
        self,
        text: str,
        result: dict,
        quality: float,
        ns: str = "",
    ) -> bool:
        """Store result in semantic cache."""
        if not self.available():
            return False
        
        try:
            key = sha(text + (f"\n{ns}" if ns else ""))
            
            self._vectors.upsert(
                "cache",
                key,
                text,
                {
                    "result": result,
                    "quality": quality,
                    "ts": now_iso(),
                },
            )
            
            with self._lock:
                self._entries[key] = {
                    "text": text[:100],
                    "quality": quality,
                    "ts": now_iso(),
                }
                self._stats["stores"] += 1
                
                # Evict if too many
                if len(self._entries) > MAX_CACHE_ENTRIES:
                    self._evict()
            
            return True
            
        except Exception:
            return False
    
    def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry."""
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
        return False
    
    def clear(self) -> int:
        """Clear all cache entries."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count
    
    def _evict(self):
        """Evict oldest entries."""
        if len(self._entries) <= MAX_CACHE_ENTRIES:
            return
        
        # Sort by timestamp, remove oldest
        sorted_entries = sorted(
            self._entries.items(),
            key=lambda x: x[1].get("ts", ""),
        )
        
        to_remove = len(self._entries) - MAX_CACHE_ENTRIES
        for key, _ in sorted_entries[:to_remove]:
            del self._entries[key]
            self._stats["evictions"] += 1
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / max(total, 1)
            
            return {
                "kind": "MEASURED",
                "available": self.available(),
                "entries": len(self._entries),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "stores": self._stats["stores"],
                "evictions": self._stats["evictions"],
                "hit_rate": round(hit_rate, 3),
                "ts": now_iso(),
            }
    
    def format_stats(self) -> str:
        """Format stats for display."""
        stats = self.get_stats()
        
        lines = [
            f"Semantic Cache: {'Available' if stats['available'] else 'Unavailable'}",
            f"Entries: {stats['entries']}",
            f"Hits: {stats['hits']} | Misses: {stats['misses']}",
            f"Hit Rate: {stats['hit_rate']*100:.1f}%",
            f"Stores: {stats['stores']} | Evictions: {stats['evictions']}",
        ]
        
        return "\n".join(lines)


# Global cache instance
_cache = SemanticCache()


def get_cache() -> SemanticCache:
    """Get the global semantic cache."""
    return _cache


def lookup(text: str, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> dict | None:
    """Look up semantically similar cached result."""
    return _cache.lookup(text, threshold)


def store(text: str, result: dict, quality: float) -> bool:
    """Store result in semantic cache."""
    return _cache.store(text, result, quality)


def available() -> bool:
    """Check if semantic cache is available."""
    return _cache.available()


def stats() -> dict:
    """Get cache statistics."""
    return _cache.get_stats()
