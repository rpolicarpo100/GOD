from __future__ import annotations

import os
import socket
import time
from typing import Any

import httpx


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class Provider:
    id: str
    name: str
    kind: str  # local | premium | api

    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        raise NotImplementedError


class OllamaAdapter(Provider):
    id = "ollama"
    name = "Ollama"
    kind = "local"

    def health(self) -> dict[str, Any]:
        open_ = _port_open("127.0.0.1", 11434)
        models: list[str] = []
        err = None
        if open_:
            try:
                r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
                if r.status_code == 200:
                    models = [m.get("name") for m in r.json().get("models", [])]
            except Exception as e:
                err = str(e)
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": bool(open_ and not err),
            "endpoint": "http://127.0.0.1:11434",
            "models": models,
            "error": None if open_ else "porta 11434 fechada — Ollama não está a correr neste host",
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        h = self.health()
        if not h["available"]:
            return {"status": "unavailable", "provider": self.id, "error": h["error"]}
        return {"status": "unavailable", "provider": self.id, "error": "complete() não chamado: sem modelos verificados em runtime"}


class ClaudeAdapter(Provider):
    id = "claude"
    name = "Claude"
    kind = "premium"

    def health(self) -> dict[str, Any]:
        key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": False,
            "endpoint": "api.anthropic.com (não chamado)",
            "models": [],
            "error": "sem credenciais no ambiente — Claude não será chamado",
            "has_key": bool(key),
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        return {"status": "unavailable", "provider": self.id, "error": "sem credenciais — recusa em chamar a API"}


class GeminiAdapter(Provider):
    id = "gemini"
    name = "Gemini"
    kind = "api"

    def health(self) -> dict[str, Any]:
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": False,
            "endpoint": None,
            "models": [],
            "error": "sem credenciais — adapter presente, provider não verificado",
            "has_key": bool(key),
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        return {"status": "unavailable", "provider": self.id, "error": "sem credenciais"}


ADAPTERS: list[Provider] = [OllamaAdapter(), ClaudeAdapter(), GeminiAdapter()]

_hcache: list[dict] | None = None
_ht = 0.0


def health_all() -> list[dict]:
    global _hcache, _ht
    now = time.time()
    if _hcache is not None and now - _ht < 2.0:
        return _hcache
    _hcache = [a.health() for a in ADAPTERS]
    _ht = now
    return _hcache


def any_llm() -> bool:
    return any(h["available"] for h in health_all())
