"""External Services Router — web search, GitHub, news, sites."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from superai import auth

router = APIRouter(prefix="/api", tags=["external"])


class SearchIn(BaseModel):
    query: str
    max_results: int = 5


# === WEB SEARCH ===

@router.get("/web/search")
def web_search(q: str = "", max_results: int = 5):
    from superai.websearch import search
    return search(q, max_results=max_results)


@router.get("/web/fetch")
def web_fetch(url: str = ""):
    from superai.websearch import fetch_page
    return fetch_page(url)


@router.get("/web/health")
def web_health():
    from superai.websearch import health
    return health()


# === GITHUB ===

@router.post("/github/configure")
def github_configure(body: dict = {}, authorization: str | None = Header(default=None)):
    from superai import github
    token = body.get("token", "")
    if token:
        github.configure(token)
        return {"ok": True, "authenticated": True}
    github.configure_from_env()
    return {"ok": True, "from_env": True}


@router.get("/github/repos")
def github_repos(owner: str = ""):
    from superai.github import list_repos
    return list_repos(owner)


@router.get("/github/file")
def github_file(owner: str, repo: str, path: str, ref: str = "main"):
    from superai.github import get_file
    return get_file(owner, repo, path, ref)


@router.get("/github/search")
def github_search(q: str = "", owner: str = "", repo: str = ""):
    from superai.github import search_code
    return search_code(q, owner=owner, repo=repo)


@router.get("/github/health")
def github_health():
    from superai.github import health
    return health()


# === NEWS ===

@router.get("/news/search")
def news_search(q: str = ""):
    from superai.news_connector import search_news
    return search_news(q)


@router.get("/news/latest")
def news_latest(limit: int = 10, category: str = ""):
    from superai.news_connector import get_latest
    return get_latest(limit=limit, category=category)


@router.get("/news/sources")
def news_sources():
    from superai.news_connector import get_sources
    return get_sources()


@router.get("/news/health")
def news_health():
    from superai.news_connector import health
    return health()


# === SITES ===

@router.get("/sites")
def list_sites():
    from superai.site_aggregator import list_sites, health
    return {"sites": list_sites(), "health": health()}


@router.post("/sites/register")
def register_site(body: dict = {}):
    from superai.site_aggregator import register_site
    return register_site(
        url=body.get("url", ""),
        name=body.get("name", ""),
        category=body.get("category", "general"),
        description=body.get("description", ""),
    )


@router.post("/sites/remove")
def remove_site(body: dict = {}):
    from superai.site_aggregator import remove_site
    return remove_site(body.get("id", ""))
