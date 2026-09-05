"""Model adapters. Keys from env/.env. available=True only after a live probe.

Order: local → cheap API → Claude last. No historical scores invented.
"""
from __future__ import annotations

import os
import socket
import time
from typing import Any

import httpx

from .config import load_dotenv

load_dotenv()

PROBE_TTL = 30.0
_SKIP_CHAT = (
    "guard",
    "safeguard",
    "embed",
    "whisper",
    "tts",
    "moderation",
    "rerank",
    "transcribe",
    "orpheus",
    "prompt-guard",
    "compound",
    "gpt-oss",
    ":batch",
)
_PREFER_CHAT = (
    "instruct",
    "-it",
    "chat",
    "flash",
    "llama",
    "gemma",
    "qwen",
    "mixtral",
    "glm",
    "sonnet",
    "haiku",
    "opus",
    "fable",
)


def is_chat_model(mid: str) -> bool:
    low = (mid or "").lower()
    return bool(low) and not any(s in low for s in _SKIP_CHAT)


def pick_chat_model(models: list[str]) -> str | None:
    """Skip STT/TTS/guard/embed/reasoning-oss. Prefer instruct/chat. Never invent an id."""
    clean = [m for m in models if is_chat_model(m)]
    if not clean:
        return None
    for m in clean:
        low = m.lower()
        if any(p in low for p in _PREFER_CHAT):
            return m
    return clean[0]


def openai_message_text(data: dict) -> str:
    """Visible chat text only. Reasoning/CoT is not GOD speech."""
    ch = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
    msg = ch.get("message") or {}
    raw = msg.get("content")
    if isinstance(raw, list):
        raw = "".join((p.get("text") or "") if isinstance(p, dict) else str(p) for p in raw)
    if not (raw or "").strip():
        raw = ch.get("text") or ""
    return (raw or "").strip()


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


def _key(*names: str) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return ""


class Provider:
    id: str
    name: str
    kind: str

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
                else:
                    err = f"HTTP {r.status_code}"
            except Exception as e:
                err = str(e)[:200]
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": bool(open_ and not err),
            "endpoint": "http://127.0.0.1:11434",
            "models": models[:8],
            "error": None if open_ else "porta 11434 fechada — Ollama local não está a correr",
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        h = self.health()
        if not h["available"]:
            return {"status": "unavailable", "provider": self.id, "error": h["error"]}
        model = kw.get("model") or (h["models"][0] if h["models"] else None)
        if not model:
            return {"status": "unavailable", "provider": self.id, "error": "sem modelos no Ollama local"}
        try:
            r = httpx.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"num_predict": int(kw.get("max_tokens") or 256)},
                },
                timeout=60.0,
            )
            r.raise_for_status()
            data = r.json()
            text = (data.get("message") or {}).get("content") or ""
            return {
                "status": "success",
                "provider": self.id,
                "model": model,
                "text": text,
                "tokens": None,
                "raw_usage": None,
            }
        except Exception as e:
            return {"status": "error", "provider": self.id, "error": str(e)[:300]}


