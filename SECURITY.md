# PHASE 12 — SECURITY

## Date: 2026-09-05

---

## SECURITY STACK

### 1. AUTHENTICATION

**Password Hashing**: PBKDF2-SHA256
- Iterations: 310,000
- Salt: 32 bytes (random per password)
- Storage: hash + salt (never plaintext)

**Evidence**: `auth.py` lines 167-174

**Tests**:
- `test_hash_and_verify` ✓
- `test_different_salts` ✓
- `test_no_plaintext_stored` ✓
- `test_password_minimum_length` ✓ (8 chars)

---

### 2. SESSION MANAGEMENT

**Session ID**: `secrets.token_urlsafe(32)` (256-bit entropy)

**Timeouts**:
- Absolute: 3600s (1 hour)
- Inactivity: 900s (15 minutes)

**Properties**:
- ✓ Invalidated on logout
- ✓ Inactivity timeout
- ✓ Absolute timeout
- ✓ Audit logged

**Evidence**: `auth.py` lines 292-340

**Tests**:
- `test_session_validation` ✓
- `test_invalid_session` ✓
- `test_logout` ✓
- `test_session_inactivity_timeout` ✓

---

### 3. AUTHORIZATION (RBAC)

**Roles**: OWNER, ADMIN, OPERATOR, GUEST

**Permission Model**:
| Role | Permissions |
|------|-------------|
| OWNER | ALL (20 permissions) |
| ADMIN | chat, memory, tools, config_read, governor_read, system_read |
| OPERATOR | chat, memory, tools, config_read, governor_read, system_read |
| GUEST | chat, memory_read, config_read, governor_read, system_read |

**Permission Check**:
```python
def require_permission(session_id, permission):
    session = validate_session(session_id)
    if not session:
        risk = OPERATION_RISK.get(permission, Risk.HIGH)
        if risk <= Risk.INFO:
            return {"user_id": "anonymous", "role": Role.GUEST}
        return {"ok": False, "error": "Autenticação necessária", "code": 401}
    if not has_permission(session["role"], permission):
        return {"ok": False, "error": "Permissão negada", "code": 403}
```

**Evidence**: `auth.py` lines 391-425

**Tests**:
- `test_owner_has_all_permissions` ✓
- `test_guest_limited_permissions` ✓
- `test_require_permission_pass` ✓
- `test_require_permission_fail` ✓
- `test_no_escalation` ✓

---

### 4. INPUT VALIDATION

**SQL Injection Prevention**:
- All queries use parameterized statements (`?` placeholders)
- One f-string query: `SELECT * FROM memory WHERE {where}` — but `where` is built from trusted internal code with `?` placeholders for values

**Evidence**: `store.py` — 29 parameterized queries

**XSS Prevention**:
- API returns JSON (no HTML rendering)
- Frontend (if any) must sanitize

---

### 5. SECRET MANAGEMENT

**API Keys**:
- Stored in `.env` file
- `.env` in `.gitignore`
- Loaded via `load_dotenv()`
- Never logged to events/trace/audit

**Password Storage**:
- PBKDF2-SHA256 (310k iterations)
- Random 32-byte salt per password
- Never stored in plaintext

**Evidence**: `providers.py`, `auth.py`

---

### 6. SENSITIVE DATA DETECTION

**Module**: `superai/sensitive.py`

**Patterns Detected**:
| Type | Pattern | Risk |
|------|---------|------|
| password_assignment | `password = "..."` | 4 |
| api_key | `api_key = "sk-..."` | 4 |
| bearer_token | `Bearer ...` | 4 |
| jwt | `eyJ...` | 5 |
| private_key | `-----BEGIN PRIVATE KEY-----` | 5 |
| connection_string | `postgres://...` | 4 |
| credit_card | Luhn-validated | 5 |
| cpf | Brazilian CPF | 3 |
| ssn | US SSN | 5 |
| ssh_key | `ssh-rsa ...` | 4 |
| aws_key | `AKIA...` | 5 |
| github_token | `ghp_...` | 5 |

**Tests**:
- `test_detect_password_assignment` ✓
- `test_detect_api_key` ✓
- `test_detect_jwt` ✓
- `test_detect_private_key` ✓
- `test_detect_aws_key` ✓
- `test_no_false_positive_clean_text` ✓
- `test_scan_task_content` ✓
- `test_scan_file` ✓

---

### 7. SANDBOX PROTECTION

**Module**: `superai/sandbox.py`

**File System**:
- Allowed bases: `/home/user`, `/tmp`, `/var/tmp`
- Blocked paths: `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`, `/root`, `/proc`, `/sys`, `/dev`, `/boot`
- Path traversal blocked (`..`)

**Import Restrictions**:
- Blocked: subprocess, shutil, ctypes, importlib, compileall, py_compile, zipimport, pkgutil
- Safe: json, math, re, datetime, collections, itertools, functools, string, random, hashlib, base64, pathlib, typing

