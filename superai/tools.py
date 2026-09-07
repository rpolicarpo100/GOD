from __future__ import annotations

import ast
import unicodedata
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

PROJECTS = DATA / "projects"
PROJECTS.mkdir(parents=True, exist_ok=True)
_WRITE_MAX = 80_000


def project_slug(text: str) -> str:
    n = unicodedata.normalize("NFD", str(text or ""))
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")[:40]
    return s or "site"

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
    timeout_s = gov.python_timeout()
    MAX_OUTPUT = 6000
    try:
        # Use process group for clean cleanup on timeout
        proc = subprocess.run(
            ["python3", str(f)],
            cwd=SANDBOX,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={
                "PYTHONPATH": "",
                "PATH": "/usr/local/bin:/usr/bin",
                "HOME": str(SANDBOX),
                "TMPDIR": str(SANDBOX),
                # Strip all API keys and secrets
                "GOD_ENV": "sandbox",
            },
        )
    except subprocess.TimeoutExpired:
        # Clean up any child processes
        try:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
        return _err(f"timeout {timeout_s}s — process killed")
    except Exception as e:
        return _err(str(e))
    out = (proc.stdout or "")[-MAX_OUTPUT:]
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


def tool_fs_write(args: dict) -> dict:
    rel = str(args.get("path") or "").strip().lstrip("/")
    body = args.get("text")
    if body is None:
        body = args.get("content") or ""
    body = str(body)
    slug = project_slug(args.get("slug") or "site")
    if not rel:
        return _err("fs.write sem path")
    if ".." in Path(rel).parts:
        return _err("path recusado")
    p = PROJECTS / slug / rel
    ok, why = gov.allow_write(p)
    if not ok:
        return _err(why)
    if len(body) > _WRITE_MAX:
        return _err(f"ficheiro > {_WRITE_MAX} chars")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return _ok(
        findings=[{"path": str(p), "bytes": p.stat().st_size, "preview": f"/preview/{slug}/"}],
        evidence=[f"write {p} {p.stat().st_size}B"],
    )


def tool_fs_mkdir(args: dict) -> dict:
    slug = project_slug(args.get("slug") or "")
    if not slug or slug == "site" and not str(args.get("slug") or "").strip():
        return _err("slug vazio")
    p = PROJECTS / slug
    ok, why = gov.allow_path(p)
    if not ok:
        return _err(why)
    if p.resolve().parent != PROJECTS.resolve():
        return _err("mkdir só em data/projects")
    p.mkdir(parents=True, exist_ok=True)
    return _ok(findings=[{"path": str(p), "preview": f"/preview/{slug}/"}], evidence=[f"mkdir {p}"])


def tool_project_list(args: dict) -> dict:
    items = []
    if PROJECTS.exists():
        for d in sorted(PROJECTS.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                items.append({"slug": d.name, "index": (d / "index.html").is_file(), "preview": f"/preview/{d.name}/"})
    return _ok(findings=items, evidence=[f"projects n={len(items)}"])



# ═══════════════════════════════
# WEB + GITHUB TOOLS
# ═══════════════════════════════

def tool_web_search(args: dict) -> dict:
    """Search the web in real-time."""
    from .websearch import search
    query = args.get("query") or args.get("text") or ""
    max_results = int(args.get("max_results", 5))
    r = search(query, max_results=max_results)
    if r.get("status") == "success":
        findings = []
        for item in r.get("results", []):
            findings.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("snippet"),
            })
        return _ok(findings=findings, evidence=[f"backend={r.get('backend')}", f"n={r.get('n')}"])
    return _err(r.get("error", "search failed"))


def tool_web_fetch(args: dict) -> dict:
    """Fetch and read a web page."""
    from .websearch import fetch_page
    url = args.get("url") or ""
    if not url:
        return _err("missing url")
    r = fetch_page(url)
    if r.get("status") == "success":
        return _ok(
            findings=[{"title": r.get("title"), "url": url, "text": r.get("text", "")[:3000]}],
            evidence=[f"url={url}", f"length={r.get('length')}"]
        )
    return _err(r.get("error", "fetch failed"))


def tool_github_file(args: dict) -> dict:
    """Get file from GitHub repo."""
    from .github import get_file
    owner = args.get("owner", "")
    repo = args.get("repo", "")
    path = args.get("path", "")
    ref = args.get("ref", "main")
    if not owner or not repo or not path:
        return _err("missing owner/repo/path")
    r = get_file(owner, repo, path, ref)
    if r.get("status") == "success":
        content_text = r.get("content", "")
        return _ok(
            findings=[{"path": path, "content": content_text[:5000], "size": r.get("size")}],
            evidence=[f"github:{owner}/{repo}/{path}"]
        )
    return _err(r.get("error", "file not found"))


