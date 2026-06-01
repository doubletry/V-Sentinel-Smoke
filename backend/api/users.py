from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiosqlite import IntegrityError
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import current_user, require_permission
from backend.auth.security import hash_password
from backend.db import database as db
from backend.models.schemas import (
    AdminPasswordResetRequest,
    CurrentUser,
    UserAccount,
    UserAccountCreate,
    UserAccountUpdate,
)

router = APIRouter(prefix="/api/users", tags=["users"])


def _normalize_iso(value: str | None) -> str | None:
    """Validate and normalize an ISO 8601 timestamp string.
    校验并规范化 ISO 8601 时间字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid expires_at timestamp") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


async def _default_expires_at_for_role(role: str) -> str | None:
    """Compute the default expiration ISO timestamp for a role, or None.
    根据角色计算默认过期 ISO 时间，若不限制则返回 None。"""
    days_setting = await db.get_setting(f"account_expiration_days_{role}")
    days_text = str(days_setting or "").strip()
    if not days_text:
        return None
    try:
        days = int(days_text)
    except ValueError:
        return None
    if days <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _count_other_active_admins(users: list[UserAccount], excluded_username: str) -> int:
    return sum(
        1
        for user in users
        if user.role == "admin" and not user.is_banned and user.username != excluded_username
    )


@router.get("", response_model=list[UserAccount])
async def list_users(
    _role: str = Depends(require_permission("users:*")),
) -> list[UserAccount]:
    """List all registered platform accounts.
    列出所有已注册平台账号。"""
    return await db.list_users()


@router.post("", response_model=UserAccount, status_code=201)
async def create_user(
    data: UserAccountCreate,
    _role: str = Depends(require_permission("users:*")),
) -> UserAccount:
    """Create a new platform account as administrator.
    由管理员创建新的平台账号。"""
    username = str(data.username or "").strip()
    password = str(data.password or "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    expires_at = _normalize_iso(data.expires_at)
    if expires_at is None:
        expires_at = await _default_expires_at_for_role(data.role)
    try:
        return await db.create_user_account(
            username=username,
            role=data.role,
            password_hash=hash_password(password),
            expires_at=expires_at,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists") from exc


@router.patch("/{username}", response_model=UserAccount)
async def update_user(
    username: str,
    data: UserAccountUpdate,
    me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_permission("users:*")),
) -> UserAccount:
    """Admin update of a user account (role / ban / expiration).
    管理员更新用户账号（角色 / 封禁 / 有效期）。"""
    target_username = str(username or "").strip()
    target = await db.get_user_account(target_username)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if data.is_banned is not None:
        if data.is_banned and target_username == me.username:
            raise HTTPException(status_code=400, detail="Cannot ban yourself")
        if data.is_banned and target.role == "admin":
            users = await db.list_users()
            if _count_other_active_admins(users, target_username) <= 0:
                raise HTTPException(
                    status_code=400, detail="Cannot ban the last admin account"
                )
        await db.set_user_banned(username=target_username, banned=bool(data.is_banned))

    if data.role is not None and data.role != target.role:
        if target.role == "admin" and data.role != "admin" and not target.is_banned:
            users = await db.list_users()
            if _count_other_active_admins(users, target_username) <= 0:
                raise HTTPException(
                    status_code=400, detail="Cannot demote the last admin account"
                )
        await db.update_user_role(username=target_username, role=data.role)

    if data.clear_expires_at:
        await db.update_user_expires_at(username=target_username, expires_at=None)
    elif data.expires_at is not None:
        normalized = _normalize_iso(data.expires_at)
        await db.update_user_expires_at(username=target_username, expires_at=normalized)

    updated = await db.get_user_account(target_username)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.delete("/{username}", status_code=204)
async def delete_user(
    username: str,
    me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_permission("users:*")),
) -> None:
    """Delete a user account.
    删除用户账号。"""
    target_username = str(username or "").strip()
    if target_username == me.username:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await db.get_user_account(target_username)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "admin" and not target.is_banned:
        users = await db.list_users()
        if _count_other_active_admins(users, target_username) <= 0:
            raise HTTPException(
                status_code=400, detail="Cannot delete the last admin account"
            )
    deleted = await db.delete_user_account(target_username)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/{username}/password")
async def admin_reset_password(
    username: str,
    data: AdminPasswordResetRequest,
    _role: str = Depends(require_permission("users:*")),
) -> dict[str, str]:
    """Admin force-reset of a user's password.
    管理员强制重置用户密码。"""
    new_password = str(data.new_password or "")
    if not new_password:
        raise HTTPException(status_code=400, detail="new_password is required")
    target_username = str(username or "").strip()
    target = await db.get_user_account(target_username)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    updated = await db.admin_update_user_password_hash(
        username=target_username,
        password_hash=hash_password(new_password),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "SUCCESS"}
