from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def count_tokens(text: str) -> dict:
    raw = text or ""
    n = len(ENC.encode(raw))
    return {"tokens": n, "method": "tiktoken cl100k_base", "verified": True, "chars": len(raw)}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_STOP = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "um", "uma",
    "deste", "desta", "este", "esta", "the", "of", "please", "por", "favor",
    "podes", "me", "faz",
}


def normalize_query(q: str) -> str:
    q = (q or "").lower().strip()
    q = re.sub(r"[^\w\s]+", " ", q, flags=re.UNICODE)
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"\bfaz uma an[aá]lise\b", "analisa", q)
    q = re.sub(r"\ban[aá]lise\b", "analisa", q)
    toks = [t for t in q.split() if t not in _STOP]
    return " ".join(toks)
