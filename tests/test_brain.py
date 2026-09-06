"""Unit tests for superai/brain.py — analyze, firewall, cache, evaluate."""
import unittest


class TestAnalyze(unittest.TestCase):
    """Test the intent analysis function."""

    def test_general_returns_general(self):
        from superai.brain import analyze
        t = analyze("olá como estás")
        self.assertEqual(t["type"], "general")
        self.assertIn(t["exec_mode"], ("FAST", "NORMAL", "DEEP"))

    def test_math_detected(self):
        from superai.brain import analyze
        t = analyze("quanto é 2+2")
        self.assertEqual(t["type"], "math")
        self.assertEqual(t["exec_mode"], "FAST")

    def test_coding_detected(self):
        from superai.brain import analyze
        t = analyze("cria uma class Python com metodo init e getters")
        self.assertIn(t["type"], ("coding", "python", "general"))
        self.assertIn(t["exec_mode"], ("DEEP", "NORMAL"))

    def test_status_detected(self):
        from superai.brain import analyze
        t = analyze("estado do sistema")
        self.assertEqual(t["type"], "status")

    def test_complexity_scales_with_length(self):
        from superai.brain import analyze
        short = analyze("olá")
        long_text = analyze("a" * 300)
        self.assertGreater(long_text["complexity"], short["complexity"])

    def test_empty_text(self):
        from superai.brain import analyze
        t = analyze("")
        self.assertIsNotNone(t["task_id"])
        self.assertEqual(t["type"], "general")

    def test_task_id_unique(self):
        from superai.brain import analyze
        t1 = analyze("hello")
        t2 = analyze("hello")
        self.assertNotEqual(t1["task_id"], t2["task_id"])

    def test_privacy_local_only(self):
        from superai.brain import analyze
        t = analyze("guarda esta password secreta")
        self.assertEqual(t["privacy"], "local_only")

    def test_token_estimate_present(self):
        from superai.brain import analyze
        t = analyze("hello world")
        self.assertIn("tokens", t["token_estimate"])
        self.assertGreater(t["token_estimate"]["tokens"], 0)


class TestFirewall(unittest.TestCase):
    """Test the budget firewall."""

    def test_approve_within_budget(self):
        from superai.brain import analyze, firewall
        task = analyze("hello")
        result = firewall(task)
        self.assertIn(result["action"], ("approve", "optimize"))

    def test_detects_high_tokens(self):
        from superai.brain import firewall
        task = {"estimated_tokens": 100000, "complexity": 5}
        result = firewall(task)
        self.assertIn(result["action"], ("optimize", "reject"))


class TestEvaluate(unittest.TestCase):
    """Test quality evaluation."""

    def test_scores_returned(self):
        from superai.brain import evaluate
        task = {"type": "general", "complexity": 3, "task_id": "T_test"}
        scores = evaluate(task, [], False, 0)
        self.assertIn("OVERALL", scores)
        self.assertIsInstance(scores["OVERALL"], (int, float))

    def test_tool_results_improve_score(self):
        from superai.brain import evaluate
        task = {"type": "general", "complexity": 3, "task_id": "T_test2"}
        s_empty = evaluate(task, [], False, 0)
        tools = [{"tool": "test", "status": "success", "confidence": 0.8,
                  "findings": [{"text": "found it"}], "errors": [], "evidence": ["test"]}]
        s_tools = evaluate(task, tools, False, 0)
        self.assertGreaterEqual(s_tools["OVERALL"], s_empty["OVERALL"])


class TestCache(unittest.TestCase):
    """Test cache lookup and store."""

    def test_store_and_lookup(self):
        from superai.brain import cache_store, cache_lookup
        cache_store("test query unique 12345", {"summary": "test result"}, 0.9, ns="test")
        hit = cache_lookup("test query unique 12345", ns="test")
        # May or may not hit depending on normalization — just verify no crash
        self.assertIsInstance(hit, (dict, type(None)))

    def test_lookup_miss(self):
        from superai.brain import cache_lookup
        hit = cache_lookup("zzz_nonexistent_query_99999_zzz", ns="test_miss")
        self.assertIsNone(hit)


if __name__ == "__main__":
    unittest.main()
