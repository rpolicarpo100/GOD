"""Plane — ferramenta externa. Nunca núcleo. Nunca inventar issues.

API oficial: https://api.plane.so/  header X-API-Key
Docs: https://developers.plane.so/api-reference/introduction

GET /workspaces/{slug}/ devolve 401 neste tenant (MEASURED).
A existência do workspace prova-se por GET /workspaces/{slug}/projects/ 200.
Project path usa UUID, não o identifier GODSX.
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


def _project_ident() -> str:
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
    """MEASURED. Sem board fictício. Issues só se a API as devolver."""
    key = _key()
    slug = _slug()
    ident = _project_ident()
    empty = {
        "kind": "MEASURED",
        "available": False,
        "in_product": False,
        "has_key": bool(key),
        "workspace_slug": slug or None,
        "workspace_found": False,
        "project_id": ident or None,
        "project_uuid": None,
        "project_found": False,
        "issues": None,
        "source": "https://developers.plane.so/api-reference/introduction",
    }
    if not key:
        empty["error"] = "sem PLANE_API_KEY"
        return empty
    st_me, me = _get("/users/me/", key)
    me_ok = st_me == 200 and isinstance(me, dict) and me.get("id")
    if not slug:
        empty["available"] = bool(me_ok)
        empty["me_http"] = st_me
        empty["user_id"] = me.get("id") if me_ok else None
        empty["display_name"] = me.get("display_name") if me_ok else None
        empty["error"] = "sem PLANE_WORKSPACE_SLUG"
        return empty

    st_ws, ws_body = _get(f"/workspaces/{slug}/", key)
    st_pj, pj_body = _get(f"/workspaces/{slug}/projects/", key)
    ws_found = st_pj == 200 and isinstance(pj_body, dict) and "results" in pj_body
    rows = (pj_body.get("results") or []) if ws_found else []
    match = None
    want = (ident or "").lower()
    for p in rows:
        if not isinstance(p, dict):
            continue
        if want and str(p.get("identifier") or "").lower() == want:
            match = p
            break
        if want and str(p.get("id") or "") == ident:
            match = p
            break
        if want and str(p.get("name") or "").lower() == want.lower():
            match = p
            break
    if not match and len(rows) == 1 and isinstance(rows[0], dict):
        match = rows[0]

    proj_found = bool(match and match.get("id"))
    uuid = match.get("id") if proj_found else None
    issues = None
    if proj_found:
        st_i, items = _get(f"/workspaces/{slug}/projects/{uuid}/work-items/", key)
        if st_i == 200 and isinstance(items, dict):
            results = items.get("results") if isinstance(items.get("results"), list) else []
            issues = {
                "kind": "MEASURED",
                "n": int(items.get("total_count") if items.get("total_count") is not None else len(results)),
                "items": [
                    {
                        "id": it.get("id"),
                        "sequence_id": it.get("sequence_id"),
                        "name": it.get("name"),
                        "priority": it.get("priority"),
                    }
                    for it in results[:20]
                    if isinstance(it, dict)
                ],
            }

    ws_error = None
    if not ws_found:
        if isinstance(pj_body, dict):
            ws_error = pj_body.get("error") or pj_body.get("detail") or f"projects HTTP {st_pj}"
        else:
            ws_error = f"projects HTTP {st_pj} {pj_body}"

    return {
        "kind": "MEASURED",
        "available": bool(me_ok and ws_found),
        "in_product": False,
        "has_key": True,
        "user_id": (me.get("id") if isinstance(me, dict) else None) if me_ok else None,
        "display_name": (me.get("display_name") if isinstance(me, dict) else None) if me_ok else None,
        "me_http": st_me,
        "workspace_slug": slug,
        "workspace_http": st_ws,
        "workspace_found": ws_found,
        "workspace_error": ws_error,
        "workspace_note": "GET /workspaces/{slug}/ 401 neste tenant; projects/ 200 prova o workspace",
        "project_id": ident or None,
        "project_uuid": uuid,
        "project_name": (match.get("name") if match else None),
        "project_identifier": (match.get("identifier") if match else None),
        "project_found": proj_found,
        "issues": issues,
        "error": None if me_ok else (me if isinstance(me, str) else f"users/me HTTP {st_me}"),
        "note": "Plane é ferramenta externa. Sem núcleo GOD. Sem issues inventadas.",
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


def reset_cache() -> None:
    global _cache, _cache_t
    _cache, _cache_t = None, 0.0
