"""VL large-model secondary confirmation for alarm verification.

This module provides a generic vision-language (VL) model client used to
verify alarms before they are dispatched.  It is scene-agnostic: callers
supply a prompt and a response key, and the model is asked to reply with a
JSON object whose boolean value determines whether the alarm is confirmed.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any

import cv2
import numpy as np
from loguru import logger

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore[assignment]


VL_TEST_PROMPT = (
    "This is a connection test image. 这是一张连通性测试图。"
    "Reply with ONLY: {\"connected\": true}"
)


def parse_vl_response(text: str, response_key: str) -> bool | None:
    """Parse a VL model response and extract the boolean for ``response_key``.

    Strategy, in order:

    1. Strip markdown code fences, JSON-parse, and read ``response_key``.
    2. Regex search for ``"<response_key>": true|false`` in the raw text.
    3. Fall back to a standalone ``true`` / ``false`` keyword search.
    4. Return ``None`` when nothing can be determined.
    """
    if not text:
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and response_key in data:
            return bool(data[response_key])
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    pattern = re.compile(
        rf'"{re.escape(response_key)}"\s*:\s*(true|false)',
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        return match.group(1).lower() == "true"

    low = text.lower()
    has_true = "true" in low
    has_false = "false" in low
    if has_true and not has_false:
        return True
    if has_false and not has_true:
        return False

    return None


DEFAULT_VL_MAX_TOKENS = 1024
DEFAULT_VL_TEMPERATURE = 0.0
VL_MAX_TOKENS_LIMIT = 32768


def _parse_float(raw: object, default: float) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError, OverflowError):
        return default


def vl_sampling_kwargs(
    settings: dict[str, str],
    scene_id: str,
    overrides: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build VLConfirmClient sampling kwargs from per-scene settings.
    从场景级设置构建 VL 采样参数。

    Merge order: ``overrides`` (request body) -> saved
    ``<scene>_vl_confirm_*`` settings -> defaults. 宽松解析：解析失败
    回退默认值，不抛错。
    """

    def merged(key: str) -> str:
        override = (overrides or {}).get(key)
        if override is not None and str(override).strip():
            return str(override).strip()
        saved = settings.get(key)
        if saved is not None and str(saved).strip():
            return str(saved).strip()
        return ""

    prefix = f"{scene_id}_vl_confirm_"

    max_tokens = _parse_float(
        merged(prefix + "max_tokens") or str(DEFAULT_VL_MAX_TOKENS),
        DEFAULT_VL_MAX_TOKENS,
    )
    max_tokens = int(max(1.0, min(max_tokens, float(VL_MAX_TOKENS_LIMIT))))

    temperature = _parse_float(
        merged(prefix + "temperature") or str(DEFAULT_VL_TEMPERATURE),
        DEFAULT_VL_TEMPERATURE,
    )
    temperature = max(0.0, min(temperature, 2.0))

    top_p: float | None = None
    raw_top_p = merged(prefix + "top_p")
    if raw_top_p:
        parsed = _parse_float(raw_top_p, 0.0)
        if 0 < parsed <= 1:
            top_p = parsed

    disable_thinking = merged(prefix + "disable_thinking").lower() == "true"

    return {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "disable_thinking": disable_thinking,
    }


