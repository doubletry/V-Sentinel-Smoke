from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
            "vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "fire_door_vl_confirm_prompt": "Verify",
            "fire_door_vl_confirm_response_key": "open",
        },
    )


async def test_vl_confirm_suppresses_alarm_when_model_returns_false():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    with patch("core.fire_door.processor.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )

    assert result.messages == []


async def test_vl_confirm_allows_alarm_when_model_returns_true():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.fire_door.processor.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )

    assert result.messages


async def test_vl_confirm_fail_open_when_model_returns_none():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=None)

    with patch("core.fire_door.processor.VLConfirmClient", return_value=mock_client):
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )

    assert result.messages


async def test_vl_confirm_skipped_when_disabled():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(vengine, settings={"vl_confirm_enabled": "false"})
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.fire_door.processor.VLConfirmClient") as mock_cls:
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )

    mock_cls.assert_not_called()
    assert result.messages
