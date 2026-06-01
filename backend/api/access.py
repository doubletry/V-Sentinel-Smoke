from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import current_user, require_permission
from backend.auth.roles import list_roles
from backend.db import database as db
from backend.models.schemas import (
    AuditLogEntry,
    BlockedIp,
    BlockIpRequest,
    CurrentUser,
    PaginatedAuditLogsResponse,
    RoleInfo,
)

router = APIRouter(prefix="/api/access", tags=["access"])


def _normalize_datetime_query(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid datetime filter") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@router.get("/roles", response_model=list[RoleInfo])
async def get_roles() -> list[RoleInfo]:
    """Return built-in user/operator/admin role definitions.
    返回内置用户、操作员、管理员角色定义。"""
    return list_roles()


@router.get("/audit-logs", response_model=PaginatedAuditLogsResponse)
async def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    username: str | None = None,
    operation_type: str | None = None,
    result: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    _role: str = Depends(require_permission("audit:read")),
) -> PaginatedAuditLogsResponse:
    """List paginated audit logs with combined filters.
    按组合条件列出分页审计日志。"""
    data = await db.list_audit_logs(
        page=page,
        page_size=page_size,
        username=username,
        operation_type=operation_type,
        result=result,
        start_time=_normalize_datetime_query(start_time),
        end_time=_normalize_datetime_query(end_time),
    )
    return PaginatedAuditLogsResponse(
        items=[AuditLogEntry(**item) for item in data["items"]],
        page=int(data["page"]),
        page_size=int(data["page_size"]),
        total=int(data["total"]),
        total_pages=int(data["total_pages"]),
        operation_types=[str(item) for item in data["operation_types"]],
    )


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
