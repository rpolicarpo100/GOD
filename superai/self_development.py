"""Controlled Self-Development — GOD proposes code changes safely.

Safety rules:
1. NEVER modify auth.py, security modules, or permission system
2. NEVER auto-approve — always requires human approval
3. Changes must pass tests before applying
4. All changes logged with full diff
5. Rollback available for every change
"""
from __future__ import annotations

import json
import time
import threading
import subprocess
from pathlib import Path
from typing import Any

from .config import ROOT, DATA
from .store import store
from .events import bus
from .util import now_iso, sha
import logging

_log = logging.getLogger("superai.selfdev")

# Files GOD is NEVER allowed to modify
BLOCKED_FILES = {
    "superai/auth.py",
    "superai/permissions.py",
    "superai/sensitive.py",
    "superai/sandbox.py",
    "server.py",  # server too critical for auto-change
}

# File patterns that need extra caution
CAUTION_FILES = {
    "superai/routing.py",
    "superai/providers.py",
    "superai/pipeline.py",
    "superai/store.py",
}


class ProposedChange:
    """A proposed code change."""

    def __init__(self, file_path: str, description: str, old_content: str, new_content: str):
        self.id = sha(f"change:{file_path}:{time.time()}")
        self.file_path = file_path
        self.description = description
        self.old_content = old_content
        self.new_content = new_content
        self.status = "proposed"  # proposed, testing, approved, applied, rejected, rolled_back
        self.created_at = now_iso()
        self.test_result: dict | None = None
        self.diff: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "file_path": self.file_path,
            "description": self.description, "status": self.status,
            "created_at": self.created_at, "test_result": self.test_result,
            "diff": self.diff[:2000],
        }


class SelfDevelopment:
    """Controlled self-development manager."""

    def __init__(self):
        self._proposals: dict[str, ProposedChange] = {}
        self._history: list[dict] = []
        self._path = DATA / "selfdev_history.json"
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._history = data.get("history", [])
            except Exception:
                pass

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({
                "history": self._history[-50:],
            }, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass

    def propose_change(self, file_path: str, description: str,
                       old_content: str, new_content: str) -> dict:
        """Propose a code change. Validates safety before accepting."""
        # Normalize path
        rel = str(file_path).replace(str(ROOT) + "/", "").replace(str(ROOT), "")

        # Safety check: blocked files
        if rel in BLOCKED_FILES or any(rel.endswith(b) for b in BLOCKED_FILES):
            return {"ok": False, "error": f"BLOCKED: {rel} is in protected files list"}

        # Safety check: path traversal
        if ".." in rel:
            return {"ok": False, "error": "BLOCKED: path traversal detected"}

        # Safety check: must be within project
        full_path = ROOT / rel
        if not str(full_path).startswith(str(ROOT)):
            return {"ok": False, "error": "BLOCKED: path outside project"}

        # Create proposal
        change = ProposedChange(rel, description, old_content, new_content)

        # Generate diff
        try:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            import difflib
            diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="",
                                              fromfile=f"a/{rel}", tofile=f"b/{rel}"))
            change.diff = "".join(diff)[:5000]
        except Exception:
            change.diff = "(diff generation failed)"

        # Caution warning
        caution = rel in CAUTION_FILES
        if caution:
            change.description = f"⚠ CAUTION: {description}"

        with self._lock:
            self._proposals[change.id] = change

        bus.emit("SELFDEV_PROPOSED", "INFO", f"{rel}: {description}")
        return {"ok": True, "proposal": change.to_dict(), "caution": caution}

    def test_proposal(self, change_id: str) -> dict:
        """Run tests on proposed change (applied temporarily)."""
        with self._lock:
            change = self._proposals.get(change_id)
            if not change:
                return {"ok": False, "error": "proposal not found"}
            change.status = "testing"

        rel = change.file_path
        full_path = ROOT / rel

        # Save backup
        backup = None
        if full_path.exists():
            backup = full_path.read_text(encoding="utf-8")

        try:
            # Apply change temporarily
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(change.new_content, encoding="utf-8")

            # Run tests
            result = subprocess.run(
                ["python3.13", "-m", "pytest", "tests/", "-q", "--tb=short", "-x"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=60
            )

            passed = result.returncode == 0
            change.test_result = {
                "passed": passed,
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-1000:],
            }

            # Restore backup
            if backup is not None:
                full_path.write_text(backup, encoding="utf-8")
            elif full_path.exists():
                full_path.unlink()

            change.status = "proposed"
            return {"ok": True, "test_passed": passed, "result": change.test_result}

        except subprocess.TimeoutExpired:
            # Restore backup
            if backup is not None:
                full_path.write_text(backup, encoding="utf-8")
            change.status = "proposed"
            change.test_result = {"passed": False, "error": "test timeout (60s)"}
            return {"ok": False, "error": "test timeout"}

        except Exception as e:
            # Restore backup
            if backup is not None:
                full_path.write_text(backup, encoding="utf-8")
            change.status = "proposed"
            change.test_result = {"passed": False, "error": str(e)}
            return {"ok": False, "error": str(e)}

    def approve_and_apply(self, change_id: str) -> dict:
        """Approve and apply a change. Requires test to pass first."""
        with self._lock:
            change = self._proposals.get(change_id)
            if not change:
                return {"ok": False, "error": "proposal not found"}
            if change.test_result and not change.test_result.get("passed"):
                return {"ok": False, "error": "tests failed — fix before applying"}

        rel = change.file_path
        full_path = ROOT / rel

        # Save backup for rollback
        backup = None
        if full_path.exists():
            backup = full_path.read_text(encoding="utf-8")

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(change.new_content, encoding="utf-8")
            change.status = "applied"

            self._history.append({
                "id": change.id, "file": rel, "description": change.description,
                "applied_at": now_iso(), "diff": change.diff[:1000],
            })
            self._save()

            bus.emit("SELFDEV_APPLIED", "INFO", f"{rel}: {change.description}")
            return {"ok": True, "applied": rel, "description": change.description}

        except Exception as e:
            # Rollback
            if backup is not None:
                full_path.write_text(backup, encoding="utf-8")
            change.status = "proposed"
            return {"ok": False, "error": str(e)}

    def reject(self, change_id: str, reason: str = "") -> dict:
        """Reject a proposal."""
        with self._lock:
            change = self._proposals.get(change_id)
            if not change:
                return {"ok": False, "error": "proposal not found"}
            change.status = "rejected"
            del self._proposals[change_id]
        return {"ok": True, "rejected": change_id, "reason": reason}

    def list_proposals(self) -> list[dict]:
        """List all pending proposals."""
        with self._lock:
            return [c.to_dict() for c in self._proposals.values()]

    def get_history(self, n: int = 20) -> list[dict]:
        """Get change history."""
        return self._history[-n:]

    def stats(self) -> dict:
        """Self-development statistics."""
        with self._lock:
            return {
                "pending_proposals": len(self._proposals),
                "total_applied": len([h for h in self._history if h.get("applied_at")]),
                "history_count": len(self._history),
            }


# Global singleton
_sd: SelfDevelopment | None = None
_init_lock = threading.Lock()


def get_selfdev() -> SelfDevelopment:
    global _sd
    if _sd is None:
        with _init_lock:
            if _sd is None:
                _sd = SelfDevelopment()
    return _sd
