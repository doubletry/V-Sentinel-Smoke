from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException, Query

from backend.auth.roles import ROLE_PERMISSIONS
from backend.auth.security import _is_account_expired, verify_access_token
from backend.db import database as db
from backend.models.schemas import CurrentUser


def _extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token.strip()


def has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, [])
    namespace = permission.split(":", 1)[0]
    return permission in permissions or f"{namespace}:*" in permissions


async def _resolve_token_payload(authorization: str | None) -> dict:
    """Verify token + recheck DB-backed account state (ban / expiration).
    校验 Bearer token 并复查数据库中的账号状态（封禁/过期）。"""
    payload = verify_access_token(_extract_bearer_token(authorization))
    username = str(payload.get("sub") or "")
    if username:
        record = await db.get_user_auth_record(username)
        if record is not None:
            _username, _password_hash, stored_role, is_banned, expires_at = record
            if is_banned:
                raise HTTPException(status_code=401, detail="Account banned")
            if _is_account_expired(expires_at):
                raise HTTPException(status_code=401, detail="Account expired")
            payload["role"] = stored_role
            payload["expires_at"] = expires_at
        elif payload.get("registered_user") is True:
            raise HTTPException(status_code=401, detail="Account not found")
    return payload


def require_permission(permission: str) -> Callable[[str | None], str]:
    """Return a FastAPI dependency requiring a role permission.
    返回要求角色权限的 FastAPI 依赖。"""

    async def dependency(authorization: str | None = Header(default=None, alias="Authorization")) -> str:
        payload = await _resolve_token_payload(authorization)
        role = str(payload["role"])
        if not has_permission(role, permission):
            raise HTTPException(status_code=403, detail="Insufficient role permission")
        return role

    return dependency


def require_any_permission(*permissions: str) -> Callable[[str | None], str]:
    """Return a FastAPI dependency requiring at least one role permission.
    返回要求角色至少拥有其中一个权限的 FastAPI 依赖。"""

    async def dependency(authorization: str | None = Header(default=None, alias="Authorization")) -> str:
        payload = await _resolve_token_payload(authorization)
        role = str(payload["role"])
        if not any(has_permission(role, permission) for permission in permissions):
            raise HTTPException(status_code=403, detail="Insufficient role permission")
        return role

    return dependency


def require_permission_for_image(permission: str) -> Callable[..., str]:
    """Return a FastAPI dependency that accepts token via Authorization header
    OR ``?token=...`` query parameter (for <img> tags that can't set headers).
    返回 FastAPI 依赖，支持通过 Authorization 头或 ``?token=...`` 查询参数
    传递 token（用于 <img> 标签无法设置请求头的场景）。"""

    async def dependency(
        authorization: str | None = Header(default=None, alias="Authorization"),
        token: str | None = Query(default=None),
    ) -> str:
        # Prefer Authorization header; fall back to query param
        if authorization:
            payload = await _resolve_token_payload(authorization)
        elif token:
            payload = await _resolve_token_payload(f"Bearer {token}")
        else:
            raise HTTPException(status_code=401, detail="Missing bearer token")
        role = str(payload["role"])
        if not has_permission(role, permission):
            raise HTTPException(status_code=403, detail="Insufficient role permission")
        return role

    return dependency


async def current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> CurrentUser:
    """Resolve the current authenticated user from a Bearer token.
    从 Bearer token 解析当前已认证用户。"""
    payload = await _resolve_token_payload(authorization)
    role = str(payload["role"])
    expires_at = payload.get("expires_at")
    return CurrentUser(
        username=str(payload.get("sub") or ""),
        role=role,
        permissions=list(ROLE_PERMISSIONS.get(role, [])),
        expires_at=expires_at if expires_at else None,
        expired=_is_account_expired(expires_at) if expires_at else False,
    )
