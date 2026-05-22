from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from backend.db.database import (
    build_analysis_message_image_url,
    get_analysis_message_for_notification,
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

    async def test_save_message_persists_original_and_detected_images(self, async_client: AsyncClient):
        original = base64.b64encode(b"original-bytes").decode("ascii")
        detected = base64.b64encode(b"detected-bytes").decode("ascii")
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "hello",
                "original_image_base64": original,
                "detected_image_base64": detected,
            }
        )

        rows = await list_analysis_messages(limit=10)
        assert rows["items"][0]["original_image_url"].startswith("/api/messages/")
        assert rows["items"][0]["detected_image_url"].startswith("/api/messages/")

        original_resp = await async_client.get(rows["items"][0]["original_image_url"])
        detected_resp = await async_client.get(rows["items"][0]["detected_image_url"])
        assert original_resp.status_code == 200
        assert detected_resp.status_code == 200
        assert original_resp.content == b"original-bytes"
        assert detected_resp.content == b"detected-bytes"

    async def test_get_message_for_notification_includes_images(self, init_db):
        original = base64.b64encode(b"original-bytes").decode("ascii")
        detected = base64.b64encode(b"detected-bytes").decode("ascii")
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "door open",
                "original_image_base64": original,
                "detected_image_base64": detected,
            }
        )

        message = await get_analysis_message_for_notification(message_id)

        assert message is not None
        assert message["message"] == "door open"
        assert message["event_label"] == "door open"
        assert message["original_image_base64"] == original
        assert message["detected_image_base64"] == detected

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
        assert data["items"][0]["false_positive"] is False

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

    async def test_list_persisted_messages_caps_to_latest_twenty_pages(self, async_client: AsyncClient):
        base_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
        for index in range(405):
            await save_analysis_message(
                {
                    "timestamp": (base_timestamp + timedelta(seconds=index)).isoformat(),
                    "source_name": "Cam1",
                    "source_id": "s1",
                    "level": "info",
                    "message": f"persisted-{index}",
                    "image_base64": None,
                }
            )

        resp = await async_client.get("/api/messages", params={"page": 21, "page_size": 20})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 20
        assert data["page_size"] == 20
        assert data["total_pages"] == 20
        assert data["total"] == 400
        assert len(data["items"]) == 20

    async def test_mark_false_positive_exports_images_and_can_filter(self, async_client: AsyncClient, _tmp_db: str):
        original = base64.b64encode(b"original-bytes").decode("ascii")
        detected = base64.b64encode(b"detected-bytes").decode("ascii")
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "persisted",
                "original_image_base64": original,
                "detected_image_base64": detected,
            }
        )

        resp = await async_client.post(f"/api/messages/{message_id}/false-positive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["false_positive"] is True
        assert any(path.endswith(".jpg") and not path.endswith("_detected.jpg") for path in data["exported_files"])
        assert any(path.endswith("_detected.jpg") for path in data["exported_files"])

        filtered = await async_client.get("/api/messages", params={"false_positive_only": "true"})
        assert filtered.status_code == 200
        filtered_data = filtered.json()
        assert len(filtered_data["items"]) == 1
        assert filtered_data["items"][0]["id"] == message_id
        assert filtered_data["items"][0]["false_positive"] is True

    async def test_unmark_false_positive_clears_filter_match(self, async_client: AsyncClient):
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "persisted",
                "false_positive": True,
            }
        )

        resp = await async_client.delete(f"/api/messages/{message_id}/false-positive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["false_positive"] is False

        filtered = await async_client.get("/api/messages", params={"false_positive_only": "true"})
        assert filtered.status_code == 200
        filtered_data = filtered.json()
        assert filtered_data["items"] == []

    async def test_resend_notification_endpoint_forwards_persisted_message(self, async_client: AsyncClient):
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "persisted alert",
            }
        )

        with patch(
            "backend.main.notification_dispatcher.send_event",
            new=AsyncMock(return_value=[{"status": "SUCCESS", "message": "sent"}]),
        ) as send_event:
            resp = await async_client.post(f"/api/messages/{message_id}/resend-notification")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sent"
        send_event.assert_awaited_once()
        event = send_event.await_args.args[0]
        assert event["message"] == "persisted alert"
        assert send_event.await_args.kwargs["force"] is True

    async def test_resend_notification_endpoint_reports_failed_provider_result(self, async_client: AsyncClient):
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "persisted alert",
            }
        )

        with patch(
            "backend.main.notification_dispatcher.send_event",
            new=AsyncMock(return_value=[{"status": "ERROR", "message": "SMTP host is required"}]),
        ):
            resp = await async_client.post(f"/api/messages/{message_id}/resend-notification")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["results"][0]["message"] == "SMTP host is required"

    async def test_resend_notification_endpoint_returns_404(self, async_client: AsyncClient):
        resp = await async_client.post("/api/messages/missing/resend-notification")

        assert resp.status_code == 404
