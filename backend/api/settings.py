from __future__ import annotations

from fastapi import APIRouter, Request
from loguru import logger

from backend.db import database as db
from backend.models.schemas import AppSettingsUpdate, EmailTestRequest
from core.notification_client import NotificationPayload, SmtpNotificationProvider

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings() -> dict[str, str]:
    """Get all application settings.
    获取所有应用设置。"""
    return await db.get_all_settings()


@router.put("")
async def update_settings(data: AppSettingsUpdate, request: Request) -> dict[str, str]:
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

    previous_settings = await db.get_all_settings()
    result = await db.update_settings(updates)
    request.app.title = result.get("site_title") or request.app.title
    if "message_retention_days" in updates:
        try:
            await db.prune_analysis_messages(int(result.get("message_retention_days", "7")))
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid message retention days while pruning: {}", exc)

    mediamtx_rtsp_keys = {
        "mediamtx_rtsp_addr",
        "mediamtx_rtsp_username",
        "mediamtx_rtsp_password",
    }
    if mediamtx_rtsp_keys.intersection(updates):
        await db.rewrite_source_rtsp_urls(
            old_rtsp_base_address=previous_settings.get("mediamtx_rtsp_addr", ""),
            new_rtsp_base_address=result.get("mediamtx_rtsp_addr", ""),
            new_rtsp_username=result.get("mediamtx_rtsp_username", ""),
            new_rtsp_password=result.get("mediamtx_rtsp_password", ""),
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
) -> dict[str, str]:
    """Send a test email using current or provided settings.
    使用当前或传入的设置发送测试邮件。"""
    app_settings = await db.get_all_settings()
    overrides = {k: v for k, v in data.model_dump().items() if v is not None}

    merged_settings = {**app_settings, **overrides}
    config = {
        "smtp_host": merged_settings.get("email_smtp_host") or merged_settings.get("vengine_host", ""),
        "smtp_port": merged_settings.get("email_smtp_port") or merged_settings.get("email_port", "587"),
        "smtp_username": merged_settings.get("email_from_address", ""),
        "smtp_password": merged_settings.get("email_from_auth_code", ""),
        "from_address": merged_settings.get("email_from_address", ""),
        "to_addresses": merged_settings.get("email_to_addresses", ""),
        "cc_addresses": merged_settings.get("email_cc_addresses", ""),
        "use_tls": merged_settings.get("email_smtp_use_tls", "true"),
    }
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
    """Return supported event-email template placeholders.
    返回事件邮件模板支持的占位符。"""
    from core.email_client import AsyncEmailClient

    return {"placeholders": AsyncEmailClient.available_template_placeholders()}
