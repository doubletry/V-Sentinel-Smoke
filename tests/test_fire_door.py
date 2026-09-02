from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from loguru import logger
import numpy as np

from core.base_processor import ROI, ROIPoint
from core.fire_door.processor import FireDoorProcessor
from core.notification_template import build_template_context
from core.vl_confirm import VLConfirmClient


def _roi(roi_id: str = "r1", tag: str = "fire_door") -> ROI:
    return ROI(
        id=roi_id,
        type="rectangle",
        tag=tag,
        points=[
            ROIPoint(x=0.1, y=0.1),
            ROIPoint(x=0.9, y=0.1),
            ROIPoint(x=0.9, y=0.9),
            ROIPoint(x=0.1, y=0.9),
        ],
    )


def _processor(vengine, *, rois=None, settings=None, source_threshold=None) -> FireDoorProcessor:
    return FireDoorProcessor(
        source_id="s1",
        source_name="DoorCam",
        rtsp_url="rtsp://10.0.0.8:8554/floor1/door-a",
        source_remark="North stairwell",
        rois=rois if rois is not None else [_roi()],
        vengine_client=vengine,
        source_alarm_confidence_threshold=source_threshold,
        app_settings={
            "fire_door_temporal_confirm_frames": "1",
            "fire_door_alarm_hold_time": "0",
            **(settings or {}),
        },
    )


async def test_open_label_is_case_insensitive_and_generates_alert():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "OPEN", "confidence": 0.91, "class_id": 1}]
    processor = _processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    result = await processor.process_frame(
        frame,
        b"frame",
        frame.shape,
        [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
    )
    await processor.finalize_result(result)

    assert result.messages
    assert result.classifications[0]["door_state"] == "open"
    assert result.extra["email_event"]["source_remark"] == "North stairwell"
    assert result.extra["email_event"]["source_route_path"] == "floor1/door-a"


async def test_closed_label_does_not_alert():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "Closed", "confidence": 0.99, "class_id": 0}]
    processor = _processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    result = await processor.process_frame(
        frame,
        b"frame",
        frame.shape,
        [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
    )

    assert result.messages == []
    assert result.classifications[0]["door_state"] == "closed"


async def test_low_confidence_open_does_not_alert():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.49, "class_id": 1}]
    processor = _processor(vengine, settings={"fire_door_classification_confidence": "0.50"})
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    result = await processor.process_frame(
        frame,
        b"frame",
        frame.shape,
        [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
    )

    assert result.messages == []


async def test_source_confidence_override_controls_alarm_threshold():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(
        vengine,
        settings={"fire_door_classification_confidence": "0.50"},
        source_threshold=0.95,
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    result = await processor.process_frame(
        frame,
        b"frame",
        frame.shape,
        [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
    )

    assert result.messages == []
    assert result.classifications[0]["confidence"] == 0.91


async def test_empty_source_confidence_uses_plugin_alarm_threshold():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.71, "class_id": 1}]
    processor = _processor(
        vengine,
        settings={"fire_door_classification_confidence": "0.72"},
        source_threshold=None,
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    result = await processor.process_frame(
        frame,
        b"frame",
        frame.shape,
        [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
    )

    assert result.messages == []
    assert result.classifications[0]["confidence"] == 0.71


async def test_multiple_rois_batch_classification_alerts_when_any_roi_is_open():
    vengine = AsyncMock()
    vengine.classify.return_value = [
        {"image_id": 0, "label": "closed", "confidence": 0.95, "class_id": 0},
        {"image_id": 1, "label": "Open", "confidence": 0.93, "class_id": 1},
    ]
    processor = _processor(vengine, rois=[_roi("r1"), _roi("r2")])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [
        [{"x": 10, "y": 10}, {"x": 40, "y": 10}, {"x": 40, "y": 40}, {"x": 10, "y": 40}],
        [{"x": 50, "y": 50}, {"x": 90, "y": 50}, {"x": 90, "y": 90}, {"x": 50, "y": 90}],
    ]

    result = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
    await processor.finalize_result(result)

    vengine.classify.assert_awaited_once()
    images = vengine.classify.await_args.kwargs["images"]
    assert len(images) == 2
    assert images[0]["image_roi"] == roi_points[0]
    assert images[1]["image_roi"] == roi_points[1]
    assert "roi" not in images[0]
    assert result.messages
    assert result.extra["email_event"]["roi_id"] == "r2"
    assert result.annotated_frame is not None
    assert result.annotated_frame.sum() > 0


async def test_classification_roi_uses_absolute_pixel_points_clamped_to_frame():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "closed", "confidence": 0.95, "class_id": 0}]
    processor = _processor(vengine)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    roi_points = [[{"x": -5, "y": 10}, {"x": 205, "y": 10}, {"x": 205, "y": 120}, {"x": -5, "y": 120}]]

    await processor.process_frame(frame, b"frame", frame.shape, roi_points)

    image = vengine.classify.await_args.kwargs["images"][0]
    assert image["shape"] == frame.shape
    assert image["image_bytes"] == b"frame"
    assert image["image_roi"] == [
        {"x": 0, "y": 10},
        {"x": 199, "y": 10},
        {"x": 199, "y": 99},
        {"x": 0, "y": 99},
    ]


async def test_temporal_confirmation_requires_configured_frames():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.95, "class_id": 1}]
    processor = _processor(vengine, settings={"fire_door_temporal_confirm_frames": "2"})
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]]

    first = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
    second = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
    await processor.finalize_result(second)

    assert first.messages == []
    assert second.messages


