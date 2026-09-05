"""Optimization — lazy loading, regex caching, performance helpers.

Features:
- Lazy module loading (import on first use)
- Compiled regex cache
- Performance timing context manager
- Memory-efficient data structures
"""
from __future__ import annotations

import re
import time
import threading
from typing import Any, Callable

# ═══════════════════════════════
# REGEX CACHE
# ═══════════════════════════════

_regex_cache: dict[str, re.Pattern] = {}
_regex_lock = threading.Lock()


def get_regex(pattern: str, flags: int = 0) -> re.Pattern:
    """Get compiled regex from cache or compile and cache it."""
    key = (pattern, flags)
    with _regex_lock:
        if key not in _regex_cache:
            _regex_cache[key] = re.compile(pattern, flags)
        return _regex_cache[key]


def clear_regex_cache():
    """Clear regex cache."""
    with _regex_lock:
        _regex_cache.clear()


def regex_cache_stats() -> dict:
    """Get regex cache statistics."""
    with _regex_lock:
        return {
            "cached": len(_regex_cache),
            "patterns": list(_regex_cache.keys())[:10],  # First 10
        }


# ═══════════════════════════════
# LAZY MODULE LOADING
# ═══════════════════════════════

class LazyModule:
    """Lazy module loader — imports on first attribute access."""
    
    def __init__(self, module_name: str):
        self._module_name = module_name
        self._module = None
        self._lock = threading.Lock()
    
    def _load(self):
        if self._module is None:
            with self._lock:
                if self._module is None:
                    self._module = __import__(self._module_name)
    
    def __getattr__(self, name: str):
        self._load()
        return getattr(self._module, name)
    
    def __repr__(self):
        return f"LazyModule({self._module_name!r})"


def lazy_import(module_name: str) -> LazyModule:
    """Create a lazy module import."""
    return LazyModule(module_name)


# ═══════════════════════════════
# PERFORMANCE TIMING
# ═══════════════════════════════

class Timer:
    """Context manager for timing code blocks."""
    
    def __init__(self, name: str = "timer"):
        self.name = name
        self.start_time: float = 0
        self.end_time: float = 0
        self.elapsed_ms: float = 0
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000
    
    def __repr__(self):
        return f"Timer({self.name}: {self.elapsed_ms:.2f}ms)"


def timed(func: Callable) -> Callable:
    """Decorator to time function execution."""
    def wrapper(*args, **kwargs):
        with Timer(func.__name__) as t:
            result = func(*args, **kwargs)
        return result
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ═══════════════════════════════
# CACHE DECORATOR
# ═══════════════════════════════

def cached(maxsize: int = 128):
    """Simple LRU cache decorator."""
    def decorator(func):
        cache: dict[tuple, Any] = {}
        order: list[tuple] = []
        lock = threading.Lock()
        
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            
            with lock:
                if key in cache:
                    # Move to end (most recent)
                    order.remove(key)
                    order.append(key)
                    return cache[key]
            
            result = func(*args, **kwargs)
            
            with lock:
                cache[key] = result
                order.append(key)
                
                # Evict oldest if over maxsize
                while len(cache) > maxsize:
                    oldest = order.pop(0)
                    cache.pop(oldest, None)
            
            return result
        
        wrapper.cache_clear = lambda: (cache.clear(), order.clear())
        wrapper.cache_info = lambda: {"hits": len(cache), "maxsize": maxsize}
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    
    return decorator


# ═══════════════════════════════
# BATCH PROCESSING
# ═══════════════════════════════

def batch_process(items: list, process_fn: Callable, batch_size: int = 100) -> list:
    """Process items in batches for memory efficiency."""
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        results.extend(process_fn(batch))
    return results


# ═══════════════════════════════
# STRING OPTIMIZATION
# ═══════════════════════════════

def fast_contains(text: str, patterns: list[str]) -> bool:
    """Fast check if text contains any pattern (uses set lookup)."""
    # For short patterns, use `in` operator
    for p in patterns:
        if p in text:
            return True
    return False


def truncate(text: str, max_len: int = 100, suffix: str = "...") -> str:
    """Truncate text efficiently."""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix


# ═══════════════════════════════
# PERFORMANCE STATS
# ═══════════════════════════════

class PerfStats:
    """Collect performance statistics."""
    
    def __init__(self):
        self._stats: dict[str, list[float]] = {}
        self._lock = threading.Lock()
    
    def record(self, name: str, elapsed_ms: float):
        """Record a timing."""
        with self._lock:
            if name not in self._stats:
                self._stats[name] = []
            self._stats[name].append(elapsed_ms)
            # Keep last 1000 entries
            if len(self._stats[name]) > 1000:
                self._stats[name] = self._stats[name][-500:]
    
    def get_stats(self, name: str) -> dict:
        """Get stats for a metric."""
        with self._lock:
            values = self._stats.get(name, [])
            if not values:
                return {"count": 0}
            
            return {
                "count": len(values),
                "avg_ms": round(sum(values) / len(values), 2),
                "min_ms": round(min(values), 2),
                "max_ms": round(max(values), 2),
                "p50_ms": round(sorted(values)[len(values) // 2], 2),
                "p95_ms": round(sorted(values)[int(len(values) * 0.95)], 2),
            }
    
    def all_stats(self) -> dict:
        """Get all stats."""
        with self._lock:
            return {name: self.get_stats(name) for name in self._stats}
    
    def reset(self):
        """Reset all stats."""
        with self._lock:
            self._stats.clear()


# Global perf stats
perf = PerfStats()
