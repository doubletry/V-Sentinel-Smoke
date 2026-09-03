"""Tests for the WSManager class."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from loguru import logger

from backend.api.ws import WSManager
from backend.models.schemas import AnalysisMessage


class TestWSManager:
    def test_init(self):
        mgr = WSManager()
        assert len(mgr._connections) == 0

    async def test_connect_and_disconnect(self):
        mgr = WSManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        assert ws in mgr._connections
        ws.accept.assert_awaited_once()

        await mgr.disconnect(ws)
        assert ws not in mgr._connections

    async def test_disconnect_unknown(self):
        mgr = WSManager()
        ws = AsyncMock()
        # Should not raise even if ws was never connected
        await mgr.disconnect(ws)

    async def test_broadcast_single(self):
        mgr = WSManager()
        ws = AsyncMock()
        await mgr.connect(ws)

        msg = AnalysisMessage(
            timestamp="2024-01-01T00:00:00Z",
            source_name="cam",
            source_id="1",
            level="info",
            message="Test",
        )
        await mgr.broadcast(msg)
        ws.send_text.assert_awaited_once()
        payload = ws.send_text.call_args[0][0]
        assert "cam" in payload
        assert "Test" in payload

    async def test_broadcast_multiple_clients(self):
        mgr = WSManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        msg = AnalysisMessage(
            timestamp="t",
            source_name="c",
            source_id="1",
            level="info",
            message="m",
        )
        await mgr.broadcast(msg)
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    async def test_broadcast_image_uses_public_api_url_after_persist(self):
        persisted = AsyncMock(return_value="message-123")
        mgr = WSManager(persist_message=persisted)
        ws = AsyncMock()
        await mgr.connect(ws)

        msg = AnalysisMessage(
            timestamp="2026-04-03T00:00:00Z",
            source_name="cam",
            source_id="1",
            level="info",
            message="snapshot",
            image_url="2026-04-03/demo.jpg",
        )

        await mgr.broadcast(msg)

        persisted.assert_awaited_once()
        payload = ws.send_text.call_args[0][0]
        assert '"id":"message-123"' in payload
        assert "/api/messages/message-123/images/detected" in payload

    async def test_broadcast_removes_dead_connections(self):
        mgr = WSManager()
        ws_ok = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = RuntimeError("connection closed")

        await mgr.connect(ws_ok)
        await mgr.connect(ws_dead)
        assert len(mgr._connections) == 2

        msg = AnalysisMessage(
            timestamp="t",
            source_name="c",
            source_id="1",
            level="info",
            message="m",
        )
        await mgr.broadcast(msg)

        # Dead connection should have been removed
        assert ws_dead not in mgr._connections
        assert ws_ok in mgr._connections

    async def test_broadcast_persist_failure_is_logged_not_raised(self):
        from backend.models.schemas import AnalysisMessage

        async def failing_persist(message):
            raise RuntimeError("db down")

        mgr = WSManager(persist_message=failing_persist)
        ws = AsyncMock()
        await mgr.connect(ws)

        msg = AnalysisMessage(
            timestamp="t",
            source_name="c",
            source_id="s-1",
            level="info",
            message="m",
        )
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="ERROR")
        try:
            await mgr.broadcast(msg)  # 不得抛出
        finally:
            logger.remove(sink_id)

        ws.send_text.assert_awaited_once()  # 广播不受持久化失败影响
        assert any(
            "Failed to persist analysis message" in r["message"] and "s-1" in r["message"]
            for r in records
        )
        assert any(
            r["exception"] is not None
            for r in records
            if "Failed to persist analysis message" in r["message"]
        )


class TestWSEndpointAuth:
    def test_ws_invalid_token_close_is_logged(self):
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        from backend.main import app

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as excinfo:
                    with client.websocket_connect("/ws/messages?token=bad-token"):
                        pass
                assert excinfo.value.code == 4001
        finally:
            logger.remove(sink_id)

        assert any("invalid token" in r["message"] for r in records)

    def test_ws_missing_token_close_is_logged(self):
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        from backend.main import app

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect):
                    with client.websocket_connect("/ws/messages"):
                        pass
        finally:
            logger.remove(sink_id)

        assert any("missing token" in r["message"] for r in records)


class TestSendNotification:
    async def test_send_notification_reaches_all_clients_without_persist(self):
        import json

        persist = AsyncMock(return_value="msg-id")
        mgr = WSManager(persist_message=persist)
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.send_notification(
            {"type": "alert_notify", "message": "Detected smoke on Cam1"}
        )

        assert ws1.send_text.await_count == 1
        assert ws2.send_text.await_count == 1
        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["type"] == "alert_notify"
        assert payload["message"] == "Detected smoke on Cam1"
        persist.assert_not_awaited()
