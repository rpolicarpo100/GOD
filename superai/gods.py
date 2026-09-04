"""GOD Builder — perfis reais, um handle.

Um GOD = nome + propósito + personalidade + subset das ferramentas que já existem.
Não é um segundo runtime. Não é swarm. Não é Desktop Windows. models='auto' (o router decide).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import DATA
from .util import now_iso

DIR = DATA / "gods"
ACTIVE = DIR / "active"
MAX_GODS = 12
MAX_RULES = 800
BANNED = ("desligar o governor", "alterar o governor", "remover limites")


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", (s or "").lower()).strip("-")[:40]
    return s or "god"


def tool_names() -> list[str]:
    from .tools import TOOLS

    return list(TOOLS)


def ensure() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    p = DIR / "master.json"
    if not p.exists():
        body = {
            "id": "master",
            "name": "GOD",
            "version": 1,
            "owner": "local",
            "purpose": "Compreender o objectivo e produzir a melhor solução verificável.",
            "personality": "Feminino. Directa. Analítica. Não inventa.",
            "capabilities": tool_names(),
            "models": "auto",
            "memory": True,
            "rules": "",
            "status": "ready",
            "created": now_iso(),
            "updated": now_iso(),
        }
        p.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    if not ACTIVE.exists():
        ACTIVE.write_text("master", encoding="utf-8")


def _path(gid: str) -> Path:
    gid = _slug(gid)
    p = (DIR / f"{gid}.json").resolve()
    if p.parent != DIR.resolve():
        raise ValueError("path recusado")
    return p


def get(gid: str) -> dict | None:
    ensure()
    p = _path(gid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_gods() -> list[dict]:
    ensure()
    aid = active_id()
    out = []
    for p in sorted(DIR.glob("*.json")):
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        gid = g.get("id") or p.stem
        out.append(
            {
                "id": gid,
                "name": g.get("name") or gid,
                "version": g.get("version") or 1,
                "purpose": (g.get("purpose") or "")[:80],
                "active": gid == aid,
            }
        )
    return out[:MAX_GODS]


def active_id() -> str:
    ensure()
    try:
        return ACTIVE.read_text(encoding="utf-8").strip() or "master"
    except Exception:
        return "master"


def active() -> dict:
    return get(active_id()) or get("master") or {"id": "master", "name": "GOD", "capabilities": tool_names()}


def activate(gid: str) -> dict:
    g = get(gid)
    if not g:
        return {"ok": False, "error": "GOD inexistente"}
    ACTIVE.write_text(g["id"], encoding="utf-8")
    return {"ok": True, "id": g["id"]}


def validate(raw: dict) -> tuple[dict | None, str]:
    names = tool_names()
    gid = _slug(str(raw.get("id") or raw.get("name") or "god"))
    if gid == "active":
        return None, "id reservado"
    caps = raw.get("capabilities")
    if caps is None:
        caps = names
    if not isinstance(caps, list):
        return None, "capabilities deve ser lista"
    clean: list[str] = []
    for c in caps:
        c = str(c)
        if c not in names:
            return None, f"ferramenta inexistente: {c}"
        if c not in clean:
            clean.append(c)
    rules = str(raw.get("rules") or "")[:MAX_RULES]
    blob = " ".join(
        [
            rules,
            str(raw.get("purpose") or ""),
            str(raw.get("personality") or ""),
        ]
    ).lower()
    for b in BANNED:
        if b in blob:
            return None, "perfil recusado pelo Governor"
    models = raw.get("models") or "auto"
    if models != "auto":
        return None, "models só 'auto' nesta fase — o router decide; não finjo provider"
    return {
        "id": gid,
        "name": str(raw.get("name") or gid)[:80],
        "version": int(raw.get("version") or 1),
        "owner": "local",
        "purpose": str(raw.get("purpose") or "")[:400],
        "personality": str(raw.get("personality") or "")[:400],
        "capabilities": clean,
        "models": "auto",
        "memory": bool(raw.get("memory", True)),
        "rules": rules,
        "status": "ready",
        "updated": now_iso(),
    }, "ok"


def save(raw: dict, bump: bool = True) -> dict:
    ensure()
    body, why = validate(raw)
    if not body:
        return {"ok": False, "error": why}
    existing = get(body["id"])
    if existing and bump:
        body["version"] = int(existing.get("version") or 1) + 1
        hist = DIR / "history"
        hist.mkdir(exist_ok=True)
        (hist / f"{body['id']}-v{existing.get('version', 1)}.json").write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        old = sorted(hist.glob(f"{body['id']}-v*.json"))
        for f in old[:-10]:
            try:
                f.unlink()
            except Exception:
                pass
    elif not existing:
        body["version"] = 1
        body["created"] = now_iso()
        if len(list(DIR.glob("*.json"))) >= MAX_GODS:
            return {"ok": False, "error": f"máximo {MAX_GODS} GODs"}
    _path(body["id"]).write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "god": body}


def allow_tool(name: str) -> bool:
    g = active()
    caps = g.get("capabilities")
    if not caps:
        return False
    return name in caps


def prompt_overlay() -> str:
    g = active()
    bits = []
    if g.get("id") and g.get("id") != "master":
        bits.append(f"Perfil activo: {g.get('name')} ({g.get('id')}).")
    if g.get("purpose"):
        bits.append("Propósito: " + str(g["purpose"])[:240])
    if g.get("personality"):
        bits.append("Personalidade: " + str(g["personality"])[:240])
    if g.get("rules"):
        bits.append("Regras extra: " + str(g["rules"])[:400])
    return " ".join(bits)
