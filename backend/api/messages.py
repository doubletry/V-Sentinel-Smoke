from __future__ import annotations

import time

import cv2
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from loguru import logger

from backend.auth.dependencies import require_permission, require_permission_for_image
from backend.db import database as db
from backend.db.database import (
    delete_analysis_message,
    delete_analysis_messages,
    get_analysis_message_image_path,
    get_analysis_message_for_notification,
    get_analysis_message_review_context,
    list_analysis_messages,
    mark_analysis_message_false_positive,
    unmark_analysis_message_false_positive,
)
from backend.models.schemas import AnalysisMessage, PaginatedMessagesResponse
from core.fire_door.constants import (
    DEFAULT_VL_CONFIRM_PROMPT as FIRE_DOOR_DEFAULT_VL_PROMPT,
    DEFAULT_VL_CONFIRM_RESPONSE_KEY as FIRE_DOOR_DEFAULT_VL_RESPONSE_KEY,
)
from core.smoke.constants import (
    DEFAULT_VL_CONFIRM_PROMPT as SMOKE_DEFAULT_VL_PROMPT,
    DEFAULT_VL_CONFIRM_RESPONSE_KEY as SMOKE_DEFAULT_VL_RESPONSE_KEY,
)
from core.vl_confirm import VLConfirmClient, encode_frame_as_data_url, parse_vl_response, vl_sampling_kwargs

router = APIRouter(prefix="/api/messages", tags=["messages"])

MAX_BATCH_DELETE_IDS = 500

# Message thumbnails are immutable once persisted, so the browser can cache
# them for a long time and skip revalidation entirely.
# 消息缩略图一旦持久化即不可变，浏览器可长时间缓存并跳过重新校验。
MESSAGE_IMAGE_CACHE_HEADERS = {
    "Cache-Control": "private, max-age=31536000, immutable",
}


