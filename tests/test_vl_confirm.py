from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import cv2
import numpy as np

from core.vl_confirm import VLConfirmClient, build_vl_image_data_url, crop_roi_image, parse_vl_response


def test_parse_json_with_response_key_true():
    assert parse_vl_response('{"open": true}', "open") is True


def test_parse_json_with_response_key_false():
    assert parse_vl_response('{"open": false}', "open") is False


def test_parse_json_code_block():
    assert parse_vl_response('```json\n{"open": true}\n```', "open") is True


def test_parse_keyword_fallback_true():
    assert parse_vl_response('The door is open. {"open": true}', "open") is True


def test_parse_keyword_fallback_false():
    assert parse_vl_response('The door is closed. {"open": false}', "open") is False


def test_parse_unparseable_returns_none():
    assert parse_vl_response("I cannot determine", "open") is None


def test_parse_different_response_key():
    assert parse_vl_response('{"smoke": true}', "smoke") is True
    assert parse_vl_response('{"smoke": false}', "smoke") is False


def test_crop_roi_image_no_roi_returns_full_frame():
    frame = np.full((100, 200, 3), 128, dtype=np.uint8)
    result = crop_roi_image(frame, None)
    assert result.startswith("data:image/jpeg;base64,")


def test_crop_roi_image_empty_points_returns_full_frame():
    frame = np.full((100, 200, 3), 128, dtype=np.uint8)
    result = crop_roi_image(frame, [])
    assert result.startswith("data:image/jpeg;base64,")


def test_crop_roi_image_rectangle_crop():
    frame = np.full((100, 200, 3), 128, dtype=np.uint8)
    frame[20:80, 50:150] = [255, 0, 0]
    points = [{"x": 50, "y": 20}, {"x": 150, "y": 80}]
    result = crop_roi_image(frame, points)
    assert result.startswith("data:image/jpeg;base64,")
    decoded = _decode_data_url(result)
    assert decoded.shape[0] == 61
    assert decoded.shape[1] == 101


def test_crop_roi_image_polygon_crops_bounding_box():
    frame = np.full((100, 200, 3), 255, dtype=np.uint8)
    points = [{"x": 50, "y": 20}, {"x": 150, "y": 20}, {"x": 100, "y": 80}]
    result = crop_roi_image(frame, points)
    assert result.startswith("data:image/jpeg;base64,")
    decoded = _decode_data_url(result)
    # Bounding box spans x in [50, 150], y in [20, 80] → 101 x 61
    assert decoded.shape[0] == 61
    assert decoded.shape[1] == 101


def _decode_data_url(data_url: str) -> np.ndarray:
    encoded = data_url.split(",", 1)[1]
    buf = np.frombuffer(base64.b64decode(encoded), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


async def test_vl_confirm_client_returns_true_on_json_confirm():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"open": true}'
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await client.confirm("data:image/jpeg;base64,abc", "Verify", "open")
    assert result is True


async def test_vl_confirm_client_returns_false_on_json_reject():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"open": false}'
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await client.confirm("data:image/jpeg;base64,abc", "Verify", "open")
    assert result is False


async def test_vl_confirm_client_returns_none_on_error():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))

    result = await client.confirm("data:image/jpeg;base64,abc", "Verify", "open")
    assert result is None


async def test_vl_confirm_client_returns_none_on_unparseable():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "I cannot determine"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await client.confirm("data:image/jpeg;base64,abc", "Verify", "open")
    assert result is None


class TestBuildVlImageDataUrl:
    def test_original_full_returns_full_frame(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(
            frame, None, "original", "full",
            [{"x": 5, "y": 5}, {"x": 55, "y": 35}],
        )
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (40, 60)

    def test_original_roi_crops_to_bbox(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(
            frame, None, "original", "roi",
            [{"x": 5, "y": 5}, {"x": 55, "y": 35}],
        )
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (31, 51)

    def test_annotated_full_uses_annotated_frame(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        annotated = np.zeros((40, 60, 3), dtype=np.uint8)
        annotated[:, :, 0] = 255  # RGB red
        url = build_vl_image_data_url(frame, annotated, "annotated", "full", None)
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (40, 60)
        assert decoded[:, :, 2].mean() > 200  # BGR 解码后 R 通道

    def test_annotated_missing_falls_back_to_original(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(frame, None, "annotated", "full", None)
        decoded = _decode_data_url(url)
        assert decoded[:, :, 2].mean() < 50

    def test_unknown_values_fall_back_to_original_roi(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(
            frame, None, "bogus", "bogus",
            [{"x": 5, "y": 5}, {"x": 55, "y": 35}],
        )
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (31, 51)
