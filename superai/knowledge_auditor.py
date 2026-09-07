"""Knowledge Auditor — analyse, criticise, summarise, and curate knowledge.

The auditor reviews ALL knowledge sources periodically:
- Idle worker research results
- Autonomous learner findings
- User interaction episodes
- News aggregation results
- Web search results

Process:
1. COLLECT: gather raw knowledge from last audit cycle
2. ANALYSE: score quality (freshness, coherence, utility, originality)
3. CRITICISE: identify duplicates, contradictions, low-quality
4. SUMMARISE: compress high-quality into dense summaries
5. CURATE: store in fine memory (kind="fine_memory")
6. PRUNE: delete low-quality raw knowledge to save space

Run cycle: every 120s (configurable).
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .events import bus
from .store import store
from .util import now_iso

_lock = threading.Lock()
_running = False
_audit_count = 0
_last_audit: dict = {}
_cycle_interval = 120  # Audit every 2 minutes

# Quality thresholds
MIN_QUALITY_SCORE = 40    # Below this → delete
FINE_MEMORY_THRESHOLD = 70  # Above this → fine memory
MAX_RAW_MEMORY = 500      # Max raw entries before aggressive pruning

# Knowledge kinds to audit
RAW_KINDS = [
    "idle_research", "site_content", "learner_finding",
    "interaction_pattern", "cached_web", "cached_github",
    "cached_news", "news_research", "topic_research",
]
FINE_KIND = "fine_memory"


def start(interval: int = 120) -> None:
    """Start the knowledge auditor."""
    global _running, _cycle_interval
    if _running:
        return
    _running = True
    _cycle_interval = interval

    def _loop():
        global _audit_count, _last_audit
        while _running:
            try:
                result = _run_audit_cycle()
                if result.get("audited", 0) > 0:
                    _audit_count += 1
                    _last_audit = result
                    bus.emit("AUDITOR", "DEBUG",
                             f"audit #{_audit_count}: {result.get('audited',0)} analisados, "
                             f"{result.get('promoted',0)} → memória fina, "
                             f"{result.get('pruned',0)} eliminados",
                             god_core_state="learning")
            except Exception as e:
                bus.emit("AUDITOR_ERROR", "WARNING", str(e))

            time.sleep(_cycle_interval)

    t = threading.Thread(target=_loop, name="god-auditor", daemon=True)
    t.start()


def stop() -> None:
    """Stop the auditor."""
    global _running
    _running = False


def status() -> dict:
    """Get auditor status."""
    fine = store.mem_search("", kinds=[FINE_KIND])
    raw_count = 0
    for kind in RAW_KINDS:
        items = store.mem_search("", kinds=[kind])
        raw_count += len(items)

    return {
        "kind": "MEASURED",
        "running": _running,
        "audit_count": _audit_count,
        "last_audit": _last_audit,
        "fine_memory_count": len(fine),
        "raw_knowledge_count": raw_count,
        "cycle_interval_s": _cycle_interval,
        "ts": now_iso(),
    }


def force_audit() -> dict:
    """Force an immediate audit cycle."""
    result = _run_audit_cycle()
    global _audit_count, _last_audit
    _audit_count += 1
    _last_audit = result
    return result


# ─── Core audit cycle ───────────────────────────────────────────

def _run_audit_cycle() -> dict:
    """Run one full audit cycle."""
    collected = _collect_raw_knowledge()
    if not collected:
        return {"audited": 0, "promoted": 0, "pruned": 0, "ts": now_iso()}

    analysed = []
    for item in collected:
        score = _score_quality(item)
        item["_quality_score"] = score
        analysed.append(item)

    # Sort by quality (highest first)
    analysed.sort(key=lambda x: x.get("_quality_score", 0), reverse=True)

    promoted = 0
    pruned = 0
    kept = 0

    for item in analysed:
        score = item.get("_quality_score", 0)

        if score >= FINE_MEMORY_THRESHOLD:
            # PROMOTE to fine memory
            _promote_to_fine(item)
            promoted += 1

        elif score < MIN_QUALITY_SCORE:
            # PRUNE low quality
            _prune(item)
            pruned += 1

        else:
            # KEEP as-is (medium quality)
            kept += 1

    # If too many raw entries, prune oldest low-scoring
    raw_count = sum(1 for i in analysed if i.get("_quality_score", 0) >= MIN_QUALITY_SCORE)
    if raw_count > MAX_RAW_MEMORY:
        excess = raw_count - MAX_RAW_MEMORY
        low_items = [i for i in analysed if MIN_QUALITY_SCORE <= i.get("_quality_score", 0) < 50]
        for item in low_items[:excess]:
            _prune(item)
            pruned += 1

    # Generate audit summary
    summary = _generate_audit_summary(analysed)

    return {
        "audited": len(analysed),
        "promoted": promoted,
        "pruned": pruned,
        "kept": kept,
        "avg_quality": round(sum(i.get("_quality_score", 0) for i in analysed) / max(len(analysed), 1), 1),
        "summary": summary,
        "ts": now_iso(),
    }


def _collect_raw_knowledge() -> list[dict]:
    """Collect all raw knowledge for audit."""
    items = []
    for kind in RAW_KINDS:
        found = store.mem_search("", kinds=[kind])
        for f in found:
            f["_source_kind"] = kind
            items.append(f)
    return items


def _score_quality(item: dict) -> int:
    """Score knowledge quality 0-100.

    Criteria:
    - Freshness (20pts): newer = better
    - Content depth (25pts): longer, richer content = better
    - Coherence (20pts): well-structured = better
    - Utility (20pts): actionable info = better
    - Originality (15pts): unique = better
    """
    score = 0
    value = item.get("value") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {"raw": value}

    # --- Freshness (0-20) ---
    ts = item.get("ts", "")
    if ts:
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_hours = (now - created).total_seconds() / 3600
            if age_hours < 1:
                score += 20
            elif age_hours < 6:
                score += 15
            elif age_hours < 24:
                score += 10
            elif age_hours < 72:
                score += 5
        except Exception:
            pass

    # --- Content depth (0-25) ---
    content = str(value)
    depth = len(content)
    if depth > 500:
        score += 25
    elif depth > 200:
        score += 20
    elif depth > 100:
        score += 15
    elif depth > 50:
        score += 10
    elif depth > 20:
        score += 5

    # --- Coherence (0-20) ---
    # Check for structured data
    if isinstance(value, dict):
        n_keys = len(value)
        if n_keys >= 4:
            score += 20
        elif n_keys >= 3:
            score += 15
        elif n_keys >= 2:
            score += 10
        elif n_keys >= 1:
            score += 5
    elif isinstance(value, list) and len(value) > 0:
        score += 10

    # --- Utility (0-20) ---
    # Check for actionable indicators
    actionable_keys = {"url", "title", "headlines", "query", "results", "summary", "topics", "scores"}
    if isinstance(value, dict):
        matches = len(set(value.keys()) & actionable_keys)
        score += min(matches * 5, 20)

    # --- Originality (0-15) ---
    # Check if similar content already in fine memory
    key = item.get("key", "")
    existing_fine = store.mem_search(key[:50], kinds=[FINE_KIND])
    if not existing_fine:
        score += 15  # Unique = full points
    elif len(existing_fine) == 1:
        score += 8   # Some overlap
    else:
        score += 3   # Lots of overlap

    return min(score, 100)


def _promote_to_fine(item: dict) -> None:
    """Promote knowledge to fine memory with summary."""
    value = item.get("value") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {"raw": value}

    key = item.get("key", "unknown")
    source = item.get("_source_kind", "unknown")

    # Generate dense summary
    summary = _summarise(value)

    # Check if already in fine memory (avoid duplicates)
    existing = store.mem_search(key[:50], kinds=[FINE_KIND])
    if existing:
        # Update existing with richer data
        for e in existing:
            old_val = e.get("value") or {}
            if isinstance(old_val, str):
                try:
                    old_val = json.loads(old_val)
                except Exception:
                    old_val = {}
            # Merge
            merged = {**old_val, **summary}
            merged["promoted_from"] = source
            merged["quality_score"] = item.get("_quality_score", 0)
            merged["last_updated"] = now_iso()
            store.mem_put(FINE_KIND, e.get("key", key), merged)
        return

    # New fine memory entry
    fine_entry = {
        **summary,
        "promoted_from": source,
        "quality_score": item.get("_quality_score", 0),
        "original_key": key,
        "ts": now_iso(),
    }
    store.mem_put(FINE_KIND, f"fine:{key[:80]}", fine_entry)


def _summarise(value: dict) -> dict:
    """Create dense summary from knowledge value."""
    summary = {}

    # Extract core facts
    if isinstance(value, dict):
        # Keep meaningful fields
        keep_keys = {"topic", "query", "title", "headlines", "url",
                     "n_results", "scores", "topics", "results",
                     "summary", "length", "titles"}
        for k in keep_keys:
            if k in value and value[k]:
                val = value[k]
                # Truncate long lists
                if isinstance(val, list) and len(val) > 5:
                    val = val[:5]
                # Truncate long strings
                if isinstance(val, str) and len(val) > 200:
                    val = val[:200] + "..."
                summary[k] = val

        # Extract key insights
        if "headlines" in value and isinstance(value["headlines"], list):
            summary["key_facts"] = [h[:100] for h in value["headlines"][:3]]

        if "titles" in value and isinstance(value["titles"], list):
            summary["key_facts"] = [t[:100] for t in value["titles"][:3]]

    return summary if summary else {"content": str(value)[:200]}


def _prune(item: dict) -> None:
    """Remove low-quality knowledge (mark for deletion).

    Note: We don't actually delete from SQLite here because
    mem_search doesn't support delete by key. Instead we
    overwrite with a tombstone marker.
    """
    key = item.get("key", "")
    kind = item.get("_source_kind", "")
    if key and kind:
        store.mem_put(kind, key, {"_pruned": True, "pruned_at": now_iso()})


def _generate_audit_summary(items: list[dict]) -> str:
    """Generate human-readable audit summary."""
    if not items:
        return "Sem conhecimento novo para auditar."

    high = sum(1 for i in items if i.get("_quality_score", 0) >= FINE_MEMORY_THRESHOLD)
    mid = sum(1 for i in items if MIN_QUALITY_SCORE <= i.get("_quality_score", 0) < FINE_MEMORY_THRESHOLD)
    low = sum(1 for i in items if i.get("_quality_score", 0) < MIN_QUALITY_SCORE)

    parts = []
    if high:
        parts.append(f"{high} promovidos para memória fina")
    if mid:
        parts.append(f"{mid} mantidos")
    if low:
        parts.append(f"{low} eliminados (baixa qualidade)")

    return ", ".join(parts) if parts else "Nenhuma acção necessária."


# ─── Fine memory access ─────────────────────────────────────────

def fine_memory_search(query: str, limit: int = 10) -> list[dict]:
    """Search fine memory specifically."""
    return store.mem_search(query, limit=limit, kinds=[FINE_KIND])


def fine_memory_list(limit: int = 50) -> list[dict]:
    """List all fine memory entries."""
    return store.mem_search("", limit=limit, kinds=[FINE_KIND])
