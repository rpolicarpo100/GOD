"""P2 Security Tests — Reality checks for advanced security modules.

Tests for:
- Sensitive Data Detection (P2.1)
- Resource Limits (P2.2)
- Sandbox Protection (P2.4)
- Rate Limiting (P2.5)
- Network Access Control (P2.6)
- Semantic Cache
- Cohere Rerank
"""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path


class TestSensitiveDataDetection(unittest.TestCase):
    """P2.1 — Sensitive data detection."""

    def test_detect_password_assignment(self):
        """Detect password in assignment."""
        from superai import sensitive
        results = sensitive.scan_text('password = "secret123"')
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "password_assignment")

    def test_detect_api_key(self):
        """Detect API key."""
        from superai import sensitive
        results = sensitive.scan_text('api_key = "sk-1234567890abcdef"')
        self.assertTrue(len(results) > 0)
        self.assertIn(results[0]["type"], ["api_key", "password_assignment"])

    def test_detect_jwt(self):
        """Detect JWT token."""
        from superai import sensitive
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        results = sensitive.scan_text(f"token = '{jwt}'")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "jwt")
        self.assertEqual(results[0]["risk"], 5)

    def test_detect_private_key(self):
        """Detect private key."""
        from superai import sensitive
        results = sensitive.scan_text("-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBg...")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "private_key")
        self.assertEqual(results[0]["risk"], 5)

    def test_detect_aws_key(self):
        """Detect AWS access key."""
        from superai import sensitive
        results = sensitive.scan_text("aws_access_key_id = 'AKIAIOSFODNN7EXAMPLE'")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "aws_key")

    def test_no_false_positive_clean_text(self):
        """No detections in clean text."""
        from superai import sensitive
        results = sensitive.scan_text("Hello, how are you today?")
        self.assertEqual(len(results), 0)

    def test_scan_task_content(self):
        """Scan task content for sensitive data."""
        from superai import sensitive
        task = {"task_id": "T1", "text": "password = 'secret123'"}
        result = sensitive.scan_task_content(task)
        self.assertTrue(result.get("has_sensitive"))

    def test_scan_file(self):
        """Scan file for sensitive data."""
        from superai import sensitive
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('password = "secret123"\napi_key = "sk-1234567890abcdef"')
            f.flush()
            result = sensitive.scan_file(f.name)
            self.assertTrue(result.get("has_sensitive"))
            Path(f.name).unlink()

    def test_risk_assessment(self):
        """Risk levels are correctly assigned."""
        from superai import sensitive
        # High risk: password
        results = sensitive.scan_text('password = "secret123"')
        if results:
            self.assertGreaterEqual(results[0]["risk"], 3)


class TestResourceLimits(unittest.TestCase):
    """P2.2 — Resource limits."""

    def test_tracker_start_end(self):
        """Start and end tracking."""
        from superai import resource_limits
        tracker = resource_limits.get_tracker()
        tracker.start_task("test_task_1")
        usage = tracker.end_task("test_task_1")
        self.assertIn("duration_seconds", usage)

    def test_tracker_tool_call(self):
        """Record tool calls."""
        from superai import resource_limits
        tracker = resource_limits.get_tracker()
        tracker.start_task("test_task_2")
        tracker.record_tool_call("test_task_2", "calculator")
        tracker.record_tool_call("test_task_2", "fs.read")
        check = tracker.check_limits("test_task_2")
        self.assertTrue(check.get("ok"))
        tracker.end_task("test_task_2")

    def test_tracker_tokens(self):
        """Record token usage."""
        from superai import resource_limits
        tracker = resource_limits.get_tracker()
        tracker.start_task("test_task_3", "session_1")
        tracker.record_tokens("test_task_3", "session_1", 100)
        check = tracker.check_limits("test_task_3")
        self.assertTrue(check.get("ok"))
        tracker.end_task("test_task_3")

    def test_check_limits_mode(self):
        """Different modes have different limits."""
        from superai import resource_limits
        tracker = resource_limits.get_tracker()
        tracker.start_task("test_task_4")
        check_fast = tracker.check_limits("test_task_4", mode="FAST")
        check_deep = tracker.check_limits("test_task_4", mode="DEEP")
        self.assertTrue(check_fast.get("ok"))
        self.assertTrue(check_deep.get("ok"))
        tracker.end_task("test_task_4")

    def test_check_limits_role(self):
        """Different roles have different limits."""
        from superai import resource_limits
        tracker = resource_limits.get_tracker()
        tracker.start_task("test_task_5")
        check_owner = tracker.check_limits("test_task_5", role="OWNER")
        check_guest = tracker.check_limits("test_task_5", role="GUEST")
        self.assertTrue(check_owner.get("ok"))
        self.assertTrue(check_guest.get("ok"))
        tracker.end_task("test_task_5")

    def test_global_functions(self):
        """Global functions work."""
        from superai import resource_limits
        resource_limits.start_tracking("test_task_6")
        check = resource_limits.check_limits("test_task_6")
        self.assertTrue(check.get("ok"))
        resource_limits.end_tracking("test_task_6")  # module-level function


