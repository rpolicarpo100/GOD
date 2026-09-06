"""Unit tests for superai/routing.py — provider racing, fallback."""
import unittest


class TestRoutingHealth(unittest.TestCase):
    """Test routing health check."""

    def test_health_returns_structure(self):
        from superai.routing import health
        h = health()
        self.assertIn("active", h)
        self.assertIn("omniroute", h)
        self.assertIn("direct", h)

    def test_health_omniroute_has_available(self):
        from superai.routing import health
        h = health()
        self.assertIn("available", h["omniroute"])

    def test_health_direct_has_available(self):
        from superai.routing import health
        h = health()
        self.assertIn("available", h["direct"])


class TestRoutingComplete(unittest.TestCase):
    """Test routing complete — should work even without providers."""

    def test_complete_returns_dict(self):
        from superai.routing import complete
        result = complete("test prompt", max_tokens=10)
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)

    def test_complete_has_latency(self):
        from superai.routing import complete
        result = complete("test prompt", max_tokens=10)
        self.assertIn("latency_ms", result)

    def test_complete_has_gateway(self):
        from superai.routing import complete
        result = complete("test prompt", max_tokens=10)
        self.assertIn("gateway", result)


if __name__ == "__main__":
    unittest.main()
