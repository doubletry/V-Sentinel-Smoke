from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from backend.db.database import (
    build_analysis_message_image_url,
    create_notification_provider,
    get_analysis_message_for_notification,
    get_false_positive_dir,
    get_message_image_dir,
    list_analysis_messages,
    save_analysis_message,
    update_settings,
)
from backend.models.schemas import NotificationProviderCreate


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

    async def test_list_persisted_messages_no_twenty_page_cap(self, async_client: AsyncClient):
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
        assert data["page"] == 21
        assert data["page_size"] == 20
        assert data["total_pages"] == 21
        assert data["total"] == 405
        assert len(data["items"]) == 5

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

        filtered = await async_client.get("/api/messages", params={"false_positive_filter": "only"})
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

        filtered = await async_client.get("/api/messages", params={"false_positive_filter": "only"})
        assert filtered.status_code == 200
        filtered_data = filtered.json()
        assert filtered_data["items"] == []

    async def test_list_messages_false_positive_filter_exclude(self, async_client: AsyncClient):
        normal_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "normal",
            }
        )
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "fp",
                "false_positive": True,
            }
        )

        excluded = await async_client.get("/api/messages", params={"false_positive_filter": "exclude"})
        assert excluded.status_code == 200
        excluded_data = excluded.json()
        assert len(excluded_data["items"]) == 1
        assert excluded_data["items"][0]["id"] == normal_id
        assert excluded_data["items"][0]["false_positive"] is False

        all_msgs = await async_client.get("/api/messages", params={"false_positive_filter": "all"})
        assert all_msgs.status_code == 200
        assert all_msgs.json()["total"] == 2

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

    async def test_resend_notification_endpoint_uses_enabled_instances_not_legacy_settings(
        self,
        async_client: AsyncClient,
    ):
        await update_settings(
            {
                "email_smtp_host": "smtp.legacy.example.com",
                "email_from_address": "legacy@example.com",
                "email_to_addresses": "legacy-ops@example.com",
                "email_event_enabled": "true",
            }
        )
        provider = await create_notification_provider(
            NotificationProviderCreate(
                name="Ops Webhook",
                type="webhook",
                enabled=True,
                config={"url": "https://example.com/hooks/ops", "method": "POST"},
            )
        )
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "persisted alert",
            }
        )

        from backend.main import notification_dispatcher

        with patch.object(
            notification_dispatcher,
            "_send_provider",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": provider.id}),
        ) as send_provider:
            resp = await async_client.post(f"/api/messages/{message_id}/resend-notification")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sent"
        assert data["results"] == [{"status": "SUCCESS", "message": provider.id}]
        send_provider.assert_awaited_once()
        provider_type, config, payload = send_provider.await_args.args
        assert provider_type == "webhook"
        assert config["url"] == "https://example.com/hooks/ops"
        assert payload.context["message"] == "persisted alert"

    async def test_resend_notification_endpoint_does_not_fallback_to_legacy_settings_email(
        self,
        async_client: AsyncClient,
    ):
        await update_settings(
            {
                "email_smtp_host": "smtp.legacy.example.com",
                "email_from_address": "legacy@example.com",
                "email_to_addresses": "legacy-ops@example.com",
                "email_event_enabled": "true",
            }
        )
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "persisted alert",
            }
        )

        from backend.main import notification_dispatcher

        with patch.object(
            notification_dispatcher,
            "_send_provider",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": "legacy"}),
        ) as send_provider:
            resp = await async_client.post(f"/api/messages/{message_id}/resend-notification")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_enabled_provider"
        assert data["results"] == []
        send_provider.assert_not_awaited()

    async def test_resend_notification_endpoint_returns_404(self, async_client: AsyncClient):
        resp = await async_client.post("/api/messages/missing/resend-notification")

        assert resp.status_code == 404