def test_fire_door_email_template_context_has_images_source_and_roi_fields():
    context = build_template_context(
        {"site_title": "V-Sentinel", "timezone": "UTC"},
        {
            "timestamp": "2026-05-20T07:08:00+00:00",
            "source_id": "s1",
            "source_name": "DoorCam",
            "source_rtsp_url": "rtsp://10.0.0.8:8554/floor1/door-a",
            "source_route_path": "floor1/door-a",
            "source_remark": "North stairwell",
            "event_type": "fire_door_open",
            "event_label": "消防门开启",
            "labels": ["open"],
            "confidence": 0.91,
            "roi_id": "r1",
            "roi_tag": "fire_door",
            "door_state": "open",
            "open_count": 1,
            "closed_count": 0,
            "original_image_base64": "YWJj",
            "detected_image_base64": "ZGVm",
        },
    )

    assert context["source_remark"] == "North stairwell"
    assert context["source_ip"] == "10.0.0.8"
    assert context["source_route_path"] == "floor1/door-a"
    assert context["roi_id"] == "r1"
    assert context["door_state"] == "open"
    assert context["has_original_image"] == "true"
    assert context["has_detected_image"] == "true"
    assert "<img" in context["original_image"]
    assert "<img" in context["detected_image"]


def _vl_processor(vengine) -> FireDoorProcessor:
    return _processor(
        vengine,
        settings={
            "fire_door_vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "fire_door_vl_confirm_prompt": "Verify",
            "fire_door_vl_confirm_response_key": "open",
        },
    )


def _decode_data_url(data_url: str) -> np.ndarray:
    import base64

    import cv2

    buf = np.frombuffer(base64.b64decode(data_url.split(",", 1)[1]), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


async def test_vl_confirm_reject_keeps_message_marked_false_positive():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )
        await processor.finalize_result(result)

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is True
    assert "email_event" not in result.extra


async def test_vl_confirm_allows_alarm_when_model_returns_true():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )
        await processor.finalize_result(result)

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert "email_event" in result.extra
    assert result.messages[0]["scene_id"] == "fire_door"


async def test_vl_confirm_fail_open_when_model_returns_none():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=None)

    with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )
        await processor.finalize_result(result)

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert "email_event" in result.extra


async def test_vl_confirm_skipped_when_disabled():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(vengine, settings={"fire_door_vl_confirm_enabled": "false"})
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.vl_confirm.VLConfirmClient") as mock_cls:
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )
        await processor.finalize_result(result)

    mock_cls.assert_not_called()
    assert result.messages


async def test_vl_annotated_full_image_sent_to_model():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(
        vengine,
        settings={
            "fire_door_vl_confirm_enabled": "true",
            "fire_door_vl_confirm_prompt": "Verify",
            "fire_door_vl_confirm_response_key": "open",
            "fire_door_vl_confirm_image_source": "annotated",
            "fire_door_vl_confirm_image_crop": "full",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )
        await processor.finalize_result(result)

    data_url = mock_client.confirm.await_args.args[0]
    decoded = _decode_data_url(data_url)
    assert decoded.shape[:2] == (100, 100)
    assert decoded.std() > 5  # 检测图上画了 ROI 标注，非纯黑（纯黑帧 std≈0）


async def test_vl_sampling_params_from_fire_door_settings_only():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(
        vengine,
        settings={
            "fire_door_vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "fire_door_vl_confirm_max_tokens": "512",
            "fire_door_vl_confirm_disable_thinking": "true",
            "smoke_vl_confirm_max_tokens": "256",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.vl_confirm.VLConfirmClient", return_value=AsyncMock()) as mock_cls:
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )
        await processor.finalize_result(result)

    assert len(result.messages) == 1
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_tokens"] == 512
    assert kwargs["disable_thinking"] is True
    assert kwargs["top_p"] is None
    assert kwargs["temperature"] == 0.0


async def test_vl_reject_logs_warning_with_source():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client):
            result = await processor.process_frame(
                frame, b"frame", frame.shape,
                [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
            )
            await processor.finalize_result(result)
    finally:
        logger.remove(sink_id)

    assert any(
        "Alarm rejected by VL confirm" in r["message"]
        and "DoorCam" in r["message"]
        and r["level"].name == "WARNING"
        for r in records
    )


async def test_process_frame_returns_before_vl_verdict():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]]

    gate = asyncio.Event()

    async def gated_verdict():
        await gate.wait()
        return True

    processor._vl_confirm_alert = lambda *args: gated_verdict()

    result = await asyncio.wait_for(
        processor.process_frame(frame, b"frame", frame.shape, roi_points),
        timeout=5.0,
    )

    vl_task = result.extra["pending_alert"]["vl_task"]
    assert vl_task is not None and not vl_task.done()
    assert result.annotated_frame is not None
    assert result.messages == []

    gate.set()
    await processor.finalize_result(result)
    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert result.messages[0]["scene_id"] == "fire_door"
    assert "email_event" in result.extra


async def test_fire_door_vl_manual_proxy_misconfig_falls_back_to_direct():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    processor.app_settings["vl_confirm_proxy_mode"] = "manual"
    processor.app_settings["vl_confirm_proxy_url"] = ""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]]

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)
    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client) as mock_cls:
            result = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
            await processor.finalize_result(result)
    finally:
        logger.remove(sink_id)

    assert len(result.messages) == 1
    assert mock_cls.call_count == 1
    assert any(
        "VL manual proxy misconfigured" in r["message"] and "DoorCam" in r["message"]
        for r in records
    )
