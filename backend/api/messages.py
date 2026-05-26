from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.auth.dependencies import require_permission
from backend.db.database import (
    delete_analysis_message,
    delete_analysis_messages,
    get_analysis_message_image_path,
    get_analysis_message_for_notification,
    list_analysis_messages,
    mark_analysis_message_false_positive,
    unmark_analysis_message_false_positive,
)
from backend.models.schemas import AnalysisMessage, PaginatedMessagesResponse

router = APIRouter(prefix="/api/messages", tags=["messages"])

MAX_BATCH_DELETE_IDS = 500


@router.get("", response_model=PaginatedMessagesResponse)
async def get_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_id: str | None = Query(default=None),
    false_positive_only: bool = Query(default=False),
    start_date: str | None = Query(default=None, description="Inclusive YYYY-MM-DD lower bound (UTC)."),
    end_date: str | None = Query(default=None, description="Inclusive YYYY-MM-DD upper bound (UTC)."),
) -> PaginatedMessagesResponse:
    """Return persisted analysis messages ordered newest-first.
    返回按时间倒序排列的持久化分析消息。

    ``start_date`` / ``end_date`` (YYYY-MM-DD) filter ``created_at`` by UTC
    calendar day; both bounds are inclusive.
    ``start_date`` / ``end_date``（YYYY-MM-DD）按 UTC 自然日过滤创建时间，
    起止日期均包含。"""
    result = await list_analysis_messages(
        page=page,
        page_size=page_size,
        source_id=source_id,
        false_positive_only=false_positive_only,
        start_date=start_date,
        end_date=end_date,
    )
    return PaginatedMessagesResponse(
        items=[AnalysisMessage(**row) for row in result["items"]],
        page=int(result["page"]),
        page_size=int(result["page_size"]),
        total=int(result["total"]),
        total_pages=int(result["total_pages"]),
    )


@router.post("/{message_id}/false-positive")
async def mark_message_false_positive(
    message_id: str,
    _role: str = Depends(require_permission("messages:annotate")),
) -> dict[str, object]:
    """Mark a message as false positive and export its original/detected images.
    将消息标记为误报并导出原图/检测图。"""
    result = await mark_analysis_message_false_positive(message_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.post("/{message_id}/resend-notification")
async def resend_message_notification(
    message_id: str,
    _role: str = Depends(require_permission("messages:annotate")),
) -> dict[str, object]:
    """Manually resend notifications for one persisted analysis message.
    手动为一条已持久化分析消息再次触发通知。"""
    message = await get_analysis_message_for_notification(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    from backend.main import notification_dispatcher  # avoid circular import

    results = await notification_dispatcher.send_event(message, force=True)
    has_success = any(result.get("status") == "SUCCESS" for result in results)
    return {
        "id": message_id,
        "status": "sent" if has_success else ("failed" if results else "no_enabled_provider"),
        "results": results,
    }


@router.delete("/{message_id}/false-positive")
async def unmark_message_false_positive(
    message_id: str,
    _role: str = Depends(require_permission("messages:annotate")),
) -> dict[str, object]:
    """Clear the false-positive flag for a message.
    清除消息的误报标记。"""
    result = await unmark_analysis_message_false_positive(message_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    _role: str = Depends(require_permission("messages:delete")),
) -> dict[str, object]:
    """Permanently delete one message and its associated thumbnail images.
    永久删除一条消息及其关联的缩略图。

    Exports under ``false_positives/`` are intentionally preserved.
    ``false_positives/`` 目录下导出的误报图片不会被删除。"""
    result = await delete_analysis_message(message_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.post("/batch-delete")
async def batch_delete_messages(
    payload: dict = Body(...),
    _role: str = Depends(require_permission("messages:delete")),
) -> dict[str, object]:
    """Permanently delete multiple messages in one request.
    一次性永久删除多条消息。

    Body: ``{"ids": ["...", "..."]}``. Exports under ``false_positives/`` are
    intentionally preserved.
    请求体：``{"ids": ["...", "..."]}``。``false_positives/`` 目录下的导出图片
    不会被删除。"""
    raw_ids = payload.get("ids") if isinstance(payload, dict) else None
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="'ids' must be a list of message IDs")
    if len(raw_ids) > MAX_BATCH_DELETE_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many ids; maximum {MAX_BATCH_DELETE_IDS} per request",
        )
    cleaned: list[str] = []
    for entry in raw_ids:
        if not isinstance(entry, str) or not entry.strip():
            raise HTTPException(status_code=400, detail="Each id must be a non-empty string")
        cleaned.append(entry.strip())
    return await delete_analysis_messages(cleaned)


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

