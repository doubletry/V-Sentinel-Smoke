"""Notification template rendering helpers.
通知模板渲染辅助函数。

This module is intentionally transport-agnostic. SMTP email, webhook delivery,
and future notification channels should all render event context through these
helpers instead of depending on a channel-specific client.
本模块不绑定具体传输方式。SMTP 邮件、Webhook 以及后续通知渠道都应通过这里
渲染事件上下文，而不是依赖某个渠道专用客户端。
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
from string import Formatter
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


NOTIFICATION_TEMPLATE_PLACEHOLDERS: tuple[str, ...] = (
    "site_title",
    "timestamp",
    "local_time",
    "timezone",
    "source_id",
    "source_name",
    "event_type",
    "event_label",
    "labels",
    "confidence",
    "confidence_percent",
    "detection_count",
    "frame_id",
    "active_tracks",
    "original_image",
    "detected_image",
    "original_image_url",
    "detected_image_url",
    "has_original_image",
    "has_detected_image",
    "source_rtsp_url",
    "source_route_path",
    "source_host",
    "source_ip",
    "source_port",
    "source_remark",
    "source_description",
    "roi_id",
    "roi_tag",
    "roi_index",
    "roi_count",
    "door_state",
    "door_state_label",
    "alarm_label",
    "open_count",
    "closed_count",
)

DEFAULT_EVENT_SUBJECT_TEMPLATE = "[{site_title}] {event_label} alert from {source_name}"
DEFAULT_EVENT_BODY_TEMPLATE = """Event: {event_label}
Time: {local_time} ({timezone})
Video source: {source_name} ({source_id})
Labels: {labels}
Highest confidence: {confidence_percent}
Detection count: {detection_count}
Frame ID: {frame_id}
Active tracks: {active_tracks}
"""


class _SafeTemplateValues(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def product_name(app_settings: dict[str, str]) -> str:
    """Return a non-empty product name for notification content.
    返回通知内容中使用的非空产品名称。"""
    return str(app_settings.get("site_title") or "V-Sentinel").strip() or "V-Sentinel"


def safe_float(value: Any) -> float:
    """Convert a value to float, returning 0.0 for invalid input.
    将输入转换为浮点数；非法输入返回 0.0。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _image_html(image_base64: str, alt: str) -> str:
    payload = str(image_base64 or "").strip()
    if not payload:
        return ""
    safe_alt = html.escape(alt, quote=True)
    return (
        f'<img alt="{safe_alt}" src="data:image/jpeg;base64,{payload}" '
        'style="max-width:100%;height:auto;border:1px solid #ddd;" />'
    )


def _source_network_context(event: dict[str, Any]) -> dict[str, str]:
    raw_url = str(event.get("source_rtsp_url") or event.get("rtsp_url") or "")
    if not raw_url:
        return {"source_host": "", "source_ip": "", "source_port": ""}
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return {"source_host": "", "source_ip": "", "source_port": ""}
    host = parsed.hostname or ""
    port = str(parsed.port or "")
    return {
        "source_host": host,
        # RTSP URLs may contain a DNS name or an IP literal.  The source_ip
        # placeholder intentionally exposes the parsed host value as a
        # best-effort address for templates.
        "source_ip": host,
        "source_port": port,
    }


def build_template_context(app_settings: dict[str, str], event: dict[str, Any]) -> dict[str, str]:
    """Build the standard placeholder context for one scene event.
    为单个场景事件构造标准占位符上下文。"""
    timezone_name = str(app_settings.get("timezone") or "UTC")
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "UTC"
        tzinfo = timezone.utc
    timestamp = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        local_time = parsed.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        local_time = timestamp
    confidence = safe_float(event.get("confidence"))
    labels_raw = event.get("labels") or event.get("event_type") or "event"
    if isinstance(labels_raw, (list, tuple, set)):
        labels = ", ".join(str(item) for item in labels_raw)
    else:
        labels = str(labels_raw)
    event_type = str(event.get("event_type") or labels).strip() or "event"
    original_image_base64 = str(event.get("original_image_base64") or "").strip()
    detected_image_base64 = str(
        event.get("detected_image_base64") or event.get("image_base64") or ""
    ).strip()
    source_network = _source_network_context(event)
    return {
        "site_title": product_name(app_settings),
        "timestamp": timestamp,
        "local_time": local_time,
        "timezone": timezone_name,
        "source_id": str(event.get("source_id") or ""),
        "source_name": str(event.get("source_name") or ""),
        "event_type": event_type,
        "event_label": str(event.get("event_label") or event_type.upper()),
        "labels": labels,
        "confidence": f"{confidence:.4f}",
        "confidence_percent": f"{confidence * 100:.1f}%",
        "detection_count": str(event.get("detection_count") or 0),
        "frame_id": str(event.get("frame_id") or ""),
        "active_tracks": str(event.get("active_tracks") or ""),
        "original_image": _image_html(original_image_base64, "original image"),
        "detected_image": _image_html(detected_image_base64, "detected image"),
        "original_image_url": str(event.get("original_image_url") or ""),
        "detected_image_url": str(event.get("detected_image_url") or event.get("image_url") or ""),
        "has_original_image": "true" if original_image_base64 or event.get("original_image_url") else "false",
        "has_detected_image": "true" if detected_image_base64 or event.get("detected_image_url") or event.get("image_url") else "false",
        "source_rtsp_url": str(event.get("source_rtsp_url") or event.get("rtsp_url") or ""),
        "source_route_path": str(event.get("source_route_path") or ""),
        **source_network,
        "source_remark": str(event.get("source_remark") or ""),
        "source_description": str(event.get("source_description") or event.get("source_remark") or ""),
        "roi_id": str(event.get("roi_id") or ""),
        "roi_tag": str(event.get("roi_tag") or ""),
        "roi_index": str(event.get("roi_index") or ""),
        "roi_count": str(event.get("roi_count") or ""),
        "door_state": str(event.get("door_state") or ""),
        "door_state_label": str(event.get("door_state_label") or ""),
        "alarm_label": str(event.get("alarm_label") or ""),
        "open_count": str(event.get("open_count") or 0),
        "closed_count": str(event.get("closed_count") or 0),
    }


def render_template(template: str, context: dict[str, str]) -> str:
    """Render a template while preserving unknown placeholders.
    渲染模板；未知占位符会原样保留，避免配置错误导致通知失败。"""
    return Formatter().vformat(template, (), _SafeTemplateValues(context))
