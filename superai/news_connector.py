"""News Intelligence Connector — access news-ai-agreger.onrender.com API.

Provides GOD with real-time news intelligence from 14+ verified sources.
Features:
- Search news by topic
- Get latest events by category
- Get event details with articles
- Source reliability tracking
- Verification status filtering
"""
from __future__ import annotations

import time

import httpx

from .util import now_iso

BASE_URL = "https://news-ai-agreger.onrender.com"
_client = httpx.Client(
    base_url=BASE_URL,
    timeout=45.0,  # Render cold start can be slow
    headers={"User-Agent": "GOD/1.0", "Accept": "application/json"},
    follow_redirects=True,
)

# Cache
_cache: dict[str, dict] = {}
_CACHE_TTL = 120  # 2 minutes


def _cached_get(path: str, params: dict = None, ttl: int = _CACHE_TTL) -> dict | None:
    """GET with cache."""
    key = f"{path}:{params}"
    cached = _cache.get(key)
    if cached and time.time() - cached.get("ts", 0) < ttl:
        return cached["data"]
    try:
        r = _client.get(path, params=params or {})
        if r.status_code == 200:
            data = r.json()
            _cache[key] = {"data": data, "ts": time.time()}
            return data
    except Exception:
        pass
    return None


def search_news(query: str, limit: int = 10) -> dict:
    """Search news events by topic."""
    data = _cached_get("/api/search", {"q": query})
    if data is None:
        return {"status": "error", "error": "news API unavailable", "kind": "MEASURED"}
    results = data.get("results", [])
    return {
        "status": "success",
        "query": query,
        "results": _format_events(results[:limit]),
        "n": len(results),
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def get_latest(limit: int = 10, category: str = "") -> dict:
    """Get latest news events."""
    params = {"limit": limit}
    if category:
        params["category"] = category
    data = _cached_get("/api/events", params)
    if data is None:
        return {"status": "error", "error": "news API unavailable", "kind": "MEASURED"}
    events = data.get("events", [])
    return {
        "status": "success",
        "events": _format_events(events),
        "n": len(events),
        "total": data.get("count", len(events)),
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def get_event(event_id: str) -> dict:
    """Get detailed event info."""
    data = _cached_get(f"/api/events/{event_id}")
    if data is None:
        return {"status": "error", "error": "event not found", "kind": "MEASURED"}
    return {
        "status": "success",
        "event": data,
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def get_sources() -> dict:
    """List all news sources."""
    data = _cached_get("/api/sources", ttl=3600)
    if data is None:
        return {"status": "error", "error": "sources unavailable", "kind": "MEASURED"}
    sources = data.get("sources", [])
    return {
        "status": "success",
        "sources": [
            {"id": s.get("id"), "name": s.get("name"), "type": s.get("origin_type"),
             "country": s.get("country"), "language": s.get("language")}
            for s in sources
        ],
        "n": len(sources),
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def health() -> dict:
    """Check news API health."""
    data = _cached_get("/api/health", ttl=30)
    if data is None:
        return {"status": "error", "available": False, "kind": "MEASURED"}
    return {
        "status": "success",
        "available": True,
        "driver": data.get("driver"),
        "total_events": data.get("events"),
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def _format_events(events: list[dict]) -> list[dict]:
    """Format events for display."""
    out = []
    for e in events:
        out.append({
            "id": e.get("id"),
            "title": e.get("title"),
            "category": e.get("category_label") or e.get("category"),
            "country": e.get("country"),
            "place": e.get("place"),
            "verification": e.get("verification"),
            "published": e.get("published_at"),
            "articles": e.get("article_count"),
            "sources": e.get("independent_sources"),
            "relevance": e.get("relevance"),
            "confidence": e.get("confidence"),
            "freshness": e.get("freshness"),
            "url": f"{BASE_URL}{e.get('url', '')}",
            "slug": e.get("slug"),
        })
    return out


def format_for_llm(results: dict) -> str:
    """Format search results as context for LLM."""
    events = results.get("results") or results.get("events", [])
    if not events:
        return ""

    lines = [f"NOTÍCIAS EM TEMPO REAL ({len(events)} resultados):"]
    for e in events[:5]:
        verif = e.get("verification", "")
        conf = e.get("confidence", "")
        lines.append(
            f"\n• {e.get('title', 'N/A')}"
            f"  [{e.get('category', '')}] {e.get('country', '')}"
            f" | Verificação: {verif} | Confiança: {conf}"
            f" | Fontes: {e.get('sources', '?')} | {e.get('published', '')[:10]}"
        )
        if e.get("place"):
            lines.append(f"  Local: {e['place']}")

    lines.append("\nFonte: Global News Intelligence (news-ai-agreger.onrender.com)")
    return "\n".join(lines)
