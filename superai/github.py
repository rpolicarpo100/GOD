"""GitHub Repository Access — read repos, search code, fetch files.

Features:
- List repos for authenticated user
- Search code in repos
- Fetch file contents
- List branches, commits
- Access raw files
- Rate limit aware (5000 req/h authenticated)
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from .util import now_iso, sha

# SSRF note: base_url is hardcoded to api.github.com (trusted).
# All requests go through this client — no user-controlled URLs.
# If raw file access is added, validate_url() must be called first.

# Shared client
_client = httpx.Client(
    base_url="https://api.github.com",
    timeout=15.0,
    headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GOD/1.0",
    },
    follow_redirects=True,
)

_token: str | None = None
_rate_remaining: int = 60  # Unauthenticated: 60/h
_rate_reset: float = 0


def configure(token: str | None = None) -> None:
    """Set GitHub token. Call on boot or when user provides token."""
    global _token
    _token = token
    if token:
        _client.headers["Authorization"] = f"token {token}"


def _check_rate() -> bool:
    """Check if we have rate limit remaining."""
    if _rate_remaining <= 1:
        if time.time() < _rate_reset:
            return False
    return True


def _update_rate(response: httpx.Response) -> None:
    """Update rate limit from response headers."""
    global _rate_remaining, _rate_reset
    try:
        _rate_remaining = int(response.headers.get("X-RateLimit-Remaining", 60))
        _rate_reset = float(response.headers.get("X-RateLimit-Reset", 0))
    except (ValueError, TypeError):
        pass


def list_repos(owner: str = "", per_page: int = 30) -> dict:
    """List repositories. If owner is empty, lists authenticated user's repos."""
    if not _check_rate():
        return {"status": "error", "error": "rate limited", "reset_at": _rate_reset}
    try:
        if owner:
            r = _client.get(f"/users/{owner}/repos", params={"per_page": per_page, "sort": "updated"})
        else:
            r = _client.get("/user/repos", params={"per_page": per_page, "sort": "updated"})
        _update_rate(r)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}", "kind": "MEASURED"}
        repos = []
        for repo in r.json():
            repos.append({
                "name": repo.get("full_name"),
                "description": repo.get("description"),
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count"),
                "updated": repo.get("updated_at"),
                "private": repo.get("private"),
                "url": repo.get("html_url"),
            })
        return {"status": "success", "repos": repos, "n": len(repos), "kind": "MEASURED", "ts": now_iso()}
    except Exception as e:
        return {"status": "error", "error": str(e), "kind": "MEASURED"}


def get_file(owner: str, repo: str, path: str, ref: str = "main") -> dict:
    """Get file contents from a repo."""
    if not _check_rate():
        return {"status": "error", "error": "rate limited"}
    try:
        r = _client.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})
        _update_rate(r)
        if r.status_code == 200:
            import base64
            data = r.json()
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            else:
                content = data.get("content", "")
            return {
                "status": "success",
                "path": path,
                "content": content,
                "size": data.get("size"),
                "sha": data.get("sha"),
                "kind": "MEASURED",
                "ts": now_iso(),
            }
        elif r.status_code == 404:
            # Try as directory
            return list_directory(owner, repo, path, ref)
        return {"status": "error", "error": f"HTTP {r.status_code}", "kind": "MEASURED"}
    except Exception as e:
        return {"status": "error", "error": str(e), "kind": "MEASURED"}


def list_directory(owner: str, repo: str, path: str = "", ref: str = "main") -> dict:
    """List files in a directory."""
    if not _check_rate():
        return {"status": "error", "error": "rate limited"}
    try:
        url = f"/repos/{owner}/{repo}/contents/{path}" if path else f"/repos/{owner}/{repo}/contents"
        r = _client.get(url, params={"ref": ref})
        _update_rate(r)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}", "kind": "MEASURED"}
        items = []
        for item in r.json():
            items.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size"),
            })
        return {"status": "success", "path": path, "items": items, "n": len(items), "kind": "MEASURED", "ts": now_iso()}
    except Exception as e:
        return {"status": "error", "error": str(e), "kind": "MEASURED"}


def search_code(query: str, owner: str = "", repo: str = "", per_page: int = 10) -> dict:
    """Search code across repos or within a specific repo."""
    if not _check_rate():
        return {"status": "error", "error": "rate limited"}
    try:
        q = query
        if owner and repo:
            q = f"{query} repo:{owner}/{repo}"
        elif owner:
            q = f"{query} user:{owner}"
        r = _client.get("/search/code", params={"q": q, "per_page": per_page})
        _update_rate(r)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}", "kind": "MEASURED"}
        data = r.json()
        results = []
        for item in data.get("items", []):
            results.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "repo": item.get("repository", {}).get("full_name"),
                "url": item.get("html_url"),
                "score": item.get("score"),
            })
        return {
            "status": "success",
            "query": query,
            "total": data.get("total_count", 0),
            "results": results,
            "n": len(results),
            "kind": "MEASURED",
            "ts": now_iso(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "kind": "MEASURED"}


def get_commits(owner: str, repo: str, per_page: int = 10, ref: str = "main") -> dict:
    """Get recent commits."""
    if not _check_rate():
        return {"status": "error", "error": "rate limited"}
    try:
        r = _client.get(f"/repos/{owner}/{repo}/commits", params={"sha": ref, "per_page": per_page})
        _update_rate(r)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}", "kind": "MEASURED"}
        commits = []
        for c in r.json():
            commits.append({
                "sha": c.get("sha", "")[:8],
                "message": (c.get("commit", {}).get("message", ""))[:200],
                "author": c.get("commit", {}).get("author", {}).get("name"),
                "date": c.get("commit", {}).get("author", {}).get("date"),
            })
        return {"status": "success", "commits": commits, "n": len(commits), "kind": "MEASURED", "ts": now_iso()}
    except Exception as e:
        return {"status": "error", "error": str(e), "kind": "MEASURED"}


def get_readme(owner: str, repo: str) -> dict:
    """Get README content."""
    for name in ("README.md", "readme.md", "README.rst", "README"):
        r = get_file(owner, repo, name)
        if r.get("status") == "success":
            return r
    return {"status": "error", "error": "README not found", "kind": "MEASURED"}


def health() -> dict:
    """Check GitHub API availability."""
    try:
        r = _client.get("/rate_limit", timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            return {
                "kind": "MEASURED",
                "available": True,
                "authenticated": _token is not None,
                "rate_limit": data.get("resources", {}).get("core", {}),
                "ts": now_iso(),
            }
        return {"kind": "MEASURED", "available": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"kind": "MEASURED", "available": False, "error": str(e)}


def configure_from_env() -> None:
    """Configure from environment variable."""
    import os
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        configure(token)
