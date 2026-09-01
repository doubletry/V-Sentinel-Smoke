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
from typing import Any

import cv2
import numpy as np
from loguru import logger

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore[assignment]


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


def _encode_frame_as_data_url(frame: np.ndarray) -> str:
    """Encode an RGB ndarray as a JPEG data URL."""
    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError("Failed to encode frame as JPEG")
    encoded = base64.b64encode(buf.tobytes()).decode()
    return f"data:image/jpeg;base64,{encoded}"


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
        return _encode_frame_as_data_url(frame)

    xs = [int(p["x"]) for p in roi_points]
    ys = [int(p["y"]) for p in roi_points]
    h, w = frame.shape[:2]
    min_x = max(0, min(xs))
    min_y = max(0, min(ys))
    max_x = min(w - 1, max(xs))
    max_y = min(h - 1, max(ys))

    if max_x <= min_x or max_y <= min_y:
        return _encode_frame_as_data_url(frame)

    cropped = frame[min_y:max_y + 1, min_x:max_x + 1]
    return _encode_frame_as_data_url(cropped)


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
    ) -> None:
        self._model = model
        if AsyncOpenAI is None:
            raise RuntimeError("openai SDK is not installed")
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=float(timeout),
        )

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
            content = [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": prompt},
            ]
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": content}],
                max_tokens=50,
                temperature=0,
            )
            raw = response.choices[0].message.content or ""
            logger.debug("VL confirm raw response: {}", raw)
            return parse_vl_response(raw, response_key)
        except Exception:
            logger.warning("VL confirm failed", exc_info=True)
            return None
