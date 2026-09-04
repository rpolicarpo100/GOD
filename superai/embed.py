"""EmbeddingAdapter — hashing-trick dense vectors (sklearn). Not a neural model.

Upgrade path (not wired): Ollama / FastEmbed when those providers are verified.
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from .util import normalize_query

DIM = 384
METHOD = "sklearn.HashingVectorizer n_features=384 ngram(1,2) l2 — lexical, not neural"

_vec = HashingVectorizer(
    n_features=DIM,
    ngram_range=(1, 2),
    alternate_sign=False,
    norm="l2",
    lowercase=True,
)


def embed(text: str) -> list[float]:
    q = normalize_query(text) or text or " "
    arr = _vec.transform([q]).toarray()[0].astype(np.float32)
    n = float(np.linalg.norm(arr))
    if n == 0:
        return arr.tolist()
    return (arr / n).tolist()


def cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)))


def info() -> dict:
    return {"dim": DIM, "method": METHOD, "neural": False, "verified": True}
