from __future__ import annotations

from sqlite3 import IntegrityError

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import current_user
from backend.auth.security import authenticate_user, create_access_token, hash_password
from backend.db import database as db
from backend.models.schemas import (
    AuthBootstrapStatus,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    CurrentUser,
    UserAccountCreate,
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
    if await db.count_users() > 0:
        raise HTTPException(status_code=403, detail="Public registration is closed")
    username = str(data.username or "").strip()
    password = str(data.password or "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    try:
        await db.create_user_account(
            UserAccountCreate(username=username, password=password, role="admin"),
            password_hash=hash_password(password),
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return AuthTokenResponse(**create_access_token(username=username, role="admin"))


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Return the current authenticated principal.
    返回当前已认证主体。"""
    return user
