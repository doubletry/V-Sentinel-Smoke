from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from backend.auth.dependencies import current_user, has_permission, require_any_permission, require_permission
from backend.db import database as db
from backend.models.schemas import AppSettingsUpdate, CurrentUser, EmailTestRequest, VlTestRequest
from backend.notifications.email_config import build_email_settings_smtp_config
from core.vl_confirm import VLConfirmClient, VL_TEST_PROMPT, build_vl_test_image_data_url, vl_sampling_kwargs
from core.notification_client import NotificationPayload, SmtpNotificationProvider
from core.notification_template import NOTIFICATION_TEMPLATE_PLACEHOLDERS

router = APIRouter(prefix="/api/settings", tags=["settings"])

NOTIFICATION_SETTING_KEYS = {
    "email_from_address",
    "email_smtp_password",
    "email_to_addresses",
    "email_cc_addresses",
    "email_smtp_host",
    "email_smtp_port",
    "email_smtp_use_tls",
    "email_event_enabled",
    "email_timed_enabled",
    "email_event_subject_template",
    "email_event_body_template",
    "message_retention_days",
}

PLUGIN_SETTING_KEYS = {
    "smoke_detection_model_name",
    "smoke_detection_model_version",
    "smoke_detection_confidence",
    "smoke_detection_nms",
    "smoke_min_confidence_smoke",
    "smoke_min_confidence_fire",
    "smoke_temporal_confirm_frames",
    "smoke_temporal_confirm_window",
    "smoke_max_miss_frames",
    "smoke_min_bbox_area_ratio",
    "smoke_max_bbox_area_ratio",
    "smoke_min_aspect_ratio",
    "smoke_max_aspect_ratio",
    "smoke_motion_blur_max_speed",
    "smoke_motion_blur_min_confidence",
    "smoke_enable_appearance_filter",
    "smoke_appearance_min_score",
    "smoke_appearance_min_history",
    "smoke_appearance_high_confidence_bypass",
    "smoke_overexposed_ratio_threshold",
    "smoke_white_object_ratio_threshold",
    "smoke_hard_boundary_density_threshold",
    "smoke_hard_laplacian_threshold",
    "smoke_fast_motion_energy_threshold",
    "smoke_static_confirm_frames",
    "smoke_static_max_center_shift",
    "smoke_static_max_area_change_ratio",
    "smoke_iou_threshold",
    "smoke_alarm_hold_time",
    "fire_door_classification_model_name",
    "fire_door_classification_confidence",
    "fire_door_open_labels",
    "fire_door_closed_labels",
    "fire_door_alarm_labels",
    "fire_door_temporal_confirm_frames",
    "fire_door_temporal_confirm_window",
    "fire_door_alarm_hold_time",
    "vl_confirm_base_url",
    "vl_confirm_api_key",
    "vl_confirm_model",
    "vl_confirm_timeout",
    "smoke_vl_confirm_enabled",
    "smoke_vl_confirm_image_source",
    "smoke_vl_confirm_image_crop",
    "smoke_vl_confirm_prompt",
    "smoke_vl_confirm_response_key",
    "fire_door_vl_confirm_enabled",
    "fire_door_vl_confirm_image_source",
    "fire_door_vl_confirm_image_crop",
    "fire_door_vl_confirm_prompt",
    "fire_door_vl_confirm_response_key",
}


def _ensure_settings_update_allowed(updates: dict[str, str], user: CurrentUser) -> None:
    if has_permission(user.role, "settings:*"):
        return
    allowed_keys: set[str] = set()
    if has_permission(user.role, "settings:notifications"):
        allowed_keys.update(NOTIFICATION_SETTING_KEYS)
    if has_permission(user.role, "settings:plugins"):
        allowed_keys.update(PLUGIN_SETTING_KEYS)
    denied_keys = sorted(set(updates) - allowed_keys)
    if denied_keys:
        raise HTTPException(
            status_code=403,
            detail="Insufficient role permission to update some settings",
        )


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
async def get_settings(
    me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_any_permission("settings:*", "settings:mediamtx")),
) -> dict[str, str]:
    """Get all application settings.
    获取所有应用设置。"""
    result = await db.get_all_settings()
    if not has_permission(me.role, "settings:*"):
        # Do not expose MediaMTX password to users without full settings access.
        result.pop("mediamtx_password", None)
    return result


@router.put("")
async def update_settings(
    data: AppSettingsUpdate,
    request: Request,
    me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_any_permission("settings:*", "settings:notifications", "settings:plugins")),
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
    _ensure_settings_update_allowed(updates, me)
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
    changed_keys = sorted(
        key for key in updates
        if str(previous_settings.get(key) or "") != str(result.get(key) or "")
    )
    if changed_keys:
        logger.info("Settings updated, changed keys: {}", changed_keys)
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
    _role: str = Depends(require_any_permission("settings:*", "settings:notifications")),
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


@router.post("/vl/test")
async def test_vl_settings(
    data: VlTestRequest,
    _role: str = Depends(require_any_permission("settings:*", "settings:plugins")),
) -> dict[str, object]:
    """Run a full connection test against the configured VL backend.
    使用当前或传入的设置对 VL 后端做一次全链路连接测试。"""
    if data.scene_id not in ("smoke", "fire_door"):
        raise HTTPException(status_code=422, detail="scene_id must be 'smoke' or 'fire_door'")
    app_settings = await db.get_all_settings()
    base_url = str(data.vl_confirm_base_url or app_settings.get("vl_confirm_base_url") or "").strip()
    api_key = str(data.vl_confirm_api_key or app_settings.get("vl_confirm_api_key") or "").strip()
    model = str(data.vl_confirm_model or app_settings.get("vl_confirm_model") or "").strip()
    timeout_raw = str(data.vl_confirm_timeout or app_settings.get("vl_confirm_timeout") or "60")
    if not base_url or not model:
        raise HTTPException(status_code=422, detail="VL base URL and model are required")
    try:
        timeout = max(1, int(float(timeout_raw)))
    except (ValueError, OverflowError):
        timeout = 60
    sampling_overrides = {
        key: value
        for key, value in data.model_dump().items()
        if key.startswith(f"{data.scene_id}_vl_confirm_") and value is not None
    }
    client = VLConfirmClient(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        model=model,
        timeout=timeout,
        **vl_sampling_kwargs(app_settings, data.scene_id, overrides=sampling_overrides),
    )
    started = time.monotonic()
    try:
        raw = await client.complete(build_vl_test_image_data_url(), VL_TEST_PROMPT)
    except Exception as exc:
        logger.opt(exception=True).warning(
            "VL connection test failed: scene={} model={} base_url={}",
            data.scene_id, model, base_url,
        )
        raise HTTPException(status_code=502, detail=f"VL request failed: {exc}")
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "VL connection test ok: scene={} model={} latency_ms={}",
        data.scene_id, model, latency_ms,
    )
    return {
        "status": "ok",
        "model": model,
        "latency_ms": latency_ms,
        "response": raw,
    }


@router.get("/email/template-placeholders")
async def get_email_template_placeholders(
    _role: str = Depends(require_any_permission("settings:*", "settings:notifications")),
) -> dict[str, list[str]]:
    """Return supported notification template placeholders.
    返回通知模板支持的占位符。"""
    return {"placeholders": list(NOTIFICATION_TEMPLATE_PLACEHOLDERS)}
