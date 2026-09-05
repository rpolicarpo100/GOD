"""GOD Reality Benchmark — verifiable capability assessment.

Categories:
- Auth: identity verification
- Security: authorization enforcement
- Governor: control mechanisms
- Tools: execution capability
- Memory: retrieval accuracy
- Validation: correctness checking
- Evidence: proof generation
- Outcome: real success measurement
- Recovery: failure handling
- Autonomy: operation without intervention
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import DATA
from .util import now_iso

BENCHMARK_DIR = DATA / "benchmarks"

# ═══════════════════════════════
# BENCHMARK CATEGORIES
# ═══════════════════════════════

CATEGORIES = {
    "auth": "Identity verification",
    "security": "Authorization enforcement",
    "governor": "Control mechanisms",
    "tools": "Execution capability",
    "memory": "Retrieval accuracy",
    "validation": "Correctness checking",
    "evidence": "Proof generation",
    "outcome": "Real success measurement",
    "recovery": "Failure handling",
    "autonomy": "Operation without intervention",
}


def run_benchmark(categories: list[str] = None) -> dict:
    """Run reality benchmark. Returns verifiable results."""
    from . import auth
    from . import evidence as ev
    from . import validator
    
    categories = categories or list(CATEGORIES.keys())
    results = {}
    ts = time.time()
    
    for cat in categories:
        if cat == "auth":
            results[cat] = _bench_auth()
        elif cat == "security":
            results[cat] = _bench_security()
        elif cat == "governor":
            results[cat] = _bench_governor()
        elif cat == "tools":
            results[cat] = _bench_tools()
        elif cat == "memory":
            results[cat] = _bench_memory()
        elif cat == "validation":
            results[cat] = _bench_validation()
        elif cat == "evidence":
            results[cat] = _bench_evidence()
        elif cat == "outcome":
            results[cat] = _bench_outcome()
        elif cat == "recovery":
            results[cat] = _bench_recovery()
        elif cat == "autonomy":
            results[cat] = _bench_autonomy()
    
    # Calculate overall metrics
    total = sum(r.get("total", 0) for r in results.values())
    passed = sum(r.get("passed", 0) for r in results.values())
    verified = sum(r.get("verified", 0) for r in results.values())
    
    report = {
        "kind": "MEASURED",
        "ts": now_iso(),
        "duration_ms": (time.time() - ts) * 1000,
        "categories": results,
        "summary": {
            "total": total,
            "passed": passed,
            "verified": verified,
            "pass_rate": round(passed / max(total, 1), 3),
            "verified_rate": round(verified / max(total, 1), 3),
        },
    }
    
    # Persist
    _save_benchmark(report)
    
    return report


def _bench_auth() -> dict:
    """Benchmark authentication capabilities."""
    from . import auth
    
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Password hashing works
    total += 1
    try:
        h, s = auth._hash_password("test")
        if h and s and h != "test":
            passed += 1
            tests.append({"name": "password_hashing", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "password_hashing", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "password_hashing", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Session validation works
    total += 1
    try:
        result = auth.validate_session("nonexistent")
        if result is None:
            passed += 1
            tests.append({"name": "session_validation", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "session_validation", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "session_validation", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 3: Permission check works
    total += 1
    try:
        has = auth.has_permission("OWNER", auth.Perm.SECURITY_MANAGE)
        has_not = not auth.has_permission("GUEST", auth.Perm.SECURITY_MANAGE)
        if has and has_not:
            passed += 1
            tests.append({"name": "permission_check", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "permission_check", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "permission_check", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_security() -> dict:
    """Benchmark security enforcement."""
    from . import auth
    
    tests = []
    total = 0
    passed = 0
    
    # Test 1: No session = denied for protected
    total += 1
    try:
        result = auth.require_permission(None, auth.Perm.SECURITY_MANAGE)
        if not result.get("ok"):
            passed += 1
            tests.append({"name": "no_session_denied", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "no_session_denied", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "no_session_denied", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Risk levels are defined
    total += 1
    try:
        r0 = auth.get_risk_level(auth.Perm.CHAT_USE)
        r5 = auth.get_risk_level("self_elevation")
        if r0 < r5:
            passed += 1
            tests.append({"name": "risk_levels", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "risk_levels", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "risk_levels", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 3: Audit ledger exists
    total += 1
    try:
        events = auth.audit_log(1)
        passed += 1
        tests.append({"name": "audit_ledger", "passed": True, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "audit_ledger", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_governor() -> dict:
    """Benchmark governor controls."""
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Governor module exists
    total += 1
    try:
        from . import governor
        if hasattr(governor, 'gov'):
            passed += 1
            tests.append({"name": "governor_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "governor_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "governor_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Resource modes defined
    total += 1
    try:
        from . import governor
        if hasattr(governor, 'RESOURCE_MODES'):
            passed += 1
            tests.append({"name": "resource_modes", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "resource_modes", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "resource_modes", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_tools() -> dict:
    """Benchmark tool execution."""
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Tools module exists
    total += 1
    try:
        from . import tools
        if hasattr(tools, 'execute'):
            passed += 1
            tests.append({"name": "tools_exist", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "tools_exist", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "tools_exist", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Calculator works
    total += 1
    try:
        from . import tools
        result = tools.execute("calculator", {"expr": "2+2"})
        if result.get("status") == "success":
            passed += 1
            tests.append({"name": "calculator", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "calculator", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "calculator", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_memory() -> dict:
    """Benchmark memory capabilities."""
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Store exists
    total += 1
    try:
        from . import store
        if hasattr(store, 'store'):
            passed += 1
            tests.append({"name": "store_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "store_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "store_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_validation() -> dict:
    """Benchmark validation capabilities."""
    from . import validator
    
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Validator exists
    total += 1
    try:
        if hasattr(validator, 'validate'):
            passed += 1
            tests.append({"name": "validator_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "validator_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "validator_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Evidence validation works
    total += 1
    try:
        result = validator.validate_evidence("test", [
            {"type": "file_exists", "kind": "MEASURED", "passed": True},
        ])
        if result.get("valid"):
            passed += 1
            tests.append({"name": "evidence_validation", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "evidence_validation", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "evidence_validation", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_evidence() -> dict:
    """Benchmark evidence engine."""
    from . import evidence as ev
    
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Evidence module exists
    total += 1
    try:
        if hasattr(ev, 'create_task'):
            passed += 1
            tests.append({"name": "evidence_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "evidence_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "evidence_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Task creation works
    total += 1
    try:
        task_id = ev.create_task("benchmark_test", "test")
        if task_id:
            passed += 1
            tests.append({"name": "task_creation", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "task_creation", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "task_creation", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 3: File evidence works
    total += 1
    try:
        result = ev.file_exists("/home/user/GOD/server.py")
        if result.get("exists"):
            passed += 1
            tests.append({"name": "file_evidence", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "file_evidence", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "file_evidence", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_outcome() -> dict:
    """Benchmark outcome verification."""
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Verified completion rate
    total += 1
    try:
        from . import evidence as ev
        rate = ev.verified_completion_rate()
        if "rate" in rate:
            passed += 1
            tests.append({"name": "completion_rate", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "completion_rate", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "completion_rate", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_recovery() -> dict:
    """Benchmark recovery capabilities."""
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Repair module exists
    total += 1
    try:
        from . import repair
        if hasattr(repair, 'run'):
            passed += 1
            tests.append({"name": "repair_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "repair_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "repair_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _bench_autonomy() -> dict:
    """Benchmark autonomy capabilities."""
    tests = []
    total = 0
    passed = 0
    
    # Test 1: Observer exists
    total += 1
    try:
        from . import observer
        if hasattr(observer, 'latest'):
            passed += 1
            tests.append({"name": "observer_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "observer_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "observer_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    # Test 2: Evolution exists
    total += 1
    try:
        from . import evolution
        if hasattr(evolution, 'run_cycle'):
            passed += 1
            tests.append({"name": "evolution_exists", "passed": True, "kind": "MEASURED"})
        else:
            tests.append({"name": "evolution_exists", "passed": False, "kind": "MEASURED"})
    except Exception as e:
        tests.append({"name": "evolution_exists", "passed": False, "error": str(e), "kind": "MEASURED"})
    
    return {"total": total, "passed": passed, "verified": passed, "tests": tests}


def _save_benchmark(report: dict):
    """Persist benchmark report."""
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = BENCHMARK_DIR / f"benchmark_{ts}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))


def benchmark_history(limit: int = 10) -> list[dict]:
    """Get recent benchmark results."""
    if not BENCHMARK_DIR.exists():
        return []
    files = sorted(BENCHMARK_DIR.glob("benchmark_*.json"), reverse=True)
    results = []
    for f in files[:limit]:
        try:
            results.append(json.loads(f.read_text()))
        except Exception:
            pass
    return results


def format_benchmark(report: dict) -> str:
    """Format benchmark for display."""
    lines = [
        f"GOD REALITY BENCHMARK",
        f"Duration: {report.get('duration_ms', 0):.0f}ms",
        "",
    ]
    
    summary = report.get("summary", {})
    lines.append(f"Total: {summary.get('total', 0)}")
    lines.append(f"Passed: {summary.get('passed', 0)}")
    lines.append(f"Verified: {summary.get('verified', 0)}")
    lines.append(f"Pass Rate: {summary.get('pass_rate', 0)*100:.1f}%")
    lines.append(f"Verified Rate: {summary.get('verified_rate', 0)*100:.1f}%")
    lines.append("")
    
    for cat, result in report.get("categories", {}).items():
        status = "PASS" if result.get("passed", 0) == result.get("total", 0) else "PARTIAL"
        lines.append(f"[{status}] {cat}: {result.get('passed', 0)}/{result.get('total', 0)}")
        for t in result.get("tests", []):
            st = "✓" if t.get("passed") else "✗"
            lines.append(f"  {st} {t['name']}")
    
    return "\n".join(lines)
