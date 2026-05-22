from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from backend.db.database import (
    get_source,
    list_desired_analysis_sources,
    set_source_desired_analysis_enabled,
)
from backend.models.schemas import ProcessorStatus
from backend.processing.agent import AnalysisAgent
from backend.processing.base import BaseVideoProcessor
from backend.processing.registry import resolve_processor_class

if TYPE_CHECKING:
    from backend.vengine.client import AsyncVEngineClient
    from backend.api.ws import WSManager
    from backend.notifications.dispatcher import NotificationDispatcher


class ProcessorManager:
    """Manages the lifecycle of all running video processors.
    管理所有运行中视频处理器的生命周期。

    Processors are keyed by ``source_id``. Each is an asyncio Task.
    An ``AnalysisAgent`` aggregates results from all processors.
    处理器以 ``source_id`` 为键。每个都是一个 asyncio 任务。
    ``AnalysisAgent`` 汇总所有处理器的结果。
    """

    def __init__(
        self,
        vengine_client: "AsyncVEngineClient",
        ws_manager: "WSManager",
        app_settings: dict[str, str],
        notification_dispatcher: "NotificationDispatcher | None" = None,
    ) -> None:
        self._vengine = vengine_client
        self._ws_manager = ws_manager
        self._app_settings = app_settings
        self._processors: dict[str, BaseVideoProcessor] = {}
        self._lock = asyncio.Lock()
        self._agent = AnalysisAgent(
            ws_manager=ws_manager,
            notification_dispatcher=notification_dispatcher,
        )

    def update_app_settings(self, app_settings: dict[str, str]) -> None:
        """Replace the settings snapshot used for newly started processors.
        更新新启动处理器使用的设置快照。"""
        self._app_settings = dict(app_settings)

    async def start_agent(self) -> None:
        """Start the analysis agent (called once during app startup).
        启动分析代理（应用启动时调用一次）。"""
        await self._agent.start()

    async def stop_agent(self) -> None:
        """Stop the analysis agent (called during shutdown).
        停止分析代理（关闭时调用）。"""
        await self._agent.stop()

    async def start_processor(self, source_id: str) -> dict:
        """Start a processor for the given source_id.
        为指定的 source_id 启动处理器。

        Returns a status dict. Raises ``ValueError`` if source not found.
        返回状态字典。如果未找到视频源则抛出 ``ValueError``。
        """
        async with self._lock:
            if source_id in self._processors:
                proc = self._processors[source_id]
                if proc.status == "running":
                    return {
                        "status": "already_running",
                        "source_id": source_id,
                    }

            source = await get_source(source_id)
            if source is None:
                raise ValueError(f"Source not found: {source_id}")

            # Each service instance loads one globally selected plugin; every
            # source started in this process uses that active plugin.
            # 每个服务实例只加载一个全局选择的插件；本进程启动的所有视频源都使用该插件。
            plugin_name = str(self._app_settings.get("active_plugin_id") or "").strip()
            if not plugin_name:
                raise ValueError("Active processing plugin is not configured")
            processor_cls = resolve_processor_class(plugin_name)

            processor = processor_cls(
                source_id=source.id,
                source_name=source.name,
                rtsp_url=source.rtsp_url,
                source_remark=source.source_remark,
                push_result_stream=source.push_result_stream,
                source_alarm_confidence_threshold=source.alarm_confidence_threshold,
                rois=source.rois,
                vengine_client=self._vengine,
                ws_manager=self._ws_manager,
                app_settings=self._app_settings,
                agent=self._agent,
            )
            await processor.start()
            self._processors[source_id] = processor
            await set_source_desired_analysis_enabled(source_id, True)
            logger.info(
                "ProcessorManager: started {} processor for {}",
                plugin_name,
                source_id,
            )
            return {
                "status": "started",
                "source_id": source_id,
                "source_name": source.name,
                "scene_id": plugin_name,
            }

    async def stop_processor(self, source_id: str, *, persist_desired: bool = True) -> dict:
        """Stop the processor for the given source_id.
        停止指定 source_id 的处理器。"""
        async with self._lock:
            proc = self._processors.pop(source_id, None)
            if proc is None:
                return {"status": "not_running", "source_id": source_id}
            await proc.stop()
            if persist_desired:
                await set_source_desired_analysis_enabled(source_id, False)
            logger.info("ProcessorManager: stopped processor for {}", source_id)
            return {"status": "stopped", "source_id": source_id}

    async def restore_desired_processors(self, *, delay_seconds: float = 1.0) -> dict:
        """Gradually restart sources that were running before process shutdown."""
        sources = await list_desired_analysis_sources()
        restored = 0
        failed: list[dict[str, str]] = []
        for index, source in enumerate(sources):
            if index > 0 and delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            try:
                result = await self.start_processor(source.id)
                if result.get("status") in {"started", "already_running"}:
                    restored += 1
            except Exception as exc:
                logger.warning(
                    "ProcessorManager: failed to restore processor for {}: {}",
                    source.id,
                    exc,
                )
                failed.append({"source_id": source.id, "reason": str(exc)})
        return {"status": "restored", "restored": restored, "failed": failed}

    async def _stop_all_processors(self) -> dict:
        """Stop all currently running processors for application shutdown.
        在应用关闭时停止所有当前运行中的处理器。"""
        async with self._lock:
            source_ids = list(self._processors.keys())

        if not source_ids:
            return {"status": "not_running", "stopped": 0}

        stopped = 0
        failed: list[dict[str, str]] = []
        for source_id in source_ids:
            try:
                result = await self.stop_processor(source_id, persist_desired=False)
                if result["status"] == "stopped":
                    stopped += 1
            except Exception as exc:
                failed.append({"source_id": source_id, "reason": str(exc)})

        return {
            "status": "stopped_all" if not failed else "partial",
            "stopped": stopped,
            "failed": failed,
        }

    async def stop_all(self) -> None:
        """Stop all running processors (called during shutdown).
        停止所有运行中的处理器（关闭时调用）。"""
        await self._stop_all_processors()
        logger.info("ProcessorManager: all processors stopped")

    def get_all_status(self) -> list[ProcessorStatus]:
        """Return status of all currently tracked processors.
        返回所有当前跟踪的处理器状态。"""
        statuses: list[ProcessorStatus] = []
        for source_id, proc in self._processors.items():
            statuses.append(
                ProcessorStatus(
                    source_id=source_id,
                    source_name=proc.source_name,
                    rtsp_url=proc.rtsp_url,
                    status=proc.status,
                    started_at=proc.started_at,
                )
            )
        return statuses
