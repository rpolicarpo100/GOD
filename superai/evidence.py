"""GOD — Task Evidence Engine

Plan → Execute → Evidence → Verify → Answer

A task is never considered complete without evidence.
"""
from __future__ import annotations

import json
import time
import secrets
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from .config import DATA

EVIDENCE_DIR = DATA / "evidence"
EVIDENCE_FILE = EVIDENCE_DIR / "outcomes.jsonl"

# ═══════════════════════════════
# TASK STATES
# ═══════════════════════════════

class TaskState(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTED = "EXECUTED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"

# ═══════════════════════════════
# TASK OUTCOME
# ═══════════════════════════════

@dataclass
class TaskOutcome:
    task_id: str
    state: str = TaskState.PLANNED
    success: bool = False
    evidence: list[dict] = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    confidence: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started_at: float = 0
    completed_at: float = 0
    duration_ms: float = 0
    action: str = ""
    resource: str = ""
    user_id: str = ""
    session_id: str = ""

# ═══════════════════════════════
# EVIDENCE TYPES
# ═══════════════════════════════

def file_exists(path: str) -> dict:
    """Evidence: file exists."""
    p = Path(path).resolve()
    return {
        "type": "file_exists",
        "path": str(p),
        "exists": p.exists(),
        "is_file": p.is_file() if p.exists() else None,
        "size": p.stat().st_size if p.exists() and p.is_file() else None,
        "kind": "MEASURED",
    }

def file_content_matches(path: str, expected: str = None, contains: str = None) -> dict:
    """Evidence: file content matches expectations."""
    p = Path(path).resolve()
    if not p.exists():
        return {"type": "file_content", "path": str(p), "exists": False, "kind": "MEASURED"}
    try:
        content = p.read_text()
        result = {
            "type": "file_content",
            "path": str(p),
            "exists": True,
            "size": len(content),
            "kind": "MEASURED",
        }
        if expected is not None:
            result["matches_exact"] = content == expected
        if contains is not None:
            result["contains"] = contains in content
        return result
    except Exception as e:
        return {"type": "file_content", "path": str(p), "error": str(e), "kind": "MEASURED"}

def syntax_valid(path: str, lang: str = "python") -> dict:
    """Evidence: file has valid syntax."""
    p = Path(path).resolve()
    if not p.exists():
        return {"type": "syntax", "path": str(p), "exists": False, "kind": "MEASURED"}
    try:
        content = p.read_text()
        if lang == "python":
            compile(content, str(p), "exec")
            return {"type": "syntax", "path": str(p), "lang": lang, "valid": True, "kind": "MEASURED"}
        elif lang == "json":
            json.loads(content)
            return {"type": "syntax", "path": str(p), "lang": lang, "valid": True, "kind": "MEASURED"}
        else:
            return {"type": "syntax", "path": str(p), "lang": lang, "valid": None, "kind": "UNKNOWN"}
    except SyntaxError as e:
        return {"type": "syntax", "path": str(p), "lang": lang, "valid": False, "error": str(e), "kind": "MEASURED"}
    except json.JSONDecodeError as e:
        return {"type": "syntax", "path": str(p), "lang": lang, "valid": False, "error": str(e), "kind": "MEASURED"}
    except Exception as e:
        return {"type": "syntax", "path": str(p), "lang": lang, "valid": False, "error": str(e), "kind": "MEASURED"}

def test_passed(test_path: str = None, test_name: str = None) -> dict:
    """Evidence: test passed."""
    import subprocess
    try:
        if test_name:
            cmd = ["python", "-m", "pytest", f"-k", test_name, "-x", "-q", "--tb=short"]
        elif test_path:
            cmd = ["python", "-m", "pytest", test_path, "-x", "-q", "--tb=short"]
        else:
            cmd = ["python", "-m", "pytest", "tests/", "-x", "-q", "--tb=short"]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "type": "test_result",
            "passed": result.returncode == 0,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
            "kind": "MEASURED",
        }
    except subprocess.TimeoutExpired:
        return {"type": "test_result", "passed": False, "error": "timeout", "kind": "MEASURED"}
    except Exception as e:
        return {"type": "test_result", "passed": False, "error": str(e), "kind": "MEASURED"}

def http_status(url: str, expected_status: int = 200) -> dict:
    """Evidence: HTTP endpoint returns expected status."""
    import urllib.request
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {
                "type": "http_status",
                "url": url,
                "status": resp.status,
                "expected": expected_status,
                "match": resp.status == expected_status,
                "kind": "MEASURED",
            }
    except Exception as e:
        return {
            "type": "http_status",
            "url": url,
            "status": None,
            "expected": expected_status,
            "match": False,
            "error": str(e),
            "kind": "MEASURED",
        }



