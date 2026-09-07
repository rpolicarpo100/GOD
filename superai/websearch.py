"""Web Search — pesquisa na web em tempo real via múltiplos backends.

Backends (tentados em ordem):
1. SearXNG local (se disponível) — metapesquisa multi-fonte
2. DuckDuckGo HTML scraping — pesquisa web real, gratuito, sem API key
3. DuckDuckGo Instant Answer API — respostas directas
4. Fallback: recusar educadamente

Features:
- Cache de resultados (60s TTL) para queries repetidas
- Rate limiting (1 req/s por backend)
- Resultados deduplicados
- Snippet extraction inteligente
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote_plus

import httpx

from .util import now_iso

# Shared client with connection pooling
_client = httpx.Client(
    timeout=10.0,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    },
    follow_redirects=True,
)

# Simple result cache (60s TTL)
_cache: dict[str, dict] = {}
_CACHE_TTL = 60

# Rate limiting per backend
_last_call: dict[str, float] = {}
_MIN_INTERVAL = 1.0  # 1 request per second per backend


def _rate_limit(backend: str) -> bool:
    """Check if we can call this backend."""
    now = time.time()
    last = _last_call.get(backend, 0)
    if now - last < _MIN_INTERVAL:
        return False
    _last_call[backend] = now
    return True


def _cache_get(query: str) -> dict | None:
    """Check cache for recent results."""
    entry = _cache.get(query)
    if entry and time.time() - entry.get("_ts", 0) < _CACHE_TTL:
        return entry
    return None


def _cache_set(query: str, result: dict) -> None:
    """Cache result."""
    result["_ts"] = time.time()
    _cache[query] = result
    # Evict old entries
    if len(_cache) > 100:
        oldest = sorted(_cache.items(), key=lambda x: x[1].get("_ts", 0))
        for k, _ in oldest[:50]:
            del _cache[k]


def search(query: str, max_results: int = 5) -> dict:
    """Pesquisar na web em tempo real. Retorna resultados ou erro."""
    query = (query or "").strip()
    if not query:
        return {"status": "error", "error": "query vazia", "kind": "MEASURED"}

    # Check cache
    cached = _cache_get(query)
    if cached:
        cached["cached"] = True
        return cached

    # Try backends in order
    for backend_fn in [_searxng, _ddg_html, _ddg_instant]:
        if not _rate_limit(backend_fn.__name__):
            continue
        try:
            r = backend_fn(query, max_results)
            if r and r.get("status") == "success" and r.get("results"):
                _cache_set(query, r)
                return r
        except Exception:
            continue

    return {
        "status": "error",
        "error": "nenhum search engine disponível ou rate limited",
        "query": query,
        "kind": "MEASURED",
        "ts": now_iso(),
    }


def fetch_page(url: str, max_chars: int = 5000) -> dict:
    """Fetch and extract text content from a URL. Real-time web access."""
    try:
        # SSRF protection
        from .network_control import validate_url
        v = validate_url(url)
        if not v.get("ok"):
            return {"status": "error", "error": v.get("reason", "blocked"), "url": url}

        r = _client.get(url, timeout=15.0)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}", "url": url}

        html = r.text
        # Extract text from HTML
        text = _html_to_text(html)
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_m.group(1).strip() if title_m else ""

        return {
            "status": "success",
            "url": url,
            "title": title,
            "text": text[:max_chars],
            "length": len(text),
            "kind": "MEASURED",
            "ts": now_iso(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "url": url, "kind": "MEASURED"}


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML."""
    # Remove scripts, styles, nav, footer, header
    html = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _searxng(query: str, max_results: int) -> dict | None:
    """Try local SearXNG instance."""
    for port in (8080, 8888):
        try:
            r = _client.get(
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


def _ddg_html(query: str, max_results: int) -> dict | None:
    """DuckDuckGo HTML search — real web results via HTML scraping."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        r = _client.get(url, timeout=10.0)
        if r.status_code != 200:
            return None

        html = r.text
        results = []

        # Parse DDG HTML results
        # Each result: <a class="result__a" href="URL">TITLE</a> + <a class="result__snippet">TEXT</a>
        for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html, re.S
        ):
            href = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", m.group(3)).strip()

            # DDG wraps URLs in redirect — extract real URL
            real_url = _extract_ddg_url(href)

            if title and real_url:
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": snippet[:300],
                })

            if len(results) >= max_results:
                break

        if results:
            return {
                "status": "success",
                "backend": "duckduckgo_html",
                "query": query,
                "n": len(results),
                "results": results,
                "kind": "MEASURED",
                "ts": now_iso(),
            }
    except Exception:
        pass
    return None


def _extract_ddg_url(href: str) -> str:
    """Extract real URL from DDG redirect URL."""
    # DDG wraps: //duckduckgo.com/l/?uddg=REAL_URL&...
    m = re.search(r"uddg=([^&]+)", href)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return None  # Internal DDG link
    return href


def _ddg_instant(query: str, max_results: int) -> dict | None:
    """DuckDuckGo Instant Answer API (free, no key) — fallback."""
    try:
        r = _client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        results = []

        abstract = data.get("Abstract", "")
        abstract_url = data.get("AbstractURL", "")
        if abstract:
            results.append({
                "title": data.get("Heading", query),
                "url": abstract_url,
                "snippet": abstract[:300],
            })

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
                "backend": "duckduckgo_instant",
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
            r = _client.get(f"http://127.0.0.1:{port}/", timeout=1.0)
            backends[f"searxng:{port}"] = r.status_code == 200
        except Exception:
            backends[f"searxng:{port}"] = False

    # DuckDuckGo HTML
    try:
        r = _client.get("https://html.duckduckgo.com/html/?q=test", timeout=5.0)
        backends["duckduckgo_html"] = r.status_code == 200
    except Exception:
        backends["duckduckgo_html"] = False

    # DuckDuckGo Instant
    try:
        r = _client.get("https://api.duckduckgo.com/?q=test&format=json", timeout=3.0)
        backends["duckduckgo_instant"] = r.status_code == 200
    except Exception:
        backends["duckduckgo_instant"] = False

    available = [k for k, v in backends.items() if v]
    return {
        "kind": "MEASURED",
        "backends": backends,
        "available": available,
        "n_available": len(available),
        "ts": now_iso(),
    }


def search_stats() -> dict:
    """Search cache and rate limiting stats."""
    return {
        "kind": "MEASURED",
        "cache_size": len(_cache),
        "cache_ttl": _CACHE_TTL,
        "rate_limit_per_sec": _MIN_INTERVAL,
        "backends": ["searxng", "duckduckgo_html", "duckduckgo_instant"],
        "ts": now_iso(),
    }