@router.get("", response_model=PaginatedMessagesResponse)
async def get_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_id: str | None = Query(default=None),
    false_positive_filter: str = Query(default="all", description="all | only | exclude"),
    start_date: str | None = Query(default=None, description="Inclusive YYYY-MM-DD lower bound (UTC)."),
    end_date: str | None = Query(default=None, description="Inclusive YYYY-MM-DD upper bound (UTC)."),
    _role: str = Depends(require_permission("messages:read")),
) -> PaginatedMessagesResponse:
    """Return persisted analysis messages ordered newest-first.
    返回按时间倒序排列的持久化分析消息。

    ``false_positive_filter``: ``all`` (default, no filter), ``only``
    (false positives only) or ``exclude`` (valid alerts only).
    ``false_positive_filter``：``all``（默认，不过滤）、``only``（仅误报）、
    ``exclude``（仅有效告警）。

    ``start_date`` / ``end_date`` (YYYY-MM-DD) filter ``created_at`` by UTC
    calendar day; both bounds are inclusive.
    ``start_date`` / ``end_date``（YYYY-MM-DD）按 UTC 自然日过滤创建时间，
    起止日期均包含。"""
    result = await list_analysis_messages(
        page=page,
        page_size=page_size,
        source_id=source_id,
        false_positive_filter=false_positive_filter,
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


SCENE_VL_DEFAULTS = {
    "smoke": (SMOKE_DEFAULT_VL_PROMPT, SMOKE_DEFAULT_VL_RESPONSE_KEY),
    "fire_door": (FIRE_DOOR_DEFAULT_VL_PROMPT, FIRE_DOOR_DEFAULT_VL_RESPONSE_KEY),
}


@router.post("/{message_id}/vl-review")
async def review_message_with_vl(
    message_id: str,
    _role: str = Depends(require_permission("messages:annotate")),
) -> dict[str, object]:
    """Re-run VL confirmation on a persisted message. Display-only.
    对一条已持久化消息重跑 VL 复盘（只展示结果，不修改消息状态）。"""
    context = await get_analysis_message_review_context(message_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Message not found")
    scene_id = context["scene_id"]
    settings_map = await db.get_all_settings()
    enabled = str(settings_map.get(f"{scene_id}_vl_confirm_enabled") or "false").strip().lower()
    if enabled != "true":
        raise HTTPException(
            status_code=422,
            detail=f"VL confirmation is not enabled for scene '{scene_id}'",
        )
    base_url = str(settings_map.get("vl_confirm_base_url") or "").strip()
    model = str(settings_map.get("vl_confirm_model") or "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=422, detail="VL base URL and model are required")
    try:
        timeout = max(1, int(float(settings_map.get("vl_confirm_timeout") or 60)))
    except ValueError:
        timeout = 60

    image_source = str(settings_map.get(f"{scene_id}_vl_confirm_image_source") or "original").strip().lower()
    kind = "detected" if image_source == "annotated" else "original"
    # Fall back to the other kind when the configured one is missing; 404 only if both are absent.
    # 配置的图缺失时回退到另一种 kind；两种都取不到才 404（消息已无任何可用图片）。
    fallback_kind = "original" if kind == "detected" else "detected"
    file_path = await get_analysis_message_image_path(message_id, kind=kind)
    if file_path is None or not file_path.is_file():
        file_path = await get_analysis_message_image_path(message_id, kind=fallback_kind)
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Message image not found")
    frame_bgr = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
    if frame_bgr is None:
        raise HTTPException(status_code=404, detail="Message image not found")
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    image_data_url = encode_frame_as_data_url(frame_rgb)

    prompt = str(settings_map.get(f"{scene_id}_vl_confirm_prompt") or "").strip()
    response_key = str(settings_map.get(f"{scene_id}_vl_confirm_response_key") or "").strip()
    default_prompt, default_response_key = SCENE_VL_DEFAULTS.get(
        scene_id, (SMOKE_DEFAULT_VL_PROMPT, SMOKE_DEFAULT_VL_RESPONSE_KEY)
    )
    prompt = prompt or default_prompt
    response_key = response_key or default_response_key

    client = VLConfirmClient(
        base_url=base_url,
        api_key=str(settings_map.get("vl_confirm_api_key") or "EMPTY").strip() or "EMPTY",
        model=model,
        timeout=timeout,
        **vl_sampling_kwargs(settings_map, scene_id),
    )
    started = time.monotonic()
    try:
        raw = await client.complete(image_data_url, prompt)
    except Exception as exc:
        logger.opt(exception=True).warning(
            "VL re-review failed: message_id={} model={}", message_id, model
        )
        raise HTTPException(status_code=502, detail=f"VL request failed: {exc}")
    latency_ms = int((time.monotonic() - started) * 1000)
    verdict = parse_vl_response(raw, response_key)
    result = "confirmed" if verdict is True else ("rejected" if verdict is False else "unknown")
    logger.info(
        "VL re-review ok: message_id={} verdict={} latency_ms={}",
        message_id, result, latency_ms,
    )
    return {
        "result": result,
        "raw_response": raw,
        "latency_ms": latency_ms,
        "model": model,
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
async def get_message_image(
    message_id: str,
    _role: str = Depends(require_permission_for_image("messages:read")),
) -> FileResponse:
    """Backward-compatible detected-image endpoint.
    向后兼容的检测图接口。"""
    file_path = await get_analysis_message_image_path(message_id, kind="detected")
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Message image not found")
    return FileResponse(file_path, headers=MESSAGE_IMAGE_CACHE_HEADERS)


@router.get("/{message_id}/images/{image_kind}", include_in_schema=False)
async def get_message_image_by_kind(
    message_id: str,
    image_kind: str,
    _role: str = Depends(require_permission_for_image("messages:read")),
) -> FileResponse:
    """Serve one persisted original/detected analysis image from disk.
    从磁盘提供单条消息的原图或检测图。"""
    file_path = await get_analysis_message_image_path(message_id, kind=image_kind)
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Message image not found")
    return FileResponse(file_path, headers=MESSAGE_IMAGE_CACHE_HEADERS)

