"""Evidence Engine — separate CLAIMS from EVIDENCE.

Never accept a claim as true just because the LLM has high confidence.
Every claim should have: source, validation, result.

CLAIM → SOURCE → VALIDATION → RESULT
"""
from __future__ import annotations

import threading
from .util import now_iso, uid
from .store import store

_lock = threading.Lock()
_evidence_store: dict[str, list[dict]] = {}  # claim_id → [evidence]


class Claim:
    """A structured claim with evidence tracking."""

    def __init__(self, text: str, source: str, confidence: float = 0.5):
        self.id = uid("claim")
        self.text = text
        self.source = source
        self.confidence = confidence
        self.evidence: list[dict] = []
        self.validation_status = "unvalidated"  # unvalidated, supported, refuted, uncertain
        self.created_at = now_iso()
        self.validated_at: str | None = None

    def add_evidence(self, evidence_type: str, data: str, strength: float = 0.5) -> dict:
        """Add evidence for or against this claim."""
        ev = {
            "id": uid("ev"),
            "claim_id": self.id,
            "type": evidence_type,  # "supporting", "refuting", "neutral"
            "data": data[:2000],
            "strength": strength,  # 0-1
            "ts": now_iso(),
        }
        self.evidence.append(ev)
        self._update_validation()
        # Persist
        with _lock:
            if self.id not in _evidence_store:
                _evidence_store[self.id] = []
            _evidence_store[self.id].append(ev)
        try:
            store.mem_put("evidence", self.id, {
                "claim": self.text, "source": self.source,
                "evidence": self.evidence, "status": self.validation_status,
                "confidence": self.confidence,
            })
        except Exception:
            pass
        return ev

    def _update_validation(self) -> None:
        """Update validation status based on evidence."""
        if not self.evidence:
            self.validation_status = "unvalidated"
            return
        supporting = sum(e["strength"] for e in self.evidence if e["type"] == "supporting")
        refuting = sum(e["strength"] for e in self.evidence if e["type"] == "refuting")
        total = supporting + refuting
        if total == 0:
            self.validation_status = "uncertain"
            return
        ratio = supporting / total
        if ratio >= 0.7:
            self.validation_status = "supported"
        elif ratio <= 0.3:
            self.validation_status = "refuted"
        else:
            self.validation_status = "uncertain"
        self.validated_at = now_iso()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "text": self.text, "source": self.source,
            "confidence": self.confidence, "evidence": self.evidence,
            "validation_status": self.validation_status,
            "created_at": self.created_at, "validated_at": self.validated_at,
            "n_evidence": len(self.evidence),
        }


def create_claim(text: str, source: str, confidence: float = 0.5) -> Claim:
    """Create a new claim."""
    return Claim(text, source, confidence)


def validate_claim_from_tools(claim_text: str, tool_results: list[dict]) -> dict:
    """Validate a claim using tool results as evidence."""
    claim = create_claim(claim_text, "pipeline", confidence=0.5)

    for result in tool_results:
        status = result.get("status", "")
        findings = result.get("findings") or []
        errors = result.get("errors") or []
        tool_name = result.get("tool", "unknown")

        if status == "success" and findings:
            for f in findings[:3]:
                if isinstance(f, dict):
                    data = f.get("text") or f.get("title") or str(f)
                else:
                    data = str(f)
                claim.add_evidence("supporting", f"[{tool_name}] {data}", strength=0.7)
        elif status == "success" and not findings:
            claim.add_evidence("neutral", f"[{tool_name}] no findings", strength=0.3)
        elif errors:
            for err in errors[:2]:
                claim.add_evidence("refuting", f"[{tool_name}] {err}", strength=0.5)

    return claim.to_dict()


def get_evidence_summary(claim_id: str) -> dict:
    """Get evidence summary for a claim."""
    with _lock:
        evidence = _evidence_store.get(claim_id, [])
    if not evidence:
        try:
            stored = store.cache_get(f"evidence:{claim_id}")
            if stored:
                return stored.get("result", {})
        except Exception:
            pass
        return {"claim_id": claim_id, "found": False}
    supporting = [e for e in evidence if e["type"] == "supporting"]
    refuting = [e for e in evidence if e["type"] == "refuting"]
    return {
        "claim_id": claim_id, "found": True,
        "n_evidence": len(evidence),
        "n_supporting": len(supporting),
        "n_refuting": len(refuting),
        "avg_strength": sum(e["strength"] for e in evidence) / len(evidence) if evidence else 0,
    }