class OpenAICompatAdapter(Provider):
    """OpenAI-compatible chat.completions. Probe GET /models before available=True."""

    def __init__(self, id: str, name: str, env: str, base: str, kind: str = "api", headers: dict | None = None):
        self.id = id
        self.name = name
        self.kind = kind
        self._env = env
        self._base = base.rstrip("/")
        self._extra = headers or {}
        self._probe: dict | None = None
        self._probe_t = 0.0

    def _headers(self) -> dict[str, str]:
        k = _key(self._env)
        h = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
        h.update(self._extra)
        return h

    def health(self) -> dict[str, Any]:
        k = _key(self._env)
        if not k:
            return {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "available": False,
                "endpoint": self._base,
                "models": [],
                "error": f"sem {self._env}",
                "has_key": False,
                "verified": True,
                "historical_score": None,
                "samples": 0,
            }
        now = time.time()
        if self._probe is not None and now - self._probe_t < PROBE_TTL:
            return self._probe
        models: list[str] = []
        err = None
        try:
            r = httpx.get(f"{self._base}/models", headers=self._headers(), timeout=8.0)
            if r.status_code == 200:
                data = r.json()
                rows = data.get("data") or data.get("models") or []
                for m in rows:
                    mid = m.get("id") or m.get("name") if isinstance(m, dict) else None
                    if mid and is_chat_model(str(mid)):
                        models.append(str(mid))
                    if len(models) >= 8:
                        break
            else:
                err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:200]
        rec = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": bool(k and not err and models),
            "endpoint": self._base,
            "models": models,
            "error": err,
            "has_key": True,
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }
        self._probe, self._probe_t = rec, now
        return rec

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        h = self.health()
        if not h["available"]:
            return {"status": "unavailable", "provider": self.id, "error": h.get("error")}
        model = kw.get("model") or pick_chat_model(h.get("models") or [])
        if not model:
            return {"status": "unavailable", "provider": self.id, "error": "sem model de chat (só guard/whisper/tts)"}
        try:
            r = httpx.post(
                f"{self._base}/chat/completions",
                headers=self._headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": int(kw.get("max_tokens") or 256),
                },
                timeout=12.0,
            )
            r.raise_for_status()
            data = r.json()
            text = openai_message_text(data)
            usage = data.get("usage") or {}
            total = usage.get("total_tokens")
            if total is None:
                it, ot = usage.get("prompt_tokens"), usage.get("completion_tokens")
                if it is not None and ot is not None:
                    total = int(it) + int(ot)
            if not text:
                return {
                    "status": "error",
                    "provider": self.id,
                    "adapter": self.id,
                    "model": model,
                    "text": "",
                    "tokens": total,
                    "raw_usage": usage if usage else None,
                    "error": "resposta vazia — content null (reasoning comeu o budget)",
                }
            return {
                "status": "success",
                "provider": self.id,
                "adapter": self.id,
                "model": model,
                "text": text,
                "tokens": total,
                "raw_usage": usage if usage else None,
            }
        except Exception as e:
            return {"status": "error", "provider": self.id, "error": str(e)[:300]}


class ClaudeAdapter(Provider):
    id = "claude"
    name = "Claude"
    kind = "premium"
    _probe: dict | None = None
    _probe_t = 0.0

    def health(self) -> dict[str, Any]:
        key = _key("ANTHROPIC_API_KEY", "CLAUDE_API_KEY")
        if not key:
            return {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "available": False,
                "endpoint": "https://api.anthropic.com/v1",
                "models": [],
                "error": "sem ANTHROPIC_API_KEY",
                "has_key": False,
                "verified": True,
                "historical_score": None,
                "samples": 0,
            }
        now = time.time()
        if self._probe is not None and now - self._probe_t < PROBE_TTL:
            return self._probe
        models: list[str] = []
        err = None
        try:
            r = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                timeout=8.0,
            )
            if r.status_code == 200:
                for m in r.json().get("data") or []:
                    if m.get("id"):
                        models.append(m["id"])
                    if len(models) >= 8:
                        break
            else:
                err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:200]
        rec = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": bool(not err and models),
            "endpoint": "https://api.anthropic.com/v1/messages",
            "models": models,
            "error": err,
            "has_key": True,
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }
        self._probe, self._probe_t = rec, now
        return rec

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        key = _key("ANTHROPIC_API_KEY", "CLAUDE_API_KEY")
        h = self.health()
        if not h["available"] or not key:
            return {"status": "unavailable", "provider": self.id, "error": h.get("error") or "sem credenciais"}
        model = kw.get("model") or (h["models"][0] if h["models"] else "claude-sonnet-4-5")
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": int(kw.get("max_tokens") or 256),
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=12.0,
            )
            r.raise_for_status()
            data = r.json()
            parts = data.get("content") or []
            text = "".join(p.get("text") or "" for p in parts if isinstance(p, dict)).strip()
            usage = data.get("usage") or {}
            total = None
            if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
                total = int(usage["input_tokens"]) + int(usage["output_tokens"])
            if not text:
                return {
                    "status": "error",
                    "provider": self.id,
                    "adapter": self.id,
                    "model": data.get("model") or model,
                    "text": "",
                    "tokens": total,
                    "error": "resposta vazia claude",
                }
            return {
                "status": "success",
                "provider": self.id,
                "adapter": self.id,
                "model": data.get("model") or model,
                "text": text,
                "tokens": total,
                "raw_usage": usage or None,
            }
        except Exception as e:
            return {"status": "error", "provider": self.id, "error": str(e)[:300]}


