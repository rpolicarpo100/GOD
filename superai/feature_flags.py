"""Feature Flags — controlo granular de funcionalidades.

Flags are DISABLED by default. A flag must be explicitly enabled.
Governor can block flag changes. HIGH RISK flags require human approval.
"""
from __future__ import annotations

import threading
from typing import Any

from .config import cfg
from .events import bus
from .governor import gov
from .store import store
from .util import now_iso, uid

_lock = threading.Lock()

# Flag definitions: name → default + risk + description
_FLAG_DEFS: dict[str, dict] = {
    "semantic_cache": {
        "default": False,
        "risk": "low",
        "description": "Usar cache semântico (Qdrant) além do hash cache",
        "requires": [],
    },
    "parallel_jobs": {
        "default": False,
        "risk": "low",
        "description": "Permitir execução paralela de jobs (inflight>1)",
        "requires": [],
    },
    "auto_evolve": {
        "default": False,
        "risk": "high",
        "description": "Auto-aplicar propostas de evolução sem aprovação humana",
        "requires": ["governor_strict_false"],
    },
    "allow_remote_tools": {
        "default": False,
        "risk": "medium",
        "description": "Permitir ferramentas em workers remotos",
        "requires": [],
    },
    "debug_trace": {
        "default": False,
        "risk": "low",
        "description": "Activar decision trace detalhado para todos os requests",
        "requires": [],
    },
    "extended_metrics": {
        "default": False,
        "risk": "low",
        "description": "Recolher métricas estendidas (latência por stage, etc)",
        "requires": [],
    },
    "cost_routing": {
        "default": False,
        "risk": "medium",
        "description": "Usar custo como critério de routing (precisa pricing verificada)",
        "requires": ["verified_pricing"],
    },
    "hardcore_mode": {
        "default": False,
        "risk": "high",
        "description": "Claude como provider primário (precisa API key + budget)",
        "requires": ["claude_api_key"],
    },
}

# Runtime state
_flags: dict[str, bool] = {}
_flag_meta: dict[str, dict] = {}  # name → {enabled_by, enabled_at, reason}


def _load_flags() -> None:
    """Load flags from config. Defaults to False."""
    global _flags, _flag_meta
    with _lock:
        cfg_flags = cfg.get("feature_flags") or {}
        for name, defn in _FLAG_DEFS.items():
            _flags[name] = bool(cfg_flags.get(name, defn["default"]))
        _flag_meta = dict(cfg.get("feature_flags_meta") or {})


# Initialize on import
_load_flags()


def is_enabled(name: str) -> bool:
    """Check if a feature flag is enabled."""
    with _lock:
        return _flags.get(name, False)


def enable(name: str, reason: str = "", actor: str = "system") -> dict:
    """Enable a feature flag. Returns result dict."""
    if name not in _FLAG_DEFS:
        return {"ok": False, "error": f"flag '{name}' desconhecida", "kind": "MEASURED"}

    defn = _FLAG_DEFS[name]

    # Governor blocks HIGH RISK in strict mode
    if defn["risk"] == "high" and gov.strict():
        return {
            "ok": False,
            "error": f"flag '{name}' é HIGH RISK e governor está em strict mode",
            "risk": defn["risk"],
            "kind": "MEASURED",
        }

    # Check requirements
    for req in defn.get("requires", []):
        if req == "governor_strict_false" and gov.strict():
            return {"ok": False, "error": "requer governor strict=false", "kind": "MEASURED"}
        if req == "verified_pricing":
            from .tokens import pricing
            if pricing().get("kind") == "UNKNOWN":
                return {"ok": False, "error": "requer pricing verificada", "kind": "MEASURED"}
        if req == "claude_api_key":
            from .providers import health_all
            claude = next((h for h in health_all() if h["id"] == "claude"), None)
            if not claude or not claude.get("has_key"):
                return {"ok": False, "error": "requer Claude API key", "kind": "MEASURED"}

    with _lock:
        _flags[name] = True
        _flag_meta[name] = {
            "enabled_by": actor,
            "enabled_at": now_iso(),
            "reason": reason or "manual",
        }
        # Persist to config
        cfg.patch({"feature_flags": {name: True}})
        cfg.patch({"feature_flags_meta": _flag_meta})

    bus.emit("FEATURE_FLAG", "INFO", f"flag '{name}' ENABLED by {actor}: {reason}")
    store.mem_put("feature_flags", name, _flag_meta[name])

    return {
        "ok": True,
        "flag": name,
        "enabled": True,
        "risk": defn["risk"],
        "meta": _flag_meta[name],
        "kind": "MEASURED",
    }


def disable(name: str, reason: str = "", actor: str = "system") -> dict:
    """Disable a feature flag."""
    if name not in _FLAG_DEFS:
        return {"ok": False, "error": f"flag '{name}' desconhecida", "kind": "MEASURED"}

    with _lock:
        _flags[name] = False
        _flag_meta[name] = {
            "disabled_by": actor,
            "disabled_at": now_iso(),
            "reason": reason or "manual",
        }
        cfg.patch({"feature_flags": {name: False}})
        cfg.patch({"feature_flags_meta": _flag_meta})

    bus.emit("FEATURE_FLAG", "INFO", f"flag '{name}' DISABLED by {actor}: {reason}")

    return {
        "ok": True,
        "flag": name,
        "enabled": False,
        "kind": "MEASURED",
    }


def list_flags() -> list[dict]:
    """List all flags with their state."""
    out = []
    for name, defn in _FLAG_DEFS.items():
        out.append({
            "name": name,
            "enabled": _flags.get(name, False),
            "risk": defn["risk"],
            "description": defn["description"],
            "requires": defn.get("requires", []),
            "meta": _flag_meta.get(name),
        })
    return out


def flags_summary() -> dict:
    """Summary for API/UI."""
    flags = list_flags()
    enabled = [f["name"] for f in flags if f["enabled"]]
    disabled = [f["name"] for f in flags if not f["enabled"]]
    high_risk = [f["name"] for f in flags if f["risk"] == "high"]
    return {
        "kind": "MEASURED",
        "n": len(flags),
        "n_enabled": len(enabled),
        "n_disabled": len(disabled),
        "enabled": enabled,
        "disabled": disabled,
        "high_risk": high_risk,
        "flags": flags,
        "ts": now_iso(),
    }


def get_flag(name: str) -> dict | None:
    """Get a single flag's state."""
    for f in list_flags():
        if f["name"] == name:
            return f
    return None
