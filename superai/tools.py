from __future__ import annotations

import ast
import csv
import io
import json
import operator
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from lxml import etree

from .config import DATA, ROOT
from .governor import gov
from .util import now_iso

SANDBOX = DATA / "sandbox"
SANDBOX.mkdir(exist_ok=True)

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _ok(findings=None, artifacts=None, evidence=None, confidence=1.0, next_action="") -> dict:
    return {
        "status": "success",
        "confidence": confidence,
        "findings": findings or [],
        "errors": [],
        "artifacts": artifacts or [],
        "next_action": next_action,
        "evidence": evidence or [],
        "ts": now_iso(),
    }


def _err(msg: str, **kw: Any) -> dict:
    return {
        "status": "error",
        "confidence": 0.0,
        "findings": [],
        "errors": [msg],
        "artifacts": [],
        "next_action": kw.get("next_action", ""),
        "evidence": kw.get("evidence", []),
        "ts": now_iso(),
    }


def _eval_ast(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in UOPS:
        return UOPS[type(node.op)](_eval_ast(node.operand))
    if isinstance(node, ast.Expr):
        return _eval_ast(node.value)
    raise ValueError("expressão não suportada (só aritmética)")


def tool_calculator(args: dict) -> dict:
    expr = str(args.get("expr") or args.get("text") or "").strip()
    expr = expr.replace("^", "**")
    # extract first arithmetic slice
    m = re.search(r"[\d\(][\d\.\s\+\-\*/%\(\)]+", expr)
    if m:
        expr = m.group(0)
    try:
        tree = ast.parse(expr, mode="eval")
        val = _eval_ast(tree.body)
    except Exception as e:
        return _err(f"calculator: {e}", evidence=[expr])
    return _ok(findings=[{"expr": expr, "result": val}], evidence=[f"{expr} = {val}"])


def tool_fs_list(args: dict) -> dict:
    raw = args.get("path") or str(ROOT)
    p = Path(raw)
    ok, why = gov.allow_path(p)
    if not ok:
        return _err(why)
    if not p.exists():
        return _err(f"não existe: {p}")
    if p.is_file():
        return _ok(findings=[{"path": str(p), "bytes": p.stat().st_size}])
    items = []
    for c in sorted(p.iterdir())[:200]:
        items.append({"name": c.name, "dir": c.is_dir(), "bytes": c.stat().st_size if c.is_file() else None})
    return _ok(findings=items, evidence=[f"list {p} n={len(items)}"])


def tool_fs_read(args: dict) -> dict:
    p = Path(args.get("path") or "")
    ok, why = gov.allow_path(p)
    if not ok:
        return _err(why)
    if not p.is_file():
        return _err(f"não é ficheiro: {p}")
    data = p.read_text(errors="replace")
    max_chars = int(args.get("max_chars") or 12000)
    truncated = len(data) > max_chars
    text = data[:max_chars]
    return _ok(
        findings=[{"path": str(p), "chars": len(data), "truncated": truncated, "preview": text}],
        evidence=[f"read {p} {len(data)} chars"],
    )


def tool_git(args: dict) -> dict:
    argv = list(args.get("args") or ["status"])
    ok, why = gov.allow_git(argv)
    if not ok:
        return _err(why)
    cwd = Path(args.get("cwd") or ROOT)
    gok, gwhy = gov.allow_path(cwd)
    if not gok:
        return _err(gwhy)
    try:
        proc = subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, timeout=8)
    except Exception as e:
        return _err(str(e))
    out = (proc.stdout or "") + (proc.stderr or "")
    st = "success" if proc.returncode == 0 else "error"
    body = {"status": st, "confidence": 1.0 if proc.returncode == 0 else 0.2, "findings": [{"cmd": argv, "exit": proc.returncode, "output": out[-8000:]}], "errors": [] if proc.returncode == 0 else [f"exit {proc.returncode}"], "artifacts": [], "next_action": "", "evidence": [f"git {' '.join(argv)} exit={proc.returncode}"], "ts": now_iso()}
    return body


def tool_json(args: dict) -> dict:
    raw = args.get("text") or args.get("json") or ""
    path = args.get("path")
    if path:
        p = Path(path)
        ok, why = gov.allow_path(p)
        if not ok:
            return _err(why)
        raw = p.read_text()
    try:
        obj = json.loads(raw)
    except Exception as e:
        return _err(f"json: {e}")
    kind = type(obj).__name__
    keys = list(obj)[:50] if isinstance(obj, dict) else None
    n = len(obj) if isinstance(obj, (list, dict)) else None
    return _ok(findings=[{"type": kind, "n": n, "keys": keys}], evidence=["json.loads ok"])


