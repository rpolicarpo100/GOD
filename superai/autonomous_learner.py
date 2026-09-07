"""Autonomous Learner — GOD learns when nobody is talking.

Runs in background during idle time. No user interaction needed.
Cycles every 5 minutes when idle, every 30 seconds when busy.

What it does each cycle:
1. ANALYZE: Review recent interactions, extract patterns
2. LEARN: Build knowledge graph, update adaptive routing
3. EVOLVE: Generate experiments, auto-apply low-risk ones
4. REFRESH: Pre-warm caches, check news for tracked topics
5. REPORT: Emit events for UI (no user-facing messages)
"""
from __future__ import annotations

import threading
import time

from .events import bus
from .store import store
from .util import now_iso

_lock = threading.Lock()
_running = False
_cycle_count = 0
_last_cycle: dict = {}
_learned_facts: list[dict] = []


def start(interval_idle: float = 300, interval_busy: float = 30) -> None:
    """Start the autonomous learner background loop.
    
    interval_idle: seconds between cycles when no user activity (default 5min)
    interval_busy: seconds between cycles when user is active (default 30s)
    """
    global _running
    if _running:
        return
    _running = True

    def _loop():
        global _cycle_count, _last_cycle
        while _running:
            try:
                # Determine interval based on activity
                from .runtime import _chat
                has_recent = False
                try:
                    with _lock:
                        if _chat:
                            last_msg = _chat[-1] if _chat else {}
                            # Check if last message is recent (< 2 min ago)
                            import datetime
                            ts_str = last_msg.get("ts", "")
                            if ts_str:
                                last_ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                now = datetime.datetime.now(datetime.timezone.utc)
                                has_recent = (now - last_ts).total_seconds() < 120
                except Exception:
                    pass

                interval = interval_busy if has_recent else interval_idle

                # Run learning cycle
                cycle_result = _run_cycle()
                _cycle_count += 1
                _last_cycle = {
                    "n": _cycle_count,
                    "ts": now_iso(),
                    "interval": interval,
                    "has_recent_activity": has_recent,
                    **cycle_result,
                }

                bus.emit("LEARN_CYCLE", "DEBUG",
                         f"cycle {_cycle_count}: {cycle_result.get('summary', 'ok')}",
                         god_core_state="learning")

            except Exception as e:
                bus.emit("LEARN_ERROR", "WARNING", str(e))

            time.sleep(interval)

    t = threading.Thread(target=_loop, name="god-learner", daemon=True)
    t.start()


def stop() -> None:
    """Stop the autonomous learner."""
    global _running
    _running = False


def status() -> dict:
    """Get learner status."""
    return {
        "kind": "MEASURED",
        "running": _running,
        "cycle_count": _cycle_count,
        "last_cycle": _last_cycle,
        "learned_facts": len(_learned_facts),
        "ts": now_iso(),
    }


def _run_cycle() -> dict:
    """Execute one learning cycle."""
    result = {"phases": {}}

    # Phase 1: ANALYZE — review recent interactions
    analysis = _phase_analyze()
    result["phases"]["analyze"] = analysis

    # Phase 2: LEARN — extract and store knowledge
    learning = _phase_learn(analysis)
    result["phases"]["learn"] = learning

    # Phase 3: EVOLVE — generate and apply experiments
    evolution = _phase_evolve()
    result["phases"]["evolve"] = evolution

    # Phase 4: REFRESH — warm caches
    refresh = _phase_refresh()
    result["phases"]["refresh"] = refresh

    # Summary
    total_learned = learning.get("facts_extracted", 0)
    total_evolved = evolution.get("experiments", 0)
    result["summary"] = f"learned={total_learned} evolved={total_evolved} refreshed={refresh.get('items', 0)}"

    return result


