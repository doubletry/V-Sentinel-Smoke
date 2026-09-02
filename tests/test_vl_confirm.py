from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import cv2
import numpy as np
import pytest

from loguru import logger

from core.vl_confirm import (
    VLConfirmClient,
    VL_TEST_PROMPT,
    build_vl_image_data_url,
    build_vl_test_image_data_url,
    crop_roi_image,
    encode_frame_as_data_url,
    parse_vl_response,
    vl_sampling_kwargs,
)


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


async def test_complete_returns_raw_text():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "hello raw"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    raw = await client.complete("data:image/jpeg;base64,abc", "Ping")
    assert raw == "hello raw"


async def test_complete_raises_on_upstream_error():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(side_effect=Exception("conn refused"))

    with pytest.raises(Exception, match="conn refused"):
        await client.complete("data:image/jpeg;base64,abc", "Ping")


async def test_complete_empty_content_returns_empty_string():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    assert await client.complete("data:image/jpeg;base64,abc", "Ping") == ""


async def test_confirm_behavior_unchanged_uses_complete():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client.complete = AsyncMock(return_value='{"smoke": true}')
    assert await client.confirm("x", "P", "smoke") is True
    client.complete = AsyncMock(side_effect=Exception("boom"))
    assert await client.confirm("x", "P", "smoke") is None


def test_build_vl_test_image_data_url_is_valid_jpeg():
    url = build_vl_test_image_data_url()
    assert url.startswith("data:image/jpeg;base64,")
    decoded = _decode_data_url(url)
    assert decoded.shape == (240, 320, 3)


def test_encode_frame_as_data_url_roundtrip():
    frame = np.zeros((30, 40, 3), dtype=np.uint8)
    decoded = _decode_data_url(encode_frame_as_data_url(frame))
    assert decoded.shape == (30, 40, 3)


def test_vl_test_prompt_mentions_json():
    assert "connected" in VL_TEST_PROMPT


async def test_complete_max_tokens_covers_thinking_models():
    """max_tokens must leave room for thinking models (e.g. Qwen3) that emit
    reasoning tokens before the final JSON answer. A small budget gets fully
    consumed by reasoning, the content is truncated to None and the review
    result degrades to 'unknown'.
    """
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"connected": true}'
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    kwargs = client._client.chat.completions.create.await_args.kwargs
    assert kwargs["max_tokens"] >= 512


def test_vl_sampling_kwargs_defaults():
    kwargs = vl_sampling_kwargs({}, "smoke")
    assert kwargs == {"max_tokens": 1024, "temperature": 0.0, "top_p": None, "disable_thinking": False}


def test_vl_sampling_kwargs_scene_isolation():
    settings = {
        "smoke_vl_confirm_max_tokens": "256",
        "smoke_vl_confirm_disable_thinking": "true",
        "fire_door_vl_confirm_max_tokens": "512",
    }
    assert vl_sampling_kwargs(settings, "smoke")["max_tokens"] == 256
    assert vl_sampling_kwargs(settings, "smoke")["disable_thinking"] is True
    assert vl_sampling_kwargs(settings, "fire_door")["max_tokens"] == 512
    assert vl_sampling_kwargs(settings, "fire_door")["disable_thinking"] is False


def test_vl_sampling_kwargs_overrides_take_precedence():
    kwargs = vl_sampling_kwargs(
        {"smoke_vl_confirm_max_tokens": "256", "smoke_vl_confirm_temperature": "0.5"},
        "smoke",
        overrides={"smoke_vl_confirm_max_tokens": "64", "smoke_vl_confirm_top_p": "0.9"},
    )
    assert kwargs["max_tokens"] == 64
    assert kwargs["temperature"] == 0.5
    assert kwargs["top_p"] == 0.9
    assert kwargs["disable_thinking"] is False


def test_vl_sampling_kwargs_lenient_parsing():
    settings = {
        "smoke_vl_confirm_max_tokens": "abc",
        "smoke_vl_confirm_temperature": "-3",
        "smoke_vl_confirm_top_p": "1.5",
        "smoke_vl_confirm_disable_thinking": "TRUE",
    }
    kwargs = vl_sampling_kwargs(settings, "smoke")
    assert kwargs["max_tokens"] == 1024
    assert kwargs["temperature"] == 0.0
    assert kwargs["top_p"] is None
    assert kwargs["disable_thinking"] is True

    clamped = vl_sampling_kwargs(
        {
            "smoke_vl_confirm_max_tokens": "0",
            "smoke_vl_confirm_temperature": "5",
            "smoke_vl_confirm_top_p": "0.9",
        },
        "smoke",
    )
    assert clamped["max_tokens"] == 1
    assert clamped["temperature"] == 2.0
    assert clamped["top_p"] == 0.9


def test_vl_sampling_kwargs_extreme_values_do_not_raise():
    kwargs = vl_sampling_kwargs(
        {
            "smoke_vl_confirm_max_tokens": "1e400",
            "smoke_vl_confirm_temperature": "1e400",
            "smoke_vl_confirm_top_p": "1e400",
        },
        "smoke",
    )
    assert kwargs["max_tokens"] == 32768
    assert kwargs["temperature"] == 2.0
    assert kwargs["top_p"] is None


async def test_complete_passes_sampling_kwargs():
    client = VLConfirmClient(
        "http://localhost:30000/v1", "EMPTY", "/models/Mage-VL",
        max_tokens=256, temperature=0.5, top_p=0.9,
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    kwargs = client._client.chat.completions.create.await_args.kwargs
    assert kwargs["max_tokens"] == 256
    assert kwargs["temperature"] == 0.5
    assert kwargs["top_p"] == 0.9
    assert "extra_body" not in kwargs


async def test_complete_omits_top_p_when_none():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    assert "top_p" not in client._client.chat.completions.create.await_args.kwargs


async def test_complete_disable_thinking_sends_extra_body():
    client = VLConfirmClient(
        "http://localhost:30000/v1", "EMPTY", "/models/Mage-VL",
        disable_thinking=True,
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    kwargs = client._client.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


async def test_complete_success_logs_raw_response():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"smoke": true}'
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        raw = await client.complete("data:image/jpeg;base64,abc", "Ping")
    finally:
        logger.remove(sink_id)

    assert raw == '{"smoke": true}'
    messages = [r["message"] for r in records]
    assert any("VL request ok" in m and "/models/Mage-VL" in m for m in messages)
    assert any("VL raw response" in m and '{"smoke": true}' in m for m in messages)


async def test_complete_failure_logs_exception_details():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("conn-refused-detail")
    )

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        with pytest.raises(RuntimeError, match="conn-refused-detail"):
            await client.complete("data:image/jpeg;base64,abc", "Ping")
    finally:
        logger.remove(sink_id)

    failures = [r for r in records if "VL request failed" in r["message"]]
    assert failures, "expected a 'VL request failed' warning"
    assert "conn-refused-detail" in failures[0]["message"]
    # 回归：loguru 忽略 stdlib 风格 exc_info=True；record 必须携带异常（完整栈），
    # 否则 VL 服务端返回的错误体在日志中不可见。
    assert failures[0]["exception"] is not None


async def test_confirm_failure_logs_failing_open():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(side_effect=Exception("boom-vl"))

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        result = await client.confirm("data:image/jpeg;base64,abc", "Verify", "open")
    finally:
        logger.remove(sink_id)

    assert result is None
    assert any(
        "failing open" in r["message"] and "/models/Mage-VL" in r["message"]
        for r in records
    )
