"""Plane — ferramenta externa. Nunca núcleo. Nunca inventar issues.

API oficial: https://api.plane.so/  header X-API-Key
Docs: https://developers.plane.so/api-reference/introduction
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from .config import load_dotenv

load_dotenv()

BASE = "https://api.plane.so/api/v1"


def _key() -> str:
    return (os.environ.get("PLANE_API_KEY") or "").strip()


def _slug() -> str:
    return (os.environ.get("PLANE_WORKSPACE_SLUG") or "").strip()


def _project() -> str:
    return (os.environ.get("PLANE_PROJECT_ID") or "").strip()


def _get(path: str, key: str) -> tuple[int | None, Any]:
    url = f"{BASE}{path}"
    try:
        r = httpx.get(url, headers={"X-API-Key": key, "Accept": "application/json"}, timeout=12.0)
        try:
            body = r.json()
        except Exception:
            body = (r.text or "")[:300]
        return r.status_code, body
    except Exception as e:
        return None, str(e)[:200]


def probe() -> dict:
    """MEASURED. Sem board se workspace 404. Sem PII no snapshot."""
    key = _key()
    slug = _slug()
    project = _project()
    if not key:
        return {
            "kind": "MEASURED",
            "available": False,
            "in_product": False,
            "has_key": False,
            "workspace_slug": slug or None,
            "workspace_found": False,
            "project_id": project or None,
            "project_found": False,
            "issues": None,
            "error": "sem PLANE_API_KEY",
            "source": "https://developers.plane.so/api-reference/introduction",
        }
    st_me, me = _get("/users/me/", key)
    me_ok = st_me == 200 and isinstance(me, dict) and me.get("id")
    ws_found = False
    ws_error = None
    st_ws = None
    if slug:
        st_ws, ws = _get(f"/workspaces/{slug}/", key)
        if st_ws == 200 and isinstance(ws, dict) and (ws.get("id") or ws.get("slug")):
            ws_found = True
        else:
            if isinstance(ws, dict):
                ws_error = ws.get("error") or ws.get("detail") or f"HTTP {st_ws}"
            else:
                ws_error = f"HTTP {st_ws} {ws}"
    else:
        ws_error = "sem PLANE_WORKSPACE_SLUG"

    proj_found = False
    issues = None
    if ws_found and project:
        st_p, pj = _get(f"/workspaces/{slug}/projects/{project}/", key)
        if st_p == 200 and isinstance(pj, dict) and pj.get("id"):
            proj_found = True
            st_i, items = _get(f"/workspaces/{slug}/projects/{project}/work-items/", key)
            if st_i == 200 and isinstance(items, dict):
                results = items.get("results")
                issues = {"n": len(results) if isinstance(results, list) else None, "kind": "MEASURED"}
            else:
                issues = None

    return {
        "kind": "MEASURED",
        "available": bool(me_ok),
        "in_product": False,
        "has_key": True,
        "user_id": (me.get("id") if isinstance(me, dict) else None) if me_ok else None,
        "display_name": (me.get("display_name") if isinstance(me, dict) else None) if me_ok else None,
        "me_http": st_me,
        "workspace_slug": slug or None,
        "workspace_http": st_ws,
        "workspace_found": ws_found,
        "workspace_error": ws_error,
        "project_id": project or None,
        "project_found": proj_found,
        "issues": issues,
        "error": None if me_ok else (me if isinstance(me, str) else f"users/me HTTP {st_me}"),
        "note": "Plane é ferramenta externa. Sem workspace encontrado não há board no produto.",
        "source": "https://developers.plane.so/api-reference/introduction",
    }


_cache: dict | None = None
_cache_t = 0.0


def status() -> dict:
    """Probe com TTL 60s — snapshot SSE não bate a API a cada frame."""
    global _cache, _cache_t
    now = time.time()
    if _cache is not None and now - _cache_t < 60:
        return _cache
    _cache = probe()
    _cache_t = now
    return _cache