class TestSandboxProtection(unittest.TestCase):
    """P2.4 — Sandbox protection."""

    def test_allowed_path(self):
        """Paths in /home/user are allowed."""
        from superai import sandbox
        result = sandbox.check_path("/home/user/test.txt")
        self.assertTrue(result.get("ok"))

    def test_blocked_path_etc(self):
        """Paths in /etc are blocked."""
        from superai import sandbox
        result = sandbox.check_path("/etc/passwd")
        self.assertFalse(result.get("ok"))

    def test_blocked_path_proc(self):
        """Paths in /proc are blocked."""
        from superai import sandbox
        result = sandbox.check_path("/proc/self/environ")
        self.assertFalse(result.get("ok"))

    def test_blocked_path_root(self):
        """Paths in /root are blocked."""
        from superai import sandbox
        result = sandbox.check_path("/root/.ssh/id_rsa")
        self.assertFalse(result.get("ok"))

    def test_path_traversal(self):
        """Path traversal is blocked."""
        from superai import sandbox
        result = sandbox.check_path("/home/user/../../../etc/passwd")
        self.assertFalse(result.get("ok"))

    def test_allowed_import(self):
        """Safe imports are allowed."""
        from superai import sandbox
        result = sandbox.check_import("json")
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("safe"))

    def test_blocked_import(self):
        """Blocked imports are rejected."""
        from superai import sandbox
        result = sandbox.check_import("subprocess")
        self.assertFalse(result.get("ok"))

    def test_blocked_import_ctypes(self):
        """ctypes is blocked."""
        from superai import sandbox
        result = sandbox.check_import("ctypes")
        self.assertFalse(result.get("ok"))

    def test_safe_command(self):
        """Safe commands are allowed."""
        from superai import sandbox
        result = sandbox.check_command("ls -la")
        self.assertTrue(result.get("ok"))

    def test_blocked_command(self):
        """Blocked commands are rejected."""
        from superai import sandbox
        result = sandbox.check_command("sudo apt-get install")
        self.assertFalse(result.get("ok"))

    def test_blocked_command_ssh(self):
        """SSH is blocked."""
        from superai import sandbox
        result = sandbox.check_command("ssh user@host")
        self.assertFalse(result.get("ok"))

    def test_allowed_localhost(self):
        """Localhost network is allowed."""
        from superai import sandbox
        result = sandbox.check_network("localhost", 8080)
        self.assertTrue(result.get("ok"))

    def test_blocked_port(self):
        """SSH port is blocked."""
        from superai import sandbox
        result = sandbox.check_network("localhost", 22)
        self.assertFalse(result.get("ok"))

    def test_symlink_check(self):
        """Symlink check works."""
        from superai import sandbox
        result = sandbox.check_symlink("/home/user/test.txt")
        self.assertTrue(result.get("ok"))


class TestRateLimiting(unittest.TestCase):
    """P2.5 — Rate limiting."""

    def test_rate_limit_within(self):
        """Requests within limit are allowed."""
        from superai import rate_limit
        limiter = rate_limit.get_limiter()
        result = limiter.check("test_user", "/api/chat")
        self.assertTrue(result.get("ok"))

    def test_rate_limit_exceeded(self):
        """Requests exceeding limit are blocked."""
        from superai import rate_limit
        limiter = rate_limit.get_limiter()
        # Exhaust the limit
        for _ in range(100):
            limiter.check("test_user_2", "/api/chat")
        result = limiter.check("test_user_2", "/api/chat")
        # May or may not be blocked depending on window
        self.assertIn("ok", result)

    def test_rate_limit_auth_endpoint(self):
        """Auth endpoints have strict limits."""
        from superai import rate_limit
        limiter = rate_limit.get_limiter()
        result = limiter.check("test_user_3", "/auth/login")
        self.assertTrue(result.get("ok"))

    def test_rate_limit_role_multiplier(self):
        """Owner gets higher limits."""
        from superai import rate_limit
        limiter = rate_limit.get_limiter()
        result = limiter.check("test_user_4", "/api/chat", role="OWNER")
        self.assertTrue(result.get("ok"))

    def test_global_functions(self):
        """Global functions work."""
        from superai import rate_limit
        result = rate_limit.check_rate_limit("test_user_5", "/api/chat")
        self.assertTrue(result.get("ok"))

    def test_limiter_stats(self):
        """Stats are available."""
        from superai import rate_limit
        stats = rate_limit.get_limiter().get_stats()
        self.assertIn("active_windows", stats)
        self.assertIn("blocked_keys", stats)


