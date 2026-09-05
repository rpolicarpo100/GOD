"""Cohere Rerank — search result reranking.

Uses Cohere's rerank API to improve search quality.
Trial key: 1000 calls/month.

Features:
- Rerank search results by relevance
- Fallback to original order if API unavailable
- Usage tracking
- Rate limiting (1000/month)
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .config import cfg
from .util import now_iso

# ═══════════════════════════════
# CONFIGURATION
# ═══════════════════════════════

COHERE_API_URL = "https://api.cohere.ai/v1/rerank"
MAX_CALLS_PER_MONTH = 1000
DEFAULT_MODEL = "rerank-english-v3.0"
DEFAULT_TOP_K = 5


class CohereReranker:
    """Cohere rerank integration."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._api_key: str | None = None
        self._usage = {
            "calls": 0,
            "month_start": None,
            "errors": 0,
        }
        self._initialized = False
    
    def _ensure_init(self):
        """Lazy initialization."""
        if self._initialized:
            return
        
        # Try to get API key from config
        self._api_key = cfg.get("cohere_api_key") or cfg.get("COHERE_API_KEY")
        self._initialized = True
    
    def available(self) -> bool:
        """Check if Cohere rerank is available."""
        self._ensure_init()
        
        if not self._api_key:
            return False
        
        # Check monthly limit
        with self._lock:
            if self._usage["month_start"]:
                # Reset if new month
                now = time.time()
                if now - self._usage["month_start"] >30 * 24 * 3600:
                    self._usage["calls"] = 0
                    self._usage["month_start"] = now
            
            if self._usage["calls"] >= MAX_CALLS_PER_MONTH:
                return False
        
        return True
    
    def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = DEFAULT_TOP_K,
        model: str = DEFAULT_MODEL,
    ) -> dict:
        """Rerank documents by relevance to query.
        
        Returns: {results, usage, kind}
        """
        if not self.available():
            return {
                "kind": "MEASURED",
                "available": False,
                "results": [
                    {"index": i, "text": doc, "score": 1.0 - (i * 0.1)}
                    for i, doc in enumerate(documents[:top_k])
                ],
                "fallback": True,
            }
        
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "query": query,
                "documents": documents,
                "top_n": top_k,
                "model": model,
            }
            
            response = requests.post(
                COHERE_API_URL,
                headers=headers,
                json=payload,
                timeout=10,
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for r in data.get("results", []):
                    results.append({
                        "index": r.get("index", 0),
                        "text": documents[r.get("index", 0)] if r.get("index", 0) < len(documents) else "",
                        "score": r.get("relevance_score", 0),
                    })
                
                with self._lock:
                    self._usage["calls"] += 1
                    if not self._usage["month_start"]:
                        self._usage["month_start"] = time.time()
                
                return {
                    "kind": "MEASURED",
                    "available": True,
                    "results": results,
                    "usage": self._usage["calls"],
                    "limit": MAX_CALLS_PER_MONTH,
                }
            else:
                with self._lock:
                    self._usage["errors"] += 1
                
                return {
                    "kind": "MEASURED",
                    "available": False,
                    "error": f"API error: {response.status_code}",
                    "results": [
                        {"index": i, "text": doc, "score": 1.0 - (i * 0.1)}
                        for i, doc in enumerate(documents[:top_k])
                    ],
                    "fallback": True,
                }
                
        except Exception as e:
            with self._lock:
                self._usage["errors"] += 1
            
            return {
                "kind": "MEASURED",
                "available": False,
                "error": str(e),
                "results": [
                    {"index": i, "text": doc, "score": 1.0 - (i * 0.1)}
                    for i, doc in enumerate(documents[:top_k])
                ],
                "fallback": True,
            }
    
    def get_usage(self) -> dict:
        """Get usage statistics."""
        with self._lock:
            return {
                "kind": "MEASURED",
                "available": self.available(),
                "calls": self._usage["calls"],
                "limit": MAX_CALLS_PER_MONTH,
                "remaining": MAX_CALLS_PER_MONTH - self._usage["calls"],
                "errors": self._usage["errors"],
                "month_start": self._usage["month_start"],
            }
    
    def format_usage(self) -> str:
        """Format usage for display."""
        usage = self.get_usage()
        
        lines = [
            f"Cohere Rerank: {'Available' if usage['available'] else 'Unavailable'}",
            f"Calls: {usage['calls']}/{usage['limit']}",
            f"Remaining: {usage['remaining']}",
            f"Errors: {usage['errors']}",
        ]
        
        return "\n".join(lines)


# Global reranker instance
_reranker = CohereReranker()


def get_reranker() -> CohereReranker:
    """Get the global Cohere reranker."""
    return _reranker


def rerank(
    query: str,
    documents: list[str],
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """Rerank documents by relevance to query."""
    return _reranker.rerank(query, documents, top_k)


def available() -> bool:
    """Check if Cohere rerank is available."""
    return _reranker.available()


def usage() -> dict:
    """Get usage statistics."""
    return _reranker.get_usage()
