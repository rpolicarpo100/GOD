"""Autonomous Research — GOD decides when to search, fetch, and analyze.

Instead of waiting for user to say "pesquisa na web", GOD autonomously:
1. Detects when it doesn't know the answer
2. Searches the web + registered sites
3. Fetches relevant pages
4. Synthesizes results into a coherent answer

Triggers:
- LLM says "não sei" / "não tenho informação" / "não disponho"
- LLM response is very short (< 50 chars) for complex queries
- Self-reflection score < 0.5
- Query contains temporal markers ("hoje", "agora", "recente", "atual", "preço")
- Query is about facts that change (news, prices, weather, versions)
"""
from __future__ import annotations

import re
import time
from typing import Any

from .events import bus
from .util import now_iso

# Patterns that indicate GOD doesn't know
_DONT_KNOW_PATTERNS = [
    r"não (sei|tenho|disponho|possuo|conheço)",
    r"não (tenho|possuo) (informação|dados|acesso)",
    r"não (me recordo|me lembro)",
    r"não (é algo que|tenho como)",
    r"(desculpa|lamento).*(não|não sei|não consigo)",
    r"informação (não )?(disponível|acessível)",
    r"sem (acesso|informação|dados)",
    r"my (knowledge|training).*(cutoff|limited|doesn't)",
    r"i (don't|do not) (know|have|possess)",
    r"as (of|an) (my|ai).*(cutoff|training|knowledge)",
]

# Temporal markers — facts that need real-time data
_TEMPORAL_MARKERS = [
    r"hoje|hj|agora|atual(mente)?|recente",
    r"preço|cotação|valor (do|da|de)",
    r"notícia|novidade|acontec|noticias",
    r"versão (do|da|mais)",
    r"como est[aá]|qual o estado",
    r"disponível (agora|hoje|hoje em dia)",
    r"último|última|mais novo|mais recente",
    r"today|now|current|latest|recent|price",
    r"o que (está|esta) a (acontecer|passar)",
    r"o que se (passa|passou)",
    r"quais (as|os) (notícias|novidades)",
    r"what.*(happening|going on|latest news)",
]


def should_research(query: str, llm_response: str = "", quality_score: float = 1.0) -> dict:
    """Decide if GOD should autonomously research this query.
    
    Returns: {should: bool, reason: str, strategy: str}
    """
    query_lower = query.lower().strip()
    response_lower = (llm_response or "").lower().strip()

    # 1. LLM explicitly says it doesn't know
    for pattern in _DONT_KNOW_PATTERNS:
        if re.search(pattern, response_lower):
            return {
                "should": True,
                "reason": "LLM indica que não sabe — vou pesquisar",
                "strategy": "web_search",
                "confidence": 0.9,
            }

    # 2. Quality score too low (self-reflection)
    if quality_score < 0.5 and len(query) > 10:
        return {
            "should": True,
            "reason": f"Qualidade baixa ({quality_score:.2f}) — vou pesquisar para melhorar",
            "strategy": "web_search",
            "confidence": 0.8,
        }

    # 3. Temporal markers — need real-time data
    for pattern in _TEMPORAL_MARKERS:
        if re.search(pattern, query_lower):
            return {
                "should": True,
                "reason": "Pedido temporal — precisa de dados em tempo real",
                "strategy": "web_search",
                "confidence": 0.85,
            }

    # 4. Very short LLM response for complex query
    if len(llm_response) < 50 and len(query) > 30:
        return {
            "should": True,
            "reason": "Resposta muito curta para pedido complexo",
            "strategy": "web_search",
            "confidence": 0.7,
        }

    # 5. Query about specific facts, names, versions
    if re.search(r"\b(que (é|e|são)|o que (é|e|são)|quem (é|foi)|quando (foi|é|aconteceu))\b", query_lower):
        if len(query) > 20:
            return {
                "should": True,
                "reason": "Pedido factual — vou verificar na web",
                "strategy": "web_search",
                "confidence": 0.6,
            }

    return {"should": False, "reason": "Não preciso de pesquisar", "strategy": "none", "confidence": 0.0}


async def autonomous_research(query: str, strategy: str = "web_search") -> dict:
    """Execute autonomous research.
    
    Strategy:
    - "web_search": search web + registered sites
    - "deep_research": fetch top results + extract key info
    - "site_specific": search only registered sites
    """
    bus.emit("RESEARCH_START", "INFO", f"autonomous research: {query[:60]}", god_core_state="researching")

    results = {
        "query": query,
        "strategy": strategy,
        "findings": [],
        "sources": [],
        "ts": now_iso(),
    }

    # 1. Search registered sites first
    try:
        from .site_aggregator import search_sites, aggregate
        agg = aggregate(query)
        if agg.get("sources"):
            for src in agg["sources"][:5]:
                results["findings"].append({
                    "source": src.get("name", ""),
                    "url": src.get("url", ""),
                    "content": src.get("content", "")[:500],
                    "type": src.get("type", ""),
                })
                results["sources"].append(src.get("url", ""))
    except Exception:
        pass

    # 2. News search (always for temporal/factual queries)
    try:
        from .news_connector import search_news, format_for_llm
        news = search_news(query, limit=5)
        if news.get("status") == "success" and news.get("results"):
            news_context = format_for_llm(news)
            if news_context:
                results["findings"].append({
                    "source": "Global News Intelligence",
                    "url": "https://news-ai-agreger.onrender.com",
                    "content": news_context,
                    "type": "news_intelligence",
                    "confidence": 0.85,
                })
                results["sources"].append("https://news-ai-agreger.onrender.com")
    except Exception:
        pass

    # 3. Web search
    try:
        from .websearch import search as web_search, fetch_page
        web = web_search(query, max_results=5)
        if web.get("status") == "success":
            for r in web.get("results", [])[:3]:
                # Fetch full page for top results
                if strategy == "deep_research" and r.get("url"):
                    page = fetch_page(r["url"])
                    if page.get("status") == "success":
                        results["findings"].append({
                            "source": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": page.get("text", "")[:1000],
                            "type": "web_page",
                        })
                        results["sources"].append(r["url"])
                        continue
                results["findings"].append({
                    "source": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("snippet", ""),
                    "type": "web_search",
                })
                results["sources"].append(r.get("url", ""))
    except Exception:
        pass

    results["total_findings"] = len(results["findings"])
    results["kind"] = "MEASURED"

    bus.emit("RESEARCH_DONE", "INFO",
             f"found {results['total_findings']} sources for: {query[:40]}",
             god_core_state="ready")

    return results


def format_research_for_llm(research: dict) -> str:
    """Format research results as context for LLM."""
    if not research.get("findings"):
        return ""

    lines = ["INFORMAÇÃO PESQUISADA NA WEB:"]
    for i, f in enumerate(research["findings"][:5], 1):
        lines.append(f"\n--- Fonte {i}: {f.get('source', 'N/A')} ---")
        if f.get("url"):
            lines.append(f"URL: {f['url']}")
        lines.append(f.get("content", "")[:500])

    lines.append("\n--- FIM DA PESQUISA ---")
    lines.append("Usa esta informação para responder ao utilizador. Cita as fontes quando relevante.")
    return "\n".join(lines)
