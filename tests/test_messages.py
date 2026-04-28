from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from backend.db.database import (
    build_analysis_message_image_url,
    list_analysis_messages,
    save_analysis_message,
    update_settings,
)


class TestMessagePersistence:
    async def test_save_and_list_messages(self, init_db):
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "info",
                "message": "hello",
                "image_base64": None,
            }
        )

        rows = await list_analysis_messages(limit=10)
        assert len(rows["items"]) == 1
        assert rows["items"][0]["message"] == "hello"

    async def test_save_message_persists_image_to_filesystem(self, async_client: AsyncClient):
        encoded = base64.b64encode(b"jpeg-bytes").decode("ascii")
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "info",
                "message": "hello",
                "image_base64": encoded,
            }
        )

        rows = await list_analysis_messages(limit=10)
        assert rows["items"][0]["image_url"].startswith("/api/messages/")
        assert rows["items"][0]["image_base64"] is None

        resp = await async_client.get(rows["items"][0]["image_url"])
        assert resp.status_code == 200
        assert resp.content == b"jpeg-bytes"

    async def test_retention_prunes_old_messages(self, init_db):
        await update_settings({"message_retention_days": "1"})
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        await save_analysis_message(
            {
                "timestamp": old_timestamp,
                "source_name": "OldCam",
                "source_id": "old",
                "level": "info",
                "message": "old",
                "image_base64": None,
            }
        )
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "NewCam",
                "source_id": "new",
                "level": "info",
                "message": "new",
                "image_base64": None,
            }
        )

        rows = await list_analysis_messages(limit=10)
        assert [row["message"] for row in rows["items"]] == ["new"]


class TestMessagesAPI:
    async def test_message_image_endpoint_uses_message_id_url(self, async_client: AsyncClient):
        encoded = base64.b64encode(b"jpeg-bytes").decode("ascii")
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "info",
                "message": "persisted",
                "image_base64": encoded,
            }
        )

        resp = await async_client.get(build_analysis_message_image_url(message_id))
        assert resp.status_code == 200
        assert resp.content == b"jpeg-bytes"

    async def test_list_persisted_messages(self, async_client: AsyncClient):
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "warning",
                "message": "persisted",
                "image_base64": None,
            }
        )

        resp = await async_client.get("/api/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["message"] == "persisted"
        assert data["items"][0]["level"] == "warning"
        assert data["total"] == 1
        assert "image_url" in data["items"][0]

    async def test_list_persisted_messages_paginates(self, async_client: AsyncClient):
        for index in range(25):
            await save_analysis_message(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_name": "Cam1",
                    "source_id": "s1",
                    "level": "info",
                    "message": f"persisted-{index}",
                    "image_base64": None,
                }
            )

        resp = await async_client.get("/api/messages", params={"page": 2, "page_size": 20})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 20
        assert data["total"] == 25
        assert len(data["items"]) == 5

    async def test_processor_plugins_endpoint(self, async_client: AsyncClient):
        resp = await async_client.get("/api/processor/plugins")
        assert resp.status_code == 200
        data = resp.json()
        values = {item["value"] for item in data}
        assert {"smoke", "example"} <= values

