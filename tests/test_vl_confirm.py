from __future__ import annotations

import base64
import http.server
import json
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


# --- Total-timeout enforcement against a real local OpenAI-compatible server ---

VALID_COMPLETION = {
    "id": "cmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": '{"connected": true}'},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_local_vl_server(completions_handler) -> tuple[str, dict]:
    """Start a local OpenAI-compatible server; returns (base_url, request_state)."""
    import threading
    import time as _time

    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    state: dict = {"n": 0}

    @app.post("/v1/chat/completions")
    async def completions():
        state["n"] += 1
        return await completions_handler(state["n"])

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = _time.monotonic() + 5
    while not server.started and _time.monotonic() < deadline:
        _time.sleep(0.01)
    assert server.started, "local VL test server did not start"

    state["shutdown"] = lambda: (setattr(server, "should_exit", True), thread.join(timeout=5))
    return f"http://127.0.0.1:{port}/v1", state


async def test_no_success_arrives_after_configured_timeout():
    """A response must never be delivered later than the configured timeout.

    The OpenAI SDK silently retries timed-out attempts (default
    max_retries=2); a retry succeeding after the budget used to surface as a
    "success" with latency far above the timeout setting.
    """
    import asyncio
    import time

    async def handler(n: int):
        if n == 1:
            await asyncio.sleep(30)  # stalls well past the 1s client timeout
        return VALID_COMPLETION

    base_url, state = _run_local_vl_server(handler)
    try:
        client = VLConfirmClient(base_url=base_url, api_key="EMPTY", model="m", timeout=1)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            await client.complete("data:image/jpeg;base64,abc", "Ping")
        elapsed = time.monotonic() - started
    finally:
        state["shutdown"]()

    assert elapsed < 5, f"call took {elapsed:.1f}s despite timeout=1s"
    assert state["n"] == 1, "timed-out attempt must not be retried past the budget"


async def test_all_slow_attempts_stay_within_total_budget():
    """When every attempt is slow, the total elapsed time must respect the budget."""
    import asyncio
    import time

    async def handler(n: int):
        await asyncio.sleep(30)  # every attempt stalls past the 1s client timeout
        return VALID_COMPLETION

    base_url, state = _run_local_vl_server(handler)
    try:
        client = VLConfirmClient(base_url=base_url, api_key="EMPTY", model="m", timeout=1)
        started = time.monotonic()
        with pytest.raises(Exception):
            await client.complete("data:image/jpeg;base64,abc", "Ping")
        elapsed = time.monotonic() - started
    finally:
        state["shutdown"]()

    assert elapsed < 2.5, (
        f"total {elapsed:.1f}s for timeout=1s (SDK retries must not extend the budget)"
    )


# ── proxy mode / 代理模式 ────────────────────────────────────────────────────


def _start_recording_proxy(handler, state):
    """Start a local recording proxy; state gains ``url`` and ``shutdown``."""
    import threading

    class _ProxyHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            try:
                handler(self.path)
            except Exception:
                pass
            body = json.dumps(VALID_COMPLETION).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), _ProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.update(
        url=f"http://127.0.0.1:{server.server_address[1]}",
        shutdown=lambda: (server.shutdown(), server.server_close(), thread.join(timeout=5)),
    )


def test_build_vl_http_client_none_mode_ignores_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_http_client

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    client = build_vl_http_client("none", "")
    assert client is not None
    assert client._trust_env is False
    assert not any("AsyncHTTPProxy" in repr(vars(t).get("_pool", "")) for t in client._mounts.values())
    monkeypatch.delenv("HTTP_PROXY")
    monkeypatch.delenv("http_proxy")


def test_build_vl_http_client_unknown_mode_behaves_like_none():
    from core.vl_confirm import build_vl_http_client

    client = build_vl_http_client("bogus", "")
    assert client is not None
    assert client._trust_env is False


def test_build_vl_http_client_manual_requires_scheme():
    from core.vl_confirm import build_vl_http_client

    with pytest.raises(ValueError, match="http:// or https://"):
        build_vl_http_client("manual", "")
    with pytest.raises(ValueError, match="http:// or https://"):
        build_vl_http_client("manual", "ftp://10.0.0.1:21")


def test_build_vl_http_client_manual_sets_proxy():
    from core.vl_confirm import build_vl_http_client

    client = build_vl_http_client("manual", "http://10.0.0.1:3128")
    assert client is not None
    assert client._trust_env is False
    # 代理挂载存在（httpx2 代理 transport 的池是 AsyncHTTPProxy）
    assert any("AsyncHTTPProxy" in repr(vars(t).get("_pool", "")) for t in client._mounts.values())


def test_build_vl_http_client_system_returns_none():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("system", "") is None
    assert build_vl_http_client("", "") is not None


