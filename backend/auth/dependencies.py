from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException

from backend.auth.roles import ROLE_PERMISSIONS


def _normalize_role(role: str | None) -> str:
    candidate = str(role or "admin").strip().lower()
    if candidate not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=401, detail="Invalid role")
    return candidate


def _has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, [])
    namespace = permission.split(":", 1)[0]
    return permission in permissions or f"{namespace}:*" in permissions


def require_permission(permission: str) -> Callable[[str | None], str]:
    """Return a FastAPI dependency requiring a role permission.
    返回要求角色权限的 FastAPI 依赖。"""

    async def dependency(x_user_role: str | None = Header(default=None, alias="X-User-Role")) -> str:
        role = _normalize_role(x_user_role)
        if not _has_permission(role, permission):
            raise HTTPException(status_code=403, detail="Insufficient role permission")
        return role

    return dependency
