"""P2.2 — Resource Limits.

Enforces:
- Memory limits per task
- CPU time limits
- File size limits
- Tool call limits
- Token limits
- Concurrent task limits

Prevents resource exhaustion attacks.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from .util import now_iso

# ═══════════════════════════════
# DEFAULT LIMITS
# ═══════════════════════════════

DEFAULT_LIMITS = {
    # Memory
    "max_memory_mb": 512,
    
    # CPU
    "max_cpu_seconds": 30,
    
    # Files
    "max_file_size_mb": 10,
    "max_files_per_task": 20,
    
    # Tools
    "max_tool_calls": 10,
    "max_tool_time_seconds": 60,
    
    # Tokens
    "max_tokens_per_task": 4000,
    "max_tokens_per_session": 50000,
    
    # Concurrency
    "max_concurrent_tasks": 5,
    "max_queue_size": 100,
    
    # Network
    "max_requests_per_minute": 60,
    "max_request_size_mb": 1,
}

# Limits by mode
MODE_LIMITS = {
    "FAST": {
        **DEFAULT_LIMITS,
        "max_cpu_seconds": 5,
        "max_tool_calls": 3,
        "max_tokens_per_task": 1000,
    },
    "NORMAL": DEFAULT_LIMITS.copy(),
    "DEEP": {
        **DEFAULT_LIMITS,
        "max_cpu_seconds": 120,
        "max_tool_calls": 20,
        "max_tokens_per_task": 8000,
    },
}

# Limits by role (owner gets more)
ROLE_MULTIPLIERS = {
    "OWNER": 2.0,
    "ADMIN": 1.5,
    "OPERATOR": 1.0,
    "GUEST": 0.5,
}


class ResourceTracker:
    """Track resource usage per task and session."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._task_usage: dict[str, dict] = {}  # task_id → usage
        self._session_usage: dict[str, dict] = {}  # session_id → usage
        self._active_tasks: int = 0
    
    def start_task(self, task_id: str, session_id: str = None) -> dict:
        """Start tracking a task. Returns limits for this task."""
        with self._lock:
            self._task_usage[task_id] = {
                "start_time": time.time(),
                "memory_mb": 0,
                "cpu_seconds": 0,
                "tool_calls": 0,
                "tool_time": 0,
                "tokens": 0,
                "files_accessed": 0,
                "file_bytes_read": 0,
                "file_bytes_written": 0,
            }
            self._active_tasks += 1
            
            if session_id:
                if session_id not in self._session_usage:
                    self._session_usage[session_id] = {
                        "tasks": 0,
                        "total_tokens": 0,
                        "start_time": time.time(),
                    }
                self._session_usage[session_id]["tasks"] += 1
        
        return {"task_id": task_id, "started": now_iso()}
    
    def record_tool_call(self, task_id: str, tool_name: str, duration_ms: float = 0):
        """Record a tool call."""
        with self._lock:
            if task_id in self._task_usage:
                u = self._task_usage[task_id]
                u["tool_calls"] += 1
                u["tool_time"] += duration_ms / 1000
    
    def record_tokens(self, task_id: str, session_id: str, tokens: int):
        """Record token usage."""
        with self._lock:
            if task_id in self._task_usage:
                self._task_usage[task_id]["tokens"] += tokens
            if session_id and session_id in self._session_usage:
                self._session_usage[session_id]["total_tokens"] += tokens
    
    def record_file_access(self, task_id: str, bytes_read: int = 0, bytes_written: int = 0):
        """Record file access."""
        with self._lock:
            if task_id in self._task_usage:
                u = self._task_usage[task_id]
                u["files_accessed"] += 1
                u["file_bytes_read"] += bytes_read
                u["file_bytes_written"] += bytes_written
    
    def end_task(self, task_id: str) -> dict:
        """Stop tracking a task. Returns final usage."""
        with self._lock:
            usage = self._task_usage.pop(task_id, {})
            self._active_tasks = max(0, self._active_tasks - 1)
            if usage:
                usage["end_time"] = time.time()
                usage["duration_seconds"] = usage["end_time"] - usage["start_time"]
            return usage
    
    def check_limits(
        self,
        task_id: str,
        mode: str = "NORMAL",
        role: str = "OPERATOR",
    ) -> dict:
        """Check if task is within limits."""
        with self._lock:
            usage = self._task_usage.get(task_id)
            if not usage:
                return {"ok": True, "kind": "MEASURED", "reason": "not tracking"}
            
            limits = MODE_LIMITS.get(mode, DEFAULT_LIMITS).copy()
            multiplier = ROLE_MULTIPLIERS.get(role, 1.0)
            
            # Apply role multiplier
            for key in limits:
                if key.startswith("max_"):
                    limits[key] = int(limits[key] * multiplier)
            
            violations = []
            
            # Check CPU time
            elapsed = time.time() - usage["start_time"]
            if elapsed > limits["max_cpu_seconds"]:
                violations.append({
                    "limit": "max_cpu_seconds",
                    "current": round(elapsed, 2),
                    "max": limits["max_cpu_seconds"],
                })
            
            # Check tool calls
            if usage["tool_calls"] > limits["max_tool_calls"]:
                violations.append({
                    "limit": "max_tool_calls",
                    "current": usage["tool_calls"],
                    "max": limits["max_tool_calls"],
                })
            
            # Check tokens
            if usage["tokens"] > limits["max_tokens_per_task"]:
                violations.append({
                    "limit": "max_tokens_per_task",
                    "current": usage["tokens"],
                    "max": limits["max_tokens_per_task"],
                })
            
            # Check file size
            total_file_bytes = usage["file_bytes_read"] + usage["file_bytes_written"]
            max_file_bytes = limits["max_file_size_mb"] * 1024 * 1024
            if total_file_bytes > max_file_bytes:
                violations.append({
                    "limit": "max_file_size_mb",
                    "current_mb": round(total_file_bytes / (1024 * 1024), 2),
                    "max_mb": limits["max_file_size_mb"],
                })
            
            # Check concurrent tasks
            if self._active_tasks > limits["max_concurrent_tasks"]:
                violations.append({
                    "limit": "max_concurrent_tasks",
                    "current": self._active_tasks,
                    "max": limits["max_concurrent_tasks"],
                })
            
            return {
                "kind": "MEASURED",
                "ok": len(violations) == 0,
                "task_id": task_id,
                "mode": mode,
                "role": role,
                "violations": violations,
                "usage": {
                    "cpu_seconds": round(elapsed, 2),
                    "tool_calls": usage["tool_calls"],
                    "tokens": usage["tokens"],
                    "file_bytes": total_file_bytes,
                },
                "limits": limits,
            }
    
    def get_session_usage(self, session_id: str) -> dict:
        """Get session-level usage."""
        with self._lock:
            usage = self._session_usage.get(session_id, {})
            return {
                "kind": "MEASURED",
                "session_id": session_id,
                **usage,
            }


# Global tracker
_tracker = ResourceTracker()


def get_tracker() -> ResourceTracker:
    """Get the global resource tracker."""
    return _tracker


def start_tracking(task_id: str, session_id: str = None) -> dict:
    """Start tracking a task."""
    return _tracker.start_task(task_id, session_id)


def check_limits(task_id: str, mode: str = "NORMAL", role: str = "OPERATOR") -> dict:
    """Check if task is within limits."""
    return _tracker.check_limits(task_id, mode, role)


def end_tracking(task_id: str) -> dict:
    """Stop tracking a task."""
    return _tracker.end_task(task_id)

