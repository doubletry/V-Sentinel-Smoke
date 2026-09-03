"""Backend-specific video processor — extends core.BaseVideoProcessor.
后台专用视频处理器 — 扩展 core.BaseVideoProcessor。

This module re-exports ``AnalysisResult`` from the core package and provides
``BaseVideoProcessor`` which adds backend-only integration:
  * ``WSManager`` for WebSocket broadcast
  * ``AnalysisAgent`` for cross-camera aggregation
  * ``started_at`` timestamp tracking

All shared processing logic (lifecycle, frame reading, RTSP push, drawing,
ROI normalisation) lives in ``core.base_processor`` — **the single source
of truth**.  Updating core automatically updates the backend.
所有共享的处理逻辑（生命周期、帧读取、RTSP 推流、绘制、ROI 归一化）
位于 ``core.base_processor`` — **唯一的代码来源**。
更新 core 即自动更新后台。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

# Re-export core classes so existing imports from backend.processing.base
# continue to work without changes.
# 重导出 core 类，使现有的 backend.processing.base 导入无需修改。
from core.base_processor import AnalysisResult  # noqa: F401
from core.base_processor import BaseVideoProcessor as _CoreBaseVideoProcessor

from backend.models.schemas import AnalysisMessage, ROI

if TYPE_CHECKING:
    from backend.vengine.client import AsyncVEngineClient
    from backend.api.ws import WSManager
    from backend.processing.agent import AnalysisAgent


class BaseVideoProcessor(_CoreBaseVideoProcessor):
    """Backend-aware video processor that extends the core base class.
    扩展 core 基类的后台感知视频处理器。

    Adds:
    * ``ws_manager``  — WebSocket broadcast for real-time messages
    * ``agent``       — Cross-camera aggregation agent
    * ``started_at``  — ISO timestamp when processing started
    * ``_run_loop``   — Overridden to route results through agent/broadcast

    All other behaviour (frame reading, RTSP push, drawing, ROI handling)
    is inherited from ``core.base_processor.BaseVideoProcessor``.
    所有其他行为（帧读取、RTSP 推流、绘制、ROI 处理）
    继承自 ``core.base_processor.BaseVideoProcessor``。
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
        source_remark: str = "",
        push_result_stream: bool = True,
        source_alarm_confidence_threshold: float | None = None,
    ) -> None:
        # Convert Pydantic ROI objects to core ROI dataclasses
        # 将 Pydantic ROI 对象转换为 core ROI 数据类
        from core.base_processor import ROI as CoreROI, ROIPoint as CoreROIPoint
        core_rois = [
            CoreROI(
                id=r.id,
                type=r.type,
                points=[CoreROIPoint(x=p.x, y=p.y) for p in r.points],
                tag=r.tag,
            )
            for r in rois
        ]
        super().__init__(
            source_id=source_id,
            source_name=source_name,
            rtsp_url=rtsp_url,
            source_remark=source_remark,
            push_result_stream=push_result_stream,
            source_alarm_confidence_threshold=source_alarm_confidence_threshold,
            rois=core_rois,
            vengine_client=vengine_client,
            app_settings=app_settings,
        )
        self.ws_manager = ws_manager
        self.agent = agent
        self.started_at: str | None = None
        self._dispatch_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the processing task with timestamp tracking.
        启动处理任务并记录时间戳。"""
        if self._task is not None and not self._task.done():
            logger.warning("Processor for {} is already running", self.source_id)
            return
        self.started_at = datetime.now(timezone.utc).isoformat()
        await super().start()

    async def stop(self) -> None:
        """Cancel pending dispatch tasks, then stop the core pipeline.
        先取消挂起的分发任务，再停止核心流水线。"""
        if self._dispatch_tasks:
            for task in list(self._dispatch_tasks):
                task.cancel()
            try:
                await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
            except Exception:
                pass
            self._dispatch_tasks.clear()
        await super().stop()

    # ── Result dispatch / 结果分发 ────────────────────────────────────────────

    async def _handle_result(self, frame, result: AnalysisResult) -> None:
        """Enqueue display first so the real-time push never waits for slow
        steps (e.g. VL confirm), then dispatch messages on a detached task.
        先入队推流，保证实时画面不等待慢速步骤（如 VL 复判）；
        消息分发在脱离帧槽位的后台任务中完成。"""
        await super()._handle_result(frame, result)
        task = asyncio.create_task(
            self._dispatch_result(result), name=f"dispatch-{self.source_id}"
        )
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)

    async def _dispatch_result(self, result: AnalysisResult) -> None:
        """Send the immediate alert, finalize (await slow verdicts), then dispatch.
        先发即时告警横幅，再完成场景钩子（等待慢速结论），最后分发消息。"""
        try:
            await self._send_immediate_alert(result)
            await self.finalize_result(result)
            if self.agent is not None:
                await self.agent.submit(
                    self.source_id, self.source_name, result
                )
            else:
                for msg in result.messages:
                    if not isinstance(msg, AnalysisMessage):
                        msg = AnalysisMessage(
                            id=msg.get("id"),
                            timestamp=msg.get(
                                "timestamp", datetime.now(timezone.utc).isoformat()
                            ),
                            source_name=msg.get("source_name", self.source_name),
                            source_id=msg.get("source_id", self.source_id),
                            scene_id=msg.get("scene_id", "smoke"),
                            level=msg.get("level", "info"),
                            message=msg.get("message", ""),
                            image_url=msg.get("image_url"),
                            image_base64=msg.get("image_base64"),
                            original_image_url=msg.get("original_image_url"),
                            original_image_base64=msg.get("original_image_base64"),
                            detected_image_url=msg.get("detected_image_url"),
                            detected_image_base64=msg.get("detected_image_base64"),
                            false_positive=bool(msg.get("false_positive", False)),
                        )
                    await self.ws_manager.broadcast(msg)
        except Exception:
            logger.opt(exception=True).error(
                "Failed to dispatch frame result: source={}", self.source_id
            )

    async def _send_immediate_alert(self, result: AnalysisResult) -> None:
        """Send the immediate top-banner alert (no VL wait, no DB persist).
        发送即时顶部告警横幅（不等 VL 结论、不入库）。"""
        pending = result.extra.get("pending_alert")
        if not isinstance(pending, dict):
            return
        text = str(pending.get("alert_text") or "").strip()
        if not text or self.ws_manager is None:
            return
        await self.ws_manager.send_notification(
            {
                "type": "alert_notify",
                "timestamp": pending.get("timestamp"),
                "source_id": self.source_id,
                "source_name": self.source_name,
                "scene_id": str(pending.get("scene_id") or ""),
                "message": text,
            }
        )

    @property
    def push_active(self) -> bool:
        """Return whether the ffmpeg push process is currently alive."""
        return super().push_active

    def set_push_result_stream(self, enabled: bool) -> None:
        """Enable or disable push at runtime without restarting analysis."""
        super().set_push_result_stream(enabled)
