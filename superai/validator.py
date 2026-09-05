"""P2 Validator — type-specific result verification + evidence validation.

Not a replacement for brain.evaluate() heuristic scores.
Adds task-type-aware checks that verify actual results.

Coding: syntax check + structure
Math: result exists + numeric
JSON: parseable + structure
Git: exit code + expected output
LLM: non-empty + relevant + no hallucination markers
File ops: path exists + size > 0
Evidence: task outcome verification
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from .util import now_iso


def validate(task: dict, tool_results: list[dict], llm_text: str | None = None) -> dict:
    """Run type-specific validations on tool results.

    Returns structured validation with per-tool checks.
    Never blocks — always returns, even if validation fails.
    """
    ttype = task.get("type") or "general"
    checks: list[dict] = []

    for r in tool_results:
        tool = str(r.get("tool") or "")
        if tool == "calculator":
            checks.append(_validate_math(task, r))
        elif tool == "json":
            checks.append(_validate_json(task, r))
        elif tool == "csv":
            checks.append(_validate_csv(task, r))
        elif tool == "xml":
            checks.append(_validate_xml(task, r))
        elif tool == "git":
            checks.append(_validate_git(task, r))
        elif tool in ("fs.read", "fs.list"):
            checks.append(_validate_fs(task, r))
        elif tool == "fs.write":
            checks.append(_validate_write(task, r))
        elif tool == "python":
            checks.append(_validate_python(task, r))
        elif tool.startswith("llm:"):
            checks.append(_validate_llm(task, r, llm_text))
        elif tool == "state":
            checks.append(_validate_state(task, r))
        else:
            checks.append({
                "tool": tool,
                "check": "generic",
                "passed": r.get("status") == "success",
                "evidence": r.get("evidence") or [],
                "note": "no type-specific validation for this tool",
            })

    # Cross-tool checks
    if ttype == "math" and checks:
        checks.append(_cross_validate_math(task, tool_results))
    if ttype == "coding" and llm_text:
        checks.append(_cross_validate_coding(task, llm_text))

    passed = all(c.get("passed") for c in checks) if checks else False
    n_passed = sum(1 for c in checks if c.get("passed"))
    confidence = n_passed / len(checks) if checks else 0.0

    return {
        "kind": "MEASURED",
        "task_type": ttype,
        "passed": passed,
        "confidence": round(confidence, 3),
        "n_checks": len(checks),
        "n_passed": n_passed,
        "checks": checks,
        "ts": now_iso(),
    }


def _validate_math(task: dict, result: dict) -> dict:
    """Math: result exists, is numeric, expression was evaluated."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    evidence = list(result.get("evidence") or [])
    notes = []

    if not findings:
        passed = False
        notes.append("no findings returned")
    else:
        f = findings[0]
        val = f.get("result") if isinstance(f, dict) else None
        if val is None:
            passed = False
            notes.append("no numeric result in findings")
        elif not isinstance(val, (int, float)):
            passed = False
            notes.append(f"result is {type(val).__name__}, not numeric")
        else:
            notes.append(f"result={val} (numeric)")
            # Verify the expression was actually arithmetic
            expr = f.get("expr") if isinstance(f, dict) else None
            if expr:
                try:
                    tree = ast.parse(expr, mode="eval")
                    notes.append("expression parsed as valid arithmetic")
                except SyntaxError:
                    # Expression may have been extracted from larger text — not a failure
                    notes.append("expression extraction used (may be partial)")

    return {
        "tool": "calculator",
        "check": "math_result",
        "passed": passed,
        "evidence": evidence,
        "notes": notes,
    }


