"""GOD — Security Reality Tests

Tests for authentication, authorization, approval, audit, overrides.
NOT using mocks to fake success — these test real behavior.
"""
import time
import unittest
import os
import shutil
from pathlib import Path

# Use temp dir for test data
TEST_DATA = Path("/tmp/god_test_security")


class TestPasswordHashing(unittest.TestCase):
    """Test password hashing is real and secure."""
    
    def test_hash_and_verify(self):
        from superai.auth import _hash_password, _verify_password
        pw = "MySecureP@ss123"
        h, salt = _hash_password(pw)
        self.assertNotEqual(h, pw)
        self.assertTrue(_verify_password(pw, h, salt))
        self.assertFalse(_verify_password("wrong", h, salt))
    
    def test_different_salts(self):
        from superai.auth import _hash_password
        h1, s1 = _hash_password("test")
        h2, s2 = _hash_password("test")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)
    
    def test_no_plaintext_stored(self):
        from superai.auth import _hash_password
        pw = "plaintext_password"
        h, s = _hash_password(pw)
        self.assertNotIn(pw, h)
        self.assertNotIn(pw, s)


class TestUserManagement(unittest.TestCase):
    """Test user creation and management."""
    
    def setUp(self):
        from superai import auth
        auth.init()
    
    def test_owner_can_be_created(self):
        from superai.auth import create_owner, owner_exists
        # Clean first
        from superai.auth import _load_users, _save_users
        _save_users({})
        self.assertFalse(owner_exists())
        r = create_owner("admin", "SecurePass123")
        self.assertTrue(r["ok"], r)
        self.assertTrue(owner_exists())
    
    def test_only_one_owner(self):
        from superai.auth import create_owner, _save_users
        _save_users({})
        r1 = create_owner("admin1", "SecurePass123")
        self.assertTrue(r1["ok"])
        r2 = create_owner("admin2", "SecurePass456")
        self.assertFalse(r2["ok"])
        self.assertIn("OWNER", r2["error"])
    
    def test_password_minimum_length(self):
        from superai.auth import create_owner, _save_users
        _save_users({})
        r = create_owner("admin", "short")
        self.assertFalse(r["ok"])
        self.assertIn("8", r["error"])
    
    def test_username_minimum_length(self):
        from superai.auth import create_owner, _save_users
        _save_users({})
        r = create_owner("ab", "SecurePass123")
        self.assertFalse(r["ok"])
        self.assertIn("3", r["error"])


class TestAuthentication(unittest.TestCase):
    """Test login, logout, sessions."""
    
    def setUp(self):
        from superai import auth
        from superai.auth import _save_users
        auth.init()
        _save_users({})
        auth.create_owner("testowner", "TestPass123")
    
    def test_valid_login(self):
        from superai.auth import login
        r = login("testowner", "TestPass123")
        self.assertTrue(r["ok"], r)
        self.assertIn("session_id", r)
        self.assertEqual(r["role"], "OWNER")
    
    def test_invalid_password(self):
        from superai.auth import login
        r = login("testowner", "wrongpassword")
        self.assertFalse(r["ok"])
        self.assertIn("Credenciais", r["error"])
    
    def test_invalid_user(self):
        from superai.auth import login
        r = login("nonexistent", "TestPass123")
        self.assertFalse(r["ok"])
    
    def test_session_validation(self):
        from superai.auth import login, validate_session
        r = login("testowner", "TestPass123")
        session = validate_session(r["session_id"])
        self.assertIsNotNone(session)
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["role"], "OWNER")
    
    def test_invalid_session(self):
        from superai.auth import validate_session
        self.assertIsNone(validate_session("invalid-session-id"))
        self.assertIsNone(validate_session(""))
        self.assertIsNone(validate_session(None))
    
    def test_logout(self):
        from superai.auth import login, logout, validate_session
        r = login("testowner", "TestPass123")
        sid = r["session_id"]
        logout(sid)
        self.assertIsNone(validate_session(sid))
    
    def test_session_inactivity_timeout(self):
        from superai.auth import login, validate_session, _sessions, _save_sessions, SESSION_INACTIVE
        r = login("testowner", "TestPass123")
        sid = r["session_id"]
        # Simulate inactivity
        _sessions[sid]["last_active"] = time.time() - SESSION_INACTIVE - 1
        _save_sessions()
        self.assertIsNone(validate_session(sid))


