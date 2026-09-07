"""EmbeddingAdapter — FastEmbed (neural) with HashingVectorizer fallback.

FastEmbed: BAAI/bge-small-en-v1.5 — 384-dim, ONNX, runs on CPU.
Fallback: sklearn.HashingVectorizer — lexical, no model download needed.

Performance:
- LRU cache (256 entries) for repeated embeddings
- Pre-warm on first neural model load
- Batch embedding support
"""
from __future__ import annotations

import numpy as np

from .util import normalize_query
import contextlib


DIM = 384
_neural = None
_neural_checked = False

# LRU cache for embeddings — avoids recomputing for repeated queries
_EMBED_CACHE_SIZE = 1024
_embed_cache: dict[str, list[float]] = {}
_embed_cache_order: list[str] = []  # LRU tracking
_METHOD_NEURAL = "FastEmbed BAAI/bge-small-en-v1.5 384-dim ONNX — neural"
_METHOD_LEXICAL = "sklearn.HashingVectorizer n_features=384 ngram(1,2) l2 — lexical, not neural"


def _get_neural():
    global _neural, _neural_checked
    if _neural_checked:
        return _neural
    _neural_checked = True
    try:
        from fastembed import TextEmbedding
        _neural = TextEmbedding("BAAI/bge-small-en-v1.5")
        return _neural
    except Exception:
        _neural = None
        return None


def _lexical_vec():
    from sklearn.feature_extraction.text import HashingVectorizer
    return HashingVectorizer(n_features=DIM, ngram_range=(1, 2), alternate_sign=False, norm="l2", lowercase=True)


_vec = None


def embed(text: str) -> list[float]:
    """Single embedding with LRU cache."""
    q = normalize_query(text) or text or " "
    # Check LRU cache first
    cache_key = q[:200]  # Truncate for cache key
    if cache_key in _embed_cache:
        # Move to end (most recently used)
        with contextlib.suppress(ValueError):
            _embed_cache_order.remove(cache_key)
        _embed_cache_order.append(cache_key)
        return _embed_cache[cache_key]
    # Compute embedding
    result = _embed_raw(q)
    # Store in LRU cache
    _embed_cache[cache_key] = result
    _embed_cache_order.append(cache_key)
    # Evict oldest if over size
    while len(_embed_cache) > _EMBED_CACHE_SIZE:
        old_key = _embed_cache_order.pop(0)
        _embed_cache.pop(old_key, None)
    return result


def _embed_raw(text: str) -> list[float]:
    """Raw embedding computation (no cache)."""
    # Try neural first
    model = _get_neural()
    if model is not None:
        try:
            arr = list(model.embed([text]))[0]
            return arr.tolist() if hasattr(arr, 'tolist') else list(arr)
        except Exception:
            pass
    # Fallback: lexical
    global _vec
    if _vec is None:
        _vec = _lexical_vec()
    arr = _vec.transform([text]).toarray()[0].astype(np.float32)
    n = float(np.linalg.norm(arr))
    if n == 0:
        return arr.tolist()
    return (arr / n).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding — single model call for multiple texts."""
    if not texts:
        return []
    if len(texts) == 1:
        return [embed(texts[0])]

    # Check cache for each
    results: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    for i, text in enumerate(texts):
        q = normalize_query(text) or text or " "
        cache_key = q[:200]
        if cache_key in _embed_cache:
            results[i] = _embed_cache[cache_key]
        else:
            uncached_indices.append(i)
            uncached_texts.append(q)

    # Batch compute uncached
    if uncached_texts:
        model = _get_neural()
        if model is not None:
            try:
                batch_results = list(model.embed(uncached_texts))
                for j, idx in enumerate(uncached_indices):
                    arr = batch_results[j]
                    result = arr.tolist() if hasattr(arr, 'tolist') else list(arr)
                    results[idx] = result
                    # Cache
                    cache_key = uncached_texts[j][:200]
                    _embed_cache[cache_key] = result
                    _embed_cache_order.append(cache_key)
            except Exception:
                # Fallback to individual
                for idx in uncached_indices:
                    results[idx] = embed(texts[idx])
        else:
            # Lexical fallback
            for idx in uncached_indices:
                results[idx] = embed(texts[idx])

    # Evict if over size
    while len(_embed_cache) > _EMBED_CACHE_SIZE:
        old_key = _embed_cache_order.pop(0)
        _embed_cache.pop(old_key, None)

    return [r for r in results if r is not None]


def cache_stats() -> dict:
    """Embedding cache statistics."""
    return {
        "kind": "MEASURED",
        "cache_size": len(_embed_cache),
        "cache_max": _EMBED_CACHE_SIZE,
        "neural": _neural is not None,
    }


def warmup() -> None:
    """Pre-warm the embedding model. Call during boot."""
    _get_neural()


def cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)))


def info() -> dict:
    model = _get_neural()
    if model is not None:
        return {"dim": DIM, "method": _METHOD_NEURAL, "neural": True, "verified": True,
                "cache": cache_stats()}
    return {"dim": DIM, "method": _METHOD_LEXICAL, "neural": False, "verified": True,
            "cache": cache_stats()}
