"""Fire door event email helpers."""
from __future__ import annotations

from typing import Any


def build_fire_door_email_event(
    *,
    timestamp: str,
    source_id: str,
    source_name: str,
    source_rtsp_url: str,
    source_route_path: str,
    source_remark: str,
    roi_id: str,
    roi_tag: str,
    roi_index: int,
    roi_count: int,
    door_state: str,
    door_state_label: str,
    confidence: float,
    alarm_label: str,
    open_count: int,
    closed_count: int,
    original_image_base64: str | None = None,
    detected_image_base64: str | None = None,
    cooldown_seconds: int | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp": timestamp,
        "source_id": source_id,
        "source_name": source_name,
        "source_rtsp_url": source_rtsp_url,
        "source_route_path": source_route_path,
        "source_remark": source_remark,
        "source_description": source_remark,
        "event_type": "fire_door_open",
        "event_label": "消防门开启",
        "labels": [door_state],
        "confidence": confidence,
        "detection_count": 1,
        "roi_id": roi_id,
        "roi_tag": roi_tag,
        "roi_index": roi_index,
        "roi_count": roi_count,
        "door_state": door_state,
        "door_state_label": door_state_label,
        "alarm_label": alarm_label,
        "open_count": open_count,
        "closed_count": closed_count,
        "image_base64": detected_image_base64 or "",
        "original_image_base64": original_image_base64 or "",
        "detected_image_base64": detected_image_base64 or "",
    }
    if cooldown_seconds is not None:
        event["cooldown_seconds"] = cooldown_seconds
    return event

