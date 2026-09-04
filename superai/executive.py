"""Executive Core — decisão determinística.

Não é um LLM. Não substitui runtime.handle. Sem classe ExecutiveBrain.
"""
from __future__ import annotations

from typing import Any


def decide(task: dict, plan: dict, *, any_llm: bool, from_worker: bool = False) -> dict[str, Any]:
    """Escolhe o caminho. Razões explícitas. Sem ranking inventado."""
    mode = str(task.get("exec_mode") or "NORMAL")
    deep = mode == "DEEP"
    fast = mode == "FAST"
    cx = int(task.get("complexity") or 0)
    need_mem = deep or cx >= 5
    reasons = list(plan.get("reason") or [])
    needs_llm = bool(plan.get("needs_llm"))
    steps = plan.get("steps") or []
    status_only = bool(steps) and len(steps) == 1 and steps[0].get("kind") == "status"

    if status_only:
        path = "state"
        reasons.append("estado do sistema é determinístico")
    elif steps and not needs_llm:
        path = "tools"
        reasons.append("ferramentas antes de LLM")
    elif needs_llm and not any_llm:
        path = "no_provider"
        reasons.append("needs_llm e nenhum provider probed up")
    elif needs_llm and deep and not from_worker:
        path = "queue"
        reasons.append("DEEP → fila; Direct LLM só FAST/NORMAL")
    elif needs_llm:
        path = "direct_llm"
        reasons.append("NORMAL/FAST com LLM → inline, não fila")
    else:
        path = "tools" if steps else "no_provider"
        reasons.append("sem steps e sem LLM")

    return {
        "exec_mode": mode,
        "path": path,
        "memory": need_mem,
        "queue": path == "queue",
        "direct_llm": path == "direct_llm",
        "fast": fast,
        "deep": deep,
        "reasons": reasons,
        "kind": "DETERMINISTIC",
        "note": "orquestração no código, não noutro modelo",
    }
