"""Runtime Protection — prevenir GOD Object anti-pattern.

Detecta quando um componente acumula demasiadas responsabilidades.
Monitoriza: tamanho de ficheiros, complexidade, acoplamento.

Não é lint. É protecção operacional em tempo real.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from typing import Any

from .config import ROOT
from .events import bus
from .util import now_iso

_lock = threading.Lock()

# Thresholds
_MAX_FILE_LINES = 800  # warn
_MAX_FILE_LINES_CRITICAL = 1200  # critical
_MAX_FILE_LINES_HARD = 1500  # hard block (refactor required)
_MAX_FUNCTION_LINES = 100  # warn
_MAX_FUNCTION_LINES_CRITICAL = 200  # critical
_MAX_CLASS_METHODS = 15  # warn
_MAX_IMPORTS = 20  # warn
_MAX_CYCLOMATIC = 20  # warn per function
_MAX_TOTAL_COMPLEXITY = 200  # warn for file total

# Cache
_inspection_cache: dict[str, dict] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 30.0


def _count_lines(filepath: Path) -> int:
    """Count lines in a file."""
    try:
        with filepath.open(encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _ast_analysis(filepath: Path) -> dict:
    """AST analysis for functions/classes/complexity."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, Exception):
        return {"error": "parse failed"}

    functions: list[dict] = []
    classes: list[dict] = []
    imports: list[str] = []
    total_complexity = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno + 1) or node.lineno + 1
            lines = end - node.lineno
            # Simple cyclomatic complexity estimate
            complexity = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                     ast.With, ast.BoolOp, ast.Assert)):
                    complexity += 1
            total_complexity += complexity
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "lines": lines,
                "complexity": complexity,
            })
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in ast.walk(node)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "n_methods": len(methods),
                "methods": methods,
            })
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            else:
                imports.append(node.module or "")

    return {
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "n_functions": len(functions),
        "n_classes": len(classes),
        "n_imports": len(imports),
        "total_complexity": total_complexity,
    }


def inspect_file(filepath: Path) -> dict:
    """Inspect a single file for anti-patterns."""
    if not filepath.exists():
        return {"file": str(filepath), "status": "not_found", "kind": "UNKNOWN"}

    lines = _count_lines(filepath)
    ast_info = _ast_analysis(filepath)
    issues: list[dict] = []

    # File size check
    if lines >= _MAX_FILE_LINES_HARD:
        issues.append({
            "severity": "HARD_BLOCK",
            "check": "file_size",
            "msg": f"{filepath.name}: {lines} linhas (HARD BLOCK: {lines} >= {_MAX_FILE_LINES_HARD})",
            "value": lines,
            "threshold": _MAX_FILE_LINES_HARD,
        })
    elif lines >= _MAX_FILE_LINES_CRITICAL:
        issues.append({
            "severity": "CRITICAL",
            "check": "file_size",
            "msg": f"{filepath.name}: {lines} linhas (CRITICAL: >= {_MAX_FILE_LINES_CRITICAL})",
            "value": lines,
            "threshold": _MAX_FILE_LINES_CRITICAL,
        })
    elif lines >= _MAX_FILE_LINES:
        issues.append({
            "severity": "WARNING",
            "check": "file_size",
            "msg": f"{filepath.name}: {lines} linhas (WARNING: >= {_MAX_FILE_LINES})",
            "value": lines,
            "threshold": _MAX_FILE_LINES,
        })

    if ast_info.get("error"):
        issues.append({
            "severity": "WARNING",
            "check": "ast_parse",
            "msg": f"{filepath.name}: AST parse failed",
        })
    else:
        # Function size check
        for fn in ast_info.get("functions", []):
            if fn["lines"] >= _MAX_FUNCTION_LINES_CRITICAL:
                issues.append({
                    "severity": "CRITICAL",
                    "check": "function_size",
                    "msg": f"{fn['name']}(): {fn['lines']} linhas (CRITICAL: >= {_MAX_FUNCTION_LINES_CRITICAL})",
                    "value": fn["lines"],
                    "threshold": _MAX_FUNCTION_LINES_CRITICAL,
                })
            elif fn["lines"] >= _MAX_FUNCTION_LINES:
                issues.append({
                    "severity": "WARNING",
                    "check": "function_size",
                    "msg": f"{fn['name']}(): {fn['lines']} linhas (WARNING: >= {_MAX_FUNCTION_LINES})",
                    "value": fn["lines"],
                    "threshold": _MAX_FUNCTION_LINES,
                })

        # Class size check
        for cls in ast_info.get("classes", []):
            if cls["n_methods"] >= _MAX_CLASS_METHODS:
                issues.append({
                    "severity": "WARNING",
                    "check": "class_size",
                    "msg": f"class {cls['name']}: {cls['n_methods']} métodos (WARNING: >= {_MAX_CLASS_METHODS})",
                    "value": cls["n_methods"],
                    "threshold": _MAX_CLASS_METHODS,
                })

        # Import count check
        if ast_info.get("n_imports", 0) >= _MAX_IMPORTS:
            issues.append({
                "severity": "WARNING",
                "check": "import_count",
                "msg": f"{filepath.name}: {ast_info['n_imports']} imports (WARNING: >= {_MAX_IMPORTS})",
                "value": ast_info["n_imports"],
                "threshold": _MAX_IMPORTS,
            })

        # Complexity check
        for fn in ast_info.get("functions", []):
            if fn["complexity"] >= _MAX_CYCLOMATIC:
                issues.append({
                    "severity": "WARNING",
                    "check": "cyclomatic_complexity",
                    "msg": f"{fn['name']}(): complexity {fn['complexity']} (WARNING: >= {_MAX_CYCLOMATIC})",
                    "value": fn["complexity"],
                    "threshold": _MAX_CYCLOMATIC,
                })

    severity_order = {"HARD_BLOCK": 4, "CRITICAL": 3, "WARNING": 2, "OK": 1}
    worst = max((severity_order.get(i["severity"], 0) for i in issues), default=1)
    worst_name = {4: "HARD_BLOCK", 3: "CRITICAL", 2: "WARNING", 1: "OK"}.get(worst, "OK")

    return {
        "file": filepath.name,
        "path": str(filepath),
        "lines": lines,
        "ast": ast_info if not ast_info.get("error") else None,
        "n_issues": len(issues),
        "issues": issues,
        "worst_severity": worst_name,
        "kind": "MEASURED",
    }


