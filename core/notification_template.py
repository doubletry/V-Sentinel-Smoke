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
from string import Formatter
from typing import Any
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
    }


def render_template(template: str, context: dict[str, str]) -> str:
    """Render a template while preserving unknown placeholders.
    渲染模板；未知占位符会原样保留，避免配置错误导致通知失败。"""
    return Formatter().vformat(template, (), _SafeTemplateValues(context))
