from __future__ import annotations

from unittest.mock import AsyncMock

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

    async def test_event_email_respects_cooldown(self, monkeypatch):
        ws = WSManager()
        ws.broadcast = AsyncMock()
        email_client = AsyncMock()

        async def fake_settings():
            return {
                "email_event_enabled": "true",
                "smoke_email_cooldown_seconds": "300",
                "email_from_address": "sender@example.com",
                "email_from_auth_code": "secret",
                "email_to_addresses": "to@example.com",
            }

        monkeypatch.setattr("backend.db.database.get_all_settings", fake_settings)
        agent = AnalysisAgent(ws_manager=ws, email_client=email_client, summary_interval=60.0)
        result = AnalysisResult(extra={"email_event": {"source_id": "s1", "source_name": "Cam1", "event_type": "smoke"}})

        await agent.submit("s1", "Cam1", result)
        await agent.submit("s1", "Cam1", result)

        email_client.send_event_email.assert_awaited_once()