class TestMessageDateFilter:
    async def test_list_filters_by_start_and_end_date(self, async_client: AsyncClient):
        now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        days = [now - timedelta(days=2), now - timedelta(days=1), now]
        labels = [day.date().isoformat() for day in days]
        for ts in days:
            await save_analysis_message(
                {
                    "timestamp": ts.isoformat(),
                    "source_name": "Cam1",
                    "source_id": "s1",
                    "level": "info",
                    "message": f"msg-{ts.date()}",
                }
            )

        resp = await async_client.get(
            "/api/messages",
            params={"start_date": labels[1], "end_date": labels[1]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["message"] == f"msg-{labels[1]}"

        resp = await async_client.get(
            "/api/messages",
            params={"start_date": labels[1]},
        )
        assert resp.status_code == 200
        data = resp.json()
        messages = {item["message"] for item in data["items"]}
        assert messages == {f"msg-{labels[1]}", f"msg-{labels[2]}"}

        resp = await async_client.get(
            "/api/messages",
            params={"end_date": labels[1]},
        )
        assert resp.status_code == 200
        data = resp.json()
        messages = {item["message"] for item in data["items"]}
        assert messages == {f"msg-{labels[0]}", f"msg-{labels[1]}"}

    async def test_list_ignores_invalid_dates(self, async_client: AsyncClient):
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "info",
                "message": "kept",
            }
        )
        resp = await async_client.get(
            "/api/messages",
            params={"start_date": "not-a-date", "end_date": "1234"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1


class TestMessageDeletion:
    async def test_delete_message_removes_row_and_thumbnails(self, async_client: AsyncClient):
        thumbnails_root = get_message_image_dir()
        before = set(thumbnails_root.rglob("*.jpg"))

        original = base64.b64encode(b"original-bytes").decode("ascii")
        detected = base64.b64encode(b"detected-bytes").decode("ascii")
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "to-delete",
                "original_image_base64": original,
                "detected_image_base64": detected,
            }
        )

        created = set(thumbnails_root.rglob("*.jpg")) - before
        assert len(created) == 2

        resp = await async_client.delete(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] is True
        assert body["id"] == message_id
        assert body["false_positive_was"] is False

        rows = await list_analysis_messages(limit=10, source_id="s1")
        assert rows["items"] == []
        # Files created by this test should be gone; pre-existing files (from
        # other tests reusing the shared /tmp directory) are not affected.
        assert all(not path.exists() for path in created)

    async def test_delete_message_preserves_false_positive_exports(self, async_client: AsyncClient):
        thumbnails_root = get_message_image_dir()
        fp_root = get_false_positive_dir()
        thumbnails_before = set(thumbnails_root.rglob("*.jpg"))
        fp_before = set(fp_root.rglob("*.jpg")) if fp_root.exists() else set()

        original = base64.b64encode(b"original-bytes").decode("ascii")
        detected = base64.b64encode(b"detected-bytes").decode("ascii")
        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s2",
                "level": "alert",
                "message": "fp-then-delete",
                "original_image_base64": original,
                "detected_image_base64": detected,
            }
        )

        resp = await async_client.post(f"/api/messages/{message_id}/false-positive")
        assert resp.status_code == 200
        exported_files = resp.json()["exported_files"]
        assert exported_files
        for path in exported_files:
            assert "false_positives" in path

        new_thumbnails = set(thumbnails_root.rglob("*.jpg")) - thumbnails_before
        new_fp = set(fp_root.rglob("*.jpg")) - fp_before
        assert len(new_thumbnails) == 2
        assert len(new_fp) == 2

        resp = await async_client.delete(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        assert resp.json()["false_positive_was"] is True

        assert all(not path.exists() for path in new_thumbnails)
        assert all(path.exists() for path in new_fp)


    async def test_delete_message_returns_404_for_missing(self, async_client: AsyncClient):
        resp = await async_client.delete("/api/messages/missing")
        assert resp.status_code == 404

    async def test_batch_delete_messages(self, async_client: AsyncClient):
        ids = []
        for index in range(3):
            ids.append(
                await save_analysis_message(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source_name": "Cam1",
                        "source_id": "s1",
                        "level": "info",
                        "message": f"bulk-{index}",
                    }
                )
            )

        resp = await async_client.post(
            "/api/messages/batch-delete",
            json={"ids": [ids[0], ids[1], "missing"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["deleted_ids"]) == {ids[0], ids[1]}
        assert body["missing_ids"] == ["missing"]

        rows = await list_analysis_messages(limit=10)
        assert [item["id"] for item in rows["items"]] == [ids[2]]

    async def test_batch_delete_rejects_invalid_payload(self, async_client: AsyncClient):
        resp = await async_client.post("/api/messages/batch-delete", json={"ids": "nope"})
        assert resp.status_code == 400

        resp = await async_client.post("/api/messages/batch-delete", json={"ids": [""]})
        assert resp.status_code == 400

        resp = await async_client.post(
            "/api/messages/batch-delete",
            json={"ids": [f"id-{i}" for i in range(501)]},
        )
        assert resp.status_code == 400

    async def test_delete_message_requires_permission(self, async_client: AsyncClient):
        from backend.auth.security import create_access_token

        message_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "info",
                "message": "guarded",
            }
        )

        user_token = create_access_token(username="user1", role="user")["access_token"]
        resp = await async_client.delete(
            f"/api/messages/{message_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

        operator_token = create_access_token(username="op1", role="operator")["access_token"]
        resp = await async_client.delete(
            f"/api/messages/{message_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