def _phase_analyze() -> dict:
    """Phase 1: Analyze recent interactions for patterns."""
    try:
        tasks = store.tasks(30)
        if not tasks:
            return {"tasks_analyzed": 0}

        # Analyze task distribution
        type_counts: dict[str, int] = {}
        via_counts: dict[str, int] = {}
        quality_scores: list[float] = []
        failed_tasks: list[dict] = []

        for t in tasks:
            ttype = t.get("type", "general")
            type_counts[ttype] = type_counts.get(ttype, 0) + 1
            via = t.get("via", "unknown")
            via_counts[via] = via_counts.get(via, 0) + 1
            if t.get("rating", {}).get("OVERALL"):
                quality_scores.append(t["rating"]["OVERALL"])
            if t.get("status") in ("failed", "blocked"):
                failed_tasks.append({"type": ttype, "via": via, "title": t.get("title", "")[:60]})

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # Find patterns
        patterns = []
        most_common_type = max(type_counts, key=type_counts.get) if type_counts else "none"
        if type_counts.get(most_common_type, 0) > len(tasks) * 0.4:
            patterns.append(f"dominant_task_type={most_common_type}")

        if avg_quality < 60 and len(quality_scores) >= 5:
            patterns.append(f"quality_below_threshold={avg_quality:.0f}")

        if len(failed_tasks) >= 3:
            patterns.append(f"frequent_failures={len(failed_tasks)}")

        return {
            "tasks_analyzed": len(tasks),
            "type_distribution": type_counts,
            "via_distribution": via_counts,
            "avg_quality": round(avg_quality, 1),
            "n_quality_scores": len(quality_scores),
            "failed_tasks": failed_tasks[:5],
            "patterns": patterns,
        }
    except Exception as e:
        return {"error": str(e)}


def _phase_learn(analysis: dict) -> dict:
    """Phase 2: Extract and store knowledge from analysis."""
    facts = 0

    try:
        # Learn task type distribution
        for ttype, count in (analysis.get("type_distribution") or {}).items():
            if count >= 3:
                store.mem_put("learned_pattern", f"task_freq:{ttype}",
                             {"type": ttype, "count": count, "ts": now_iso()})
                facts += 1

        # Learn quality patterns
        avg_q = analysis.get("avg_quality", 0)
        if avg_q > 0:
            store.mem_put("learned_pattern", "quality_trend",
                         {"avg_quality": avg_q, "n": analysis.get("n_quality_scores", 0), "ts": now_iso()})
            facts += 1

        # Learn from failures
        for fail in (analysis.get("failed_tasks") or [])[:3]:
            store.mem_put("learned_failure", f"fail:{fail['type']}:{fail['via']}",
                         {"type": fail["type"], "via": fail["via"], "title": fail["title"], "ts": now_iso()})
            facts += 1

        # Extract knowledge from recent interactions
        try:
            from .pipeline import _extract_and_store_knowledge
            tasks = store.tasks(10)
            for t in tasks:
                if t.get("status") == "done" and t.get("title"):
                    # Re-extract knowledge from completed tasks
                    _extract_and_store_knowledge(
                        t.get("title", ""),
                        str(t.get("result_summary", "")),
                        t
                    )
                    facts += 1
        except Exception:
            pass

        # Update adaptive routing from ratings
        try:
            from . import adaptive_routing
            import json
            with store._lock, store._conn() as c:
                rows = c.execute(
                    "SELECT task_id, scores FROM ratings ORDER BY ts DESC LIMIT 20"
                ).fetchall()
            for row in rows:
                try:
                    scores = json.loads(row["scores"]) if isinstance(row["scores"], str) else row["scores"]
                    # We need task type — look it up
                    task = next((t for t in store.tasks(50) if t.get("task_id") == row["task_id"]), None)
                    if task and task.get("via"):
                        provider = task.get("via")
                        ttype = task.get("type", "general")
                        overall = scores.get("OVERALL", 50) / 100.0
                        adaptive_routing.record_quality(provider, ttype, overall)
                except Exception:
                    pass
        except Exception:
            pass

        # Build knowledge graph from preferences
        try:
            from .knowledge_graph import extract_triples, store_triple
            knowledge = store.mem_search("", kinds=["knowledge"])
            for k in knowledge[:10]:
                val = str(k.get("value") or "")
                triples = extract_triples(val)
                for t in triples:
                    store_triple(t)
                    facts += 1
        except Exception:
            pass

        with _lock:
            _learned_facts.append({"ts": now_iso(), "facts": facts})
            if len(_learned_facts) > 100:
                _learned_facts.pop(0)

    except Exception as e:
        return {"facts_extracted": facts, "error": str(e)}

    return {"facts_extracted": facts}


