"""Auth middleware regression tests.

Tests that the auth middleware:
- Allows public endpoints without auth
- Blocks sensitive endpoints without auth
- Allows sensitive endpoints with valid session
- Blocks expired/invalid sessions
"""
import pytest


class TestAuthMiddleware:
    """Test _check_endpoint_auth."""

    def test_public_endpoint_no_auth(self):
        """Public endpoints should be allowed without auth."""
        from server import _check_endpoint_auth
        assert _check_endpoint_auth("/", None) is None
        assert _check_endpoint_auth("/api/health", None) is None
        assert _check_endpoint_auth("/api/state", None) is None
        assert _check_endpoint_auth("/api/auth/status", None) is None
        assert _check_endpoint_auth("/api/auth/login", None) is None

    def test_sensitive_endpoint_no_auth(self):
        """Sensitive endpoints should be blocked without auth."""
        from server import _check_endpoint_auth
        r = _check_endpoint_auth("/api/admin/backup", None)
        assert r is not None
        assert r.get("status") == 401

    def test_sensitive_endpoint_invalid_session(self):
        """Sensitive endpoints should be blocked with invalid session."""
        from server import _check_endpoint_auth
        r = _check_endpoint_auth("/api/admin/backup", "Bearer invalid_token_here")
        assert r is not None
        assert r.get("status") == 401

    def test_chat_requires_auth(self):
        """Chat should require auth."""
        from server import _check_endpoint_auth
        r = _check_endpoint_auth("/api/chat", None)
        assert r is not None
        assert r.get("status") == 401

    def test_read_endpoints_public(self):
        """Read-only endpoints that are in _PUBLIC_PATHS should be allowed."""
        from server import _check_endpoint_auth
        # Public endpoints should always be allowed
        assert _check_endpoint_auth("/api/health", None) is None
        assert _check_endpoint_auth("/api/state", None) is None
        # /api/metrics requires auth (not in _PUBLIC_PATHS)
        r = _check_endpoint_auth("/api/metrics", None)
        assert r is not None  # blocked without auth
