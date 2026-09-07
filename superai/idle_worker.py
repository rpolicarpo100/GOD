"""Idle Worker — gain knowledge when nobody is talking.

When the task queue is empty, the idle worker:
1. RESEARCHES: fetches news on tracked topics
2. READS: scrapes web pages from registered sites
3. LEARNS: extracts knowledge from interactions
4. BUILDS: expands knowledge graph
5. EVOLVES: runs experiments on collected data
6. WARMS: pre-caches embeddings for common patterns

Runs as a daemon thread. Checks queue every 30s.
Only acts when queue is truly empty (0 queued + 0 running).
"""
from __future__ import annotations

import threading
import time

from .events import bus
from .store import store
from .util import now_iso

_lock = threading.Lock()
_running = False
_tasks_done = 0
_last_task: dict = {}
_cycle_interval = 30  # Check every 30s


def start(interval: int = 30) -> None:
    """Start the idle worker."""
    global _running, _cycle_interval
    if _running:
        return
    _running = True
    _cycle_interval = interval

    def _loop():
        global _tasks_done, _last_task
        while _running:
            try:
                # Check if queue is empty
                from . import queue as tq
                q = tq.stats()
                is_idle = (q.get("queued", 0) + q.get("running", 0) + q.get("assigned", 0)) == 0

                if is_idle:
                    task = _pick_task()
                    if task:
                        result = _execute(task)
                        _tasks_done += 1
                        _last_task = {
                            "task": task.get("name", ""),
                            "result": result.get("summary", "ok"),
                            "ts": now_iso(),
                        }
                        bus.emit("IDLE_WORKER", "DEBUG",
                                 f"idle worker: {task['name']} → {result.get('summary', 'ok')[:60]}",
                                 god_core_state="learning")

            except Exception as e:
                bus.emit("IDLE_WORKER_ERROR", "WARNING", f"idle worker: {e}"[:100])

            time.sleep(_cycle_interval)

    t = threading.Thread(target=_loop, name="god-idle-worker", daemon=True)
    t.start()


def stop() -> None:
    """Stop the idle worker."""
    global _running
    _running = False


def status() -> dict:
    """Get idle worker status."""
    return {
        "kind": "MEASURED",
        "running": _running,
        "tasks_done": _tasks_done,
        "last_task": _last_task,
        "interval_s": _cycle_interval,
        "ts": now_iso(),
    }


def _pick_task() -> dict | None:
    """Pick what knowledge to acquire next. Priority-ordered."""

    # Priority 1: Research tracked news topics
    tracked = store.mem_search("", kinds=["tracked_topic"])
    if tracked:
        for t in tracked[:2]:
            val = t.get("value") or {}
            if isinstance(val, dict) and val.get("topic"):
                return {"name": "news_research", "topic": val["topic"], "type": "news"}
    # Default: research interesting global topics
    default_topics = [
        "artificial intelligence breakthroughs",
        "Portugal tecnologia",
        "ciência espaço",
        "economia global",
        "programação python",
    ]
    import random
    return {"name": "news_research", "topic": random.choice(default_topics), "type": "news"}

    # Priority 2: Explore registered sites for new content
    try:
        from .site_aggregator import list_sites
        sites = list_sites()
        if sites:
            import random
            site = random.choice(sites)
            return {"name": "site_explore", "url": site.get("url", ""), "type": "site"}
    except Exception:
        pass

    # Priority 3: Research topics from recent user queries (skip garbage)
    recent = store.tasks(20)
    research_topics = []
    _garbage = {"test", "query", "expire", "stale", "unique", "xyz", "benchmark", "debug"}
    for t in recent:
        if t.get("type") in ("research", "general", "web_search") and t.get("title"):
            title = t["title"].lower().strip()
            # Skip garbage test queries
            words = set(title.split())
            if len(title) > 10 and not words.intersection(_garbage):
                research_topics.append(title[:80])
    # If no real queries, use default interesting topics
    if not research_topics:
        research_topics = [
            "inteligência artificial 2026",
            "python machine learning",
            "tecnologia portugal",
            "ciência descobertas",
            "economia digital",
        ]
    if research_topics:
        import random
        return {"name": "topic_research", "query": random.choice(research_topics), "type": "research"}

    # Priority 4: Build knowledge graph from existing knowledge
    knowledge = store.mem_search("", kinds=["knowledge", "episode"])
    if knowledge and len(knowledge) > 5:
        return {"name": "knowledge_graph_build", "type": "graph"}

    # Priority 5: Pre-warm caches
    return {"name": "cache_warmup", "type": "cache"}


