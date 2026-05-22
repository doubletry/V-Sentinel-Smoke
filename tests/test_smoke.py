from __future__ import annotations

from unittest.mock import AsyncMock

import numpy as np

from core.smoke.email import build_event_label, build_event_type
from core.smoke.post_processor import Detection, DetectionClass, PostProcessorConfig, SmokeFirePostProcessor
from core.smoke.processor import SmokeFireProcessor


class TestSmokePostProcessor:
    def test_n_frame_confirmation_triggers_alarm(self):
        processor = SmokeFirePostProcessor(PostProcessorConfig(
            temporal_confirm_frames=2,
            temporal_confirm_window=10.0,
            enable_smoke_appearance_filter=False,
        ))
        det1 = Detection(10, 10, 60, 60, 0.9, DetectionClass.SMOKE, timestamp=1.0)
        det2 = Detection(10, 10, 60, 60, 0.9, DetectionClass.SMOKE, timestamp=2.0)
        first = processor.process_frame([det1], timestamp=1.0)
        assert not first.has_alarm
        second = processor.process_frame([det2], timestamp=2.0)
        assert second.has_alarm
        assert second.filtered_detections[0].cls == DetectionClass.SMOKE


class TestSmokeEmailHelpers:
    def test_event_label_and_type(self):
        assert build_event_label(["smoke"]) == "烟雾"
        assert build_event_label(["fire"]) == "火焰"
        assert build_event_label(["smoke", "fire"]) == "烟雾/火焰"
        assert build_event_type(["fire", "smoke", "fire"]) == "fire_smoke"


class TestSmokeProcessor:
    async def test_process_frame_generates_alert_message(self):
        vengine = AsyncMock()
        vengine.detect.return_value = [
            {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
        ]
        processor = SmokeFireProcessor(
            source_id="s1",
            source_name="Cam1",
            rtsp_url="",
            rois=[],
            vengine_client=vengine,
            app_settings={
                "smoke_temporal_confirm_frames": "1",
                "smoke_enable_appearance_filter": "false",
            },
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
        assert result.messages
        assert result.messages[0]["level"] == "alert"
        assert result.extra["email_event"]["event_type"] == "smoke"
        assert result.extra["email_event"]["image_base64"]

    def test_processor_reads_postprocess_config_from_settings(self):
        processor = SmokeFireProcessor(
            source_id="s1",
            source_name="Cam1",
            rtsp_url="",
            rois=[],
            vengine_client=None,
            app_settings={
                "smoke_temporal_confirm_frames": "7",
                "smoke_enable_appearance_filter": "false",
                "smoke_iou_threshold": "0.45",
            },
        )
        config = processor._post_processor.config
        assert config.temporal_confirm_frames == 7
        assert config.enable_smoke_appearance_filter is False
        assert config.iou_threshold == 0.45

    async def test_source_confidence_override_controls_detection_threshold(self):
        vengine = AsyncMock()
        vengine.detect.return_value = []
        processor = SmokeFireProcessor(
            source_id="s1",
            source_name="Cam1",
            rtsp_url="",
            rois=[],
            vengine_client=vengine,
            source_alarm_confidence_threshold=0.77,
            app_settings={
                "smoke_detection_confidence": "0.35",
                "smoke_enable_appearance_filter": "false",
            },
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

        assert vengine.detect.await_args.kwargs["conf"] == 0.77
        assert processor._post_processor.config.min_confidence_smoke == 0.77
        assert processor._post_processor.config.min_confidence_fire == 0.77

    async def test_empty_source_confidence_uses_plugin_detection_threshold(self):
        vengine = AsyncMock()
        vengine.detect.return_value = []
        processor = SmokeFireProcessor(
            source_id="s1",
            source_name="Cam1",
            rtsp_url="",
            rois=[],
            vengine_client=vengine,
            source_alarm_confidence_threshold=None,
            app_settings={
                "smoke_detection_confidence": "0.62",
                "smoke_enable_appearance_filter": "false",
            },
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

        assert vengine.detect.await_args.kwargs["conf"] == 0.62
