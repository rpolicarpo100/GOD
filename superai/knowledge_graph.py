"""Knowledge Graph — Extract and query SPO triples from interactions.

Simple subject-predicate-object graph stored in SQLite memory table.
No external graph database needed — queries are in-memory with index.
"""
from __future__ import annotations

import re
import threading
from typing import Any

from .store import store
from .util import now_iso, sha

_lock = threading.Lock()

# In-memory graph: {(subject, predicate): [objects]}
_graph: dict[tuple[str, str], list[str]] = {}
_graph_loaded = False

# Common predicates
PREDICATES = {
    "prefers": r"prefiro|prefere|gosto de|gosta de|quero|quer",
    "uses": r"utilizo|utiliza| usa |trabalho com|trabalha com",
    "knows": r" sei |sabe |conheço|conhece|entendo|entende",
    "dislikes": r"não gosto|não gosta|odeio|odeia|evito|evita",
    "type": r"é um|é uma|tipo de",
    "language": r"em (português|inglês|espanhol|francês)",
    "style": r"curto|longo|detalhado|resumido|técnico|simples",
}


def _load_graph() -> None:
    """Load persisted triples from store."""
    global _graph_loaded
    if _graph_loaded:
        return
    _graph_loaded = True
    try:
        # Load from memory table
        with store._lock, store._conn() as c:
            rows = c.execute(
                "SELECT key, value FROM memory WHERE kind = 'knowledge_graph'"
            ).fetchall()
        for r in rows:
            try:
                import json
                data = json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]
                if isinstance(data, dict):
                    subj = data.get("subject", "")
                    pred = data.get("predicate", "")
                    obj = data.get("object", "")
                    if subj and pred and obj:
                        key = (subj.lower(), pred.lower())
                        if key not in _graph:
                            _graph[key] = []
                        if obj not in _graph[key]:
                            _graph[key].append(obj)
            except Exception:
                pass
    except Exception:
        pass


def extract_triples(text: str) -> list[dict]:
    """Extract SPO triples from text using pattern matching."""
    triples = []
    low = text.lower()
    
    # Pattern: "User prefers/likes Python" style
    for pred, pattern in PREDICATES.items():
        m = re.search(pattern, low)
        if m:
            # Try to extract subject and object
            before = low[:m.start()].strip()
            after = low[m.end():].strip()
            
            # Subject is usually before the predicate
            subject = _extract_subject(before) or "user"
            # Object is usually after the predicate
            obj = _extract_object(after)
            
            if obj:
                triples.append({
                    "subject": subject,
                    "predicate": pred,
                    "object": obj,
                    "source": text[:100],
                    "ts": now_iso(),
                })
    
    # Pattern: "X is Y" / "X é Y"
    for m in re.finditer(r"(\w+)\s+(?:é|is)\s+(?:um|uma|a|o)?\s*(\w+)", low):  # noqa: W605
        subj = m.group(1).strip()
        obj = m.group(2).strip()
        if len(subj) > 2 and len(obj) > 2:
            triples.append({
                "subject": subj,
                "predicate": "type",
                "object": obj,
                "source": text[:100],
                "ts": now_iso(),
            })
    
    return triples


def _extract_subject(before: str) -> str:
    """Extract subject from text before predicate."""
    # Common subjects
    for s in ["eu", "user", "utilizador", "god", "sistema"]:
        if s in before:
            return s
    # Last noun-like word
    words = before.split()
    return words[-1] if words else "user"


def _extract_object(after: str) -> str:
    """Extract object from text after predicate."""
    # Clean up
    after = after.strip(".,;:!?")
    if not after:
        return ""
    # Take up to next punctuation or conjunction
    m = re.match(r"([^,;.]+)", after)
    return m.group(1).strip() if m else after[:50]


def store_triple(triple: dict) -> None:
    """Persist a triple to the knowledge graph."""
    subj = triple.get("subject", "").lower()
    pred = triple.get("predicate", "").lower()
    obj = triple.get("object", "")
    
    if not subj or not pred or not obj:
        return
    
    # Update in-memory
    with _lock:
        key = (subj, pred)
        if key not in _graph:
            _graph[key] = []
        if obj not in _graph[key]:
            _graph[key].append(obj)
    
    # Persist
    try:
        triple_id = sha(f"{subj}:{pred}:{obj}")
        store.mem_put("knowledge_graph", triple_id, triple)
    except Exception:
        pass


def query(subject: str = "", predicate: str = "") -> list[dict]:
    """Query the knowledge graph."""
    _load_graph()
    results = []
    
    with _lock:
        for (s, p), objects in _graph.items():
            if subject and subject.lower() not in s:
                continue
            if predicate and predicate.lower() not in p:
                continue
            for obj in objects:
                results.append({"subject": s, "predicate": p, "object": obj})
    
    return results


def get_user_preferences() -> dict:
    """Get all known user preferences."""
    _load_graph()
    prefs = {}
    with _lock:
        for (s, p), objects in _graph.items():
            if p in ("prefers", "likes", "language", "style"):
                prefs[p] = objects
    return prefs


def enrich_context(text: str, task_type: str) -> str:
    """Enrich LLM context with relevant knowledge graph facts."""
    _load_graph()
    facts = []
    
    # Get user preferences
    prefs = get_user_preferences()
    if prefs:
        for pred, objs in prefs.items():
            facts.append(f"User {pred}: {', '.join(objs[:3])}")
    
    # Get task-type relevant facts
    with _lock:
        for (s, p), objects in _graph.items():
            if task_type in s or task_type in p:
                for obj in objects[:2]:
                    facts.append(f"{s} {p} {obj}")
    
    if facts:
        return "KNOWLEDGE:\n" + "\n".join(f"- {f}" for f in facts[:5])
    return ""


def stats() -> dict:
    """Knowledge graph statistics."""
    _load_graph()
    with _lock:
        n_triples = sum(len(objs) for objs in _graph.values())
        n_subjects = len(set(s for s, _ in _graph.keys()))
        n_predicates = len(set(p for _, p in _graph.keys()))
        return {
            "kind": "MEASURED",
            "triples": n_triples,
            "subjects": n_subjects,
            "predicates": n_predicates,
            "ts": now_iso(),
        }
