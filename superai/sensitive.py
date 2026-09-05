"""P2.1 — Sensitive Data Detection.

Detects and protects:
- Passwords (plaintext detection)
- API keys (format-based detection)
- Tokens (JWT, Bearer, etc.)
- Credit cards (Luhn validation)
- Personal data (CPF, SSN, etc.)
- Connection strings (database URLs)
- Private keys (PEM, SSH)

Never stores detected data. Only reports risk.
"""
from __future__ import annotations

import re
from typing import Any

from .util import now_iso

# ═══════════════════════════════
# DETECTION PATTERNS
# ═══════════════════════════════

_PATTERNS = {
    "password_assignment": re.compile(
        r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{4,})',
        re.IGNORECASE,
    ),
    "password_in_text": re.compile(
        r'(?i)(?:senha|password|passwd|pwd)[:\s]+([^\s]{4,})',
        re.IGNORECASE,
    ),
    "api_key": re.compile(
        r'(?i)(api[_-]?key|apikey|api[_-]?secret)\s*[=:]\s*["\']?([A-Za-z0-9\-_]{16,})',
        re.IGNORECASE,
    ),
    "bearer_token": re.compile(
        r'(?i)(bearer|authorization)\s*[:=]\s*["\']?([A-Za-z0-9\-_.]{20,})',
        re.IGNORECASE,
    ),
    "jwt": re.compile(
        r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+',
    ),
    "private_key": re.compile(
        r'-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----',
        re.IGNORECASE,
    ),
    "connection_string": re.compile(
        r'(?i)(postgres|mysql|mongodb|redis|sqlite):\/\/[^\s"\']+',
    ),
    "credit_card": re.compile(
        r'\b(?:\d[ -]*?){13,19}\b',
    ),
    "cpf": re.compile(
        r'\b\d{3}[\.]?\d{3}[\.]?\d{3}[-]?\d{2}\b',
    ),
    "ssn": re.compile(
        r'\b\d{3}[-]?\d{2}[-]?\d{4}\b',
    ),
    "ssh_key": re.compile(
        r'ssh-(?:rsa|ed25519|dss)\s+[A-Za-z0-9+/=]{40,}',
    ),
    "aws_key": re.compile(
        r'(?i)(AKIA|ASIA)[A-Z0-9]{16}',
    ),
    "github_token": re.compile(
        r'gh[ps]_[A-Za-z0-9_]{36,}',
    ),
}

# High-confidence patterns (no false positives)
_HIGH_CONFIDENCE = {"private_key", "jwt", "aws_key", "github_token", "ssh_key"}

# Patterns that need context (may have false positives)
_CONTEXT_REQUIRED = {"credit_card", "cpf", "ssn"}


def scan_text(text: str) -> list[dict]:
    """Scan text for sensitive data. Returns list of detections.
    
    Each detection: {type, risk, context (truncated), line_number}
    Never returns the actual sensitive data.
    """
    if not text:
        return []
    
    detections = []
    lines = text.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        for pattern_name, pattern in _PATTERNS.items():
            matches = pattern.finditer(line)
            for m in matches:
                risk = _assess_risk(pattern_name, m.group())
                detections.append({
                    "type": pattern_name,
                    "risk": risk,
                    "line": line_num,
                    "context": _mask_context(line, m.start(), m.end()),
                    "kind": "MEASURED",
                })
    
    return detections


def scan_file(path: str) -> dict:
    """Scan a file for sensitive data."""
    from pathlib import Path
    
    p = Path(path)
    if not p.exists():
        return {"kind": "MEASURED", "exists": False, "detections": []}
    
    try:
        text = p.read_text(errors='ignore')
        detections = scan_text(text)
        return {
            "kind": "MEASURED",
            "exists": True,
            "path": str(p),
            "size": p.stat().st_size,
            "detections": detections,
            "has_sensitive": len(detections) > 0,
            "risk_score": max((d["risk"] for d in detections), default=0),
        }
    except Exception as e:
        return {"kind": "MEASURED", "exists": True, "error": str(e), "detections": []}


