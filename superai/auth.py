"""GOD — Human Authority Layer: Authentication + Authorization + Audit

Central security module. Never duplicate auth logic elsewhere.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from .config import DATA

# ═══════════════════════════════
# CONSTANTS
# ═══════════════════════════════

AUTH_DIR = DATA / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SESSIONS_FILE = AUTH_DIR / "sessions.json"
AUDIT_FILE = AUTH_DIR / "audit.jsonl"
OVERRIDES_FILE = AUTH_DIR / "overrides.json"
APPROVALS_FILE = AUTH_DIR / "approvals.json"

SESSION_TIMEOUT = 3600  # 1 hour absolute
SESSION_INACTIVE = 900  # 15 min inactivity
REAUTH_TIMEOUT = 300    # 5 min for critical actions

# ═══════════════════════════════
# ROLES
# ═══════════════════════════════

class Role(str, Enum):
    OWNER = "OWNER"
    GUEST = "GUEST"
    SYSTEM = "SYSTEM"
    WORKER = "WORKER"

# ═══════════════════════════════
# PERMISSIONS
# ═══════════════════════════════

class Perm:
    # Chat
    CHAT_USE = "chat.use"
    
    # Memory
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    
    # Tools
    TOOLS_EXECUTE = "tools.execute"
    
    # Config
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"
    
    # Governor
    GOVERNOR_READ = "governor.read"
    GOVERNOR_OVERRIDE = "governor.override"
    
    # GOD profiles
    GODS_MANAGE = "gods.manage"
    GODS_ACTIVATE = "gods.activate"
    
    # Admin
    REPAIR_EXECUTE = "repair.execute"
    EVOLUTION_EXECUTE = "evolution.execute"
    WORKER_MANAGE = "worker.manage"
    OS_EXECUTE = "os.execute"
    OS_KILL = "os.kill"
    SECURITY_MANAGE = "security.manage"
    REMOTE_ENABLE = "remote.enable"
    
    # System
    SYSTEM_READ = "system.read"
    SYSTEM_WRITE = "system.write"
    FLAGS_MANAGE = "flags.manage"
    BENCHMARK_RUN = "benchmark.run"

# Role → permissions mapping
ROLE_PERMS: dict[str, set[str]] = {
    Role.OWNER: {
        # Everything
        Perm.CHAT_USE, Perm.MEMORY_READ, Perm.MEMORY_WRITE,
        Perm.TOOLS_EXECUTE, Perm.CONFIG_READ, Perm.CONFIG_WRITE,
        Perm.GOVERNOR_READ, Perm.GOVERNOR_OVERRIDE,
        Perm.GODS_MANAGE, Perm.GODS_ACTIVATE,
        Perm.REPAIR_EXECUTE, Perm.EVOLUTION_EXECUTE,
        Perm.WORKER_MANAGE, Perm.OS_EXECUTE, Perm.OS_KILL,
        Perm.SECURITY_MANAGE, Perm.REMOTE_ENABLE,
        Perm.SYSTEM_READ, Perm.SYSTEM_WRITE, Perm.FLAGS_MANAGE,
        Perm.BENCHMARK_RUN,
    },
    Role.GUEST: {
        Perm.CHAT_USE, Perm.MEMORY_READ,
        Perm.CONFIG_READ, Perm.GOVERNOR_READ,
        Perm.SYSTEM_READ,
    },
    Role.SYSTEM: {
        Perm.CHAT_USE, Perm.MEMORY_READ, Perm.MEMORY_WRITE,
        Perm.TOOLS_EXECUTE, Perm.CONFIG_READ,
        Perm.GOVERNOR_READ, Perm.SYSTEM_READ,
    },
    Role.WORKER: {
        Perm.TOOLS_EXECUTE, Perm.SYSTEM_READ,
    },
}

# ═══════════════════════════════
# RISK LEVELS
# ═══════════════════════════════

class Risk:
    INFO = 0       # Pure info, auto-execute
    LOW = 1        # Low risk, auto + log
    MODERATE = 2   # Moderate, auto + notify
    HIGH = 3       # Requires human approval
    CRITICAL = 4   # Requires auth + approval + confirmation
    FORBIDDEN = 5  # Prohibited by default

# Risk classification for operations
OPERATION_RISK: dict[str, int] = {
    # Read operations
    "chat.use": Risk.INFO,
    "memory.read": Risk.INFO,
    "config.read": Risk.INFO,
    "governor.read": Risk.INFO,
    "system.read": Risk.INFO,
    
    # Low risk
    "memory.write": Risk.LOW,
    "tools.execute": Risk.LOW,
    "benchmark.run": Risk.LOW,
    
    # Moderate
    "config.write": Risk.MODERATE,
    "evolution.execute": Risk.MODERATE,
    "repair.execute": Risk.MODERATE,
    
    # High risk — requires approval
    "governor.override": Risk.HIGH,
    "gods.manage": Risk.HIGH,
    "gods.activate": Risk.HIGH,
    "flags.manage": Risk.HIGH,
    "worker.manage": Risk.HIGH,
    
    # Critical — requires auth + approval + confirmation
    "os.execute": Risk.CRITICAL,
    "os.kill": Risk.CRITICAL,
    "security.manage": Risk.CRITICAL,
    "remote.enable": Risk.CRITICAL,
    
    # Forbidden by default
    "self_elevation": Risk.FORBIDDEN,
}

# ═══════════════════════════════
# PASSWORD HASHING
# ═══════════════════════════════

def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Hash password with PBKDF2-SHA256. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = os.urandom(32)
    else:
        salt = bytes.fromhex(salt) if isinstance(salt, str) else salt
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310000)
    return key.hex(), salt.hex()

def _verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    """Verify password against stored hash."""
    computed, _ = _hash_password(password, stored_salt)
    return secrets.compare_digest(computed, stored_hash)

# ═══════════════════════════════
# USER MANAGEMENT
# ═══════════════════════════════

@dataclass
class User:
    id: str
    username: str
    role: str
    password_hash: str = ""
    password_salt: str = ""
    created_at: float = 0
    last_login: float = 0
    active: bool = True

def _ensure_auth_dir():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

def _load_users() -> dict[str, dict]:
    _ensure_auth_dir()
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return {}

def _save_users(users: dict[str, dict]):
    _ensure_auth_dir()
    USERS_FILE.write_text(json.dumps(users, indent=2))

def owner_exists() -> bool:
    """Check if an OWNER account exists."""
    users = _load_users()
    return any(u.get("role") == Role.OWNER for u in users.values())

def create_owner(username: str, password: str) -> dict:
    """Create the OWNER account. Only one allowed."""
    users = _load_users()
    if any(u.get("role") == Role.OWNER for u in users.values()):
        return {"ok": False, "error": "OWNER já existe"}
    if not username or len(username) < 3:
        return {"ok": False, "error": "Username deve ter >= 3 caracteres"}
    if not password or len(password) < 8:
        return {"ok": False, "error": "Password deve ter >= 8 caracteres"}
    
    uid = "owner-" + secrets.token_hex(8)
    pw_hash, pw_salt = _hash_password(password)
    users[uid] = {
        "id": uid,
        "username": username,
        "role": Role.OWNER,
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "created_at": time.time(),
        "last_login": 0,
        "active": True,
    }
    _save_users(users)
    _audit("user.create", uid, {"role": Role.OWNER, "username": username})
    return {"ok": True, "user_id": uid}

def create_user(username: str, password: str, role: str = Role.GUEST) -> dict:
    """Create a user. Only OWNER can create users with privileged roles."""
    users = _load_users()
    if role not in [r.value for r in Role]:
        return {"ok": False, "error": f"Role inválida: {role}"}
    if role == Role.OWNER:
        return {"ok": False, "error": "Não é possível criar OWNER via create_user"}
    if any(u.get("username") == username for u in users.values()):
        return {"ok": False, "error": "Username já existe"}
    
    uid = f"{role.lower()}-{secrets.token_hex(8)}"
    pw_hash, pw_salt = _hash_password(password)
    users[uid] = {
        "id": uid,
        "username": username,
        "role": role,
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "created_at": time.time(),
        "last_login": 0,
        "active": True,
    }
    _save_users(users)
    _audit("user.create", uid, {"role": role, "username": username})
    return {"ok": True, "user_id": uid}

# ═══════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════

@dataclass
class Session:
    session_id: str
    user_id: str
    role: str
    created_at: float
    last_active: float
    ip: str = ""
    active: bool = True

_sessions: dict[str, dict] = {}

def _load_sessions():
    global _sessions
    if SESSIONS_FILE.exists():
        _sessions = json.loads(SESSIONS_FILE.read_text())

def _save_sessions():
    _ensure_auth_dir()
    SESSIONS_FILE.write_text(json.dumps(_sessions, indent=2))

def login(username: str, password: str) -> dict:
    """Authenticate user and create session."""
    users = _load_users()
    user = None
    for u in users.values():
        if u.get("username") == username and u.get("active"):
            user = u
            break
    
    if not user:
        _audit("auth.login_fail", None, {"username": username, "reason": "user_not_found"})
        return {"ok": False, "error": "Credenciais inválidas"}
    
    if not _verify_password(password, user["password_hash"], user["password_salt"]):
        _audit("auth.login_fail", user["id"], {"username": username, "reason": "bad_password"})
        return {"ok": False, "error": "Credenciais inválidas"}
    
    # Update last login
    users[user["id"]]["last_login"] = time.time()
    _save_users(users)
    
    # Create session
    session_id = secrets.token_urlsafe(32)
    now = time.time()
    _sessions[session_id] = {
        "session_id": session_id,
        "user_id": user["id"],
        "role": user["role"],
        "created_at": now,
        "last_active": now,
        "active": True,
    }
    _save_sessions()
    
    _audit("auth.login", user["id"], {"session_id": session_id})
    return {
        "ok": True,
        "session_id": session_id,
        "user_id": user["id"],
        "role": user["role"],
        "username": user["username"],
    }

def logout(session_id: str) -> dict:
    """Invalidate session."""
    if session_id in _sessions:
        uid = _sessions[session_id]["user_id"]
        _sessions[session_id]["active"] = False
        _save_sessions()
        _audit("auth.logout", uid, {"session_id": session_id})
    return {"ok": True}

def validate_session(session_id: str) -> dict | None:
    """Validate session. Returns session info or None."""
    if not session_id or session_id not in _sessions:
        return None
    
    s = _sessions[session_id]
    if not s.get("active"):
        return None
    
    now = time.time()
    # Check absolute timeout
    if now - s["created_at"] > SESSION_TIMEOUT:
        s["active"] = False
        _save_sessions()
        _audit("auth.session_expired", s["user_id"], {"reason": "absolute_timeout"})
        return None
    
    # Check inactivity
    if now - s["last_active"] > SESSION_INACTIVE:
        s["active"] = False
        _save_sessions()
        _audit("auth.session_expired", s["user_id"], {"reason": "inactivity"})
        return None
    
    # Update last active
    s["last_active"] = now
    _save_sessions()
    
    return {
        "session_id": s["session_id"],
        "user_id": s["user_id"],
        "role": s["role"],
        "authenticated": True,
    }

# ═══════════════════════════════
# AUTHORIZATION
# ═══════════════════════════════

def has_permission(role: str, permission: str) -> bool:
    """Check if role has permission."""
    perms = ROLE_PERMS.get(role, set())
    return permission in perms

def require_permission(session_id: str | None, permission: str) -> dict:
    """Require permission. Returns session info or raises."""
    if not session_id:
        session = None
    else:
        session = validate_session(session_id)
    
    # No session = check if operation is low risk (auto-allow for chat/read)
    if not session:
        risk = OPERATION_RISK.get(permission, Risk.HIGH)
        if risk <= Risk.INFO:
            return {"user_id": "anonymous", "role": Role.GUEST, "permission": permission}
        _audit("auth.no_session", None, {"permission": permission})
        return {"ok": False, "error": "Autenticação necessária", "code": 401}
    
    if not has_permission(session["role"], permission):
        _audit("auth.denied", session["user_id"], {"permission": permission, "role": session["role"]})
        return {"ok": False, "error": "Permissão negada", "code": 403}
    
    return {
        "ok": True,
        "user_id": session["user_id"],
        "role": session["role"],
        "session_id": session["session_id"],
        "permission": permission,
    }

def get_risk_level(permission: str) -> int:
    """Get risk level for an operation."""
    return OPERATION_RISK.get(permission, Risk.MODERATE)

# ═══════════════════════════════
# AUDIT LEDGER
# ═══════════════════════════════

def _audit(action: str, user_id: str | None, details: dict | None = None):
    """Write audit event. Rotates log when > 5000 lines."""
    _ensure_auth_dir()
    # Rotate if too large
    _MAX_LINES = 5000
    if AUDIT_FILE.exists():
        try:
            size = AUDIT_FILE.stat().st_size
            if size > 1_000_000:  # > 1MB
                lines = AUDIT_FILE.read_text().strip().split("\n")
                if len(lines) > _MAX_LINES:
                    # Keep last 2000 lines
                    keep = lines[-2000:]
                    AUDIT_FILE.write_text("\n".join(keep) + "\n")
        except Exception:
            pass  # Never block audit on rotation failure
    event = {
        "id": secrets.token_hex(8),
        "ts": time.time(),
        "action": action,
        "user_id": user_id,
        "details": details or {},
    }
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def audit_log(limit: int = 50) -> list[dict]:
    """Read audit log."""
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text().strip().split("\n")
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events

# ═══════════════════════════════
# GOVERNOR OVERRIDES
# ═══════════════════════════════

@dataclass
class GovernorOverride:
    id: str
    user_id: str
    action: str
    scope: str
    reason: str
    risk_level: int
    created_at: float
    expires_at: float
    approved: bool = False
    used: bool = False
    result: str = ""

_overrides: dict[str, dict] = {}

def _load_overrides():
    global _overrides
    if OVERRIDES_FILE.exists():
        _overrides = json.loads(OVERRIDES_FILE.read_text())

def _save_overrides():
    _ensure_auth_dir()
    OVERRIDES_FILE.write_text(json.dumps(_overrides, indent=2))

def create_override(user_id: str, action: str, scope: str, reason: str, 
                   risk_level: int = Risk.HIGH, duration_seconds: int = 600) -> dict:
    """Create a governor override request."""
    oid = "ovr-" + secrets.token_hex(8)
    now = time.time()
    _overrides[oid] = {
        "id": oid,
        "user_id": user_id,
        "action": action,
        "scope": scope,
        "reason": reason,
        "risk_level": risk_level,
        "created_at": now,
        "expires_at": now + duration_seconds,
        "approved": False,
        "used": False,
        "result": "",
    }
    _save_overrides()
    _audit("override.created", user_id, {"override_id": oid, "action": action, "scope": scope})
    return {"ok": True, "override_id": oid, "expires_at": now + duration_seconds}

def approve_override(override_id: str, approver_id: str) -> dict:
    """Approve a governor override."""
    _load_overrides()
    if override_id not in _overrides:
        return {"ok": False, "error": "Override não encontrado"}
    o = _overrides[override_id]
    if o["approved"]:
        return {"ok": False, "error": "Já aprovado"}
    if time.time() > o["expires_at"]:
        return {"ok": False, "error": "Override expirado"}
    o["approved"] = True
    _save_overrides()
    _audit("override.approved", approver_id, {"override_id": override_id})
    return {"ok": True}

def consume_override(override_id: str) -> dict:
    """Consume an approved override. Single use only."""
    _load_overrides()
    if override_id not in _overrides:
        return {"ok": False, "error": "Override não encontrado"}
    o = _overrides[override_id]
    if not o["approved"]:
        return {"ok": False, "error": "Override não aprovado"}
    if o["used"]:
        return {"ok": False, "error": "Override já consumido"}
    if time.time() > o["expires_at"]:
        return {"ok": False, "error": "Override expirado"}
    o["used"] = True
    _save_overrides()
    _audit("override.consumed", o["user_id"], {"override_id": override_id})
    return {"ok": True}

def validate_override(override_id: str, action: str, scope: str) -> bool:
    """Validate an override is approved, not consumed, not expired, and matches action/scope."""
    _load_overrides()
    if override_id not in _overrides:
        return False
    o = _overrides[override_id]
    if not o["approved"] or o["used"]:
        return False
    if time.time() > o["expires_at"]:
        return False
    if o["action"] != action:
        return False
    # Scope check: override scope must contain or match the requested scope
    if scope and not (o["scope"] == "*" or scope.startswith(o["scope"])):
        return False
    return True

# ═══════════════════════════════
# APPROVAL ENGINE
# ═══════════════════════════════

class ApprovalState:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONSUMED = "CONSUMED"

_approvals: dict[str, dict] = {}

def _load_approvals():
    global _approvals
    if APPROVALS_FILE.exists():
        _approvals = json.loads(APPROVALS_FILE.read_text())

def _save_approvals():
    _ensure_auth_dir()
    APPROVALS_FILE.write_text(json.dumps(_approvals, indent=2))

def request_approval(user_id: str, action: str, resource: str, scope: str = "",
                    reason: str = "", risk_level: int = Risk.HIGH,
                    duration_seconds: int = 300) -> dict:
    """Request approval for a risky action."""
    aid = "apr-" + secrets.token_hex(8)
    now = time.time()
    _approvals[aid] = {
        "id": aid,
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "scope": scope,
        "reason": reason,
        "risk_level": risk_level,
        "state": ApprovalState.PENDING,
        "created_at": now,
        "expires_at": now + duration_seconds,
        "approved_by": None,
        "decision_at": None,
        "consumed": False,
    }
    _save_approvals()
    _audit("approval.requested", user_id, {"approval_id": aid, "action": action})
    return {"ok": True, "approval_id": aid, "state": ApprovalState.PENDING}

def decide_approval(approval_id: str, approver_id: str, approve: bool) -> dict:
    """Approve or deny an approval request."""
    _load_approvals()
    if approval_id not in _approvals:
        return {"ok": False, "error": "Approval não encontrado"}
    a = _approvals[approval_id]
    if a["state"] != ApprovalState.PENDING:
        return {"ok": False, "error": f"Estado inválido: {a['state']}"}
    if time.time() > a["expires_at"]:
        a["state"] = ApprovalState.EXPIRED
        _save_approvals()
        return {"ok": False, "error": "Approval expirado"}
    
    a["state"] = ApprovalState.APPROVED if approve else ApprovalState.DENIED
    a["approved_by"] = approver_id
    a["decision_at"] = time.time()
    _save_approvals()
    
    action = "approval.approved" if approve else "approval.denied"
    _audit(action, approver_id, {"approval_id": approval_id})
    return {"ok": True, "state": a["state"]}

def consume_approval(approval_id: str) -> dict:
    """Consume an approved approval. Single use."""
    _load_approvals()
    if approval_id not in _approvals:
        return {"ok": False, "error": "Approval não encontrado"}
    a = _approvals[approval_id]
    if a["state"] != ApprovalState.APPROVED:
        return {"ok": False, "error": f"Estado inválido: {a['state']}"}
    if a["consumed"]:
        return {"ok": False, "error": "Já consumido"}
    if time.time() > a["expires_at"]:
        a["state"] = ApprovalState.EXPIRED
        _save_approvals()
        return {"ok": False, "error": "Approval expirado"}
    
    a["consumed"] = True
    a["state"] = ApprovalState.CONSUMED
    _save_approvals()
    _audit("approval.consumed", a["user_id"], {"approval_id": approval_id})
    return {"ok": True}

def validate_approval(approval_id: str, action: str) -> bool:
    """Validate an approval is valid for the given action."""
    _load_approvals()
    if approval_id not in _approvals:
        return False
    a = _approvals[approval_id]
    if a["state"] != ApprovalState.APPROVED:
        return False
    if a["consumed"]:
        return False
    if time.time() > a["expires_at"]:
        return False
    if a["action"] != action:
        return False
    return True

def pending_approvals() -> list[dict]:
    """List pending approvals."""
    _load_approvals()
    return [a for a in _approvals.values() 
            if a["state"] == ApprovalState.PENDING 
            and time.time() <= a["expires_at"]]

# ═══════════════════════════════
# SECURITY FLOW
# ═══════════════════════════════

def security_check(session_id: str | None, permission: str, 
                  resource: str = "", scope: str = "") -> dict:
    """
    Full security flow:
    1. Authenticate
    2. Authorize
    3. Risk classification
    4. Return result
    """
    # Step 1: Authenticate
    if session_id:
        session = validate_session(session_id)
        if not session:
            return {"ok": False, "error": "Sessão inválida ou expirada", "code": 401}
    else:
        session = {"user_id": "anonymous", "role": Role.GUEST}
    
    # Step 2: Authorize
    if not has_permission(session["role"], permission):
        _audit("security.denied", session["user_id"], {"permission": permission})
        return {"ok": False, "error": "Permissão negada", "code": 403}
    
    # Step 3: Risk classification
    risk = get_risk_level(permission)
    
    # Step 4: If high/critical risk, require approval
    if risk >= Risk.HIGH:
        # Check for existing valid approval
        approvals = _approvals if hasattr(_approvals, 'values') else {}
        for a in (approvals.values() if hasattr(approvals, 'values') else []):
            if (a.get("user_id") == session["user_id"] 
                and a.get("action") == permission
                and a.get("state") == ApprovalState.APPROVED
                and not a.get("consumed")
                and time.time() <= a.get("expires_at", 0)):
                return {
                    "ok": True,
                    "user_id": session["user_id"],
                    "role": session["role"],
                    "risk": risk,
                    "requires_approval": True,
                    "approval_id": a["id"],
                }
        
        return {
            "ok": False,
            "error": f"Operação de risco {risk} requer aprovação",
            "code": 428,  # Precondition Required
            "risk": risk,
            "requires_approval": True,
        }
    
    return {
        "ok": True,
        "user_id": session["user_id"],
        "role": session["role"],
        "risk": risk,
    }

# ═══════════════════════════════
# INITIALIZATION
# ═══════════════════════════════

def init():
    """Initialize auth system. Call on startup."""
    _ensure_auth_dir()
    _load_sessions()
    _load_overrides()
    _load_approvals()
    # Clean expired sessions
    now = time.time()
    expired = [sid for sid, s in _sessions.items() 
               if now - s.get("created_at", 0) > SESSION_TIMEOUT
               or now - s.get("last_active", 0) > SESSION_INACTIVE]
    for sid in expired:
        _sessions[sid]["active"] = False
    if expired:
        _save_sessions()

def auth_status() -> dict:
    """Get auth system status."""
    users = _load_users()
    active_sessions = sum(1 for s in _sessions.values() if s.get("active"))
    return {
        "owner_exists": owner_exists(),
        "total_users": len(users),
        "active_sessions": active_sessions,
        "pending_approvals": len(pending_approvals()),
    }
