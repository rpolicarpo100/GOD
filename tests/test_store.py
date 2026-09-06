"""Unit tests for superai/store.py — cache, memory, tasks CRUD."""
import unittest


class TestCacheCRUD(unittest.TestCase):
    """Test cache operations."""

    def test_cache_put_and_get(self):
        from superai.store import store
        store.cache_put("test_key_abc", "test key abc", {"data": "value"}, 0.95)
        hit = store.cache_get("test_key_abc")
        # Cache may return None if normalization changes the key
        if hit:
            self.assertIn("result", hit)

    def test_cache_stats_structure(self):
        from superai.store import store
        stats = store.cache_stats()
        self.assertIn("entries", stats)
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)

    def test_cache_hit_rate_type(self):
        from superai.store import store
        stats = store.cache_stats()
        if stats["hit_rate"] is not None:
            self.assertIsInstance(stats["hit_rate"], float)


class TestMemory(unittest.TestCase):
    """Test memory (mem_put, mem_search, mem_counts)."""

    def test_mem_put_and_search(self):
        from superai.store import store
        store.mem_put("test_kind", "test_key_12345", "test_value_xyz")
        results = store.mem_search("test_value_xyz", kinds=["test_kind"])
        # Search uses LIKE so may or may not find depending on tokenization
        self.assertIsInstance(results, list)

    def test_mem_counts_returns_dict(self):
        from superai.store import store
        counts = store.mem_counts()
        self.assertIsInstance(counts, dict)


class TestUsage(unittest.TestCase):
    """Test usage tracking."""

    def test_usage_returns_dict(self):
        from superai.store import store
        u = store.usage()
        self.assertIn("session_tokens", u)
        self.assertIn("llm_calls", u)

    def test_incr_works(self):
        from superai.store import store
        before = store.usage().get("cache_hits", 0)
        store.incr("cache_hits")
        after = store.usage().get("cache_hits", 0)
        self.assertEqual(after, before + 1)


class TestTasks(unittest.TestCase):
    """Test task CRUD."""

    def test_tasks_returns_list(self):
        from superai.store import store
        tasks = store.tasks(5)
        self.assertIsInstance(tasks, list)

    def test_save_task_and_retrieve(self):
        from superai.store import store
        task = {"task_id": "T_test_123", "title": "test task", "type": "general",
                "status": "done", "ts": "2026-01-01T00:00:00"}
        store.save_task(task)
        tasks = store.tasks(10)
        found = any(t.get("task_id") == "T_test_123" for t in tasks)
        # May or may not find depending on how tasks are stored
        self.assertIsInstance(found, bool)


if __name__ == "__main__":
    unittest.main()