def test_build_vl_client_merge_order_and_defaults():
    from core.vl_confirm import build_vl_client

    settings = {
        "vl_confirm_base_url": "http://settings-host/v1",
        "vl_confirm_api_key": "settings-key",
        "vl_confirm_model": "settings-model",
        "vl_confirm_timeout": "7",
        "smoke_vl_confirm_max_tokens": "128",
    }
    client = build_vl_client(settings, "smoke", overrides={"vl_confirm_base_url": "http://override-host/v1"})
    assert client._base_url == "http://override-host/v1"
    assert client._api_key == "settings-key"
    assert client._model == "settings-model"
    assert client._timeout == 7.0
    assert client._max_tokens == 128


def test_build_vl_client_scene_specific_sampling():
    from core.vl_confirm import build_vl_client

    settings = {
        "smoke_vl_confirm_temperature": "0.1",
        "fire_door_vl_confirm_temperature": "0.9",
    }
    assert build_vl_client(settings, "smoke")._temperature == 0.1
    assert build_vl_client(settings, "fire_door")._temperature == 0.9


def test_build_vl_client_defaults_when_settings_empty():
    from core.vl_confirm import build_vl_client

    client = build_vl_client({}, "smoke")
    assert client._base_url == "http://localhost:30000/v1"
    assert client._api_key == "EMPTY"
    assert client._model == "/models/Mage-VL"
    assert client._timeout == 60.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 1.0),
        ("-5", 1.0),
        ("inf", 60.0),
        ("abc", 60.0),
    ],
)
def test_build_vl_client_timeout_floor_and_lenient_parse(raw, expected):
    from core.vl_confirm import build_vl_client

    client = build_vl_client({"vl_confirm_timeout": raw}, "smoke")
    assert client._timeout == expected


def test_build_vl_client_logs_normalized_mode_after_success():
    from core.vl_confirm import build_vl_client

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        client = build_vl_client(
            {
                "vl_confirm_proxy_mode": " MANUAL ",
                "vl_confirm_proxy_url": "http://127.0.0.1:3128",
                "vl_confirm_timeout": "90",
            },
            "smoke",
        )
    finally:
        logger.remove(sink_id)

    assert client._timeout == 90.0
    assert any(r["message"] == "VL client: proxy_mode=manual" for r in records)


def test_build_vl_client_rejected_manual_config_logs_nothing():
    from core.vl_confirm import build_vl_client

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        with pytest.raises(ValueError, match="http:// or https://"):
            build_vl_client(
                {"vl_confirm_proxy_mode": "manual", "vl_confirm_proxy_url": ""}, "smoke"
            )
    finally:
        logger.remove(sink_id)

    assert not any("VL client: proxy_mode" in r["message"] for r in records)


async def _model_ok(request):
    return VALID_COMPLETION


async def test_vl_none_mode_reaches_model_not_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    base_url, model_state = _run_local_vl_server(_model_ok)
    proxy_state: dict = {"n": 0}
    _start_recording_proxy(
        lambda path: proxy_state.update(n=proxy_state["n"] + 1), proxy_state
    )
    monkeypatch.setenv("HTTP_PROXY", proxy_state["url"])
    monkeypatch.setenv("http_proxy", proxy_state["url"])
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        client = build_vl_client(
            {"vl_confirm_base_url": base_url, "vl_confirm_timeout": "5"}, "smoke"
        )
        result = await client.complete("hi", "text")
    finally:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        proxy_state["shutdown"]()
        model_state["shutdown"]()
    assert result == VALID_COMPLETION["choices"][0]["message"]["content"]
    assert model_state["n"] == 1
    assert proxy_state["n"] == 0


async def test_vl_manual_mode_routes_through_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    base_url, model_state = _run_local_vl_server(_model_ok)
    proxy_state: dict = {"n": 0}
    _start_recording_proxy(
        lambda path: proxy_state.update(n=proxy_state["n"] + 1), proxy_state
    )
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    try:
        client = build_vl_client(
            {
                "vl_confirm_base_url": base_url,
                "vl_confirm_timeout": "5",
                "vl_confirm_proxy_mode": "manual",
                "vl_confirm_proxy_url": proxy_state["url"],
            },
            "smoke",
        )
        result = await client.complete("hi", "text")
    finally:
        proxy_state["shutdown"]()
        model_state["shutdown"]()
    assert result == VALID_COMPLETION["choices"][0]["message"]["content"]
    assert proxy_state["n"] == 1
    assert model_state["n"] == 0


async def test_vl_system_mode_uses_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    base_url, model_state = _run_local_vl_server(_model_ok)
    proxy_state: dict = {"n": 0}
    _start_recording_proxy(
        lambda path: proxy_state.update(n=proxy_state["n"] + 1), proxy_state
    )
    monkeypatch.setenv("HTTP_PROXY", proxy_state["url"])
    monkeypatch.setenv("http_proxy", proxy_state["url"])
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        client = build_vl_client(
            {
                "vl_confirm_base_url": base_url,
                "vl_confirm_timeout": "5",
                "vl_confirm_proxy_mode": "system",
            },
            "smoke",
        )
        await client.complete("hi", "text")
    finally:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        proxy_state["shutdown"]()
        model_state["shutdown"]()
    assert proxy_state["n"] == 1
    assert model_state["n"] == 0
