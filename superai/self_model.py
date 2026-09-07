"""Self-Model — GOD knows what it can and can't do.

Not consciousness. Operational awareness based on observable state.
Answers: WHAT CAN I DO? WHAT IS WORKING? WHAT FAILED? WHAT SHOULD IMPROVE?
"""
from __future__ import annotations

import time
from .util import now_iso
from .events import bus

_snapshot: dict = {}
_last_update: float = 0.0
_UPDATE_INTERVAL = 30  # seconds


def _build_snapshot() -> dict:
    """Build self-model from current system state."""
    global _snapshot, _last_update
    now = time.time()
    if now - _last_update < _UPDATE_INTERVAL and _snapshot:
        return _snapshot

    model = {
        "ts": now_iso(),
        "kind": "MEASURED",
    }

    # Capabilities
    try:
        from .tools import TOOLS
        model["capabilities"] = {
            "tools": sorted(TOOLS.keys()),
            "n_tools": len(TOOLS),
        }
    except Exception:
        model["capabilities"] = {"tools": [], "n_tools": 0}

    # Providers
    try:
        from . import providers
        hs = providers.health_all()
        avail = [h["id"] for h in hs if h.get("available")]
        down = [h["id"] for h in hs if not h.get("available")]
        model["providers"] = {
            "available": avail,
            "down": down,
            "n_available": len(avail),
            "n_total": len(hs),
        }
    except Exception:
        model["providers"] = {"available": [], "down": [], "n_available": 0, "n_total": 0}

    # Memory
    try:
        from .memory_vec import vectors
        if vectors.available():
            h = vectors.health()
            model["memory"] = {
                "qdrant": True,
                "collections": h.get("collections", {}),
                "embed_method": h.get("embed", {}).get("method", "unknown"),
            }
        else:
            model["memory"] = {"qdrant": False}
    except Exception:
        model["memory"] = {"qdrant": False}

    # Evolution
    try:
        from .evolution import experiments_summary
        es = experiments_summary()
        model["evolution"] = {
            "n_experiments": es.get("n", 0),
            "applied": es.get("applied", 0),
            "pending": es.get("pending", 0),
        }
    except Exception:
        model["evolution"] = {"n_experiments": 0, "applied": 0, "pending": 0}

    # Telemetry
    try:
        from .trace import get_system_metrics, all_provider_scores
        model["telemetry"] = get_system_metrics()
        model["provider_scores"] = all_provider_scores()
    except Exception:
        model["telemetry"] = {}
        model["provider_scores"] = {}

    # Health
    try:
        from .health import diagnostics
        d = diagnostics()
        model["health"] = {
            "pct": d.get("health_pct", 0),
            "n_ok": d.get("n_ok", 0),
            "n_down": d.get("n_down", 0),
        }
    except Exception:
        model["health"] = {"pct": 0, "n_ok": 0, "n_down": 0}

    # Active GOD profile
    try:
        from . import gods
        g = gods.active()
        model["profile"] = {
            "id": g.get("id", "unknown"),
            "name": g.get("name", "unknown"),
            "n_capabilities": len(g.get("capabilities", [])),
        }
    except Exception:
        model["profile"] = {"id": "unknown", "name": "unknown", "n_capabilities": 0}

    # Known limitations
    model["limitations"] = _detect_limitations(model)

    # Improvement suggestions
    model["suggestions"] = _generate_suggestions(model)

    _snapshot = model
    _last_update = now
    return model


def _detect_limitations(model: dict) -> list[str]:
    """Detect what GOD currently can't do well."""
    limits = []
    prov = model.get("providers", {})
    if prov.get("n_available", 0) == 0:
        limits.append("NO_LLM: nenhum provider disponível — apenas tools locais")
    elif prov.get("n_available", 0) < 3:
        limits.append(f"LOW_REDUNDANCY: apenas {prov['n_available']} provider(s) — risco de falha")

    mem = model.get("memory", {})
    if not mem.get("qdrant"):
        limits.append("NO_VECTOR: Qdrant indisponível — cache semântico desligado")

    health = model.get("health", {})
    if health.get("pct", 0) < 50:
        limits.append(f"LOW_HEALTH: {health['pct']}% — sistema degradado")

    evo = model.get("evolution", {})
    if evo.get("applied", 0) == 0 and evo.get("n_experiments", 0) == 0:
        limits.append("NO_EVOLUTION: nenhuma experiência executada — GOD não aprendeu nada ainda")

    return limits


def _generate_suggestions(model: dict) -> list[str]:
    """Generate improvement suggestions based on current state."""
    sug = []
    prov = model.get("providers", {})
    if prov.get("n_available", 0) == 0:
        sug.append("Configura pelo menos1 API key: ./god.sh config")
    elif prov.get("n_available", 0) < 5:
        sug.append("Adiciona mais providers para redundância (Groq free, Gemini free)")

    health = model.get("health", {})
    if health.get("pct", 0) < 70:
        sug.append(f"Saúde a {health['pct']}% — verifica componentes em Activity tab")

    evo = model.get("evolution", {})
    if evo.get("n_experiments", 0) == 0:
        sug.append("GOD ainda não fez experiências — interage mais para gerar dados")

    tel = model.get("telemetry", {})
    if tel.get("llm_calls_total", 0) == 0:
        sug.append("Nenhuma chamada LLM registada — faz uma pergunta para ativar")

    return sug


def get_self_model() -> dict:
    """Get the current self-model."""
    return _build_snapshot()


def what_can_i_do() -> list[str]:
    """List current capabilities."""
    m = _build_snapshot()
    caps = []
    caps.extend(m.get("capabilities", {}).get("tools", []))
    for p in m.get("providers", {}).get("available", []):
        caps.append(f"llm:{p}")
    return caps


def what_cant_i_do() -> list[str]:
    """List current limitations."""
    return _build_snapshot().get("limitations", [])


def what_should_improve() -> list[str]:
    """List improvement suggestions."""
    return _build_snapshot().get("suggestions", [])
