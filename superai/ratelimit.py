"""Rate Limiting — proteger free tier quotas.

Contar requests por provider por janela temporal.
Quando provider atinge limite, bloquear até janela resetar.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from .feature_flags import is_enabled
from .util import now_iso

_lock = threading.Lock()

# Per-provider limits (requests per minute)
# Conservative defaults — free tier quotas vary
_LIMITS: dict[str, int] = {
    "groq": 30,          # 30 req/min (free tier generous)
    "cerebras": 20,      # 20 req/min
    "gemini": 15,        # 15 req/min (free tier 15 RPM)
    "openrouter": 10,    # 10 req/min (free models)
    "inference": 10,     # 10 req/min
    "zai": 10,           # 10 req/min
    "nvidia": 10,        # 10 req/min
    "sambanova": 10,     # 10 req/min
    "mistral": 10,       # 10 req/min
    "claude": 5,         # 5 req/min (paid, be conservative)
}

# Tracking: provider → list of timestamps
_windows: dict[str, list[float]] = {}
_WINDOW_S = 60.0  # 1 minute window


def check(provider: str) -> dict:
    """Check if provider is within rate limit. Returns {allowed, remaining, reset_at}."""
    if not is_enabled("rate_limiting"):
        return {"allowed": True, "remaining": -1, "reset_at": None, "kind": "SKIPPED"}

    limit = _LIMITS.get(provider, 10)
    now = time.time()

    with _lock:
        if provider not in _windows:
            _windows[provider] = []

        # Clean old entries
        _windows[provider] = [t for t in _windows[provider] if now - t < _WINDOW_S]

        count = len(_windows[provider])
        allowed = count < limit
        remaining = max(0, limit - count)
        reset_at = _windows[provider][0] + _WINDOW_S if _windows[provider] else None

        return {
            "allowed": allowed,
            "remaining": remaining,
            "limit": limit,
            "reset_at": round(reset_at, 1) if reset_at else None,
            "kind": "MEASURED",
        }


def record(provider: str) -> None:
    """Record a request to provider."""
    if not is_enabled("rate_limiting"):
        return
    with _lock:
        _windows.setdefault(provider, []).append(time.time())


def status() -> dict:
    """Status of all rate limiters."""
    now = time.time()
    result: dict[str, Any] = {"kind": "MEASURED", "ts": now_iso(), "providers": {}}
    with _lock:
        for provider, limit in _LIMITS.items():
            timestamps = _windows.get(provider, [])
            active = [t for t in timestamps if now - t < _WINDOW_S]
            result["providers"][provider] = {
                "limit": limit,
                "used": len(active),
                "remaining": max(0, limit - len(active)),
            }
    return result
