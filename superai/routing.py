"""RoutingAdapter — Intelligent Router decides; this layer only executes.

OmniRoute (npm, :20128) is optional upstream. If absent, DirectAdapter
fails over our ModelAdapters. Core never talks to a provider SDK directly.
"""
from __future__ import annotations

import socket
from typing import Any

import httpx

from . import providers

OMNI_HOST = "127.0.0.1"
OMNI_PORT = 20128
OMNI_BASE = f"http://{OMNI_HOST}:{OMNI_PORT}/v1"


def _port(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.25)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class RoutingAdapter:
    id: str

    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        raise NotImplementedError


class OmniRouteAdapter(RoutingAdapter):
    id = "omniroute"

    def health(self) -> dict[str, Any]:
        up = _port(OMNI_HOST, OMNI_PORT)
        models: list[str] = []
        err = None
        if up:
            try:
                r = httpx.get(f"{OMNI_BASE}/models", timeout=1.0)
                if r.status_code == 200:
                    models = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
                else:
                    err = f"HTTP {r.status_code}"
            except Exception as e:
                err = str(e)
        else:
            err = "porta 20128 fechada — processo OmniRoute (npm) não está a correr"
        return {
            "id": self.id,
            "name": "OmniRoute",
            "kind": "gateway",
            "available": bool(up and err is None),
            "endpoint": OMNI_BASE,
            "models": models,
            "error": err,
            "verified": True,
            "role": "executor abaixo do Intelligent Router",
        }

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        h = self.health()
        if not h["available"]:
            return {"status": "unavailable", "adapter": self.id, "error": h["error"]}
        model = kw.get("model") or (h["models"][0] if h["models"] else "default")
        try:
            r = httpx.post(
                f"{OMNI_BASE}/chat/completions",
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": int(kw.get("max_tokens") or 256)},
                timeout=30.0,
            )
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return {
                "status": "success",
                "adapter": self.id,
                "model": model,
                "text": text,
                "tokens": usage.get("total_tokens"),
                "raw_usage": usage,
            }
        except Exception as e:
            return {"status": "error", "adapter": self.id, "error": str(e)}


class DirectAdapter(RoutingAdapter):
    """Fallback when OmniRoute is down — still goes through ModelAdapters."""

    id = "direct"

    def health(self) -> dict[str, Any]:
        hs = providers.health_all()
        any_up = any(h["available"] for h in hs)
        return {
            "id": self.id,
            "name": "DirectRoutingAdapter",
            "kind": "gateway",
            "available": any_up,
            "endpoint": "in-process ModelAdapter",
            "models": [h["id"] for h in hs if h["available"]],
            "error": None if any_up else "nenhum ModelAdapter available",
            "verified": True,
            "role": "substituto do OmniRoute",
            "upstreams": hs,
        }

    def complete(self, prompt: str, **kw: Any) -> dict[str, Any]:
        prefer = kw.get("prefer")
        order = list(providers.ADAPTERS)
        if prefer:
            order = sorted(order, key=lambda a: 0 if a.id == prefer else 1)
        last = None
        for a in order:
            h = a.health()
            if not h["available"]:
                last = {"adapter": a.id, "error": h.get("error")}
                continue
            res = a.complete(prompt, **kw)
            if res.get("status") == "success":
                return res
            last = res
        return {"status": "unavailable", "adapter": self.id, "error": "todos os upstreams falharam", "last": last}


omni = OmniRouteAdapter()
direct = DirectAdapter()


def active_gateway() -> RoutingAdapter:
    h = omni.health()
    if h["available"]:
        return omni
    return direct


def health() -> dict:
    o, d = omni.health(), direct.health()
    act = omni if o["available"] else direct
    return {"active": act.id, "omniroute": o, "direct": d}


def complete(prompt: str, **kw: Any) -> dict[str, Any]:
    o = omni.health()
    act = omni if o["available"] else direct
    res = act.complete(prompt, **kw)
    res["gateway"] = act.id
    res["fallback"] = act.id == "direct" and not o["available"]
    res["retry_count"] = int(kw.get("retry_count") or 0)
    return res
