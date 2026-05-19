from __future__ import annotations

from fastapi import APIRouter

from backend.auth.roles import list_roles
from backend.models.schemas import RoleInfo

router = APIRouter(prefix="/api/access", tags=["access"])


@router.get("/roles", response_model=list[RoleInfo])
async def get_roles() -> list[RoleInfo]:
    """Return built-in user/operator/admin role definitions.
    返回内置用户、操作员、管理员角色定义。"""
    return list_roles()
