from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth.dependencies import current_user
from backend.auth.security import authenticate_role
from backend.models.schemas import AuthLoginRequest, AuthTokenResponse, CurrentUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenResponse)
async def login(data: AuthLoginRequest) -> AuthTokenResponse:
    """Authenticate a user/operator/admin role and return a signed token.
    认证用户/操作员/管理员角色并返回签名 token。"""
    return AuthTokenResponse(**authenticate_role(data.username, data.password, data.role))


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Return the current authenticated principal.
    返回当前已认证主体。"""
    return user
