"""GOD — End-to-End tests.

These tests verify the full flow: start server → send request → verify response.
Run with: pytest tests/test_e2e.py -v -m e2e

Requires the server to be running on localhost:8000 (or GOD_PORT).
"""
from __future__ import annotations

import os
import subprocess
import time

import httpx
import pytest

PORT = int(os.environ.get("GOD_PORT", "8000"))
BASE = f"http://127.0.0.1:{PORT}"


def _server_running() -> bool:
    """Check if server is responding."""
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_running(),
    reason="GOD server not running (start with: god start)",
)


class TestHealth:
    """Basic health endpoints."""

    def test_health(self):
        r = httpx.get(f"{BASE}/api/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "ok" in data or "mode" in data

    def test_state(self):
        r = httpx.get(f"{BASE}/api/state", timeout=5)
        assert r.status_code == 200

    def test_liveness(self):
        r = httpx.get(f"{BASE}/api/system/liveness", timeout=5)
        assert r.status_code == 200

    def test_readiness(self):
        r = httpx.get(f"{BASE}/api/system/readiness", timeout=5)
        assert r.status_code == 200


class TestAPI:
    """Core API endpoints."""

    def test_token_usage(self):
        r = httpx.get(f"{BASE}/api/token/usage", timeout=5)
        assert r.status_code == 200

    def test_os_snapshot(self):
        r = httpx.get(f"{BASE}/api/os", timeout=5)
        assert r.status_code == 200

    def test_gods_list(self):
        r = httpx.get(f"{BASE}/api/gods", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "active" in data

    def test_system_state(self):
        r = httpx.get(f"{BASE}/api/system/state", timeout=5)
        assert r.status_code == 200

    def test_capabilities(self):
        r = httpx.get(f"{BASE}/api/system/capabilities", timeout=5)
        assert r.status_code == 200

    def test_flags(self):
        r = httpx.get(f"{BASE}/api/system/flags", timeout=5)
        assert r.status_code == 200


class TestAuth:
    """Auth endpoints (unauthenticated)."""

    def test_auth_status(self):
        r = httpx.get(f"{BASE}/api/auth/status", timeout=5)
        assert r.status_code == 200

    def test_protected_endpoint_rejects(self):
        """Admin endpoints should reject unauthenticated requests."""
        r = httpx.get(f"{BASE}/api/auth/audit", timeout=5)
        assert r.status_code in (401, 403)


class TestOpenAICompat:
    """OpenAI-compatible endpoints."""

    def test_models(self):
        r = httpx.get(f"{BASE}/v1/models", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data.get("object") == "list"


class TestChat:
    """Chat endpoint."""

    def test_chat_returns_response(self):
        r = httpx.post(
            f"{BASE}/api/chat",
            json={"text": "hello", "from_worker": False},
            timeout=30,
        )
        assert r.status_code == 200
