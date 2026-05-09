"""Generic backend analysis agent with event-email hooks.
通用 backend 分析代理，支持事件邮件扩展。"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from backend.models.schemas import AnalysisMessage
from core.analysis_agent import BaseAnalysisAgent
from core.proto import email_pb2

if TYPE_CHECKING:
    from backend.api.ws import WSManager
    from core.email_client import AsyncEmailClient
    from core.base_processor import AnalysisResult


class AnalysisAgent(BaseAnalysisAgent):
    """Backend-specific generic analysis agent.
    backend 专用通用分析代理。"""

    def __init__(
        self,
        ws_manager: "WSManager",
        email_client: "AsyncEmailClient | None" = None,
        summary_interval: float = 10.0,
    ) -> None:
        super().__init__(broadcaster=ws_manager, summary_interval=summary_interval)
        self._email_client = email_client
        self._last_email_at: dict[str, float] = {}

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
        if self._email_client is None:
            return

        from backend.db.database import get_all_settings

        app_settings = await get_all_settings()
        if str(app_settings.get("email_event_enabled", "true")).lower() not in {"true", "1", "yes"}:
            return

        event = {**event, "source_id": event.get("source_id", source_id), "source_name": event.get("source_name", source_name)}
        if not self._should_send_event_email(app_settings, event):
            return

        attachments = self._build_event_attachments(event)
        try:
            await self._email_client.reconnect_from_settings(app_settings)
            await self._email_client.send_event_email(
                app_settings=app_settings,
                event=event,
                attachments=attachments,
            )
            self._mark_event_email_sent(event)
        except Exception as exc:  # pragma: no cover - side-effect logging
            logger.warning("Failed to send event email for {}: {}", source_id, exc)

    def _event_cooldown_key(self, event: dict[str, Any]) -> str:
        event_type = str(event.get("event_type") or event.get("label") or "event")
        return f"{event.get('source_id', '')}:{event_type}"

    def _should_send_event_email(
        self, app_settings: dict[str, str], event: dict[str, Any]
    ) -> bool:
        try:
            cooldown = max(0.0, float(app_settings.get("smoke_email_cooldown_seconds", "300")))
        except (TypeError, ValueError):
            cooldown = 300.0
        now_ts = datetime.now(timezone.utc).timestamp()
        last_ts = self._last_email_at.get(self._event_cooldown_key(event), 0.0)
        return now_ts - last_ts >= cooldown

    def _mark_event_email_sent(self, event: dict[str, Any]) -> None:
        self._last_email_at[self._event_cooldown_key(event)] = datetime.now(timezone.utc).timestamp()

    def _build_event_attachments(self, event: dict[str, Any]) -> list[email_pb2.Attachment]:
        image_base64 = str(event.get("image_base64") or "").strip()
        if not image_base64:
            return []
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except Exception:
            return []
        timestamp = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())[:19]
        safe_timestamp = timestamp.replace(":", "-")
        event_type = str(event.get("event_type") or "event").replace("/", "_")
        return [
            email_pb2.Attachment(
                filename=f"{event_type}-{safe_timestamp}.jpg",
                data=image_bytes,
                content_type="image/jpeg",
            )
        ]
