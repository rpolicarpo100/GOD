"""P2.4 — Sandbox Protection.

Sandboxes:
- File system (restricted paths)
- Network (blocked by default)
- Process (no subprocess)
- Import (restricted modules)

Prevents:
- Path traversal (../../../etc/passwd)
- Symlink attacks
- Import escalation
- Network exfiltration
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .util import now_iso

# ═══════════════════════════════
# PATH RESTRICTIONS
# ═══════════════════════════════

# Allowed base directories (everything else is blocked)
_ALLOWED_BASES = [
    "/home/user",
    "/tmp",
    "/var/tmp",
]

# Always blocked paths
_BLOCKED_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
]

# Blocked patterns
_BLOCKED_PATTERNS = [
    re.compile(r'\.\./'),  # Path traversal
    re.compile(r'/\.'),  # Hidden files/dirs (except allowed)
    re.compile(r'~/' ),  # Home expansion
]

# Allowed hidden paths
_ALLOWED_HIDDEN = [
    "/home/user/.ssh",
    "/home/user/.git",
]


def check_path(path: str, operation: str = "read") -> dict:
    """Check if a path is allowed for the given operation.
    
    Returns: {ok, reason, kind}
    """
    try:
        resolved = Path(path).resolve()
        resolved_str = str(resolved)
    except Exception:
        return {
            "ok": False,
            "kind": "MEASURED",
            "reason": f"Cannot resolve path: {path}",
        }
    
    # Check blocked paths
    for blocked in _BLOCKED_PATHS:
        if resolved_str.startswith(blocked):
            return {
                "ok": False,
                "kind": "MEASURED",
                "reason": f"Blocked path: {blocked}",
            }
    
    # Check allowed bases
    allowed = False
    for base in _ALLOWED_BASES:
        if resolved_str.startswith(base):
            allowed = True
            break
    
    if not allowed:
        return {
            "ok": False,
            "kind": "MEASURED",
            "reason": f"Path outside allowed bases: {resolved_str}",
        }
    
    # Check traversal in original path
    if '..' in path:
        # Check if resolved path is still within allowed base
        in_base = any(resolved_str.startswith(b) for b in _ALLOWED_BASES)
        if not in_base:
            return {
                "ok": False,
                "kind": "MEASURED",
                "reason": "Path traversal detected",
            }
    
    # Write operations: extra restrictions
    if operation == "write":
        # Can't write to system dirs
        for base in _ALLOWED_BASES:
            if resolved_str == base or resolved_str == base + "/":
                return {
                    "ok": False,
                    "kind": "MEASURED",
                    "reason": "Cannot write to base directory",
                }
    
    return {
        "ok": True,
        "kind": "MEASURED",
        "resolved": resolved_str,
    }


def check_symlink(path: str) -> dict:
    """Check if path is a symlink pointing outside allowed area."""
    p = Path(path)
    
    if not p.is_symlink():
        return {"ok": True, "kind": "MEASURED", "is_symlink": False}
    
    try:
        target = p.resolve()
        target_str = str(target)
        
        for base in _ALLOWED_BASES:
            if target_str.startswith(base):
                return {
                    "ok": True,
                    "kind": "MEASURED",
                    "is_symlink": True,
                    "target": target_str,
                }
        
        return {
            "ok": False,
            "kind": "MEASURED",
            "is_symlink": True,
            "target": target_str,
            "reason": "Symlink points outside allowed area",
        }
    except Exception as e:
        return {
            "ok": False,
            "kind": "MEASURED",
            "is_symlink": True,
            "reason": f"Cannot resolve symlink: {e}",
        }


# ═══════════════════════════════
# IMPORT RESTRICTIONS
# ═══════════════════════════════

# Modules that can't be imported in sandboxed code
_BLOCKED_MODULES = {
    "subprocess",
    "shutil",
    "ctypes",
    "importlib",
    "compileall",
    "py_compile",
    "zipimport",
    "pkgutil",
}

# Modules that are always safe
_SAFE_MODULES = {
    "json",
    "math",
    "re",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "string",
    "random",
    "hashlib",
    "base64",
    "pathlib",
    "typing",
}


def check_import(module_name: str) -> dict:
    """Check if a module import is allowed in sandbox."""
    # Extract top-level module
    top = module_name.split('.')[0]
    
    if top in _BLOCKED_MODULES:
        return {
            "ok": False,
            "kind": "MEASURED",
            "reason": f"Blocked module: {top}",
        }
    
    if top in _SAFE_MODULES:
        return {
            "ok": True,
            "kind": "MEASURED",
            "safe": True,
        }
    
    # Unknown modules need review
    return {
        "ok": True,
        "kind": "MEASURED",
        "safe": False,
        "note": f"Module '{top}' not in safe list — review recommended",
    }


# ═══════════════════════════════
# NETWORK RESTRICTIONS
# ═══════════════════════════════

# Allowed hosts (localhost only by default)
_ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
}

# Blocked ports
_BLOCKED_PORTS = {
    22,    # SSH
    23,    # Telnet
    25,    # SMTP
    445,   # SMB
    3389,  # RDP
}


def check_network(host: str, port: int, allow_lan: bool = False) -> dict:
    """Check if network access is allowed."""
    host_lower = host.lower()
    
    # Always blocked ports
    if port in _BLOCKED_PORTS:
        return {
            "ok": False,
            "kind": "MEASURED",
            "reason": f"Blocked port: {port}",
        }
    
    # Localhost always allowed
    if host_lower in _ALLOWED_HOSTS:
        return {
            "ok": True,
            "kind": "MEASURED",
            "host": host,
            "port": port,
        }
    
    # LAN: only with explicit flag
    if allow_lan:
        # Check if it's actually a LAN address
        if _is_lan_address(host):
            return {
                "ok": True,
                "kind": "MEASURED",
                "host": host,
                "port": port,
                "lan": True,
            }
    
    return {
        "ok": False,
        "kind": "MEASURED",
        "reason": f"Network access denied: {host}:{port}",
    }


def _is_lan_address(host: str) -> bool:
    """Check if host is a LAN address."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private
    except ValueError:
        # Not an IP, check common LAN patterns
        return host.endswith('.local') or host.endswith('.lan')


# ═══════════════════════════════
# PROCESS RESTRICTIONS
# ═══════════════════════════════

# Blocked commands
_BLOCKED_COMMANDS = {
    "sudo",
    "su",
    "chmod",
    "chown",
    "mount",
    "umount",
    "fdisk",
    "mkfs",
    "dd",
    "wget",
    "curl",
    "nc",
    "ncat",
    "ssh",
    "scp",
    "rsync",
}

# Safe commands
_SAFE_COMMANDS = {
    "ls",
    "cat",
    "grep",
    "find",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "echo",
    "pwd",
    "date",
    "whoami",
}


def check_command(cmd: str) -> dict:
    """Check if a command is allowed in sandbox."""
    parts = cmd.strip().split()
    if not parts:
        return {"ok": False, "kind": "MEASURED", "reason": "Empty command"}
    
    base_cmd = parts[0]
    
    # Check path
    if '/' in base_cmd:
        base_cmd = os.path.basename(base_cmd)
    
    if base_cmd in _BLOCKED_COMMANDS:
        return {
            "ok": False,
            "kind": "MEASURED",
            "reason": f"Blocked command: {base_cmd}",
        }
    
    if base_cmd in _SAFE_COMMANDS:
        return {
            "ok": True,
            "kind": "MEASURED",
            "safe": True,
        }
    
    return {
        "ok": True,
        "kind": "MEASURED",
        "safe": False,
        "note": f"Command '{base_cmd}' not in safe list — review recommended",
    }

