"""Auth Router — authentication and authorization endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from superai import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "GUEST"


class ApprovalDecisionIn(BaseModel):
    approve: bool


class OverrideIn(BaseModel):
    action: str
    scope: str = "*"
    reason: str = ""
    risk_level: int = 3
    duration_seconds: int = 600


def _extract_session(authorization: str | None) -> str | None:
    if not authorization:
        return None
    return authorization.replace("Bearer ", "").strip() or None


@router.get("/status")
def auth_status():
    return auth.auth_status()


@router.post("/setup")
def auth_setup(body: LoginIn):
    r = auth.create_owner(body.username, body.password)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error"))
    return r


@router.post("/login")
def login(body: LoginIn):
    from superai.rate_limit import check as rl_check
    rl = rl_check("login", "auth/login", "anonymous")
    if not rl.get("allowed", True):
        raise HTTPException(429, f"Rate limited. Tenta novamente em {rl.get('retry_after', 60)}s")
    r = auth.login(body.username, body.password)
    if not r.get("ok"):
        raise HTTPException(401, r.get("error"))
    return r


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    return auth.logout(session_id)


@router.get("/session")
def session_info(authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    session = auth.validate_session(session_id)
    if not session:
        raise HTTPException(401, "Sessão inválida")
    return session


@router.post("/users")
def create_user(body: CreateUserIn, authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return auth.create_user(body.username, body.password, body.role)


@router.get("/users")
def list_users(authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    users = auth._load_users()
    return [{"id": u["id"], "username": u["username"], "role": u["role"], "active": u["active"]} for u in users.values()]


@router.get("/audit")
def audit_log(limit: int = 50, authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return {"events": auth.audit_log(limit)}


@router.get("/approvals")
def pending_approvals(authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return {"approvals": auth.pending_approvals()}


@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: str, body: ApprovalDecisionIn, authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.SECURITY_MANAGE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return auth.decide_approval(approval_id, check["user_id"], body.approve)


@router.post("/overrides")
def create_override(body: OverrideIn, authorization: str | None = Header(default=None)):
    session_id = authorization.replace("Bearer ", "") if authorization else None
    check = auth.require_permission(session_id, auth.Perm.GOVERNOR_OVERRIDE)
    if not check.get("ok"):
        raise HTTPException(check.get("code", 403), check.get("error"))
    return auth.create_override(check["user_id"], body.action, body.scope, body.reason, body.risk_level, body.duration_seconds)
