from __future__ import annotations

from aiosqlite import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth.dependencies import current_user
from backend.auth.security import (
    authenticate_user,
    create_access_token,
    hash_password,
    verify_password,
)
from backend.db import database as db
from backend.models.schemas import (
    AuthBootstrapStatus,
    AuthLoginRequest,
    AuthPasswordChangeRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    CurrentUser,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    if request.client is not None and request.client.host:
        return str(request.client.host)
    return ""


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: str | None, default: int) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


async def _enforce_ip_block(ip: str) -> None:
    if not ip:
        return
    blocked, blocked_until = await db.is_ip_blocked(ip)
    if blocked:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "IP_BLOCKED",
                "message": "IP temporarily blocked due to repeated login failures",
                "blocked_until": blocked_until,
            },
        )


async def _register_failure_and_maybe_block(ip: str, username: str) -> None:
    if not ip:
        return
    await db.record_login_failure(ip, username)
    settings_map = await db.get_all_settings()
    max_attempts = _safe_int(settings_map.get("login_lockout_max_attempts"), 5)
    window_seconds = _safe_int(settings_map.get("login_lockout_window_seconds"), 300)
    duration_seconds = _safe_int(settings_map.get("login_lockout_duration_seconds"), 900)
    if max_attempts <= 0 or window_seconds <= 0:
        return
    failures = await db.count_recent_failures(ip, window_seconds)
    if failures >= max_attempts:
        await db.block_ip(
            ip=ip,
            duration_seconds=duration_seconds if duration_seconds > 0 else None,
            reason=f"Exceeded {max_attempts} failed login attempts in {window_seconds}s",
        )
        blocked, blocked_until = await db.is_ip_blocked(ip)
        raise HTTPException(
            status_code=403,
            detail={
                "code": "IP_BLOCKED",
                "message": "IP temporarily blocked due to repeated login failures",
                "blocked_until": blocked_until,
            },
        )


@router.post("/login", response_model=AuthTokenResponse)
async def login(data: AuthLoginRequest, request: Request) -> AuthTokenResponse:
    """Authenticate a user/operator/admin role and return a signed token.
    认证用户/操作员/管理员角色并返回签名 token。"""
    settings_map = await db.get_all_settings()
    trust_proxy = _truthy(settings_map.get("login_lockout_trust_proxy"))
    ip = _client_ip(request, trust_proxy)

    await _enforce_ip_block(ip)

    try:
        token = await authenticate_user(data.username, data.password, data.role)
    except HTTPException as exc:
        if exc.status_code == 401:
            await _register_failure_and_maybe_block(ip, str(data.username or ""))
        raise

    await db.clear_login_failures(ip)
    return AuthTokenResponse(**token)


@router.get("/bootstrap", response_model=AuthBootstrapStatus)
async def bootstrap_status() -> AuthBootstrapStatus:
    """Return whether the system is still waiting for its first admin account.
    返回系统是否仍在等待首个管理员账号。"""
    user_count = await db.count_users()
    return AuthBootstrapStatus(has_users=user_count > 0, registration_open=user_count == 0)


@router.post("/register", response_model=AuthTokenResponse, status_code=201)
async def register_first_admin(data: AuthRegisterRequest) -> AuthTokenResponse:
    """Register the very first platform account as admin.
    将平台首个账号注册为管理员。"""
    username = str(data.username or "").strip()
    password = str(data.password or "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    try:
        await db.create_first_user_account(
            username=username,
            password_hash=hash_password(password),
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return AuthTokenResponse(
        **create_access_token(username=username, role="admin", registered_user=True)
    )


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Return the current authenticated principal.
    返回当前已认证主体。"""
    return user


@router.post("/password")
async def change_password(
    data: AuthPasswordChangeRequest,
    user: CurrentUser = Depends(current_user),
) -> dict[str, str]:
    """Change the password for the current registered account.
    修改当前已注册账号的密码。"""
    current_password = str(data.current_password or "")
    new_password = str(data.new_password or "")
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Current password and new password are required")
    record = await db.get_user_auth_record(user.username)
    if record is None:
        raise HTTPException(status_code=400, detail="Only registered accounts can change passwords")
    record_username, password_hash, _stored_role, _is_banned, _expires_at = record
    if not verify_password(current_password, password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await db.update_user_password_hash(
        username=record_username,
        password_hash=hash_password(new_password),
    )
    return {"status": "SUCCESS"}
