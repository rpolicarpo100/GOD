"""P2.5 — Rate Limiting.

Prevents:
- API abuse
- Brute force attacks
- Resource exhaustion
- Denial of service

Uses sliding window algorithm.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any

from .util import now_iso

# ═══════════════════════════════
# RATE LIMIT CONFIGS
# ═══════════════════════════════

# endpoint → (max_requests, window_seconds)
RATE_LIMITS = {
    # Auth endpoints (strict)
    "/auth/login": (5, 60),  # 5 per minute
    "/auth/change-password": (3, 300),  # 3 per5 minutes
    "/auth/reset-password": (3, 300),
    
    # Task endpoints (moderate)
    "/task/submit": (30, 60),  # 30 per minute
    "/task/execute": (20, 60),
    
    # API endpoints (generous)
    "/api/": (100, 60),  # 100 per minute
    "/ws": (10, 60),  # 10 connections per minute
    
    # Admin endpoints (restrictive)
    "/admin/": (20, 60),
    
    # Default
    "_default": (60, 60),  # 60 per minute
}

# Per-user limits (override per-endpoint)
USER_LIMITS = {
    "OWNER": 2.0,  # 2x default
    "ADMIN": 1.5,
    "OPERATOR": 1.0,
    "GUEST": 0.5,  # Half
}


class RateLimiter:
    """Sliding window rate limiter."""
    
    def __init__(self):
        self._lock = threading.Lock()
        # key → [(timestamp, count)]
        self._windows: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._blocked: dict[str, float] = {}  # key → unblock_time
    
    def check(
        self,
        key: str,
        endpoint: str,
        role: str = "OPERATOR",
    ) -> dict:
        """Check if request is allowed.
        
        key: user_id or IP
        endpoint: request path
        role: user role
        """
        now = time.time()
        
        # Check if blocked
        with self._lock:
            if key in self._blocked:
                if now < self._blocked[key]:
                    remaining = self._blocked[key] - now
                    return {
                        "ok": False,
                        "kind": "MEASURED",
                        "reason": "blocked",
                        "retry_after": round(remaining, 1),
                    }
                else:
                    del self._blocked[key]
        
        # Find matching rate limit
        max_requests, window = self._find_limit(endpoint)
        
        # Apply role multiplier
        multiplier = USER_LIMITS.get(role, 1.0)
        max_requests = int(max_requests * multiplier)
        
        # Check sliding window
        with self._lock:
            window_key = f"{key}:{endpoint}"
            entries = self._windows[window_key]
            
            # Remove expired entries
            cutoff = now - window
            entries[:] = [(t, c) for t, c in entries if t > cutoff]
            
            # Count requests in window
            total = sum(c for _, c in entries)
            
            if total >= max_requests:
                # Rate limited
                oldest = entries[0][0] if entries else now
                retry_after = window - (now - oldest)
                
                return {
                    "ok": False,
                    "kind": "MEASURED",
                    "reason": "rate_limited",
                    "limit": max_requests,
                    "window": window,
                    "current": total,
                    "retry_after": round(max(0, retry_after), 1),
                }
            
            # Allow and record
            entries.append((now, 1))
            
            return {
                "ok": True,
                "kind": "MEASURED",
                "limit": max_requests,
                "window": window,
                "remaining": max_requests - total - 1,
            }
    
    def block(self, key: str, duration: float =300):
        """Block a key for duration seconds."""
        with self._lock:
            self._blocked[key] = time.time() + duration
    
    def _find_limit(self, endpoint: str) -> tuple[int, int]:
        """Find rate limit for endpoint."""
        # Check specific endpoints first
        for pattern, limit in sorted(RATE_LIMITS.items(), key=lambda x: -len(x[0])):
            if pattern == "_default":
                continue
            if endpoint.startswith(pattern):
                return limit
        
        return RATE_LIMITS["_default"]
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "kind": "MEASURED",
                "active_windows": len(self._windows),
                "blocked_keys": len(self._blocked),
                "ts": now_iso(),
            }


# Global limiter
_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    """Get the global rate limiter."""
    return _limiter


def check_rate_limit(key: str, endpoint: str, role: str = "OPERATOR") -> dict:
    """Check rate limit for a request."""
    return _limiter.check(key, endpoint, role)


def block_key(key: str, duration: float =300):
    """Block a key."""
    _limiter.block(key, duration)


def format_rate_limit(result: dict) -> str:
    """Format rate limit result for display."""
    if result.get("ok"):
        return f"✓ Allowed ({result.get('remaining', '?')} remaining)"
    return f"✗ Rate limited: {result.get('reason')} (retry in {result.get('retry_after', '?')}s)"