def tool_github_search(args: dict) -> dict:
    """Search code in GitHub repos."""
    from .github import search_code
    query = args.get("query", "")
    owner = args.get("owner", "")
    repo = args.get("repo", "")
    if not query:
        return _err("missing query")
    r = search_code(query, owner=owner, repo=repo)
    if r.get("status") == "success":
        return _ok(
            findings=r.get("results", []),
            evidence=[f"total={r.get('total')}", f"n={r.get('n')}"]
        )
    return _err(r.get("error", "search failed"))


def tool_news_search(args: dict) -> dict:
    """Search news intelligence."""
    from .news_connector import search_news
    query = args.get("query", "")
    if not query:
        return _err("missing query")
    r = search_news(query)
    if r.get("status") == "success":
        return _ok(findings=r.get("results", []), evidence=[f"n={r.get('n')}"])
    return _err(r.get("error", "news search failed"))


def tool_news_latest(args: dict) -> dict:
    """Get latest news events."""
    from .news_connector import get_latest
    limit = int(args.get("limit", 10))
    category = args.get("category", "")
    r = get_latest(limit=limit, category=category)
    if r.get("status") == "success":
        return _ok(findings=r.get("events", []), evidence=[f"n={r.get('n')}", f"total={r.get('total')}"])
    return _err(r.get("error", "news fetch failed"))


def tool_site_search(args: dict) -> dict:
    """Search across registered sites."""
    from .site_aggregator import search_sites
    query = args.get("query", "")
    if not query:
        return _err("missing query")
    r = search_sites(query)
    if r.get("status") == "success":
        return _ok(findings=r.get("results", []), evidence=[f"sites={r.get('sites_searched')}", f"matched={r.get('sites_matched')}"])
    return _err(r.get("error", "search failed"))


def tool_site_fetch(args: dict) -> dict:
    """Fetch content from a registered site."""
    from .site_aggregator import fetch_site
    url = args.get("url", "")
    path = args.get("path", "")
    if not url:
        return _err("missing url")
    r = fetch_site(url, path)
    if r.get("status") == "success":
        return _ok(
            findings=[{"title": r.get("title"), "url": r.get("url"), "text": r.get("text", "")[:3000]}],
            evidence=[f"url={r.get('url')}", f"length={r.get('length')}"]
        )
    return _err(r.get("error", "fetch failed"))


def tool_github_repos(args: dict) -> dict:
    """List GitHub repos."""
    from .github import list_repos
    owner = args.get("owner", "")
    r = list_repos(owner)
    if r.get("status") == "success":
        return _ok(findings=r.get("repos", []), evidence=[f"n={r.get('n')}"])
    return _err(r.get("error", "list failed"))



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
    "fs.write": {
        "fn": tool_fs_write,
        "capabilities": ["filesystem", "site"],
        "cost": 0,
        "latency": "low",
        "risk": "medium",
        "permissions": "write-projects",
    },
    "fs.mkdir": {
        "fn": tool_fs_mkdir,
        "capabilities": ["filesystem", "site"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "write-projects",
    },
    "project.list": {
        "fn": tool_project_list,
        "capabilities": ["site"],
        "cost": 0,
        "latency": "low",
        "risk": "low",
        "permissions": "read",
    },
    "web.search": {
        "fn": tool_web_search,
        "capabilities": ["web", "search", "internet"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "web.fetch": {
        "fn": tool_web_fetch,
        "capabilities": ["web", "fetch", "internet"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "github.file": {
        "fn": tool_github_file,
        "capabilities": ["github", "code"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "github.search": {
        "fn": tool_github_search,
        "capabilities": ["github", "code", "search"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "github.repos": {
        "fn": tool_github_repos,
        "capabilities": ["github"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "news.search": {
        "fn": tool_news_search,
        "capabilities": ["news", "web", "intelligence"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "news.latest": {
        "fn": tool_news_latest,
        "capabilities": ["news", "web", "intelligence"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "site.search": {
        "fn": tool_site_search,
        "capabilities": ["web", "sites", "search"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
    },
    "site.fetch": {
        "fn": tool_site_fetch,
        "capabilities": ["web", "sites", "fetch"],
        "cost": 0,
        "latency": "medium",
        "risk": "low",
        "permissions": "read",
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
    from . import gods

    if not gods.allow_tool(name):
        return _err(f"GOD {gods.active_id()} não tem a ferramenta {name}")
    try:
        res = TOOLS[name]["fn"](args)
    except Exception as e:
        res = _err(f"{name} crashed: {e}")
    STATS[name]["ok" if res.get("status") == "success" else "fail"] += 1
    res["tool"] = name
    return res