class GeminiAdapter(Provider):
    id = "gemini"
    name = "Gemini"
    kind = "api"
    _probe: dict | None = None
    _probe_t = 0.0

    def health(self) -> dict[str, Any]:
        key = _key("GOOGLE_API_KEY", "GEMINI_API_KEY")
        if not key:
            return {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "available": False,
                "endpoint": "generativelanguage.googleapis.com",
                "models": [],
                "error": "sem GOOGLE_API_KEY",
                "has_key": False,
                "verified": True,
                "historical_score": None,
                "samples": 0,
            }
        now = time.time()
        if self._probe is not None and now - self._probe_t < PROBE_TTL:
            return self._probe
        models: list[str] = []
        err = None
        try:
            r = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": key},
                timeout=8.0,
            )
            if r.status_code == 200:
                for m in r.json().get("models") or []:
                    name = (m.get("name") or "").split("/")[-1]
                    methods = m.get("supportedGenerationMethods") or []
                    if name and is_chat_model(name) and (not methods or "generateContent" in methods):
                        models.append(name)
                    if len(models) >= 8:
                        break
            else:
                err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:200]
        rec = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "available": bool(not err and models),
            "endpoint": "https://generativelanguage.googleapis.com/v1beta",
            "models": models,
            "error": err,
            "has_key": True,
            "verified": True,
            "historical_score": None,
            "samples": 0,
        }
        self._probe, self._probe_t = rec, now
        return rec

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        key = _key("GOOGLE_API_KEY", "GEMINI_API_KEY")
        h = self.health()
        if not h["available"] or not key:
            return {"status": "unavailable", "provider": self.id, "error": h.get("error")}
        model = kw.get("model") or next((m for m in h["models"] if "flash" in m), None) or h["models"][0]
        try:
            r = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": key},
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": int(kw.get("max_tokens") or 256)}},
                timeout=12.0,
            )
            r.raise_for_status()
            data = r.json()
            cands = data.get("candidates") or []
            text = ""
            if cands:
                parts = ((cands[0].get("content") or {}).get("parts")) or []
                text = "".join(p.get("text") or "" for p in parts)
            usage = data.get("usageMetadata") or {}
            total = usage.get("totalTokenCount")
            if not (text or "").strip():
                return {
                    "status": "error",
                    "provider": self.id,
                    "adapter": self.id,
                    "model": model,
                    "text": "",
                    "tokens": int(total) if total is not None else None,
                    "error": "resposta vazia gemini",
                }
            return {
                "status": "success",
                "provider": self.id,
                "adapter": self.id,
                "model": model,
                "text": text,
                "tokens": int(total) if total is not None else None,
                "raw_usage": usage or None,
            }
        except Exception as e:
            return {"status": "error", "provider": self.id, "error": str(e)[:300]}


# LLM-last among providers: local → fast API → Claude premium last.
ADAPTERS: list[Provider] = [
    OllamaAdapter(),
    OpenAICompatAdapter("groq", "Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    OpenAICompatAdapter("cerebras", "Cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1"),
    GeminiAdapter(),
    OpenAICompatAdapter(
        "openrouter",
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1",
        headers={"HTTP-Referer": "https://github.com/rpolicarpo100/GOD", "X-Title": "GOD"},
    ),
    OpenAICompatAdapter("inference", "Inference.net", "INFERENCE_API_KEY", "https://api.inference.net/v1"),
    OpenAICompatAdapter("zai", "Z.ai", "ZAI_API_KEY", "https://api.z.ai/api/paas/v4"),
    OpenAICompatAdapter("nvidia", "NVIDIA NIM", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
    OpenAICompatAdapter("sambanova", "SambaNova", "SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1"),
    OpenAICompatAdapter("mistral", "Mistral AI", "MISTRAL_API_KEY", "https://api.mistral.ai/v1"),
    ClaudeAdapter(),
]

_hcache: list[dict] | None = None
_ht = 0.0


def health_all() -> list[dict]:
    global _hcache, _ht
    now = time.time()
    if _hcache is not None and now - _ht < 5.0:
        return _hcache
    _hcache = [a.health() for a in ADAPTERS]
    _ht = now
    return _hcache


def any_llm() -> bool:
    return any(h["available"] for h in health_all())
