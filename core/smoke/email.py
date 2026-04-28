"""Smoke/fire event email helpers.
烟火事件邮件辅助函数。"""
from __future__ import annotations

from typing import Any

from core.smoke.constants import FIRE_LABEL, LABEL_TO_ZH, SMOKE_LABEL


def build_event_label(labels: list[str]) -> str:
    normalized = {str(label).lower() for label in labels}
    if SMOKE_LABEL in normalized and FIRE_LABEL in normalized:
        return "烟雾/火焰"
    if FIRE_LABEL in normalized:
        return LABEL_TO_ZH[FIRE_LABEL]
    if SMOKE_LABEL in normalized:
        return LABEL_TO_ZH[SMOKE_LABEL]
    return "事件"


def build_event_type(labels: list[str]) -> str:
    normalized = sorted({str(label).lower() for label in labels if label})
    return "_".join(normalized) if normalized else "event"


def build_smoke_email_event(
    *,
    timestamp: str,
    source_id: str,
    source_name: str,
    labels: list[str],
    confidence: float,
    detection_count: int,
    frame_id: int,
    active_tracks: int,
    image_base64: str | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "source_id": source_id,
        "source_name": source_name,
        "event_type": build_event_type(labels),
        "event_label": build_event_label(labels),
        "labels": labels,
        "confidence": confidence,
        "detection_count": detection_count,
        "frame_id": frame_id,
        "active_tracks": active_tracks,
        "image_base64": image_base64 or "",
    }