def _execute(task: dict) -> dict:
    """Execute a knowledge acquisition task."""
    task_type = task.get("type", "")

    if task_type == "news":
        return _do_news_research(task)
    elif task_type == "site":
        return _do_site_explore(task)
    elif task_type == "research":
        return _do_topic_research(task)
    elif task_type == "graph":
        return _do_graph_build(task)
    elif task_type == "cache":
        return _do_cache_warmup(task)

    return {"summary": "unknown task type"}


def _do_news_research(task: dict) -> dict:
    """Fetch news on a tracked topic."""
    try:
        from .news_connector import search_news
        topic = task.get("topic", "")
        news = search_news(topic, limit=5)
        if news.get("status") == "success" and news.get("results"):
            # Store findings
            store.mem_put("idle_research", f"news:{topic[:50]}", {
                "topic": topic,
                "n_results": news["n"],
                "headlines": [r.get("title", "") for r in news["results"][:3]],
                "ts": now_iso(),
            })
            return {"summary": f"news: {news['n']} resultados para '{topic[:30]}'"}
        return {"summary": f"news: sem resultados para '{topic[:30]}'"}
    except Exception as e:
        return {"summary": f"news error: {str(e)[:40]}"}


def _do_site_explore(task: dict) -> dict:
    """Fetch and analyze a registered site."""
    try:
        from .site_aggregator import fetch_site
        url = task.get("url", "")
        if not url:
            return {"summary": "site: no url"}
        r = fetch_site(url)
        if r.get("status") == "success":
            text = r.get("text", "")
            # Extract key info
            store.mem_put("site_content", f"site:{url[:50]}", {
                "url": url,
                "title": r.get("title", ""),
                "length": len(text),
                "ts": now_iso(),
            })
            return {"summary": f"site: {r.get('title', '')[:30]} ({len(text)} chars)"}
        return {"summary": f"site: fetch failed {url[:30]}"}
    except Exception as e:
        return {"summary": f"site error: {str(e)[:40]}"}


def _do_topic_research(task: dict) -> dict:
    """Research a topic from user's query history."""
    try:
        from .websearch import search as web_search
        query = task.get("query", "")
        if not query:
            return {"summary": "research: no query"}
        r = web_search(query, max_results=3)
        if r.get("status") == "success" and r.get("results"):
            store.mem_put("idle_research", f"web:{query[:50]}", {
                "query": query,
                "n_results": r["n"],
                "titles": [x.get("title", "") for x in r["results"][:3]],
                "ts": now_iso(),
            })
            return {"summary": f"research: {r['n']} resultados para '{query[:30]}'"}
        return {"summary": f"research: sem resultados para '{query[:30]}'"}
    except Exception as e:
        return {"summary": f"research error: {str(e)[:40]}"}


def _do_graph_build(task: dict) -> dict:
    """Build knowledge graph from existing knowledge."""
    try:
        from .knowledge_graph import extract_triples, store_triple
        knowledge = store.mem_search("", kinds=["knowledge", "episode"])
        triples_added = 0
        for k in knowledge[:10]:
            val = str(k.get("value") or "")
            triples = extract_triples(val)
            for t in triples:
                store_triple(t)
                triples_added += 1
        return {"summary": f"graph: {triples_added} triples adicionados"}
    except Exception as e:
        return {"summary": f"graph error: {str(e)[:40]}"}


def _do_cache_warmup(task: dict) -> dict:
    """Pre-warm caches with recent data."""
    try:
        from .embed import embed, cache_stats
        tasks = store.tasks(20)
        warmed = 0
        for t in tasks:
            title = t.get("title", "")
            if title:
                embed(title)
                warmed += 1
        stats = cache_stats()
        return {"summary": f"cache: {warmed} queries pre-warmed ({stats.get('cache_size', 0)} total)"}
    except Exception as e:
        return {"summary": f"cache error: {str(e)[:40]}"}
