from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from backend.api.ws import WSManager
from backend.models.schemas import AnalysisMessage
from backend.processing.agent import AnalysisAgent
from backend.processing.base import AnalysisResult


class TestAnalysisAgent:
    async def test_submit_forwards_messages(self):
        ws = WSManager()
        ws.broadcast = AsyncMock()
        agent = AnalysisAgent(ws_manager=ws, summary_interval=60.0)
        msg = AnalysisMessage(
            timestamp="2024-01-01T00:00:00Z",
            source_name="cam1",
            source_id="s1",
            level="alert",
            message="Detected smoke",
        )

        await agent.submit("s1", "cam1", AnalysisResult(messages=[msg]))

        ws.broadcast.assert_awaited_once_with(msg)
        assert not agent._queue.empty()

    async def test_event_notification_is_delegated(self):
        ws = WSManager()
        ws.broadcast = AsyncMock()
        dispatcher = Mock()

        agent = AnalysisAgent(
            ws_manager=ws,
            notification_dispatcher=dispatcher,
            summary_interval=60.0,
        )
        result = AnalysisResult(extra={"email_event": {"source_id": "s1", "source_name": "Cam1", "event_type": "smoke"}})

        await agent.submit("s1", "Cam1", result)

        dispatcher.schedule_event.assert_called_once()