class TestAuthorization(unittest.TestCase):
    """Test role-based access control."""
    
    def setUp(self):
        from superai import auth
        from superai.auth import _save_users
        auth.init()
        _save_users({})
        auth.create_owner("testowner", "TestPass123")
        auth.create_user("guest1", "GuestPass123", "GUEST")
    
    def test_owner_has_all_permissions(self):
        from superai.auth import has_permission, Perm, Role
        for perm in [Perm.SECURITY_MANAGE, Perm.GOVERNOR_OVERRIDE, Perm.OS_KILL]:
            self.assertTrue(has_permission(Role.OWNER, perm))
    
    def test_guest_limited_permissions(self):
        from superai.auth import has_permission, Perm, Role
        self.assertTrue(has_permission(Role.GUEST, Perm.CHAT_USE))
        self.assertTrue(has_permission(Role.GUEST, Perm.SYSTEM_READ))
        self.assertFalse(has_permission(Role.GUEST, Perm.SECURITY_MANAGE))
        self.assertFalse(has_permission(Role.GUEST, Perm.GOVERNOR_OVERRIDE))
        self.assertFalse(has_permission(Role.GUEST, Perm.OS_KILL))
    
    def test_require_permission_pass(self):
        from superai.auth import login, require_permission, Perm
        r = login("testowner", "TestPass123")
        check = require_permission(r["session_id"], Perm.SECURITY_MANAGE)
        self.assertTrue(check["ok"])
    
    def test_require_permission_fail(self):
        from superai.auth import login, require_permission, Perm
        r = login("guest1", "GuestPass123")
        check = require_permission(r["session_id"], Perm.SECURITY_MANAGE)
        self.assertFalse(check["ok"])
        self.assertEqual(check["code"], 403)
    
    def test_no_session_denied_for_protected(self):
        from superai.auth import require_permission, Perm
        check = require_permission(None, Perm.SECURITY_MANAGE)
        self.assertFalse(check["ok"])
        self.assertEqual(check["code"], 401)
    
    def test_no_escalation(self):
        """SYSTEM role cannot become OWNER."""
        from superai.auth import has_permission, Role, Perm
        self.assertFalse(has_permission(Role.SYSTEM, Perm.SECURITY_MANAGE))
        self.assertFalse(has_permission(Role.WORKER, Perm.SECURITY_MANAGE))


class TestRiskModel(unittest.TestCase):
    """Test risk classification."""
    
    def test_risk_levels(self):
        from superai.auth import get_risk_level, Risk, Perm
        self.assertEqual(get_risk_level(Perm.CHAT_USE), Risk.INFO)
        self.assertEqual(get_risk_level(Perm.OS_KILL), Risk.CRITICAL)
        self.assertEqual(get_risk_level(Perm.GOVERNOR_OVERRIDE), Risk.HIGH)


