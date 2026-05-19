from __future__ import annotations

from aiosqlite import IntegrityError
from fastapi import APIRouter, Depends, HTTPException

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


@router.post("/login", response_model=AuthTokenResponse)
async def login(data: AuthLoginRequest) -> AuthTokenResponse:
    """Authenticate a user/operator/admin role and return a signed token.
    认证用户/操作员/管理员角色并返回签名 token。"""
    return AuthTokenResponse(**await authenticate_user(data.username, data.password, data.role))


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
    return AuthTokenResponse(**create_access_token(username=username, role="admin"))


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
    record_username, password_hash, _stored_role = record
    if not verify_password(current_password, password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await db.update_user_password_hash(
        username=record_username,
        password_hash=hash_password(new_password),
    )
    return {"status": "SUCCESS"}
