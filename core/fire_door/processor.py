"""Fire safety door classification processor."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import time
from typing import Any

import cv2
import numpy as np
from loguru import logger

from core.base_processor import AnalysisResult, BaseVideoProcessor
from core.constants import DRAW_CLASSIFICATION_COLOR, DRAW_FONT_SCALE, DRAW_FONT_THICKNESS
from core.fire_door.constants import (
    DEFAULT_ALARM_LABELS,
    DEFAULT_CLASSIFICATION_MODEL,
    DEFAULT_CLOSED_LABELS,
    DEFAULT_OPEN_LABELS,
    DEFAULT_VL_CONFIRM_PROMPT,
    DEFAULT_VL_CONFIRM_RESPONSE_KEY,
    FIRE_DOOR_ROI_TAG,
)
from core.fire_door.email import build_fire_door_email_event
from core.vl_confirm import VLConfirmClient, build_vl_image_data_url, vl_sampling_kwargs


class FireDoorProcessor(BaseVideoProcessor):
    """Classify one or more fire-door ROIs and alert on configured open states."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._roi_alarm_history: dict[str, deque[float]] = {}
        self._roi_last_alarm_at: dict[str, float] = {}
        self._pending_vl_tasks: set[asyncio.Task] = set()

    async def stop(self) -> None:
        if self._pending_vl_tasks:
            for task in list(self._pending_vl_tasks):
                task.cancel()
            try:
                await asyncio.gather(*self._pending_vl_tasks, return_exceptions=True)
            except Exception:
                pass
            self._pending_vl_tasks.clear()
        await super().stop()

    def _setting_float(self, key: str, default: float) -> float:
        try:
            return float(self.app_settings.get(key, str(default)))
        except (TypeError, ValueError):
            return default

    def _setting_int(self, key: str, default: int) -> int:
        try:
            return int(float(self.app_settings.get(key, str(default))))
        except (TypeError, ValueError):
            return default

    def _setting_labels(self, key: str, default: tuple[str, ...]) -> set[str]:
        raw = self.app_settings.get(key)
        labels = [
            self._normalize_label(part)
            for part in str(raw or ",".join(default)).split(",")
        ]
        return {label for label in labels if label}

    @staticmethod
    def _normalize_label(value: Any) -> str:
        return str(value or "").strip().lower()

    def _door_state(self, label: str) -> str:
        normalized = self._normalize_label(label)
        if normalized in self._setting_labels("fire_door_open_labels", DEFAULT_OPEN_LABELS):
            return "open"
        if normalized in self._setting_labels("fire_door_closed_labels", DEFAULT_CLOSED_LABELS):
            return "closed"
        return normalized

    def _fire_door_rois(self, roi_pixel_points: list[list[dict]]) -> list[tuple[int, Any, list[dict]]]:
        tagged = [
            (idx, roi, points)
            for idx, (roi, points) in enumerate(zip(self.rois, roi_pixel_points))
            if self._normalize_label(getattr(roi, "tag", "")) == FIRE_DOOR_ROI_TAG
        ]
        if tagged:
            return tagged
        return [
            (idx, roi, points)
            for idx, (roi, points) in enumerate(zip(self.rois, roi_pixel_points))
        ]

    def _temporal_alarm_confirmed(self, roi_id: str, now_ts: float) -> bool:
        frames = max(1, self._setting_int("fire_door_temporal_confirm_frames", 1))
        window = max(0.0, self._setting_float("fire_door_temporal_confirm_window", 2.0))
        hold_time = max(0.0, self._setting_float("fire_door_alarm_hold_time", 3.0))
        history = self._roi_alarm_history.setdefault(roi_id, deque())
        history.append(now_ts)
        if window > 0:
            while history and now_ts - history[0] > window:
                history.popleft()
        else:
            while len(history) > frames:
                history.popleft()
        if len(history) < frames:
            return False
        last_alarm = self._roi_last_alarm_at.get(roi_id, 0.0)
        if now_ts - last_alarm < hold_time:
            return False
        self._roi_last_alarm_at[roi_id] = now_ts
        return True

    async def process_frame(
        self,
        frame: np.ndarray,
        encoded: bytes,
        shape: tuple[int, int, int],
        roi_pixel_points: list[list[dict]],
    ) -> AnalysisResult:
        if self.vengine is None:
            return AnalysisResult(annotated_frame=frame.copy())

        fire_rois = self._fire_door_rois(roi_pixel_points)
        if not fire_rois:
            return AnalysisResult(annotated_frame=frame.copy())

        images = [
            {
                "shape": shape,
                "image_bytes": encoded,
                "image_roi": self._bounded_roi_points(points, shape),
            }
            for _, _, points in fire_rois
        ]
        raw_result = await self._do_classify(
            images,
            model_name=str(
                self.app_settings.get("fire_door_classification_model_name")
                or DEFAULT_CLASSIFICATION_MODEL
            ),
        )
        confidence_threshold = self._source_confidence_threshold(
            self._setting_float("fire_door_classification_confidence", 0.5)
        )
        alarm_labels = self._setting_labels("fire_door_alarm_labels", DEFAULT_ALARM_LABELS)
        classifications: list[dict[str, Any]] = []
        now_ts = time.monotonic()
        timestamp = datetime.now(timezone.utc).isoformat()

        raw_classifications = raw_result["classifications"]
        for result_index, item in enumerate(raw_classifications):
            image_id = int(item.get("image_id", result_index))
            if image_id < 0 or image_id >= len(fire_rois):
                continue
            roi_index, roi, points = fire_rois[image_id]
            raw_label = str(item.get("label") or "")
            state = self._door_state(raw_label)
            confidence = float(item.get("confidence") or 0.0)
            is_alarm_label = state in alarm_labels
            qualifies = confidence >= confidence_threshold and is_alarm_label
            roi_id = str(getattr(roi, "id", "") or f"roi-{roi_index + 1}")
            alert = qualifies and self._temporal_alarm_confirmed(roi_id, now_ts)
            classifications.append(
                {
                    **item,
                    "label": state or raw_label,
                    "raw_label": raw_label,
                    "stable_label": state or raw_label,
                    "confidence": confidence,
                    "roi_id": roi_id,
                    "roi_tag": str(getattr(roi, "tag", "") or ""),
                    "roi_index": roi_index + 1,
                    "roi_count": len(fire_rois),
                    "roi_points": points,
                    "door_state": state,
                    "alarm": alert,
                }
            )

        result = AnalysisResult(classifications=classifications)
        annotated = self._draw_fire_door_rois(frame, classifications)
        result.annotated_frame = annotated

        alert_items = [item for item in classifications if item.get("alarm")]
        pending_alert = None
        if alert_items:
            vl_task = None
            if self._vl_confirm_enabled():
                vl_task = asyncio.create_task(
                    self._vl_confirm_alert(frame, annotated, alert_items, roi_pixel_points)
                )
                self._pending_vl_tasks.add(vl_task)
                vl_task.add_done_callback(self._pending_vl_tasks.discard)
            pending_alert = {
                "frame": frame,
                "annotated": annotated,
                "alert_items": alert_items,
                "classifications": classifications,
                "fire_rois": fire_rois,
                "timestamp": timestamp,
                "vl_task": vl_task,
            }
        result.extra["pending_alert"] = pending_alert
        return result

    async def finalize_result(self, result: AnalysisResult) -> None:
        """Build the alarm message once the VL verdict (if any) resolves.
        在 VL 复判结论（如有）落地后构建告警消息。"""
        pending = result.extra.pop("pending_alert", None)
        if pending is None:
            return
        vl_task = pending["vl_task"]
        vl_result = await vl_task if vl_task is not None else None
        vl_rejected = vl_result is False
        if vl_result is False:
            logger.warning(
                "Alarm rejected by VL confirm, marked false positive: source={}",
                self.source_name,
            )
        elif vl_result is True:
            logger.info(
                "Alarm confirmed by VL confirm: source={}", self.source_name
            )
        frame = pending["frame"]
        annotated = pending["annotated"]
        alert_items = pending["alert_items"]
        classifications = pending["classifications"]
        fire_rois = pending["fire_rois"]
        timestamp = pending["timestamp"]
        best = max(alert_items, key=lambda item: float(item.get("confidence") or 0.0))
        open_count = sum(1 for item in classifications if item.get("door_state") == "open")
        closed_count = sum(1 for item in classifications if item.get("door_state") == "closed")
        original_image_base64 = self._encode_thumbnail(frame)
        detected_image_base64 = self._encode_thumbnail(annotated)
        confidence = float(best.get("confidence") or 0.0)
        event = build_fire_door_email_event(
            timestamp=timestamp,
            source_id=self.source_id,
            source_name=self.source_name,
            source_rtsp_url=self.rtsp_url,
            source_route_path=self._stream_path(),
            source_remark=str(getattr(self, "source_remark", "") or ""),
            roi_id=str(best.get("roi_id") or ""),
            roi_tag=str(best.get("roi_tag") or ""),
            roi_index=int(best.get("roi_index") or 0),
            roi_count=len(fire_rois),
            door_state=str(best.get("door_state") or ""),
            door_state_label=str(best.get("stable_label") or ""),
            confidence=confidence,
            alarm_label=str(best.get("door_state") or best.get("raw_label") or ""),
            open_count=open_count,
            closed_count=closed_count,
            original_image_base64=original_image_base64,
            detected_image_base64=detected_image_base64,
        )
        result.messages.append(
            {
                "timestamp": timestamp,
                "source_name": self.source_name,
                "source_id": self.source_id,
                "scene_id": "fire_door",
                "level": "alert",
                "message": (
                    f"Fire door open on {self.source_name} "
                    f"ROI {event['roi_index']}/{event['roi_count']} "
                    f"({confidence:.2f})"
                ),
                "image_base64": detected_image_base64,
                "original_image_base64": original_image_base64,
                "detected_image_base64": detected_image_base64,
                "false_positive": vl_rejected,
            }
        )
        if not vl_rejected:
            result.extra["email_event"] = event
            result.extra["fire_door_event"] = event

    def _vl_confirm_enabled(self) -> bool:
        return str(self.app_settings.get("fire_door_vl_confirm_enabled") or "false").lower() == "true"

    async def _vl_confirm_alert(
        self,
        frame: np.ndarray,
        annotated: np.ndarray,
        alert_items: list[dict[str, Any]],
        roi_pixel_points: list[list[dict]],
    ) -> bool | None:
        """Ask the VL model to verify an alarm. Returns True/False/None."""
        best = max(alert_items, key=lambda item: float(item.get("confidence") or 0.0))
        roi_index = int(best.get("roi_index", 1)) - 1
        roi_points = (
            roi_pixel_points[roi_index]
            if 0 <= roi_index < len(roi_pixel_points)
            else None
        )

        image_data_url = build_vl_image_data_url(
            frame,
            annotated,
            str(self.app_settings.get("fire_door_vl_confirm_image_source") or "original"),
            str(self.app_settings.get("fire_door_vl_confirm_image_crop") or "roi"),
            roi_points,
        )
        prompt = str(
            self.app_settings.get("fire_door_vl_confirm_prompt")
            or DEFAULT_VL_CONFIRM_PROMPT
        )
        response_key = str(
            self.app_settings.get("fire_door_vl_confirm_response_key")
            or DEFAULT_VL_CONFIRM_RESPONSE_KEY
        )

        client = VLConfirmClient(
            base_url=str(
                self.app_settings.get("vl_confirm_base_url")
                or "http://localhost:30000/v1"
            ),
            api_key=str(self.app_settings.get("vl_confirm_api_key") or "EMPTY"),
            model=str(self.app_settings.get("vl_confirm_model") or "/models/Mage-VL"),
            timeout=self._setting_int("vl_confirm_timeout", 60),
            **vl_sampling_kwargs(self.app_settings, "fire_door"),
        )
        return await client.confirm(image_data_url, prompt, response_key)

    def _draw_fire_door_rois(
        self,
        frame: np.ndarray,
        classifications: list[dict[str, Any]],
    ) -> np.ndarray:
        out = frame.copy()
        for item in classifications:
            points = item.get("roi_points") or []
            if len(points) < 2:
                continue
            pts = np.array([[int(p["x"]), int(p["y"])] for p in points], dtype=np.int32)
            color = (255, 80, 80) if item.get("door_state") == "open" else DRAW_CLASSIFICATION_COLOR
            cv2.polylines(out, [pts], isClosed=True, color=color, thickness=2)
            x = int(min(p["x"] for p in points))
            y = int(min(p["y"] for p in points))
            label = item.get("stable_label") or item.get("raw_label") or "door"
            confidence = float(item.get("confidence") or 0.0)
            cv2.putText(
                out,
                f"{label} {confidence:.2f}",
                (x, max(y - 8, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                DRAW_FONT_SCALE,
                color,
                DRAW_FONT_THICKNESS,
                cv2.LINE_AA,
            )
        return out

    @staticmethod
    def _bounded_roi_points(
        points: list[dict],
        shape: tuple[int, int, int],
    ) -> list[dict[str, int]]:
        height, width = shape[:2]
        max_x = width - 1 if width > 0 else 0
        max_y = height - 1 if height > 0 else 0
        bounded: list[dict[str, int]] = []
        for point in points:
            x = max(0, min(int(point.get("x", 0)), max_x))
            y = max(0, min(int(point.get("y", 0)), max_y))
            bounded.append({"x": x, "y": y})
        return bounded