def inspect_all() -> dict:
    """Inspect all source files."""
    global _inspection_cache, _cache_ts
    now = time.time()
    if _inspection_cache and now - _cache_ts < _CACHE_TTL:
        return _inspection_cache

    src = ROOT / "superai"
    results: list[dict] = []
    hard_blocks: list[dict] = []
    criticals: list[dict] = []
    warnings: list[dict] = []

    for f in sorted(src.glob("*.py")):
        if f.name == "__pycache__":
            continue
        r = inspect_file(f)
        results.append(r)
        for issue in r.get("issues", []):
            if issue["severity"] == "HARD_BLOCK":
                hard_blocks.append(issue)
            elif issue["severity"] == "CRITICAL":
                criticals.append(issue)
            elif issue["severity"] == "WARNING":
                warnings.append(issue)

    summary = {
        "kind": "MEASURED",
        "ts": now_iso(),
        "n_files": len(results),
        "n_hard_blocks": len(hard_blocks),
        "n_critical": len(criticals),
        "n_warnings": len(warnings),
        "hard_blocks": hard_blocks,
        "criticals": criticals,
        "warnings": warnings,
        "files": results,
    }
    _inspection_cache = summary
    _cache_ts = now
    return summary


def check_god_object() -> dict:
    """Specifically check for GOD Object anti-pattern.

    GOD Object = single file doing too much.
    Detect: runtime.py as the prime suspect.
    """
    runtime = ROOT / "superai" / "runtime.py"
    if not runtime.exists():
        return {"status": "not_found", "kind": "UNKNOWN"}

    r = inspect_file(runtime)
    lines = r["lines"]
    ast_info = r.get("ast") or {}
    n_functions = ast_info.get("n_functions", 0)
    total_complexity = ast_info.get("total_complexity", 0)

    # GOD Object heuristics
    is_god_object = False
    reasons = []

    if lines >= _MAX_FILE_LINES_CRITICAL:
        is_god_object = True
        reasons.append(f"{lines} linhas (>= {_MAX_FILE_LINES_CRITICAL})")

    # Check for handle() function size
    handle_fn = next((f for f in ast_info.get("functions", []) if f["name"] == "handle"), None)
    if handle_fn and handle_fn["lines"] >= _MAX_FUNCTION_LINES_CRITICAL:
        is_god_object = True
        reasons.append(f"handle(): {handle_fn['lines']} linhas")

    if total_complexity >= _MAX_TOTAL_COMPLEXITY:
        is_god_object = True
        reasons.append(f"complexidade total {total_complexity}")

    # Check if single file has too many functions (responsibility sprawl)
    # But only if functions are large — many small functions is OK
    avg_fn_lines = sum(f["lines"] for f in ast_info.get("functions", [])) / max(n_functions, 1)
    if n_functions >= 30 and avg_fn_lines > 40:
        is_god_object = True
        reasons.append(f"{n_functions} funções com média {avg_fn_lines:.0f} linhas")

    return {
        "kind": "MEASURED",
        "ts": now_iso(),
        "file": "runtime.py",
        "lines": lines,
        "n_functions": n_functions,
        "total_complexity": total_complexity,
        "is_god_object": is_god_object,
        "reasons": reasons,
        "handle_fn": handle_fn,
        "recommendation": (
            "REFACTOR OBRIGATÓRIO: extrair funções de runtime.py para módulos separados"
            if is_god_object
            else "OK: runtime.py dentro dos limites"
        ),
    }


def protection_report() -> dict:
    """Full protection report for API/UI."""
    return {
        "kind": "MEASURED",
        "ts": now_iso(),
        "god_object": check_god_object(),
        "all_files": inspect_all(),
    }