def git_state() -> dict:
    """Evidence: git repository state."""
    import subprocess
    try:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10)
        log = subprocess.run(["git", "log", "-1", "--oneline"], capture_output=True, text=True, timeout=10)
        return {
            "type": "git_state",
            "clean": not status.stdout.strip(),
            "last_commit": log.stdout.strip() if log.returncode == 0 else None,
            "modified_files": len(status.stdout.strip().split("\n")) if status.stdout.strip() else 0,
            "kind": "MEASURED",
        }
    except Exception as e:
        return {"type": "git_state", "error": str(e), "kind": "MEASURED"}

# ═══════════════════════════════
# TASK TRACKING
# ═══════════════════════════════

_tasks: dict[str, TaskOutcome] = {}

def create_task(action: str, resource: str = "", user_id: str = "", session_id: str = "") -> str:
    """Create a new task and return task_id."""
    task_id = "task-" + secrets.token_hex(8)
    _tasks[task_id] = TaskOutcome(
        task_id=task_id,
        action=action,
        resource=resource,
        user_id=user_id,
        session_id=session_id,
        started_at=time.time(),
        state=TaskState.RUNNING,
    )
    return task_id

def add_evidence(task_id: str, evidence: dict):
    """Add evidence to a task."""
    if task_id in _tasks:
        _tasks[task_id].evidence.append(evidence)

def complete_task(task_id: str, success: bool, verification: dict = None):
    """Mark task as complete with verification."""
    if task_id not in _tasks:
        return
    task = _tasks[task_id]
    task.completed_at = time.time()
    task.duration_ms = (task.completed_at - task.started_at) * 1000
    task.success = success
    
    if verification:
        task.verification = verification
    
    # Calculate confidence from evidence
    evidence_count = len(task.evidence)
    verified_count = sum(1 for e in task.evidence if e.get("kind") == "MEASURED")
    task.confidence = verified_count / max(evidence_count, 1)
    
    # Determine state
    if not success:
        task.state = TaskState.FAILED
    elif task.confidence >= 0.8:
        task.state = TaskState.VERIFIED
    elif task.confidence >= 0.5:
        task.state = TaskState.PARTIAL
    else:
        task.state = TaskState.UNVERIFIED
    
    # Persist
    _persist_outcome(task)

def fail_task(task_id: str, error: str):
    """Mark task as failed."""
    if task_id not in _tasks:
        return
    task = _tasks[task_id]
    task.completed_at = time.time()
    task.duration_ms = (task.completed_at - task.started_at) * 1000
    task.success = False
    task.state = TaskState.FAILED
    task.errors.append(error)
    _persist_outcome(task)

def get_task(task_id: str) -> dict | None:
    """Get task outcome."""
    if task_id not in _tasks:
        return None
    return asdict(_tasks[task_id])

def recent_tasks(limit: int = 20) -> list[dict]:
    """Get recent tasks."""
    tasks = sorted(_tasks.values(), key=lambda t: t.started_at or 0, reverse=True)
    return [asdict(t) for t in tasks[:limit]]

def _persist_outcome(task: TaskOutcome):
    """Persist task outcome to evidence log."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVIDENCE_FILE, "a") as f:
        f.write(json.dumps(asdict(task), ensure_ascii=False) + "\n")

# ═══════════════════════════════
# VERIFIED COMPLETION RATE
# ═══════════════════════════════

def verified_completion_rate() -> dict:
    """Calculate verified completion rate from persisted outcomes."""
    if not EVIDENCE_FILE.exists():
        return {"rate": 0, "verified": 0, "total": 0, "kind": "UNKNOWN"}
    
    lines = EVIDENCE_FILE.read_text().strip().split("\n")
    total = 0
    verified = 0
    failed = 0
    unverified = 0
    
    for line in lines:
        try:
            outcome = json.loads(line)
            total += 1
            state = outcome.get("state", "")
            if state == TaskState.VERIFIED:
                verified += 1
            elif state == TaskState.FAILED:
                failed += 1
            elif state == TaskState.UNVERIFIED:
                unverified += 1
        except json.JSONDecodeError:
            pass
    
    rate = verified / max(total, 1)
    return {
        "rate": round(rate, 3),
        "verified": verified,
        "failed": failed,
        "unverified": unverified,
        "total": total,
        "kind": "MEASURED" if total > 0 else "UNKNOWN",
    }