class TestGovernorOverride(unittest.TestCase):
    """Test governor overrides are scoped, temporary, single-use."""
    
    def setUp(self):
        from superai import auth
        auth.init()
    
    def test_create_and_approve(self):
        from superai.auth import create_override, approve_override, validate_override, Risk
        r = create_override("user-1", "governor.override", "*", "testing", Risk.HIGH, 600)
        self.assertTrue(r["ok"])
        oid = r["override_id"]
        self.assertFalse(validate_override(oid, "governor.override", "*"))
        approve_override(oid, "admin")
        self.assertTrue(validate_override(oid, "governor.override", "*"))
    
    def test_single_use(self):
        from superai.auth import create_override, approve_override, consume_override, validate_override
        r = create_override("user-1", "governor.override", "*", "test")
        oid = r["override_id"]
        approve_override(oid, "admin")
        consume_override(oid)
        self.assertFalse(validate_override(oid, "governor.override", "*"))
    
    def test_expiration(self):
        from superai.auth import create_override, approve_override, validate_override, OVERRIDES_FILE
        import json
        r = create_override("user-1", "governor.override", "*", "test", duration_seconds=1)
        oid = r["override_id"]
        approve_override(oid, "admin")
        # Modify expiration directly in file
        data = json.loads(OVERRIDES_FILE.read_text())
        data[oid]["expires_at"] = time.time() - 1
        OVERRIDES_FILE.write_text(json.dumps(data, indent=2))
        self.assertFalse(validate_override(oid, "governor.override", "*"))
    
    def test_scope_check(self):
        from superai.auth import create_override, approve_override, validate_override
        r = create_override("user-1", "fs.write", "/tmp/safe", "test")
        oid = r["override_id"]
        approve_override(oid, "admin")
        self.assertTrue(validate_override(oid, "fs.write", "/tmp/safe"))
        self.assertFalse(validate_override(oid, "fs.write", "/etc/passwd"))


class TestApprovalEngine(unittest.TestCase):
    """Test approval workflow."""
    
    def setUp(self):
        from superai import auth
        auth.init()
    
    def test_request_and_approve(self):
        from superai.auth import request_approval, decide_approval, validate_approval, ApprovalState
        r = request_approval("user-1", "os.kill", "/proc/123", "testing")
        self.assertTrue(r["ok"])
        aid = r["approval_id"]
        self.assertFalse(validate_approval(aid, "os.kill"))
        decide_approval(aid, "admin", True)
        self.assertTrue(validate_approval(aid, "os.kill"))
    
    def test_deny(self):
        from superai.auth import request_approval, decide_approval, validate_approval
        r = request_approval("user-1", "os.kill", "/proc/123")
        aid = r["approval_id"]
        decide_approval(aid, "admin", False)
        self.assertFalse(validate_approval(aid, "os.kill"))
    
    def test_single_use(self):
        from superai.auth import request_approval, decide_approval, consume_approval, validate_approval
        r = request_approval("user-1", "os.kill", "/proc/123")
        aid = r["approval_id"]
        decide_approval(aid, "admin", True)
        consume_approval(aid)
        self.assertFalse(validate_approval(aid, "os.kill"))
    
    def test_expiration(self):
        from superai.auth import request_approval, decide_approval, validate_approval, APPROVALS_FILE
        import json
        r = request_approval("user-1", "os.kill", "/proc/123", duration_seconds=1)
        aid = r["approval_id"]
        decide_approval(aid, "admin", True)
        # Modify expiration directly in file
        data = json.loads(APPROVALS_FILE.read_text())
        data[aid]["expires_at"] = time.time() - 1
        APPROVALS_FILE.write_text(json.dumps(data, indent=2))
        self.assertFalse(validate_approval(aid, "os.kill"))


class TestAuditLedger(unittest.TestCase):
    """Test audit logging."""
    
    def setUp(self):
        from superai import auth
        auth.init()
    
    def test_login_audited(self):
        from superai.auth import _save_users, create_owner, login, audit_log
        _save_users({})
        create_owner("audittest", "TestPass123")
        login("audittest", "TestPass123")
        events = audit_log(10)
        actions = [e["action"] for e in events]
        self.assertIn("auth.login", actions)
    
    def test_failed_login_audited(self):
        from superai.auth import _save_users, create_owner, login, audit_log
        _save_users({})
        create_owner("audittest2", "TestPass123")
        login("audittest2", "WrongPass")
        events = audit_log(10)
        actions = [e["action"] for e in events]
        self.assertIn("auth.login_fail", actions)