def scan_task_content(task: dict) -> dict:
    """Scan task text and params for sensitive data."""
    parts = []
    
    # Scan task text
    if task.get("text"):
        parts.append(("text", scan_text(task["text"])))
    
    # Scan task params
    params = task.get("params") or {}
    for key, value in params.items():
        if isinstance(value, str):
            parts.append((f"param:{key}", scan_text(value)))
    
    all_detections = []
    for source, detections in parts:
        for d in detections:
            d["source"] = source
            all_detections.append(d)
    
    return {
        "kind": "MEASURED",
        "task_id": task.get("task_id"),
        "detections": all_detections,
        "has_sensitive": len(all_detections) > 0,
        "risk_score": max((d["risk"] for d in all_detections), default=0),
        "recommendation": _get_recommendation(all_detections),
    }


def scan_tool_output(tool_name: str, output: str) -> dict:
    """Scan tool output for leaked sensitive data."""
    detections = scan_text(output)
    
    # Tool output leaking sensitive data is higher risk
    for d in detections:
        d["risk"] = min(d["risk"] + 2, 5)
        d["source"] = f"tool:{tool_name}"
    
    return {
        "kind": "MEASURED",
        "tool": tool_name,
        "detections": detections,
        "has_sensitive": len(detections) > 0,
        "risk_score": max((d["risk"] for d in detections), default=0),
    }


def _assess_risk(pattern_name: str, match: str) -> int:
    """Assess risk level (0-5)."""
    if pattern_name in _HIGH_CONFIDENCE:
        return 5
    if pattern_name in {"password_assignment", "password_in_text", "connection_string"}:
        return 5
    if pattern_name in {"api_key", "bearer_token"}:
        return 4
    if pattern_name in _CONTEXT_REQUIRED:
        # Validate format before high risk
        if pattern_name == "credit_card":
            digits = re.sub(r'\D', '', match)
            if len(digits) in (13, 15, 16) and _luhn_valid(digits):
                return 4
            return 1  # Probably not a real credit card
        if pattern_name == "cpf":
            digits = re.sub(r'\D', '', match)
            if _cpf_valid(digits):
                return 4
            return 1
        return 3
    return 3


def _luhn_valid(number: str) -> bool:
    """Luhn algorithm for credit card validation."""
    digits = [int(d) for d in number]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10 == 0


def _cpf_valid(cpf: str) -> bool:
    """Validate Brazilian CPF."""
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False
    
    # First digit
    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digit1 = (total * 10 % 11) % 10
    if int(cpf[9]) != digit1:
        return False
    
    # Second digit
    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digit2 = (total * 10 % 11) % 10
    return int(cpf[10]) == digit2


def _mask_context(line: str, start: int, end: int) -> str:
    """Mask the sensitive part, show context around it."""
    before = line[max(0, start - 10):start]
    after = line[end:min(len(line), end + 10)]
    return f"{before}***{after}"


def _get_recommendation(detections: list[dict]) -> str:
    """Get recommendation based on detections."""
    if not detections:
        return "No sensitive data detected"
    
    max_risk = max(d["risk"] for d in detections)
    
    if max_risk >= 5:
        return "BLOCK: Contains high-risk sensitive data (keys, passwords)"
    if max_risk >= 4:
        return "WARN: Contains likely sensitive data (tokens, cards)"
    if max_risk >= 3:
        return "REVIEW: May contain sensitive data"
    return "LOW: Possible false positives"


def format_detections(scan_result: dict) -> str:
    """Format scan results for display."""
    detections = scan_result.get("detections", [])
    
    if not detections:
        return "✓ No sensitive data detected"
    
    lines = [f"⚠ {len(detections)} sensitive data detection(s):"]
    
    for d in detections[:10]:  # Limit display
        risk_emoji = "🔴" if d["risk"] >= 5 else "🟡" if d["risk"] >= 3 else "🟢"
        lines.append(f"  {risk_emoji} [{d['type']}] risk={d['risk']} line={d.get('line', '?')}")
        if d.get("context"):
            lines.append(f"     context: {d['context']}")
    
    if len(detections) > 10:
        lines.append(f"  ... and {len(detections) - 10} more")
    
    rec = scan_result.get("recommendation")
    if rec:
        lines.append(f"\n{rec}")
    
    return "\n".join(lines)
