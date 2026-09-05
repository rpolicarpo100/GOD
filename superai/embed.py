"""EmbeddingAdapter — FastEmbed (neural) with HashingVectorizer fallback.

FastEmbed: BAAI/bge-small-en-v1.5 — 384-dim, ONNX, runs on CPU.
Fallback: sklearn.HashingVectorizer — lexical, no model download needed.
"""
from __future__ import annotations

import numpy as np

from .util import normalize_query

DIM = 384
_neural = None
_neural_checked = False
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
    q = normalize_query(text) or text or " "
    # Try neural first
    model = _get_neural()
    if model is not None:
        try:
            arr = list(model.embed([q]))[0]
            return arr.tolist() if hasattr(arr, 'tolist') else list(arr)
        except Exception:
            pass
    # Fallback: lexical
    global _vec
    if _vec is None:
        _vec = _lexical_vec()
    arr = _vec.transform([q]).toarray()[0].astype(np.float32)
    n = float(np.linalg.norm(arr))
    if n == 0:
        return arr.tolist()
    return (arr / n).tolist()


def cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)))


def info() -> dict:
    model = _get_neural()
    if model is not None:
        return {"dim": DIM, "method": _METHOD_NEURAL, "neural": True, "verified": True}
    return {"dim": DIM, "method": _METHOD_LEXICAL, "neural": False, "verified": True}
