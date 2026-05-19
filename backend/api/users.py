from __future__ import annotations

from sqlite3 import IntegrityError

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import require_permission
from backend.auth.security import hash_password
from backend.db import database as db
from backend.models.schemas import UserAccount, UserAccountCreate

router = APIRouter(prefix="/api/users", tags=["users"])


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
    try:
        return await db.create_user_account(data, password_hash=hash_password(password))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists") from exc
