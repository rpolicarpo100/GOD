"""Site Aggregator — fetch and aggregate info from configured sites.

GOD can autonomously fetch information from user-configured sites.
Sites are stored in config and can be managed via API.

Features:
- Register sites by URL + category
- Fetch + extract text from any site
- Search across all registered sites
- Cache results per site (5min TTL)
- Aggregate results from multiple sites
- Auto-detect site type (API docs, blog, dashboard, etc.)
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from .config import cfg
from .store import store
from .util import now_iso, sha

_client = httpx.Client(
    timeout=15.0,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    },
    follow_redirects=True,
)

# Site registry: {id: {url, name, category, description, added_at}}
_sites: dict[str, dict] = {}
_sites_loaded = False

# Cache: {url_hash: {content, ts}}
_cache: dict[str, dict] = {}
_CACHE_TTL = 300  # 5 minutes


def _load_sites() -> None:
    """Load sites from config/store."""
    global _sites, _sites_loaded
    if _sites_loaded:
        return
    _sites_loaded = True
    try:
        # Load from store
        stored = store.mem_search("", kinds=["site_registry"])
        for s in stored:
            val = s.get("value") or {}
            if isinstance(val, dict) and val.get("url"):
                site_id = sha(val["url"])
                _sites[site_id] = val
        # Load from config
        cfg_sites = cfg.get("sites") or []
        for site in cfg_sites:
            if isinstance(site, dict) and site.get("url"):
                site_id = sha(site["url"])
                _sites[site_id] = site
    except Exception:
        pass


def register_site(url: str, name: str = "", category: str = "general",
                  description: str = "") -> dict:
    """Register a new site for aggregation."""
    url = url.strip().rstrip("/")
    if not url:
        return {"ok": False, "error": "missing url"}

    site_id = sha(url)
    site = {
        "url": url,
        "name": name or urlparse(url).netloc,
        "category": category,
        "description": description,
        "added_at": now_iso(),
    }

    _sites[site_id] = site

    # Persist
    try:
        store.mem_put("site_registry", site_id, site)
    except Exception:
        pass

    return {"ok": True, "site_id": site_id, "site": site}


def remove_site(site_id: str) -> dict:
    """Remove a registered site."""
    if site_id in _sites:
        del _sites[site_id]
        return {"ok": True}
    return {"ok": False, "error": "site not found"}


def list_sites() -> list[dict]:
    """List all registered sites."""
    _load_sites()
    return [{"id": sid, **site} for sid, site in _sites.items()]


def fetch_site(url: str, path: str = "") -> dict:
    """Fetch content from a specific site/path."""
    full_url = url.rstrip("/")
    if path:
        full_url += "/" + path.lstrip("/")

    # Check cache
    cache_key = sha(full_url)
    cached = _cache.get(cache_key)
    if cached and time.time() - cached.get("ts", 0) < _CACHE_TTL:
        return {**cached["result"], "cached": True}

    try:
        # SSRF protection
        from .network_control import validate_url
        v = validate_url(full_url)
        if not v.get("ok"):
            return {"status": "error", "error": v.get("reason", "blocked"), "url": full_url}

        r = _client.get(full_url)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}", "url": full_url}

        content_type = r.headers.get("content-type", "")

        if "json" in content_type:
            data = r.json()
            text = str(data)[:5000]
            title = "JSON Response"
        else:
            html = r.text
            title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            title = title_m.group(1).strip() if title_m else ""
            text = _html_to_text(html)

        result = {
            "status": "success",
            "url": full_url,
            "title": title,
            "text": text[:5000],
            "length": len(text),
            "content_type": content_type,
            "kind": "MEASURED",
            "ts": now_iso(),
        }

        # Cache
        _cache[cache_key] = {"result": result, "ts": time.time()}

        return result
    except Exception as e:
        return {"status": "error", "error": str(e), "url": full_url}


def search_sites(query: str, max_per_site: int = 3) -> dict:
    """Search across all registered sites.
    
    For each site, fetches the page and searches for the query in content.
    Returns aggregated results.
    """
    _load_sites()
    if not _sites:
        return {
            "status": "error",
            "error": "nenhum site configurado. Usa /api/sites/register",
            "kind": "MEASURED",
        }

    results = []
    for site_id, site in _sites.items():
        try:
            r = fetch_site(site["url"])
            if r.get("status") == "success":
                text = r.get("text", "")
                # Simple relevance: check if query terms appear in content
                query_terms = query.lower().split()
                text_lower = text.lower()
                matches = sum(1 for term in query_terms if term in text_lower)
                relevance = matches / max(len(query_terms), 1)

                if relevance > 0:
                    # Extract relevant snippets
                    snippets = _extract_snippets(text, query_terms, max_snippets=max_per_site)
                    results.append({
                        "site": site["name"],
                        "url": site["url"],
                        "category": site.get("category", "general"),
                        "relevance": round(relevance, 2),
                        "snippets": snippets,
                        "title": r.get("title", ""),
                    })
        except Exception:
            continue

    # Sort by relevance
    results.sort(key=lambda x: x["relevance"], reverse=True)

    return {
        "status": "success",
        "query": query,
        "sites_searched": len(_sites),
        "sites_matched": len(results),
        "results": results,
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def aggregate(query: str) -> dict:
    """Aggregate info from all sources: registered sites + web search.
    
    This is the main entry point for autonomous research.
    """
    _load_sites()
    
    aggregated = {
        "query": query,
        "sources": [],
        "kind": "MEASURED",
        "ts": now_iso(),
    }

    # 1. Search registered sites
    site_results = search_sites(query)
    if site_results.get("status") == "success" and site_results.get("results"):
        for r in site_results["results"][:5]:
            aggregated["sources"].append({
                "type": "registered_site",
                "name": r["site"],
                "url": r["url"],
                "relevance": r["relevance"],
                "content": " ".join(r.get("snippets", [])),
            })

    # 2. Web search
    try:
        from .websearch import search as web_search
        web_results = web_search(query, max_results=5)
        if web_results.get("status") == "success":
            for r in web_results.get("results", []):
                aggregated["sources"].append({
                    "type": "web_search",
                    "name": r.get("title", ""),
                    "url": r.get("url", ""),
                    "relevance": 0.5,  # Default relevance for web results
                    "content": r.get("snippet", ""),
                })
    except Exception:
        pass

    # Sort by relevance
    aggregated["sources"].sort(key=lambda x: x.get("relevance", 0), reverse=True)
    aggregated["total_sources"] = len(aggregated["sources"])

    return aggregated


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML."""
    html = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_snippets(text: str, terms: list[str], max_snippets: int = 3,
                      context_chars: int = 200) -> list[str]:
    """Extract relevant snippets from text around matching terms."""
    snippets = []
    text_lower = text.lower()

    for term in terms:
        idx = 0
        while idx < len(text_lower) and len(snippets) < max_snippets:
            pos = text_lower.find(term, idx)
            if pos == -1:
                break
            start = max(0, pos - context_chars)
            end = min(len(text), pos + len(term) + context_chars)
            snippet = text[start:end].strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            idx = pos + len(term)

    return snippets[:max_snippets]


def health() -> dict:
    """Site aggregator health."""
    _load_sites()
    return {
        "kind": "MEASURED",
        "n_sites": len(_sites),
        "sites": [{"name": s.get("name"), "url": s.get("url"), "category": s.get("category")}
                  for s in _sites.values()],
        "cache_entries": len(_cache),
        "ts": now_iso(),
    }
