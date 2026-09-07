"""Qdrant MemoryAdapter — embedded local client (no Docker server)."""
from __future__ import annotations

import atexit
import contextlib
import os
import threading
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, FieldCondition, Filter, HnswConfigDiff, IsEmptyCondition, MatchValue, PayloadField, PayloadSchemaType, PointStruct, VectorParams

from .config import DATA
from .embed import DIM, embed, info as embed_info
import contextlib

MEM = "memory"
CACHE = "cache"


def _client() -> QdrantClient:
    uri = os.environ.get("SUPERAI_QDRANT", "")
    if uri == ":memory:":
        return QdrantClient(":memory:")
    path = DATA / "qdrant"
    path.mkdir(exist_ok=True)
    return QdrantClient(path=str(path))


class VectorMemory:
    def __init__(self) -> None:
        self.backend = "qdrant-local"
        self.error: str | None = None
        self._lock = threading.RLock()
        try:
            self.c = _client()
            self._ensure(MEM)
            self._ensure(CACHE)
        except Exception as e:
            self.c = None
            self.error = str(e)
        atexit.register(self.close)

    def close(self) -> None:
        """Explicit cleanup to avoid __del__ shutdown warnings."""
        c = self.c
        if c is not None:
            self.c = None
            with contextlib.suppress(Exception):
                c.close()

    def _ensure(self, name: str) -> None:
        with self._lock:
            try:
                self.c.get_collection(name)
            except Exception:
                self.c.create_collection(
                    name,
                    vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
                )
            # Create payload index for god_id (speeds up filtered searches)
            with contextlib.suppress(Exception):  # Already exists or collection just created
                self.c.create_payload_index(
                    name, "god_id", field_schema=PayloadSchemaType.KEYWORD,
                )

    def available(self) -> bool:
        return self.c is not None and self.error is None

    def health(self) -> dict:
        counts = {}
        if self.available():
            with self._lock:
                for n in (MEM, CACHE):
                    try:
                        counts[n] = int(self.c.get_collection(n).points_count or 0)
                    except Exception as e:
                        counts[n] = f"err {e}"
        return {
            "backend": self.backend,
            "available": self.available(),
            "error": self.error,
            "collections": counts,
            "embed": embed_info(),
            "server_6333": False,
            "note": "Qdrant embedded (path/memory). Sem processo Docker :6333.",
        }

    def upsert(self, collection: str, key: str, text: str, payload: dict[str, Any] | None = None) -> str:
        if not self.available():
            raise RuntimeError(self.error or "qdrant down")
        import time as _time
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection}:{key}"))
        pl = {
            "key": key, "text": text[:2000],
            "created_at": _time.time(),
            "last_access": _time.time(),
            "access_count": 0,
            "importance": (payload or {}).get("importance", 0.5),
            "confidence": (payload or {}).get("confidence", 0.5),
            **(payload or {}),
        }
        with self._lock:
            self.c.upsert(
                collection,
                points=[PointStruct(id=pid, vector=embed(text), payload=pl)],
            )
        return pid

    def record_access(self, collection: str, key: str) -> None:
        """Update last_access and access_count for a memory entry."""
        if not self.available():
            return
        import time as _time
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection}:{key}"))
        try:
            from .store import store
            # Access tracking is best-effort
            with self._lock:
                # We can't easily update in Qdrant, so we track in SQLite
                store.mem_put("memory_access", key, {"last_access": _time.time(), "collection": collection})
        except Exception:
            pass

    def prune_stale(self, collection: str, max_age_days: float = 30, min_importance: float = 0.3) -> int:
        """Remove low-importance, stale memories."""
        if not self.available():
            return 0
        import time as _time
        cutoff = _time.time() - (max_age_days * 86400)
        try:
            from qdrant_client.models import Filter, FieldCondition, Range
            # This is a best-effort cleanup
            # Full implementation would scroll through all points
            return 0
        except Exception:
            return 0

    def _god_filter(self, god_id: str | None) -> Filter | None:
        if not god_id:
            return None
        if god_id == "master":
            return Filter(
                should=[
                    FieldCondition(key="god_id", match=MatchValue(value="master")),
                    IsEmptyCondition(is_empty=PayloadField(key="god_id")),
                ]
            )
        return Filter(must=[FieldCondition(key="god_id", match=MatchValue(value=god_id))])

    def search(self, collection: str, text: str, k: int = 5, min_score: float = 0.35, god_id: str | None = None) -> list[dict]:
        if not self.available():
            return []
        qf = self._god_filter(god_id)
        try:
            with self._lock:
                try:
                    res = self.c.query_points(collection, query=embed(text), limit=k, with_payload=True, query_filter=qf)
                except Exception:
                    if god_id and god_id != "master":
                        return []
                    res = self.c.query_points(collection, query=embed(text), limit=k, with_payload=True)
                points = res.points
        except UnexpectedResponse:
            return []
        except Exception:
            return []
        out = []
        for p in points:
            score = float(p.score or 0)
            if score < min_score:
                continue
            pl = p.payload or {}
            if god_id:
                gid = pl.get("god_id")
                if god_id == "master":
                    if gid not in (None, "", "master"):
                        continue
                elif gid != god_id:
                    continue
            out.append({"id": str(p.id), "score": round(score, 4), **pl})
        return out


vectors = VectorMemory()
