from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from backend.auth.dependencies import require_permission
from backend.db import database as db
from backend.models.schemas import AppSettingsUpdate, EmailTestRequest
from backend.notifications.email_config import build_email_settings_smtp_config
from core.notification_client import NotificationPayload, SmtpNotificationProvider
from core.notification_template import NOTIFICATION_TEMPLATE_PLACEHOLDERS

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _ensure_legacy_mediamtx_credentials_are_consistent(updates: dict[str, str]) -> None:
    """Reject conflicting legacy RTSP/WebRTC MediaMTX credentials in one request.
    拒绝单次请求里彼此冲突的旧 RTSP/WebRTC MediaMTX 凭据。"""
    legacy_keys = {
        "mediamtx_rtsp_username",
        "mediamtx_rtsp_password",
        "mediamtx_webrtc_username",
        "mediamtx_webrtc_password",
    }
    if not legacy_keys.intersection(updates):
        return
    legacy_pairs = [
        ("mediamtx_rtsp_username", "mediamtx_webrtc_username", "username"),
        ("mediamtx_rtsp_password", "mediamtx_webrtc_password", "password"),
    ]
    for left_key, right_key, label in legacy_pairs:
        if left_key not in updates or right_key not in updates:
            continue
        if str(updates[left_key]) == str(updates[right_key]):
            continue
        raise HTTPException(
            status_code=422,
            detail=f"Legacy MediaMTX {label} fields must match when both RTSP and WebRTC values are provided",
        )


@router.get("")
async def get_settings() -> dict[str, str]:
    """Get all application settings.
    获取所有应用设置。"""
    return await db.get_all_settings()


@router.put("")
async def update_settings(
    data: AppSettingsUpdate,
    request: Request,
    _role: str = Depends(require_permission("settings:*")),
) -> dict[str, str]:
    """Update application settings.
    更新应用设置。

    After saving, the V-Engine gRPC client is reconnected with the new
    addresses so changes take effect immediately.
    保存后重新连接 V-Engine gRPC 客户端以使新地址立即生效。
    """
    # Build dict of only the fields that were actually provided
    # 仅构建实际提供了值的字段字典
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        return await db.get_all_settings()
    _ensure_legacy_mediamtx_credentials_are_consistent(updates)
    if "active_plugin_id" in updates:
        plugin_id = str(updates["active_plugin_id"] or "").strip()
        if not plugin_id:
            raise HTTPException(status_code=422, detail="Plugin ID cannot be empty")
        if await db.get_scene(plugin_id) is None:
            raise HTTPException(status_code=422, detail=f"Plugin not found: {plugin_id}")
        updates["active_plugin_id"] = plugin_id

    previous_settings = await db.get_all_settings()
    result = await db.update_settings(updates)
    request.app.title = result.get("site_title") or request.app.title
    if "message_retention_days" in updates:
        try:
            await db.prune_analysis_messages(int(result.get("message_retention_days", "7")))
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid message retention days while pruning: {}", exc)

    mediamtx_related_keys = {
        "mediamtx_rtsp_addr",
        "mediamtx_webrtc_addr",
        "mediamtx_username",
        "mediamtx_password",
        "mediamtx_rtsp_username",
        "mediamtx_rtsp_password",
        "mediamtx_webrtc_username",
        "mediamtx_webrtc_password",
    }
    if mediamtx_related_keys.intersection(updates):
        await db.rewrite_source_rtsp_urls(
            old_rtsp_base_address=previous_settings.get("mediamtx_rtsp_addr", ""),
            new_rtsp_base_address=result.get("mediamtx_rtsp_addr", ""),
            new_rtsp_username=result.get("mediamtx_username", ""),
            new_rtsp_password=result.get("mediamtx_password", ""),
        )
        await db.sync_default_video_gateway_from_settings(result)
    if (
        "active_plugin_id" in updates
        and previous_settings.get("active_plugin_id") != result.get("active_plugin_id")
    ):
        await db.update_all_sources_scene(
            result.get("active_plugin_id", db.DEFAULT_SCENE_ID)
        )

    # Reconnect V-Engine client with new addresses / 使用新地址重连 V-Engine 客户端
    vengine_client = request.app.state.vengine_client
    await vengine_client.reconnect_from_settings(result)
    request.app.state.processor_manager.update_app_settings(result)

    return result


@router.post("/email/test")
async def test_email_settings(
    data: EmailTestRequest,
    request: Request,
    _role: str = Depends(require_permission("settings:*")),
) -> dict[str, str]:
    """Send a test email using current or provided settings.
    使用当前或传入的设置发送测试邮件。"""
    app_settings = await db.get_all_settings()
    overrides = {k: v for k, v in data.model_dump().items() if v is not None}

    merged_settings = {**app_settings, **overrides}
    config = build_email_settings_smtp_config(merged_settings)
    provider = SmtpNotificationProvider(config)
    site_title = merged_settings.get("site_title") or "V-Sentinel"
    return await provider.send(
        NotificationPayload(
            subject=f"{site_title} 邮件配置测试",
            body=f"这是一封来自 {site_title} 的 SMTP 测试邮件，用于验证邮件配置是否正确。",
        )
    )


@router.get("/email/template-placeholders")
async def get_email_template_placeholders() -> dict[str, list[str]]:
    """Return supported notification template placeholders.
    返回通知模板支持的占位符。"""
    return {"placeholders": list(NOTIFICATION_TEMPLATE_PLACEHOLDERS)}
