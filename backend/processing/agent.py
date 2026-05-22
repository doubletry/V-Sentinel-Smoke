"""Generic backend analysis agent with notification hooks.
通用 backend 分析代理，支持通知扩展。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from backend.models.schemas import AnalysisMessage
from core.analysis_agent import BaseAnalysisAgent

if TYPE_CHECKING:
    from backend.api.ws import WSManager
    from backend.notifications.dispatcher import NotificationDispatcher
    from core.base_processor import AnalysisResult


class AnalysisAgent(BaseAnalysisAgent):
    """Backend-specific generic analysis agent.
    backend 专用通用分析代理。"""

    def __init__(
        self,
        ws_manager: "WSManager",
        notification_dispatcher: "NotificationDispatcher | None" = None,
        summary_interval: float = 10.0,
    ) -> None:
        super().__init__(broadcaster=ws_manager, summary_interval=summary_interval)
        self._notification_dispatcher = notification_dispatcher

    def normalize_message(self, message: Any) -> AnalysisMessage:
        if isinstance(message, AnalysisMessage):
            return message
        if isinstance(message, dict):
            return AnalysisMessage(**message)
        raise TypeError(f"Unsupported message type: {type(message)!r}")

    @classmethod
    def _build_summary(cls, items: list[tuple[str, str, "AnalysisResult"]]) -> None:
        """Suppress generic periodic summaries by default.
        默认不发送通用周期汇总，避免场景无关噪音。"""
        del items
        return None

    async def handle_result_extras(
        self,
        source_id: str,
        source_name: str,
        result: "AnalysisResult",
    ) -> None:
        event = result.extra.get("email_event") or result.extra.get("event")
        if not isinstance(event, dict):
            return
        if self._notification_dispatcher is None:
            return

        event = {**event, "source_id": event.get("source_id", source_id), "source_name": event.get("source_name", source_name)}
        try:
            self._notification_dispatcher.schedule_event(event)
        except Exception as exc:  # pragma: no cover - side-effect logging
            logger.warning("Failed to send event notification for {}: {}", source_id, exc)
