from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import current_user, require_permission
from backend.auth.roles import list_roles
from backend.db import database as db
from backend.models.schemas import BlockedIp, BlockIpRequest, CurrentUser, RoleInfo

router = APIRouter(prefix="/api/access", tags=["access"])


@router.get("/roles", response_model=list[RoleInfo])
async def get_roles() -> list[RoleInfo]:
    """Return built-in user/operator/admin role definitions.
    返回内置用户、操作员、管理员角色定义。"""
    return list_roles()


@router.get("/blocked-ips", response_model=list[BlockedIp])
async def get_blocked_ips(
    _role: str = Depends(require_permission("users:*")),
) -> list[BlockedIp]:
    """List currently blocked client IPs.
    列出当前被封锁的客户端 IP。"""
    return await db.list_blocked_ips()


@router.post("/blocked-ips", response_model=BlockedIp, status_code=201)
async def add_blocked_ip(
    data: BlockIpRequest,
    me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_permission("users:*")),
) -> BlockedIp:
    """Manually block a client IP.
    手动封锁某客户端 IP。"""
    ip = str(data.ip or "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip is required")
    duration = data.duration_seconds
    if duration is not None and duration < 0:
        raise HTTPException(status_code=400, detail="duration_seconds must be >= 0")
    blocked = await db.block_ip(
        ip=ip,
        duration_seconds=duration if duration and duration > 0 else None,
        reason=str(data.reason or "Manually blocked"),
        blocked_by=me.username or None,
    )
    if blocked is None:
        raise HTTPException(status_code=400, detail="ip is required")
    return blocked


@router.delete("/blocked-ips/{ip}", status_code=204)
async def remove_blocked_ip(
    ip: str,
    _role: str = Depends(require_permission("users:*")),
) -> None:
    """Manually unblock a client IP and clear its failure counter.
    手动解除客户端 IP 封锁并清空失败计数。"""
    normalized = str(ip or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="ip is required")
    removed = await db.unblock_ip(normalized)
    if not removed:
        raise HTTPException(status_code=404, detail="IP is not blocked")
