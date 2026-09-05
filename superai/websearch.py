"""Web Search — pesquisa na web via múltiplos backends.

Backends (tentados em ordem):
1. SearXNG local (se disponível)
2. DuckDuckGo Instant API (gratuito, sem key)
3. Fallback: recusar educadamente
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from .util import now_iso


def search(query: str, max_results: int = 5) -> dict:
    """Pesquisar na web. Retorna resultados ou erro."""
    query = (query or "").strip()
    if not query:
        return {"status": "error", "error": "query vazia", "kind": "MEASURED"}

    # Try SearXNG local
    r = _searxng(query, max_results)
    if r:
        return r

    # Try DuckDuckGo
    r = _duckduckgo(query, max_results)
    if r:
        return r

    return {
        "status": "error",
        "error": "nenhum search engine disponível",
        "query": query,
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def _searxng(query: str, max_results: int) -> dict | None:
    """Try local SearXNG instance."""
    for port in (8080, 8888):
        try:
            r = httpx.get(
                f"http://127.0.0.1:{port}/search",
                params={"q": query, "format": "json", "pageno": 1},
                timeout=5.0,
            )
            if r.status_code == 200:
                data = r.json()
                results = []
                for item in (data.get("results") or [])[:max_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", "")[:300],
                    })
                if results:
                    return {
                        "status": "success",
                        "backend": f"searxng:{port}",
                        "query": query,
                        "n": len(results),
                        "results": results,
                        "kind": "MEASURED",
                        "ts": now_iso(),
                    }
        except Exception:
            continue
    return None


def _duckduckgo(query: str, max_results: int) -> dict | None:
    """Try DuckDuckGo Instant Answer API (free, no key)."""
    try:
        r = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            headers={"User-Agent": "GOD/1.0"},
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        results = []

        # Abstract (main answer)
        abstract = data.get("Abstract", "")
        abstract_url = data.get("AbstractURL", "")
        if abstract:
            results.append({
                "title": data.get("Heading", query),
                "url": abstract_url,
                "snippet": abstract[:300],
            })

        # Related topics
        for topic in (data.get("RelatedTopics") or [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:100],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", "")[:300],
                })

        if results:
            return {
                "status": "success",
                "backend": "duckduckgo",
                "query": query,
                "n": min(len(results), max_results),
                "results": results[:max_results],
                "kind": "MEASURED",
                "ts": now_iso(),
            }
    except Exception:
        pass
    return None


def health() -> dict:
    """Check which search backends are available."""
    backends = {}

    # SearXNG
    for port in (8080, 8888):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/", timeout=1.0)
            backends[f"searxng:{port}"] = r.status_code == 200
        except Exception:
            backends[f"searxng:{port}"] = False

    # DuckDuckGo
    try:
        r = httpx.get("https://api.duckduckgo.com/?q=test&format=json", timeout=3.0, headers={"User-Agent": "GOD/1.0"})
        backends["duckduckgo"] = r.status_code == 200
    except Exception:
        backends["duckduckgo"] = False

    available = [k for k, v in backends.items() if v]
    return {
        "kind": "MEASURED",
        "backends": backends,
        "available": available,
        "n_available": len(available),
        "ts": now_iso(),
    }