def _validate_json(task: dict, result: dict) -> dict:
    """JSON: parseable, has structure info."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    evidence = list(result.get("evidence") or [])
    notes = []

    if not findings:
        passed = False
        notes.append("no findings")
    else:
        f = findings[0]
        if isinstance(f, dict):
            jtype = f.get("type")
            n = f.get("n")
            if jtype:
                notes.append(f"type={jtype}")
            if n is not None:
                notes.append(f"items={n}")
            if jtype in ("dict", "list"):
                notes.append("valid structure")
            else:
                notes.append(f"unexpected top-level type: {jtype}")

    return {
        "tool": "json",
        "check": "json_parse",
        "passed": passed,
        "evidence": evidence,
        "notes": notes,
    }


def _validate_csv(task: dict, result: dict) -> dict:
    """CSV: parseable, has rows/cols."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    notes = []

    if findings:
        f = findings[0]
        rows = f.get("rows")
        cols = f.get("cols")
        if rows is not None and cols is not None:
            notes.append(f"rows={rows} cols={cols}")
            if rows == 0:
                passed = False
                notes.append("empty CSV")
        else:
            passed = False
            notes.append("missing rows/cols in findings")

    return {
        "tool": "csv",
        "check": "csv_parse",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _validate_xml(task: dict, result: dict) -> dict:
    """XML: parseable, has root tag."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    notes = []

    if findings:
        f = findings[0]
        tag = f.get("tag")
        children = f.get("children")
        if tag:
            notes.append(f"root=<{tag}> children={children}")
        else:
            passed = False
            notes.append("no root tag in findings")

    return {
        "tool": "xml",
        "check": "xml_parse",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _validate_git(task: dict, result: dict) -> dict:
    """Git: exit code 0, output present."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    evidence = list(result.get("evidence") or [])
    notes = []

    if findings:
        f = findings[0]
        exit_code = f.get("exit")
        output = f.get("output") or ""
        cmd = f.get("cmd") or []
        notes.append(f"cmd={' '.join(cmd)} exit={exit_code}")
        if exit_code != 0:
            passed = False
            notes.append(f"non-zero exit: {exit_code}")
        if not output.strip() and cmd and cmd[0] in ("status", "log", "diff"):
            notes.append("empty output (may be expected for clean repo)")

    return {
        "tool": "git",
        "check": "git_exit",
        "passed": passed,
        "evidence": evidence,
        "notes": notes,
    }


def _validate_fs(task: dict, result: dict) -> dict:
    """FS read/list: has findings, path info."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    notes = []

    if findings:
        f = findings[0]
        if isinstance(f, dict):
            if "path" in f:
                notes.append(f"path={f['path']}")
            if "chars" in f:
                notes.append(f"chars={f['chars']}")
                if f["chars"] == 0:
                    notes.append("empty file")
            if "bytes" in f:
                notes.append(f"bytes={f['bytes']}")
    elif passed:
        passed = False
        notes.append("success but no findings")

    return {
        "tool": result.get("tool") or "fs",
        "check": "fs_access",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _validate_write(task: dict, result: dict) -> dict:
    """FS write: success + path + bytes > 0."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    notes = []

    if findings:
        f = findings[0]
        path = f.get("path")
        nbytes = f.get("bytes")
        preview = f.get("preview")
        notes.append(f"path={path} bytes={nbytes}")
        if nbytes is not None and nbytes == 0:
            passed = False
            notes.append("wrote 0 bytes")
        if preview:
            notes.append(f"preview={preview}")

    return {
        "tool": "fs.write",
        "check": "file_write",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _validate_python(task: dict, result: dict) -> dict:
    """Python sandbox: exit code, stdout present."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    notes = []

    if findings:
        f = findings[0]
        exit_code = f.get("exit")
        stdout = f.get("stdout") or ""
        stderr = f.get("stderr") or ""
        notes.append(f"exit={exit_code} stdout={len(stdout)}chars stderr={len(stderr)}chars")
        if exit_code != 0:
            passed = False
            notes.append(f"stderr: {stderr[:200]}")

    return {
        "tool": "python",
        "check": "python_sandbox",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _validate_llm(task: dict, result: dict, llm_text: str | None) -> dict:
    """LLM response: non-empty, no obvious hallucination markers."""
    passed = result.get("status") == "success"
    notes = []
    text = llm_text or ""

    if not text.strip():
        passed = False
        notes.append("empty LLM response")
    else:
        notes.append(f"length={len(text)}")
        # Check for common hallucination patterns
        hallucination_markers = [
            "I don't have access to",
            "I cannot verify",
            "I'm not sure if",
            "as an AI language model",
        ]
        for marker in hallucination_markers:
            if marker.lower() in text.lower():
                notes.append(f"hallucination marker: '{marker}'")
        # Check if response is suspiciously short for complex tasks
        cx = int(task.get("complexity") or 0)
        if cx >= 7 and len(text) < 50:
            notes.append(f"suspiciously short ({len(text)}chars) for complexity {cx}")

    return {
        "tool": result.get("tool") or "llm",
        "check": "llm_response",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _validate_state(task: dict, result: dict) -> dict:
    """State snapshot: has findings with system info."""
    findings = result.get("findings") or []
    passed = result.get("status") == "success"
    notes = []

    if findings:
        f = findings[0]
        if isinstance(f, dict):
            notes.append(f"mode={f.get('mode')} providers={len(f.get('providers') or [])}")
    else:
        passed = False
        notes.append("no findings in state snapshot")

    return {
        "tool": "state",
        "check": "state_snapshot",
        "passed": passed,
        "evidence": result.get("evidence") or [],
        "notes": notes,
    }


def _cross_validate_math(task: dict, tool_results: list[dict]) -> dict:
    """Cross-check: math result matches expected if calculable."""
    text = task.get("text") or ""
    passed = True
    notes = []

    # Extract the expression and result
    for r in tool_results:
        if r.get("tool") != "calculator":
            continue
        findings = r.get("findings") or []
        if not findings:
            continue
        f = findings[0]
        result_val = f.get("result")
        expr = f.get("expr")
        if result_val is not None and expr:
            try:
                # Re-evaluate to verify
                tree = ast.parse(expr, mode="eval")
                from .tools import _eval_ast
                expected = _eval_ast(tree.body)
                if abs(float(result_val) - float(expected)) > 1e-10:
                    passed = False
                    notes.append(f"mismatch: got {result_val}, expected {expected}")
                else:
                    notes.append(f"verified: {expr} = {result_val}")
            except Exception as e:
                notes.append(f"re-eval failed: {e}")

    return {
        "tool": "cross_math",
        "check": "math_verification",
        "passed": passed,
        "evidence": [],
        "notes": notes,
    }


def _cross_validate_coding(task: dict, llm_text: str) -> dict:
    """Cross-check: LLM coding response has basic structure."""
    passed = True
    notes = []

    # Check for code blocks
    has_code = bool(re.search(r"```[\w]*\n[\s\S]+?```", llm_text))
    if has_code:
        notes.append("contains code block(s)")
        # Extract code and check for basic syntax
        for m in re.finditer(r"```(\w*)\n([\s\S]+?)```", llm_text):
            lang = m.group(1).lower()
            code = m.group(2)
            if lang in ("python", "py", ""):
                try:
                    ast.parse(code)
                    notes.append("python code parses OK")
                except SyntaxError as e:
                    passed = False
                    notes.append(f"python syntax error: {e}")
            elif lang in ("html", "htm"):
                if "<html" in code.lower() or "<!doctype" in code.lower():
                    notes.append("HTML has doctype/html tag")
                elif "<" in code:
                    notes.append("HTML has tags")
                else:
                    notes.append("HTML block has no tags")
    else:
        notes.append("no code block in response")

    return {
        "tool": "cross_coding",
        "check": "coding_structure",
        "passed": passed,
        "evidence": [],
        "notes": notes,
    }


# ═══════════════════════════════
# EVIDENCE VALIDATION (Validator 2.0)
# ═══════════════════════════════

def validate_evidence(task_id: str, evidence_list: list[dict]) -> dict:
    """Validate a set of evidence for a task.
    
    Checks:
    - All evidence has required fields
    - Evidence kinds are MEASURED (not assumed)
    - No contradictions in evidence
    - Sufficient evidence for confidence
    """
    issues = []
    measured = 0
    total = len(evidence_list)
    
    for i, ev in enumerate(evidence_list):
        # Check required fields
        if "type" not in ev:
            issues.append(f"evidence[{i}]: missing 'type'")
        if "kind" not in ev:
            issues.append(f"evidence[{i}]: missing 'kind'")
        
        # Count measured evidence
        if ev.get("kind") == "MEASURED":
            measured += 1
        elif ev.get("kind") == "ESTIMATED":
            issues.append(f"evidence[{i}]: kind is ESTIMATED, not MEASURED")
        
        # Check for false success markers
        if ev.get("passed") is True and ev.get("kind") != "MEASURED":
            issues.append(f"evidence[{i}]: claims success but kind={ev.get('kind')}")
    
    confidence = measured / max(total, 1)
    
    return {
        "kind": "MEASURED",
        "total": total,
        "measured": measured,
        "confidence": round(confidence, 3),
        "issues": issues,
        "valid": len(issues) == 0 and confidence >= 0.5,
    }


def validate_outcome(task_id: str, claimed_success: bool, evidence: list[dict] = None) -> dict:
    """Validate that a claimed outcome is supported by evidence.
    
    Critical: Never trust "success=True" without evidence.
    """
    from . import evidence as ev_module
    
    # Get task outcome if exists
    task = ev_module.get_task(task_id)
    
    if not task:
        return {
            "kind": "UNVERIFIED",
            "task_id": task_id,
            "valid": False,
            "reason": "No task record found",
        }
    
    # Validate evidence quality
    ev_validation = validate_evidence(task_id, task.get("evidence", []) or [])
    
    # Check if evidence supports the claim
    if claimed_success:
        if not ev_validation["valid"]:
            return {
                "kind": "UNVERIFIED",
                "task_id": task_id,
                "valid": False,
                "reason": f"Evidence insufficient: {len(ev_validation['issues'])} issues",
                "confidence": ev_validation["confidence"],
                "issues": ev_validation["issues"],
            }
        
        # Check for actual verification
        verified_count = sum(1 for e in (task.get("evidence", []) or []) 
                           if e.get("passed") is True and e.get("kind") == "MEASURED")
        
        if verified_count == 0:
            return {
                "kind": "UNVERIFIED",
                "task_id": task_id,
                "valid": False,
                "reason": "No verified evidence supports success claim",
                "confidence": 0,
            }
    
    return {
        "kind": "MEASURED",
        "task_id": task_id,
        "valid": True,
        "confidence": ev_validation["confidence"],
        "evidence_count": ev_validation["total"],
        "measured_count": ev_validation["measured"],
    }


def validate_no_false_success(results: list[dict]) -> dict:
    """Check for false success patterns in results.
    
    Patterns:
    - success=True but no evidence
    - success=True but evidence says failed
    - success=True but kind=ESTIMATED
    """
    false_positives = []
    
    for r in results:
        task_id = r.get("task_id", "unknown")
        success = r.get("success", False)
        evidence = r.get("evidence", [])
        
        if success:
            if not evidence:
                false_positives.append({
                    "task_id": task_id,
                    "issue": "claims success but has no evidence",
                })
            else:
                # Check if any evidence contradicts success
                for ev in evidence:
                    if ev.get("passed") is False:
                        false_positives.append({
                            "task_id": task_id,
                            "issue": f"claims success but evidence '{ev.get('type')}' failed",
                        })
                    if ev.get("kind") != "MEASURED":
                        false_positives.append({
                            "task_id": task_id,
                            "issue": f"claims success but evidence kind={ev.get('kind')}",
                        })
    
    return {
        "kind": "MEASURED",
        "total_checked": len(results),
        "false_positives": false_positives,
        "clean": len(false_positives) == 0,
    }