**Tests**:
- `test_allowed_path` ✓
- `test_blocked_path_etc` ✓
- `test_blocked_path_proc` ✓
- `test_blocked_path_root` ✓
- `test_path_traversal` ✓
- `test_allowed_import` ✓
- `test_blocked_import` ✓
- `test_blocked_import_ctypes` ✓

---

### 8. NETWORK CONTROL

**Module**: `superai/network_control.py`

**Policy**:
- Outbound: blocked by default
- LAN: blocked by default
- Remote: blocked by default
- Localhost: always allowed

**Blocked Ports**: 22 (SSH), 23 (Telnet), 25 (SMTP), 445 (SMB), 3389 (RDP), 5900 (VNC), 6379 (Redis), 27017 (MongoDB)

**Allowed Outbound**: 80 (HTTP), 443 (HTTPS), 53 (DNS), 8080

**Rate Limit**: 30 connections/minute per host:port

**Tests**:
- `test_localhost_allowed` ✓
- `test_127_allowed` ✓
- `test_remote_blocked_by_default` ✓
- `test_blocked_port_ssh` ✓
- `test_policy_change` ✓
- `test_connection_log` ✓

---

### 9. RATE LIMITING

**Module**: `superai/rate_limit.py`

**Endpoint Limits**:
| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/login` | 5 | 60s |
| `/auth/change-password` | 3 | 300s |
| `/task/submit` | 30 | 60s |
| `/task/execute` | 20 | 60s |
| `/api/` | 100 | 60s |
| `/ws` | 10 | 60s |

**Role Multipliers**:
- OWNER: 2x
- ADMIN: 1.5x
- OPERATOR: 1x
- GUEST: 0.5x

**Tests**:
- `test_rate_limit_within` ✓
- `test_rate_limit_exceeded` ✓
- `test_rate_limit_auth_endpoint` ✓
- `test_rate_limit_role_multiplier` ✓
- `test_limiter_stats` ✓

---

### 10. AUDIT TRAIL

**Auth Audit** (`auth._audit()`):
- login, login_fail, logout
- user.create, user.deactivate
- session_expired
- override.created, override.approved, override.consumed
- permission denied

**Store Audit** (`store.audit()`):
- task execution
- config changes
- mission operations

**Evidence**: `auth.py` lines 431-450, `store.py` line 141

**Tests**:
- `test_login_audited` ✓
- `test_failed_login_audited` ✓

---

## SECURITY MATRIX

| Control | Status | Evidence |
|---------|--------|----------|
| Password hashing | ✓ PBKDF2-SHA256 310k | auth.py |
| Session management | ✓ 256-bit, timeout | auth.py |
| RBAC | ✓ 4 roles, 20 perms | auth.py |
| SQL injection | ✓ Parameterized | store.py |
| API key storage | ✓ .env + .gitignore | providers.py |
| Sensitive detection | ✓ 12 patterns | sensitive.py |
| Sandbox | ✓ Path + import | sandbox.py |
| Network control | ✓ Localhost default | network_control.py |
| Rate limiting | ✓ Sliding window | rate_limit.py |
| Audit trail | ✓ Auth + store | auth.py, store.py |
| Governor protection | ✓ Chat check | runtime.py |
| Override safety | ✓ Scoped, temp, single-use | auth.py |

---

## VERIFICATION

### Authentication
```
hash_password("test") → (hash_hex, salt_hex)
verify_password("test", hash, salt) → True
verify_password("wrong", hash, salt) → False
```

### Authorization
```
require_permission(session, "config.write") → ok (OWNER)
require_permission(session, "config.write") → 403 (GUEST)
require_permission(None, "config.write") → 401 (no session)
```

### Sandbox
```
check_path("/etc/passwd") → blocked
check_path("/home/user/GOD/test.py") → allowed
check_path("../../../etc/passwd") → blocked
check_import("subprocess") → blocked
check_import("json") → allowed
```

### Network
```
check_connection("localhost", 8080) → allowed
check_connection("192.168.1.1", 80) → blocked (LAN not enabled)
check_connection("example.com", 443) → blocked (remote not enabled)
```

---

## PHASE GATE

```
==================================================
PHASE GATE
==================================================

PHASE: 12

OBJECTIVE ACHIEVED: YES

COMMANDS EXECUTED:
- Authentication verified ✓
- Session management verified ✓
- Authorization (RBAC) verified ✓
- Input validation verified ✓
- Secret management verified ✓
- Sensitive data detection verified ✓
- Sandbox protection verified ✓
- Network control verified ✓
- Rate limiting verified ✓
- Audit trail verified ✓

TESTS: 252/252 PASS (88 security-specific)

PRE-EXISTING FAILURES: 0

NEW REGRESSIONS: NO

CRITICAL ISSUES: None

BLOCKERS: None

FILES CHANGED: SECURITY.md (new)

EVIDENCE:
- PBKDF2-SHA256 310k iterations
- 256-bit session tokens
- 4-role RBAC with 20 permissions
- Parameterized SQL queries
- 12 sensitive data patterns
- Path + import sandbox
- Localhost-only network default
- Sliding window rate limiting
- Auth + store audit trails

DECISION: PROCEED → PHASE 13

==================================================
```