def tool_csv(args: dict) -> dict:
    raw = args.get("text") or ""
    path = args.get("path")
    if path:
        p = Path(path)
        ok, why = gov.allow_path(p)
        if not ok:
            return _err(why)
        raw = p.read_text()
    try:
        rows = list(csv.reader(io.StringIO(raw)))
    except Exception as e:
        return _err(str(e))
    return _ok(findings=[{"rows": len(rows), "cols": len(rows[0]) if rows else 0, "head": rows[:5]}], evidence=[f"csv rows={len(rows)}"])


def tool_xml(args: dict) -> dict:
    raw = args.get("text") or ""
    path = args.get("path")
    if path:
        p = Path(path)
        ok, why = gov.allow_path(p)
        if not ok:
            return _err(why)
        raw = p.read_text()
    try:
        root = etree.fromstring(raw.encode() if isinstance(raw, str) else raw)
    except Exception as e:
        return _err(f"xml: {e}")
    return _ok(findings=[{"tag": root.tag, "children": len(root)}], evidence=[f"xml root=<{root.tag}>"])


def tool_regex(args: dict) -> dict:
    pat = args.get("pattern") or ""
    text = args.get("text") or ""
    if len(pat) > 200 or len(text) > 200_000:
        return _err("regex demasiado grande")
    try:
        rx = re.compile(pat)
        found = rx.findall(text)[:50]
    except Exception as e:
        return _err(str(e))
    return _ok(findings=[{"n": len(found), "matches": found[:20]}], evidence=[f"re n={len(found)}"])


def tool_python(args: dict) -> dict:
    code = str(args.get("code") or "")
    ok, why = gov.allow_python(code)
    if not ok:
        return _err(why)
    f = SANDBOX / "job.py"
    f.write_text(code)
    try:
        proc = subprocess.run(
            ["python3", str(f)],
            cwd=SANDBOX,
            capture_output=True,
            text=True,
            timeout=gov.python_timeout(),
            env={"PYTHONPATH": "", "PATH": "/usr/local/bin:/usr/bin"},
        )
    except subprocess.TimeoutExpired:
        return _err(f"timeout {gov.python_timeout()}s")
    except Exception as e:
        return _err(str(e))
    out = (proc.stdout or "")[-6000:]
    err = (proc.stderr or "")[-3000:]
    st = "success" if proc.returncode == 0 else "error"
    return {
        "status": st,
        "confidence": 0.9 if proc.returncode == 0 else 0.3,
        "findings": [{"exit": proc.returncode, "stdout": out, "stderr": err}],
        "errors": [] if proc.returncode == 0 else [err or f"exit {proc.returncode}"],
        "artifacts": [str(f)],
        "next_action": "",
        "evidence": [f"python exit={proc.returncode}"],
        "ts": now_iso(),
    }


TOOLS: dict[str, dict] = {
    "calculator": {
        "fn": tool_calculator,
        "capabilities": ["arithmetic"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "none",
    },
    "fs.list": {
        "fn": tool_fs_list,
        "capabilities": ["filesystem"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "read",
    },
    "fs.read": {
        "fn": tool_fs_read,
        "capabilities": ["filesystem"],
        "cost": 0,
        "latency": "low",
        "risk": "medium",
        "permissions": "read",
    },
    "git": {
        "fn": tool_git,
        "capabilities": ["git"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "read",
    },
    "json": {
        "fn": tool_json,
        "capabilities": ["parse"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "none",
    },
    "csv": {
        "fn": tool_csv,
        "capabilities": ["parse"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "none",
    },
    "xml": {
        "fn": tool_xml,
        "capabilities": ["parse"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "none",
    },
    "regex": {
        "fn": tool_regex,
        "capabilities": ["regex"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "none",
    },
    "python": {
        "fn": tool_python,
        "capabilities": ["python"],
        "cost": 0,
        "latency": "medium",
        "risk": "high",
        "permissions": "sandbox",
    },
}

STATS: dict[str, dict[str, int]] = {k: {"ok": 0, "fail": 0} for k in TOOLS}


def catalog() -> list[dict]:
    out = []
    for name, meta in TOOLS.items():
        st = STATS[name]
        out.append(
            {
                "name": name,
                "capabilities": meta["capabilities"],
                "cost": meta["cost"],
                "latency": meta["latency"],
                "risk": meta["risk"],
                "permissions": meta["permissions"],
                "ok": st["ok"],
                "fail": st["fail"],
                "available": True,
            }
        )
    return out


def execute(name: str, args: dict) -> dict:
    if name not in TOOLS:
        return _err(f"ferramenta inexistente: {name}")
    try:
        res = TOOLS[name]["fn"](args)
    except Exception as e:
        res = _err(f"{name} crashed: {e}")
    STATS[name]["ok" if res.get("status") == "success" else "fail"] += 1
    res["tool"] = name
    return res
