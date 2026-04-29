from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.db.database import (
    get_analysis_message_image_path,
    list_analysis_messages,
    mark_analysis_message_false_positive,
)
from backend.models.schemas import AnalysisMessage, PaginatedMessagesResponse

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("", response_model=PaginatedMessagesResponse)
async def get_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_id: str | None = Query(default=None),
    false_positive_only: bool = Query(default=False),
) -> PaginatedMessagesResponse:
    """Return persisted analysis messages ordered newest-first.
    返回按时间倒序排列的持久化分析消息。"""
    result = await list_analysis_messages(
        page=page,
        page_size=page_size,
        source_id=source_id,
        false_positive_only=false_positive_only,
    )
    return PaginatedMessagesResponse(
        items=[AnalysisMessage(**row) for row in result["items"]],
        page=int(result["page"]),
        page_size=int(result["page_size"]),
        total=int(result["total"]),
        total_pages=int(result["total_pages"]),
    )


@router.post("/{message_id}/false-positive")
async def mark_message_false_positive(message_id: str) -> dict[str, object]:
    """Mark a message as false positive and export its original/detected images.
    将消息标记为误报并导出原图/检测图。"""
    result = await mark_analysis_message_false_positive(message_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.get("/{message_id}/image", include_in_schema=False)
async def get_message_image(message_id: str) -> FileResponse:
    """Backward-compatible detected-image endpoint.
    向后兼容的检测图接口。"""
    file_path = await get_analysis_message_image_path(message_id, kind="detected")
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Message image not found")
    return FileResponse(file_path)


@router.get("/{message_id}/images/{image_kind}", include_in_schema=False)
async def get_message_image_by_kind(message_id: str, image_kind: str) -> FileResponse:
    """Serve one persisted original/detected analysis image from disk.
    从磁盘提供单条消息的原图或检测图。"""
    file_path = await get_analysis_message_image_path(message_id, kind=image_kind)
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Message image not found")
    return FileResponse(file_path)