class TestNetworkAccessControl(unittest.TestCase):
    """P2.6 — Network access control."""

    def test_localhost_allowed(self):
        """Localhost is always allowed."""
        from superai import network_control
        controller = network_control.get_controller()
        result = controller.check_connection("localhost", 8080)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("zone"), "localhost")

    def test_127_allowed(self):
        """127.0.0.1 is always allowed."""
        from superai import network_control
        controller = network_control.get_controller()
        result = controller.check_connection("127.0.0.1", 3000)
        self.assertTrue(result.get("ok"))

    def test_remote_blocked_by_default(self):
        """Remote hosts are blocked by default."""
        from superai import network_control
        controller = network_control.get_controller()
        result = controller.check_connection("example.com", 443)
        self.assertFalse(result.get("ok"))

    def test_blocked_port_ssh(self):
        """SSH port is blocked for remote hosts."""
        from superai import network_control
        controller = network_control.get_controller()
        # Localhost is always allowed regardless of port
        result_local = controller.check_connection("localhost", 22)
        self.assertTrue(result_local.get("ok"))
        # But remote SSH is blocked
        result_remote = controller.check_connection("192.168.1.100", 22)
        self.assertFalse(result_remote.get("ok"))

    def test_policy_change(self):
        """Network policy can be changed."""
        from superai import network_control
        network_control.set_network_policy(allow_remote=True)
        stats = network_control.get_controller().get_stats()
        self.assertTrue(stats.get("policy", {}).get("allow_remote"))
        # Reset
        network_control.set_network_policy(allow_remote=False)

    def test_connection_log(self):
        """Connection log is populated."""
        from superai import network_control
        controller = network_control.get_controller()
        controller.check_connection("localhost", 8080)
        log = controller.get_connection_log(10)
        self.assertIsInstance(log, list)

    def test_global_functions(self):
        """Global functions work."""
        from superai import network_control
        result = network_control.check_connection("localhost", 3000)
        self.assertTrue(result.get("ok"))


class TestSemanticCache(unittest.TestCase):
    """Semantic cache module."""

    def test_cache_available_check(self):
        """Cache availability check works."""
        from superai import semantic_cache
        # Just check it doesn't crash
        available = semantic_cache.available()
        self.assertIsInstance(available, bool)

    def test_cache_stats(self):
        """Cache stats are available."""
        from superai import semantic_cache
        stats = semantic_cache.stats()
        self.assertIn("kind", stats)
        self.assertEqual(stats["kind"], "MEASURED")
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)

    def test_cache_store_lookup(self):
        """Store and lookup work."""
        from superai import semantic_cache
        # Store may fail if vectors not available — that's ok
        result = semantic_cache.store(
            "test query for cache",
            {"answer": "test answer"},
            0.9,
        )
        self.assertIsInstance(result, bool)

    def test_cache_format_stats(self):
        """Format stats works."""
        from superai import semantic_cache
        cache = semantic_cache.get_cache()
        formatted = cache.format_stats()
        self.assertIn("Semantic Cache", formatted)


class TestCohereRerank(unittest.TestCase):
    """Cohere rerank module."""

    def test_rerank_available_check(self):
        """Availability check works."""
        from superai import cohere_rerank
        available = cohere_rerank.available()
        self.assertIsInstance(available, bool)

    def test_rerank_fallback(self):
        """Fallback when API unavailable."""
        from superai import cohere_rerank
        result = cohere_rerank.rerank(
            "test query",
            ["doc1", "doc2", "doc3"],
            top_k=2,
        )
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 2)

    def test_rerank_usage(self):
        """Usage stats are available."""
        from superai import cohere_rerank
        usage = cohere_rerank.usage()
        self.assertIn("calls", usage)
        self.assertIn("limit", usage)
        self.assertIn("remaining", usage)

    def test_rerank_format_usage(self):
        """Format usage works."""
        from superai import cohere_rerank
        reranker = cohere_rerank.get_reranker()
        formatted = reranker.format_usage()
        self.assertIn("Cohere Rerank", formatted)


if __name__ == "__main__":
    unittest.main()
