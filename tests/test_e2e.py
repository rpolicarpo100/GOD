"""GOD — End-to-End tests.

Verifies the full flow: health → API → auth → chat → tools → security → memory.
Run: pytest tests/test_e2e.py -v

Requires the server to be running on localhost:8000 (or GOD_PORT).
Tests auto-skip if server is not responding.
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

PORT = int(os.environ.get("GOD_PORT", "8000"))
BASE = f"http://127.0.0.1:{PORT}"


def _server_running() -> bool:
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_running(),
    reason="GOD server not running (start with: god start)",
)


# ═══════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════


class TestHealth:
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

    def test_full_health(self):
        r = httpx.get(f"{BASE}/api/system/health", timeout=5)
        assert r.status_code == 200

    def test_diagnostics(self):
        r = httpx.get(f"{BASE}/api/system/diagnostics", timeout=5)
        assert r.status_code == 200


# ═══════════════════════════════════════
# API — CORE ENDPOINTS
# ═══════════════════════════════════════


class TestAPI:
    def test_token_usage(self):
        r = httpx.get(f"{BASE}/api/token/usage", timeout=5)
        assert r.status_code == 200

    def test_token_cost(self):
        r = httpx.get(f"{BASE}/api/token/cost", timeout=5)
        assert r.status_code == 200

    def test_token_budget(self):
        r = httpx.get(f"{BASE}/api/token/budget", timeout=5)
        assert r.status_code == 200

    def test_token_forecast(self):
        r = httpx.get(f"{BASE}/api/token/forecast", timeout=5)
        assert r.status_code == 200

    def test_token_models(self):
        r = httpx.get(f"{BASE}/api/token/models", timeout=5)
        assert r.status_code == 200

    def test_os_snapshot(self):
        r = httpx.get(f"{BASE}/api/os", timeout=5)
        assert r.status_code == 200

    def test_os_ps(self):
        r = httpx.get(f"{BASE}/api/os/ps", timeout=5)
        assert r.status_code == 200

    def test_os_mounts(self):
        r = httpx.get(f"{BASE}/api/os/mounts", timeout=5)
        assert r.status_code == 200

    def test_os_drivers(self):
        r = httpx.get(f"{BASE}/api/os/drivers", timeout=5)
        assert r.status_code == 200

    def test_gods_list(self):
        r = httpx.get(f"{BASE}/api/gods", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "active" in data

    def test_graph(self):
        r = httpx.get(f"{BASE}/api/graph", timeout=5)
        assert r.status_code == 200

    def test_missions(self):
        r = httpx.get(f"{BASE}/api/missions", timeout=5)
        assert r.status_code == 200

    def test_repair_endpoint(self):
        """Repair endpoint requires auth — should reject without token."""
        r = httpx.post(f"{BASE}/api/repair", timeout=5)
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════
# SYSTEM ENDPOINTS
# ═══════════════════════════════════════


class TestSystem:
    def test_system_state(self):
        r = httpx.get(f"{BASE}/api/system/state", timeout=5)
        assert r.status_code == 200

    def test_capabilities(self):
        r = httpx.get(f"{BASE}/api/system/capabilities", timeout=5)
        assert r.status_code == 200

    def test_flags(self):
        r = httpx.get(f"{BASE}/api/system/flags", timeout=5)
        assert r.status_code == 200

    def test_protection(self):
        r = httpx.get(f"{BASE}/api/system/protection", timeout=5)
        assert r.status_code == 200

    def test_god_object_check(self):
        r = httpx.get(f"{BASE}/api/system/god-object", timeout=5)
        assert r.status_code == 200

    def test_resource_mode(self):
        r = httpx.get(f"{BASE}/api/system/resource-mode", timeout=5)
        assert r.status_code == 200

    def test_experiments(self):
        r = httpx.get(f"{BASE}/api/system/experiments", timeout=5)
        assert r.status_code == 200

    def test_nodes(self):
        r = httpx.get(f"{BASE}/api/system/nodes", timeout=5)
        assert r.status_code == 200

    def test_trace(self):
        r = httpx.get(f"{BASE}/api/system/trace", timeout=5)
        assert r.status_code == 200


# ═══════════════════════════════════════
# AUTH
# ═══════════════════════════════════════


class TestAuth:
    def test_auth_status(self):
        r = httpx.get(f"{BASE}/api/auth/status", timeout=5)
        assert r.status_code == 200

    def test_protected_audit_rejects(self):
        r = httpx.get(f"{BASE}/api/auth/audit", timeout=5)
        assert r.status_code in (401, 403)

    def test_protected_users_rejects(self):
        r = httpx.get(f"{BASE}/api/auth/users", timeout=5)
        assert r.status_code in (401, 403)

    def test_protected_approvals_rejects(self):
        r = httpx.get(f"{BASE}/api/auth/approvals", timeout=5)
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════
# OPENAI COMPAT
# ═══════════════════════════════════════


class TestOpenAICompat:
    def test_models(self):
        r = httpx.get(f"{BASE}/v1/models", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data.get("object") == "list"
        assert "data" in data


# ═══════════════════════════════════════
# CHAT
# ═══════════════════════════════════════


class TestChat:
    def test_chat_returns_response(self):
        r = httpx.post(
            f"{BASE}/api/chat",
            json={"text": "hello", "from_worker": False},
            timeout=30,
        )
        assert r.status_code == 200

    def test_chat_returns_json(self):
        r = httpx.post(
            f"{BASE}/api/chat",
            json={"text": "echo test", "from_worker": False},
            timeout=30,
        )
        assert r.status_code == 200
        # Response should be valid JSON (dict)
        assert isinstance(r.json(), dict)


# ═══════════════════════════════════════
# STREAM (SSE)
# ═══════════════════════════════════════


class TestStream:
    def test_stream_connects(self):
        """SSE endpoint should accept connection and send snapshot."""
        with httpx.stream("GET", f"{BASE}/api/stream", timeout=5) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            # Read first chunk (should be snapshot event)
            for line in r.iter_lines():
                if line.startswith("event:"):
                    assert "snapshot" in line or "data:" in line
                    break


# ═══════════════════════════════════════
# SECURITY ENDPOINTS
# ═══════════════════════════════════════


class TestSecurity:
    def test_sensitive_scan_requires_auth(self):
        r = httpx.get(f"{BASE}/api/security/sensitive/scan?text=test", timeout=5)
        assert r.status_code in (401, 403)

    def test_sandbox_check_requires_auth(self):
        r = httpx.get(f"{BASE}/api/security/sandbox/check?path=/tmp", timeout=5)
        assert r.status_code in (401, 403)

    def test_rate_limit_requires_auth(self):
        r = httpx.get(f"{BASE}/api/security/rate-limit", timeout=5)
        assert r.status_code in (401, 403)

    def test_network_requires_auth(self):
        r = httpx.get(f"{BASE}/api/security/network", timeout=5)
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════
# VOICE & WEBSEARCH (optional)
# ═══════════════════════════════════════


class TestOptional:
    def test_voice_health(self):
        r = httpx.get(f"{BASE}/api/system/voice", timeout=5)
        # Should respond even if voice is unavailable
        assert r.status_code == 200

    def test_websearch_health(self):
        r = httpx.get(f"{BASE}/api/system/websearch", timeout=5)
        assert r.status_code == 200


# ═══════════════════════════════════════
# INDEX (UI)
# ═══════════════════════════════════════


class TestUI:
    def test_index_returns_html(self):
        r = httpx.get(f"{BASE}/", timeout=5)
        assert r.status_code == 200
        assert "html" in r.headers.get("content-type", "").lower() or "<!DOCTYPE" in r.text[:100]


# ═══════════════════════════════════════
# RESPONSE FORMAT
# ═══════════════════════════════════════


class TestResponseFormat:
    """Verify API responses are well-formed JSON."""

    def test_health_is_json(self):
        r = httpx.get(f"{BASE}/api/health", timeout=5)
        assert r.headers.get("content-type", "").startswith("application/json")

    def test_state_is_json(self):
        r = httpx.get(f"{BASE}/api/state", timeout=5)
        assert r.headers.get("content-type", "").startswith("application/json")

    def test_gods_is_json(self):
        r = httpx.get(f"{BASE}/api/gods", timeout=5)
        assert r.headers.get("content-type", "").startswith("application/json")
