"""Unit tests for superai/observer.py — alerts, suggestions."""
import unittest


class TestObserver(unittest.TestCase):
    """Test observer inspection."""

    def test_inspect_returns_structure(self):
        from superai.observer import inspect
        result = inspect()
        self.assertIn("ok", result)
        self.assertIn("alerts", result)
        self.assertIn("metrics", result)

    def test_alerts_is_list(self):
        from superai.observer import inspect
        result = inspect()
        self.assertIsInstance(result["alerts"], list)

    def test_metrics_has_cpu(self):
        from superai.observer import inspect
        result = inspect()
        self.assertIn("cpu_load1", result["metrics"])


class TestSuggestions(unittest.TestCase):
    """Test proactive suggestions."""

    def test_generate_suggestions_returns_list(self):
        from superai.observer import generate_suggestions
        sug = generate_suggestions()
        self.assertIsInstance(sug, list)
        self.assertLessEqual(len(sug), 3)

    def test_suggestions_are_strings(self):
        from superai.observer import generate_suggestions
        for s in generate_suggestions():
            self.assertIsInstance(s, str)
            self.assertGreater(len(s), 10)


if __name__ == "__main__":
    unittest.main()
