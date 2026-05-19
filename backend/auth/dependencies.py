from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException

from backend.auth.roles import ROLE_PERMISSIONS
from backend.auth.security import verify_access_token
from backend.models.schemas import CurrentUser


def _extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token.strip()


def _has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, [])
    namespace = permission.split(":", 1)[0]
    return permission in permissions or f"{namespace}:*" in permissions


def require_permission(permission: str) -> Callable[[str | None], str]:
    """Return a FastAPI dependency requiring a role permission.
    返回要求角色权限的 FastAPI 依赖。"""

    async def dependency(authorization: str | None = Header(default=None, alias="Authorization")) -> str:
        payload = verify_access_token(_extract_bearer_token(authorization))
        role = str(payload["role"])
        if not _has_permission(role, permission):
            raise HTTPException(status_code=403, detail="Insufficient role permission")
        return role

    return dependency


async def current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> CurrentUser:
    """Resolve the current authenticated user from a Bearer token.
    从 Bearer token 解析当前已认证用户。"""
    payload = verify_access_token(_extract_bearer_token(authorization))
    role = str(payload["role"])
    return CurrentUser(
        username=str(payload.get("sub") or ""),
        role=role,
        permissions=list(ROLE_PERMISSIONS.get(role, [])),
    )