def _phase_evolve() -> dict:
    """Phase 3: Generate and auto-apply experiments."""
    try:
        from .evolution import generate_usage_experiments
        from .feature_flags import is_enabled

        # Generate experiments from usage patterns
        experiments = generate_usage_experiments()

        applied = 0
        if is_enabled("auto_evolve"):
            # Auto-apply LOW risk experiments
            from .evolution import _auto_apply_pending
            _auto_apply_pending()
            applied = len([e for e in store.experiments(20) if e.get("adopted_by") == "auto_evolve"])

        return {
            "experiments": len(experiments),
            "auto_applied": applied,
        }
    except Exception as e:
        return {"experiments": 0, "error": str(e)}


def _phase_refresh() -> dict:
    """Phase 4: Refresh caches, pre-warm, monitor tracked topics."""
    items = 0

    try:
        # Pre-warm embedding cache with recent queries
        from .embed import embed, cache_stats
        recent_tasks = store.tasks(10)
        for t in recent_tasks:
            title = t.get("title", "")
            if title:
                embed(title)
                items += 1

        embed_stats = cache_stats()

        # Pre-warm intent classification
        try:
            from .brain import _classify_by_embedding
            _classify_by_embedding("warmup")
            items += 1
        except Exception:
            pass

        # ═══ NEWS MONITORING ═══
        # Track topics the user has asked about and fetch updates
        try:
            _monitor_tracked_topics()
            items += 1
        except Exception:
            pass

        return {
            "items": items,
            "embedding_cache": embed_stats.get("cache_size", 0),
        }
    except Exception as e:
        return {"items": items, "error": str(e)}


def _monitor_tracked_topics() -> None:
    """Monitor news for topics the user has asked about.
    
    Extracts topics from recent user queries, checks news API for updates,
    and stores new findings for the user to see next time they ask.
    """
    try:
        from .news_connector import search_news

        # Get recent user queries to learn what topics interest them
        recent = store.tasks(20)
        user_topics: dict[str, int] = {}

        for t in recent:
            if t.get("type") in ("news", "research", "general"):
                title = (t.get("title") or "").lower().strip()
                if len(title) > 5:
                    # Extract key terms (simple: most frequent non-stop words)
                    words = title.split()
                    for w in words:
                        w = w.strip('.,;:!?"\' \t')
                        if len(w) > 3 and w not in ("como", "qual", "sobre", "para", "com", "that", "what", "this"):
                            user_topics[w] = user_topics.get(w, 0) + 1

        if not user_topics:
            return

        # Get top 3 topics
        top_topics = sorted(user_topics.items(), key=lambda x: x[1], reverse=True)[:3]

        for topic, count in top_topics:
            if count < 2:  # Only track if asked about 2+ times
                continue

            # Check news for this topic
            news = search_news(topic, limit=3)
            if news.get("status") == "success" and news.get("results"):
                # Store as tracked update
                store.mem_put("tracked_topic", f"news:{topic}", {
                    "topic": topic,
                    "asked_count": count,
                    "latest_news": [
                        {"title": n.get("title"), "verification": n.get("verification")}
                        for n in news["results"][:3]
                    ],
                    "ts": now_iso(),
                })
    except Exception:
        pass
