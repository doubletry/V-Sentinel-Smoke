from __future__ import annotations

from unittest.mock import AsyncMock, patch

from loguru import logger
import numpy as np

from core.smoke.email import build_event_label, build_event_type
from core.smoke.post_processor import Detection, DetectionClass, PostProcessorConfig, SmokeFirePostProcessor
from core.smoke.processor import SmokeFireProcessor
from core.vl_confirm import VLConfirmClient


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
        assert result.messages[0]["scene_id"] == "smoke"
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


def _vl_processor(vengine) -> SmokeFireProcessor:
    return SmokeFireProcessor(
        source_id="s1",
        source_name="Cam1",
        rtsp_url="",
        rois=[],
        vengine_client=vengine,
        app_settings={
            "smoke_temporal_confirm_frames": "1",
            "smoke_enable_appearance_filter": "false",
            "smoke_vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "smoke_vl_confirm_prompt": "Verify",
            "smoke_vl_confirm_response_key": "smoke",
        },
    )


def _decode_data_url(data_url: str) -> np.ndarray:
    import base64

    import cv2

    buf = np.frombuffer(base64.b64decode(data_url.split(",", 1)[1]), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


async def test_vl_confirm_reject_keeps_message_marked_false_positive():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is True
    assert "email_event" not in result.extra


async def test_vl_confirm_allows_alarm_when_model_returns_true():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert result.extra["email_event"]["event_type"] == "smoke"


async def test_vl_confirm_fail_open_when_model_returns_none():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=None)

    with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert "email_event" in result.extra


async def test_vl_confirm_skipped_when_disabled():
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
            "smoke_vl_confirm_enabled": "false",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.smoke.processor.VLConfirmClient") as mock_cls:
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    mock_cls.assert_not_called()
    assert result.messages


async def test_vl_annotated_full_image_sent_to_model():
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
            "smoke_vl_confirm_enabled": "true",
            "smoke_vl_confirm_image_source": "annotated",
            "smoke_vl_confirm_image_crop": "full",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
        await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    data_url = mock_client.confirm.await_args.args[0]
    decoded = _decode_data_url(data_url)
    assert decoded.shape[:2] == (100, 100)
    assert decoded.std() > 5  # 检测图上画了检测框，非纯黑（纯黑帧 std≈0）


async def test_vl_sampling_params_from_smoke_settings_only():
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
            "smoke_vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "smoke_vl_confirm_max_tokens": "256",
            "smoke_vl_confirm_temperature": "0.5",
            "smoke_vl_confirm_top_p": "0.9",
            "smoke_vl_confirm_disable_thinking": "true",
            "fire_door_vl_confirm_max_tokens": "32",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.smoke.processor.VLConfirmClient", return_value=AsyncMock()) as mock_cls:
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    assert len(result.messages) == 1
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_tokens"] == 256
    assert kwargs["temperature"] == 0.5
    assert kwargs["top_p"] == 0.9
    assert kwargs["disable_thinking"] is True


async def test_vl_reject_logs_warning_with_source():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
            await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
    finally:
        logger.remove(sink_id)

    assert any(
        "Alarm rejected by VL confirm" in r["message"]
        and "Cam1" in r["message"]
        and r["level"].name == "WARNING"
        for r in records
    )