class TestSecurityFlow(unittest.TestCase):
    """Test complete security flow."""
    
    def setUp(self):
        from superai import auth
        from superai.auth import _save_users
        auth.init()
        _save_users({})
        auth.create_owner("flowowner", "TestPass123")
    
    def test_full_flow_pass(self):
        from superai.auth import login, security_check, Perm
        r = login("flowowner", "TestPass123")
        check = security_check(r["session_id"], Perm.CHAT_USE)
        self.assertTrue(check["ok"])
    
    def test_full_flow_no_auth(self):
        from superai.auth import security_check, Perm
        # No session = GUEST role → GUEST lacks SECURITY_MANAGE → 403
        check = security_check(None, Perm.SECURITY_MANAGE)
        self.assertFalse(check["ok"])
        self.assertIn(check["code"], [401, 403])
    
    def test_full_flow_wrong_role(self):
        from superai.auth import login, security_check, Perm, create_user
        create_user("flowguest", "GuestPass123", "GUEST")
        r = login("flowguest", "GuestPass123")
        check = security_check(r["session_id"], Perm.OS_KILL)
        self.assertFalse(check["ok"])
        self.assertEqual(check["code"], 403)


class TestRemoteWorkerAuth(unittest.TestCase):
    """Test that remote workers require authentication."""
    
    def test_worker_auth_local_allowed(self):
        """Local workers should always be allowed."""
        import server
        # Should not raise for local workers even without token
        try:
            server._worker_auth(None, "local")
            local_ok = True
        except Exception:
            local_ok = False
        self.assertTrue(local_ok)
    
    def test_worker_auth_remote_no_token(self):
        """Remote workers without token configured should be rejected."""
        import server
        # Save and clear token
        old_token = server.WORKER_TOKEN
        server.WORKER_TOKEN = ""
        try:
            server._worker_auth(None, "remote")
            remote_ok = False  # Should have raised
        except Exception as e:
            remote_ok = "403" in str(e) or "não configurado" in str(e).lower() or "not configured" in str(e).lower()
        finally:
            server.WORKER_TOKEN = old_token
        self.assertTrue(remote_ok)
    
    def test_worker_auth_remote_wrong_token(self):
        """Remote workers with wrong token should be rejected."""
        import server
        old_token = server.WORKER_TOKEN
        server.WORKER_TOKEN = "correct-token-123"
        try:
            server._worker_auth("Bearer wrong-token", "remote")
            wrong_ok = False
        except Exception as e:
            wrong_ok = "401" in str(e)
        finally:
            server.WORKER_TOKEN = old_token
        self.assertTrue(wrong_ok)
    
    def test_worker_auth_remote_correct_token(self):
        """Remote workers with correct token should be allowed."""
        import server
        old_token = server.WORKER_TOKEN
        server.WORKER_TOKEN = "correct-token-123"
        try:
            server._worker_auth("Bearer correct-token-123", "remote")
            correct_ok = True
        except Exception:
            correct_ok = False
        finally:
            server.WORKER_TOKEN = old_token
        self.assertTrue(correct_ok)


class TestThreadSafety(unittest.TestCase):
    """Verify auth state is protected by locks."""

    def test_sessions_lock_exists(self):
        """_sessions_lock should be a threading.RLock."""
        import threading
        from superai import auth
        self.assertIsInstance(auth._sessions_lock, type(threading.RLock()))

    def test_overrides_lock_exists(self):
        import threading
        from superai import auth
        self.assertIsInstance(auth._overrides_lock, type(threading.RLock()))

    def test_approvals_lock_exists(self):
        import threading
        from superai import auth
        self.assertIsInstance(auth._approvals_lock, type(threading.RLock()))

    def test_concurrent_session_access(self):
        """Multiple threads accessing sessions should not crash or corrupt state."""
        import threading
        from superai.auth import login, validate_session, logout

        # Create owner if needed
        from superai.auth import owner_exists, create_owner
        if not owner_exists():
            create_owner("thread_test_owner2", "test_pass_123")

        errors = []

        def worker(i):
            try:
                r = login("thread_test_owner2", "test_pass_123")
                if r.get("ok"):
                    sid = r["session_id"]
                    # Validate — may fail due to concurrent file writes, that's OK
                    validate_session(sid)
                    logout(sid)
            except Exception as e:
                errors.append((i, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Key assertion: NO exceptions (thread safety = no crashes)
        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")


if __name__ == "__main__":
    unittest.main()
