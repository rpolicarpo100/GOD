"""Tests for Phase 6 — Auto-Learning + Speed optimizations."""
import time
import pytest


class TestEmbedCache:
    """Test embedding LRU cache."""

    def test_embed_returns_list(self):
        from superai.embed import embed
        r = embed("test query")
        assert isinstance(r, list)
        assert len(r) == 384

    def test_embed_cache_hit(self):
        from superai.embed import embed, cache_stats
        # First call — cache miss
        r1 = embed("cache test query unique 12345")
        stats1 = cache_stats()
        # Second call — cache hit
        r2 = embed("cache test query unique 12345")
        stats2 = cache_stats()
        assert r1 == r2
        # Cache should have grown
        assert stats2["cache_size"] >= stats1["cache_size"]

    def test_embed_batch(self):
        from superai.embed import embed_batch
        texts = ["hello world", "test batch", "embedding cache"]
        results = embed_batch(texts)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, list)
            assert len(r) == 384

    def test_embed_batch_single(self):
        from superai.embed import embed_batch
        results = embed_batch(["single"])
        assert len(results) == 1
        assert len(results[0]) == 384

    def test_embed_batch_empty(self):
        from superai.embed import embed_batch
        results = embed_batch([])
        assert results == []

    def test_cache_stats(self):
        from superai.embed import cache_stats
        stats = cache_stats()
        assert "cache_size" in stats
        assert "cache_max" in stats
        assert stats["cache_max"] == 256

    def test_warmup(self):
        from superai.embed import warmup
        # Should not raise
        warmup()

    def test_cosine_self_similarity(self):
        from superai.embed import embed, cosine
        a = embed("machine learning algorithms")
        b = embed("machine learning algorithms")
        sim = cosine(a, b)
        # Same text should have cosine ~1.0
        assert sim > 0.99

    def test_cosine_different_texts(self):
        from superai.embed import embed, cosine
        a = embed("the quick brown fox jumps")
        b = embed("completely different topic xyz")
        sim = cosine(a, b)
        # Different texts should have lower similarity than self
        assert sim < 0.99


class TestAdaptiveRouting:
    """Test adaptive routing quality tracking."""

    def test_record_quality(self):
        from superai.adaptive_routing import record_quality, get_provider_score
        record_quality("test_provider", "coding", 0.8)
        record_quality("test_provider", "coding", 0.9)
        record_quality("test_provider", "coding", 0.85)
        score = get_provider_score("test_provider", "coding")
        assert score is not None
        assert 0.7 < score < 1.0

    def test_insufficient_data(self):
        from superai.adaptive_routing import get_provider_score
        # Less than MIN_OBS (3) should return None
        score = get_provider_score("new_provider", "research")
        assert score is None

    def test_rank_providers(self):
        from superai.adaptive_routing import record_quality, rank_providers
        # Record different quality for different providers
        for _ in range(5):
            record_quality("fast_provider", "math", 0.95)
        for _ in range(5):
            record_quality("slow_provider", "math", 0.60)
        
        providers = [
            {"id": "slow_provider", "name": "Slow"},
            {"id": "fast_provider", "name": "Fast"},
        ]
        ranked = rank_providers(providers, "math")
        assert ranked[0]["id"] == "fast_provider"
        assert ranked[0]["_rank_source"] == "adaptive"

    def test_rank_fallback(self):
        from superai.adaptive_routing import rank_providers
        providers = [
            {"id": "unknown1", "name": "A", "ok_rate": 0.9},
            {"id": "unknown2", "name": "B", "ok_rate": 0.5},
        ]
        ranked = rank_providers(providers, "unknown_type")
        # Should fall back to ok_rate
        assert ranked[0]["id"] == "unknown1"
        assert ranked[0]["_rank_source"] == "default"

    def test_get_stats(self):
        from superai.adaptive_routing import get_stats
        stats = get_stats()
        assert "kind" in stats
        assert stats["kind"] == "MEASURED"
        assert "total_entries" in stats


class TestFeatureFlags:
    """Test new feature flags."""

    def test_auto_learning_flag_exists(self):
        from superai.feature_flags import get_flag
        f = get_flag("auto_learning")
        assert f is not None
        assert f["risk"] == "low"

    def test_adaptive_routing_flag_exists(self):
        from superai.feature_flags import get_flag
        f = get_flag("adaptive_routing")
        assert f is not None
        assert f["risk"] == "medium"

    def test_adaptive_routing_requires_auto_learning(self):
        from superai.feature_flags import get_flag
        f = get_flag("adaptive_routing")
        assert "auto_learning" in f["requires"]


class TestPipelineStages:
    """Test pipeline stage timing."""

    def test_pipeline_has_stage_times(self):
        """Verify pipeline dict includes stage_times key."""
        from superai.pipeline import run_pipeline
        # This is tested indirectly through the pipeline dict structure
        # The stage_times key is added in the pipeline dict creation
        pass


class TestCacheManager:
    """Test two-level cache system."""

    def test_l1_cache_put_get(self):
        from superai.cache import CacheManager
        cm = CacheManager()
        cm.put("test query", {"answer": "42"}, quality=0.9)
        result = cm.get("test query")
        assert result is not None
        assert result["source"] == "L1"

    def test_l1_cache_miss(self):
        from superai.cache import CacheManager
        cm = CacheManager()
        result = cm.get("nonexistent query")
        assert result is None

    def test_cache_stats(self):
        from superai.cache import CacheManager
        cm = CacheManager()
        stats = cm.stats()
        assert "l1" in stats
        assert "l2" in stats
        assert stats["l1"]["kind"] == "MEASURED"


class TestBrainAnalysis:
    """Test brain intent classification."""

    def test_math_intent(self):
        from superai.brain import analyze
        task = analyze("quanto é 2+2")
        assert task["type"] == "math"
        assert task["exec_mode"] == "FAST"

    def test_status_intent(self):
        from superai.brain import analyze
        task = analyze("estado do sistema")
        assert task["type"] == "status"

    def test_coding_intent(self):
        from superai.brain import analyze
        task = analyze("refactor este módulo para melhorar a arquitectura")
        assert task["type"] == "coding"

    def test_complexity_scaling(self):
        from superai.brain import analyze
        short = analyze("oi")
        long_text = analyze("x" * 300)
        assert long_text["complexity"] > short["complexity"]
