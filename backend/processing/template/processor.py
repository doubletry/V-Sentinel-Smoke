from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import cv2
import numpy as np

from backend.models.schemas import ROI
from backend.processing.base import AnalysisResult, BaseVideoProcessor

if TYPE_CHECKING:
    from backend.api.ws import WSManager
    from backend.processing.agent import AnalysisAgent
    from backend.vengine.client import AsyncVEngineClient


class TemplateSceneProcessor(BaseVideoProcessor):
    """Runnable backend template for developing a new scene.
    用于开发新场景的可运行后端模板。

    The base class already reads RTSP frames, converts configured ROIs to pixel
    coordinates, calls ``process_frame()``, pushes annotated frames, broadcasts
    messages, and hands results to the agent. The agent persists messages and
    dispatches notifications when ``result.extra["event"]`` is present.
    基类已经负责读取 RTSP 帧、把配置的 ROI 转为像素坐标、调用
    ``process_frame()``、推送标注帧、广播消息，并把结果交给 agent。agent
    会持久化消息；当 ``result.extra["event"]`` 存在时会调用通知调度器。
    """

    def __init__(
        self,
        source_id: str,
        source_name: str,
        rtsp_url: str,
        rois: list[ROI],
        vengine_client: "AsyncVEngineClient",
        ws_manager: "WSManager",
        app_settings: dict[str, str],
        agent: "AnalysisAgent | None" = None,
    ) -> None:
        super().__init__(
            source_id=source_id,
            source_name=source_name,
            rtsp_url=rtsp_url,
            rois=rois,
            vengine_client=vengine_client,
            ws_manager=ws_manager,
            app_settings=app_settings,
            agent=agent,
        )
        self._frame_count = 0

    async def process_frame(
        self,
        frame: np.ndarray,
        encoded: bytes,
        shape: tuple[int, int, int],
        roi_pixel_points: list[list[dict]],
    ) -> AnalysisResult:
        """Process one decoded frame and return a complete analysis result.
        处理一帧已解码图像并返回完整分析结果。

        ``frame`` is the BGR image from OpenCV, ``encoded`` is the original JPEG
        bytes, ``shape`` is ``(height, width, channels)``, and
        ``roi_pixel_points`` contains the configured source ROIs in pixel
        coordinates. Replace the demo rule below with model inference or custom
        image processing.
        ``frame`` 是 OpenCV BGR 图像，``encoded`` 是原始 JPEG 字节，
        ``shape`` 为 ``(高, 宽, 通道数)``，``roi_pixel_points`` 是当前视频源
        配置的 ROI 像素坐标。实际开发时把下面的示例规则替换为模型推理或自定义
        图像处理即可。
        """
        del encoded
        self._frame_count += 1
        now = datetime.now(timezone.utc).isoformat()
        height, width = shape[:2]
        annotated = frame.copy()

        # Example custom processing: measure mean brightness in the first ROI
        # (or the full frame when no ROI is configured). This keeps the template
        # runnable without external AI services while showing where custom logic
        # belongs.
        # 示例自定义处理：计算第一个 ROI 的平均亮度（没有 ROI 时使用整帧）。
        # 该模板无需外部 AI 服务即可运行，同时明确展示自定义逻辑的位置。
        roi_polygon = roi_pixel_points[0] if roi_pixel_points else []
        if roi_polygon:
            mask = np.zeros((height, width), dtype=np.uint8)
            points = np.array([[int(p["x"]), int(p["y"])] for p in roi_polygon], dtype=np.int32)
            cv2.fillPoly(mask, [points], 255)
            mean_brightness = float(cv2.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), mask=mask)[0])
            cv2.polylines(annotated, [points], isClosed=True, color=(0, 255, 255), thickness=2)
        else:
            mean_brightness = float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))

        label = "bright_area" if mean_brightness >= 200.0 else "normal_area"
        cv2.putText(
            annotated,
            f"template frame={self._frame_count} brightness={mean_brightness:.1f}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        message = {
            "timestamp": now,
            "source_name": self.source_name,
            "source_id": self.source_id,
            "level": "info",
            "message": f"Template scene processed frame {self._frame_count}: {label}",
        }
        event = {
            "timestamp": now,
            "source_name": self.source_name,
            "source_id": self.source_id,
            "event_type": label,
            "event_label": "模板事件" if label == "bright_area" else "模板心跳",
            "labels": [label],
            "confidence": min(1.0, mean_brightness / 255.0),
            "detection_count": 1,
            "frame_id": self._frame_count,
            "active_tracks": 0,
        }
        return AnalysisResult(
            detections=[
                {
                    "label": label,
                    "confidence": event["confidence"],
                    "x_min": 0,
                    "y_min": 0,
                    "x_max": width,
                    "y_max": height,
                }
            ],
            messages=[message],
            annotated_frame=annotated,
            extra={"event": event},
        )
