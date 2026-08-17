"""Smoke/fire video processor.
烟雾/火焰视频处理器。"""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

import cv2
import numpy as np

from core.base_processor import AnalysisResult, BaseVideoProcessor
from core.smoke.constants import (
    DEFAULT_DETECTION_MODEL,
    DEFAULT_VL_CONFIRM_PROMPT,
    DEFAULT_VL_CONFIRM_RESPONSE_KEY,
    FIRE_LABEL,
    SMOKE_FIRE_LABELS,
    SMOKE_LABEL,
)
from core.smoke.email import build_smoke_email_event
from core.smoke.post_processor import Detection, DetectionClass, PostProcessorConfig, SmokeFirePostProcessor
from core.vl_confirm import VLConfirmClient, crop_roi_image


class SmokeFireProcessor(BaseVideoProcessor):
    """Processor for smoke/fire detection with temporal post-processing."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._post_processor = SmokeFirePostProcessor(self._build_postprocess_config())

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

    def _setting_bool(self, key: str, default: bool) -> bool:
        raw = self.app_settings.get(key, str(default).lower())
        return str(raw).strip().lower() in {"true", "1", "yes", "on"}

    def _build_postprocess_config(self) -> PostProcessorConfig:
        return PostProcessorConfig(
            min_confidence_smoke=self._source_confidence_threshold(
                self._setting_float("smoke_min_confidence_smoke", 0.35)
            ),
            min_confidence_fire=self._source_confidence_threshold(
                self._setting_float("smoke_min_confidence_fire", 0.40)
            ),
            temporal_confirm_frames=self._setting_int("smoke_temporal_confirm_frames", 3),
            temporal_confirm_window=self._setting_float("smoke_temporal_confirm_window", 2.0),
            max_miss_frames=self._setting_int("smoke_max_miss_frames", 5),
            min_bbox_area_ratio=self._setting_float("smoke_min_bbox_area_ratio", 0.0005),
            max_bbox_area_ratio=self._setting_float("smoke_max_bbox_area_ratio", 0.60),
            smoke_min_aspect_ratio=self._setting_float("smoke_min_aspect_ratio", 0.2),
            smoke_max_aspect_ratio=self._setting_float("smoke_max_aspect_ratio", 8.0),
            motion_blur_max_speed=self._setting_float("smoke_motion_blur_max_speed", 100.0),
            motion_blur_min_confidence=self._setting_float("smoke_motion_blur_min_confidence", 0.65),
            enable_smoke_appearance_filter=self._setting_bool("smoke_enable_appearance_filter", True),
            smoke_appearance_min_score=self._setting_float("smoke_appearance_min_score", 0.42),
            smoke_appearance_min_history=self._setting_int("smoke_appearance_min_history", 2),
            smoke_appearance_high_confidence_bypass=self._setting_float("smoke_appearance_high_confidence_bypass", 0.82),
            smoke_overexposed_ratio_threshold=self._setting_float("smoke_overexposed_ratio_threshold", 0.18),
            smoke_white_object_ratio_threshold=self._setting_float("smoke_white_object_ratio_threshold", 0.62),
            smoke_hard_boundary_density_threshold=self._setting_float("smoke_hard_boundary_density_threshold", 0.14),
            smoke_hard_laplacian_threshold=self._setting_float("smoke_hard_laplacian_threshold", 520.0),
            smoke_fast_motion_energy_threshold=self._setting_float("smoke_fast_motion_energy_threshold", 0.16),
            smoke_static_confirm_frames=self._setting_int("smoke_static_confirm_frames", 5),
            smoke_static_max_center_shift=self._setting_float("smoke_static_max_center_shift", 10.0),
            smoke_static_max_area_change_ratio=self._setting_float("smoke_static_max_area_change_ratio", 0.08),
            iou_threshold=self._setting_float("smoke_iou_threshold", 0.3),
            alarm_hold_time=self._setting_float("smoke_alarm_hold_time", 3.0),
        )

    async def process_frame(
        self,
        frame: np.ndarray,
        encoded: bytes,
        shape: tuple[int, int, int],
        roi_pixel_points: list[list[dict]],
    ) -> AnalysisResult:
        if self.vengine is None:
            return AnalysisResult(annotated_frame=frame.copy())

        primary_roi = roi_pixel_points[0] if roi_pixel_points else None
        detect_result = await self._do_detect(
            shape=shape,
            model_name=str(self.app_settings.get("smoke_detection_model_name") or DEFAULT_DETECTION_MODEL),
            conf=self._source_confidence_threshold(
                self._setting_float("smoke_detection_confidence", 0.35)
            ),
            nms=self._setting_float("smoke_detection_nms", 0.7),
            model_version=str(self.app_settings.get("smoke_detection_model_version") or ""),
            model_roi=primary_roi,
            image_bytes=encoded,
        )
        raw_detections = [det for det in detect_result["detections"] if str(det.get("label", "")).lower() in SMOKE_FIRE_LABELS]
        timestamp = datetime.now(timezone.utc).isoformat()
        monotonic_ts = time.monotonic()
        post_result = self._post_processor.process_frame(
            [self._to_post_detection(det, monotonic_ts) for det in raw_detections],
            timestamp=monotonic_ts,
            frame=cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
        )
        confirmed = [self._from_post_detection(det) for det in post_result.filtered_detections]
        result = AnalysisResult(detections=confirmed)
        annotated = self.draw_on_frame(frame, result)
        result.annotated_frame = annotated

        if post_result.has_alarm and confirmed:
            if self._vl_confirm_enabled():
                vl_result = await self._vl_confirm_alert(frame, primary_roi)
                if vl_result is False:
                    confirmed = []
                # True or None (fail-open) → keep alerts
        if post_result.has_alarm and confirmed:
            labels = sorted({str(det.get("label", "")).lower() for det in confirmed})
            confidence = max(float(det.get("confidence", 0.0)) for det in confirmed)
            original_image_base64 = self._encode_thumbnail(frame)
            detected_image_base64 = self._encode_thumbnail(annotated)
            event = build_smoke_email_event(
                timestamp=timestamp,
                source_id=self.source_id,
                source_name=self.source_name,
                labels=labels,
                confidence=confidence,
                detection_count=len(confirmed),
                frame_id=post_result.frame_id,
                active_tracks=post_result.active_tracks,
                image_base64=detected_image_base64,
            )
            message = f"Detected {event['event_label']} on {self.source_name} ({len(confirmed)} confirmed detection(s))"
            result.messages.append({
                "timestamp": timestamp,
                "source_name": self.source_name,
                "source_id": self.source_id,
                "level": "alert",
                "message": message,
                "image_base64": detected_image_base64,
                "original_image_base64": original_image_base64,
                "detected_image_base64": detected_image_base64,
            })
            result.extra["email_event"] = event
            result.extra["smoke_event"] = event
        return result

    def _vl_confirm_enabled(self) -> bool:
        return str(self.app_settings.get("vl_confirm_enabled") or "false").lower() == "true"

    async def _vl_confirm_alert(
        self,
        frame: np.ndarray,
        primary_roi: list[dict] | None,
    ) -> bool | None:
        """Ask the VL model to verify a smoke/fire alarm. Returns True/False/None."""
        image_data_url = crop_roi_image(frame, primary_roi)
        prompt = str(
            self.app_settings.get("smoke_vl_confirm_prompt")
            or DEFAULT_VL_CONFIRM_PROMPT
        )
        response_key = str(
            self.app_settings.get("smoke_vl_confirm_response_key")
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
        )
        return await client.confirm(image_data_url, prompt, response_key)

    def _to_post_detection(self, det: dict[str, Any], timestamp: float) -> Detection:
        label = str(det.get("label", "")).lower()
        cls = DetectionClass.FIRE if label == FIRE_LABEL else DetectionClass.SMOKE
        return Detection(
            x1=float(det.get("x_min", 0.0)),
            y1=float(det.get("y_min", 0.0)),
            x2=float(det.get("x_max", 0.0)),
            y2=float(det.get("y_max", 0.0)),
            confidence=float(det.get("confidence", 0.0)),
            cls=cls,
            timestamp=timestamp,
        )

    def _from_post_detection(self, det: Detection) -> dict[str, Any]:
        label = FIRE_LABEL if det.cls == DetectionClass.FIRE else SMOKE_LABEL
        return {
            "x_min": det.x1,
            "y_min": det.y1,
            "x_max": det.x2,
            "y_max": det.y2,
            "confidence": det.confidence,
            "class_id": det.cls.value,
            "label": label,
        }