def encode_frame_as_data_url(frame: np.ndarray) -> str:
    """Encode an RGB ndarray as a JPEG data URL."""
    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError("Failed to encode frame as JPEG")
    encoded = base64.b64encode(buf.tobytes()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def build_vl_test_image_data_url() -> str:
    """Build a deterministic synthetic test image as a JPEG data URL.
    生成确定性合成测试图并编码为 JPEG data URL。"""
    frame = np.full((240, 320, 3), 200, dtype=np.uint8)
    frame[80:160, 110:210] = (255, 0, 0)
    return encode_frame_as_data_url(frame)


def crop_roi_image(
    frame: np.ndarray,
    roi_points: list[dict[str, Any]] | None,
) -> str:
    """Crop ``frame`` to a ROI's axis-aligned bounding box and return a JPEG data URL.

    - ``roi_points`` is ``None`` or empty → encode the full frame.
    - Rectangle (2 points) or polygon (3+ points) → crop the smallest
      axis-aligned bounding box that encloses all points.
    """
    if not roi_points:
        return encode_frame_as_data_url(frame)

    xs = [int(p["x"]) for p in roi_points]
    ys = [int(p["y"]) for p in roi_points]
    h, w = frame.shape[:2]
    min_x = max(0, min(xs))
    min_y = max(0, min(ys))
    max_x = min(w - 1, max(xs))
    max_y = min(h - 1, max(ys))

    if max_x <= min_x or max_y <= min_y:
        return encode_frame_as_data_url(frame)

    cropped = frame[min_y:max_y + 1, min_x:max_x + 1]
    return encode_frame_as_data_url(cropped)


def build_vl_image_data_url(
    frame: np.ndarray,
    annotated_frame: np.ndarray | None,
    image_source: str,
    image_crop: str,
    roi_points: list[dict[str, Any]] | None,
) -> str:
    """Build the JPEG data URL sent to the VL model from configured options.

    - ``image_source``: ``"original"`` (raw frame, default) or ``"annotated"``
      (frame with detection drawings). Unknown values, or a missing
      ``annotated_frame``, fall back to the original frame.
    - ``image_crop``: ``"roi"`` (crop to the ``roi_points`` bounding box,
      default) or ``"full"`` (full frame). Unknown values fall back to
      ``"roi"``.
    """
    selected = frame
    if str(image_source or "").strip().lower() == "annotated" and annotated_frame is not None:
        selected = annotated_frame
    if str(image_crop or "").strip().lower() == "full":
        return crop_roi_image(selected, None)
    return crop_roi_image(selected, roi_points)


class VLConfirmClient:
    """Async VL model client for alarm secondary confirmation."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        top_p: float | None = None,
        disable_thinking: bool = False,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._disable_thinking = disable_thinking
        if AsyncOpenAI is None:
            raise RuntimeError("openai SDK is not installed")
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=float(timeout),
        )

    async def complete(self, image_data_url: str, prompt: str) -> str:
        """Send an image + prompt to the model and return the raw text.

        Unlike :meth:`confirm`, any failure is raised to the caller so
        endpoints can surface the concrete upstream error.
        与 ``confirm`` 不同，任何失败都会抛给调用方，便于端点展示具体错误。
        """
        content = [
            {"type": "image_url", "image_url": {"url": image_data_url}},
            {"type": "text", "text": prompt},
        ]
        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if self._top_p is not None:
            create_kwargs["top_p"] = self._top_p
        if self._disable_thinking:
            create_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        started = time.monotonic()
        try:
            response = await self._client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.opt(exception=True).warning(
                "VL request failed: model={} base_url={} latency_ms={} error={}",
                self._model,
                self._base_url,
                latency_ms,
                exc,
            )
            raise
        raw = response.choices[0].message.content or ""
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info("VL request ok: model={} latency_ms={}", self._model, latency_ms)
        logger.info("VL raw response: {}", raw)
        return raw

    async def confirm(
        self,
        image_data_url: str,
        prompt: str,
        response_key: str,
    ) -> bool | None:
        """Send an image to the VL model and parse the confirmation result.

        Returns ``True`` (confirmed), ``False`` (rejected), or ``None`` on
        error / unparseable output (callers should fail-open).
        """
        try:
            raw = await self.complete(image_data_url, prompt)
            verdict = parse_vl_response(raw, response_key)
            logger.info("VL confirm verdict={}", verdict)
            return verdict
        except Exception:
            logger.warning("VL confirm failed, failing open: model={}", self._model)
            return None
