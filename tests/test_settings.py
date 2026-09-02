"""Tests for app_settings DB operations and Settings API."""
from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from loguru import logger

from backend.config import DEFAULT_APP_SETTINGS
from backend.db.database import (
    create_source,
    get_all_settings,
    get_setting,
    get_source,
    rewrite_source_rtsp_urls,
    update_settings,
)
from backend.models.schemas import VideoSourceCreate
from core.notification_client import NotificationPayload


class TestSettingsDB:
    async def test_defaults_seeded(self, init_db):
        """init_db should seed default settings."""
        all_settings = await get_all_settings()
        assert all_settings["ui_language"] == "zh-CN"
        assert all_settings["timezone"] == "Asia/Shanghai"
        assert all_settings["site_title"] == "V-Sentinel"
        assert all_settings["favicon_url"] == "/favicon.ico"
        assert all_settings["active_plugin_id"] == "smoke"
        assert all_settings["vengine_host"] == "localhost"
        assert all_settings["detection_port"] == "50051"
        assert all_settings["ocr_port"] == "50054"
        assert all_settings["email_from_address"] == ""
        assert all_settings["email_to_addresses"] == ""
        assert all_settings["email_smtp_port"] == "587"
        assert all_settings["email_event_enabled"] == "true"
        assert all_settings["smoke_temporal_confirm_frames"] == "3"
        assert all_settings["fire_door_classification_model_name"] == "fire-door-classification"
        assert all_settings["fire_door_alarm_labels"] == "open"
        assert "email_event_body_template" in all_settings
        assert "{event_label}" in all_settings["email_event_body_template"]
        assert all_settings["message_retention_days"] == "7"
        assert all_settings["mediamtx_username"] == ""
        assert all_settings["mediamtx_password"] == ""
        assert all_settings["smoke_vl_confirm_enabled"] == "false"
        assert all_settings["smoke_vl_confirm_image_source"] == "original"
        assert all_settings["smoke_vl_confirm_image_crop"] == "roi"
        assert all_settings["fire_door_vl_confirm_enabled"] == "false"
        assert all_settings["fire_door_vl_confirm_image_source"] == "original"
        assert all_settings["fire_door_vl_confirm_image_crop"] == "roi"
        assert "vl_confirm_enabled" not in all_settings

    async def test_get_setting(self, init_db):
        val = await get_setting("vengine_host")
        assert val == "localhost"

    async def test_get_setting_missing(self, init_db):
        val = await get_setting("nonexistent_key")
        assert val is None

    async def test_update_settings(self, init_db):
        result = await update_settings({"vengine_host": "192.168.1.100", "detection_port": "9001"})
        assert result["vengine_host"] == "192.168.1.100"
        assert result["detection_port"] == "9001"
        # Other defaults should still be there
        assert result["ocr_port"] == "50054"

    async def test_update_new_key(self, init_db):
        result = await update_settings({"custom_key": "custom_value"})
        assert result["custom_key"] == "custom_value"

    async def test_idempotent_init(self, init_db):
        """Calling init_db again should not duplicate settings."""
        from backend.db.database import init_db as re_init
        await re_init()
        all_settings = await get_all_settings()
        # Should still only have the default keys (no duplicates)
        assert all_settings["vengine_host"] == "localhost"

    async def test_legacy_vl_confirm_enabled_is_migrated(self, init_db):
        """Legacy global vl_confirm_enabled migrates into per-scene keys, then disappears."""
        await update_settings({"vl_confirm_enabled": "true"})

        from backend.db.database import init_db as re_init
        await re_init()

        all_settings = await get_all_settings()
        assert all_settings["smoke_vl_confirm_enabled"] == "true"
        assert all_settings["fire_door_vl_confirm_enabled"] == "true"
        assert "vl_confirm_enabled" not in all_settings

    async def test_rewrite_source_rtsp_urls(self, init_db):
        source = await create_source(
            VideoSourceCreate(name="Cam1", rtsp_url="rtsp://localhost:8554/cam1")
        )

        updated = await rewrite_source_rtsp_urls(
            old_rtsp_base_address="rtsp://localhost:8554",
            new_rtsp_base_address="rtsp://gateway.example.com:9554/live",
            new_rtsp_username="stream-user",
            new_rtsp_password="stream-pass",
        )

        assert updated == 1
        rewritten = await get_source(source.id)
        assert rewritten is not None
        assert (
            rewritten.rtsp_url
            == "rtsp://stream-user:stream-pass@gateway.example.com:9554/live/cam1"
        )


class TestSettingsAPI:
    async def test_get_settings(self, async_client: AsyncClient):
        resp = await async_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vengine_host"] == "localhost"
        assert data["detection_port"] == "50051"

    async def test_update_settings(self, async_client: AsyncClient):
        resp = await async_client.put(
            "/api/settings",
            json={
                "vengine_host": "10.0.0.1",
                "timezone": "UTC",
                "detection_port": "9999",
                "site_title": "My Sentinel",
                "active_plugin_id": "template",
                "email_from_address": "sender@example.com",
                "email_smtp_password": "secret",
                "email_to_addresses": "to1@example.com,to2@example.com",
                "email_cc_addresses": "cc@example.com",
                "email_smtp_host": "smtp.example.com",
                "email_smtp_port": "587",
                "email_smtp_use_tls": "true",
                "email_event_enabled": "true",
                "email_event_subject_template": "Alert {event_label}",
                "smoke_temporal_confirm_frames": "5",
                "fire_door_classification_confidence": "0.75",
                "fire_door_alarm_labels": "open,opened",
                "message_retention_days": "14",
                "mediamtx_rtsp_addr": "rtsp://stream.example.com:8554/live",
                "mediamtx_webrtc_addr": "https://stream.example.com:8889/whep",
                "mediamtx_username": "shared-user",
                "mediamtx_password": "shared-pass",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["vengine_host"] == "10.0.0.1"
        assert data["timezone"] == "UTC"
        assert data["detection_port"] == "9999"
        assert data["site_title"] == "My Sentinel"
        assert data["active_plugin_id"] == "template"
        assert data["email_from_address"] == "sender@example.com"
        assert data["email_smtp_password"] == "secret"
        assert data["email_to_addresses"] == "to1@example.com,to2@example.com"
        assert data["email_cc_addresses"] == "cc@example.com"
        assert data["email_smtp_host"] == "smtp.example.com"
        assert data["email_smtp_port"] == "587"
        assert data["email_smtp_use_tls"] == "true"
        assert data["email_event_enabled"] == "true"
        assert data["email_event_subject_template"] == "Alert {event_label}"
        assert data["smoke_temporal_confirm_frames"] == "5"
        assert data["fire_door_classification_confidence"] == "0.75"
        assert data["fire_door_alarm_labels"] == "open,opened"
        assert data["message_retention_days"] == "14"
        assert data["mediamtx_rtsp_addr"] == "rtsp://stream.example.com:8554/live"
        assert data["mediamtx_webrtc_addr"] == "https://stream.example.com:8889/whep"
        assert data["mediamtx_username"] == "shared-user"
        assert data["mediamtx_password"] == "shared-pass"

    async def test_update_empty(self, async_client: AsyncClient):
        """Empty update should return current settings."""
        resp = await async_client.put("/api/settings", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "vengine_host" in data

    async def test_email_test_endpoint(self, async_client: AsyncClient):
        captured_config = {}

        async def fake_send(provider, payload):
            assert isinstance(payload, NotificationPayload)
            captured_config.update(provider.config)
            return {"status": "SUCCESS", "message": "ok"}

        with patch(
            "core.notification_client.SmtpNotificationProvider.send",
            new=fake_send,
        ):
            resp = await async_client.post(
                "/api/settings/email/test",
                json={
                    "email_smtp_host": "smtp.example.com",
                    "email_smtp_port": "587",
                    "email_from_address": "sender@example.com",
                    "email_smtp_password": "test-password-do-not-use",
                    "email_to_addresses": "to@example.com",
                    "email_cc_addresses": "cc@example.com",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert captured_config["smtp_username"] == "sender@example.com"
        assert captured_config["smtp_password"] == "test-password-do-not-use"
        assert captured_config["use_tls"] is True

    async def test_vl_test_endpoint_ok(self, async_client: AsyncClient):
        with patch(
            "core.vl_confirm.VLConfirmClient.complete",
            new=AsyncMock(return_value='{"connected": true}'),
        ) as mock_complete:
            resp = await async_client.post(
                "/api/settings/vl/test",
                json={
                    "scene_id": "smoke",
                    "vl_confirm_base_url": "http://vl.example.com/v1",
                    "vl_confirm_api_key": "test-key",
                    "vl_confirm_model": "/models/test-vl",
                    "vl_confirm_timeout": "30",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model"] == "/models/test-vl"
        assert data["response"] == '{"connected": true}'
        assert isinstance(data["latency_ms"], int)
        assert mock_complete.await_count == 1

    async def test_vl_test_endpoint_missing_model_rejected(self, async_client: AsyncClient):
        await update_settings({"vl_confirm_model": ""})
        resp = await async_client.post(
            "/api/settings/vl/test", json={"scene_id": "smoke", "vl_confirm_base_url": "http://x/v1"}
        )
        assert resp.status_code == 422

    async def test_vl_test_endpoint_upstream_error_502(self, async_client: AsyncClient):
        with patch(
            "core.vl_confirm.VLConfirmClient.complete",
            new=AsyncMock(side_effect=Exception("401 unauthorized")),
        ):
            resp = await async_client.post(
                "/api/settings/vl/test",
                json={
                    "scene_id": "smoke",
                    "vl_confirm_base_url": "http://vl.example.com/v1",
                    "vl_confirm_model": "/models/test-vl",
                },
            )
        assert resp.status_code == 502
        assert "401 unauthorized" in resp.json()["detail"]

    async def test_vl_test_failure_logs_warning(self, async_client: AsyncClient):
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with patch(
                "core.vl_confirm.VLConfirmClient.complete",
                new=AsyncMock(side_effect=Exception("vl backend down")),
            ):
                resp = await async_client.post(
                    "/api/settings/vl/test",
                    json={
                        "scene_id": "smoke",
                        "vl_confirm_base_url": "http://vl.example.com/v1",
                        "vl_confirm_model": "/models/test-vl",
                    },
                )
        finally:
            logger.remove(sink_id)

        assert resp.status_code == 502
        failures = [r for r in records if "VL connection test failed" in r["message"]]
        assert failures
        assert "smoke" in failures[0]["message"]
        assert "/models/test-vl" in failures[0]["message"]

    async def test_vl_test_endpoint_missing_scene_rejected(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/settings/vl/test",
            json={"vl_confirm_base_url": "http://x/v1"},
        )
        assert resp.status_code == 422

    async def test_vl_test_endpoint_invalid_scene_rejected(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/settings/vl/test",
            json={"scene_id": "foo", "vl_confirm_base_url": "http://x/v1"},
        )
        assert resp.status_code == 422

    async def test_vl_test_endpoint_sampling_overrides_applied(self, async_client: AsyncClient):
        with patch("backend.api.settings.VLConfirmClient") as mock_cls:
            mock_cls.return_value.complete = AsyncMock(return_value='{"connected": true}')
            resp = await async_client.post(
                "/api/settings/vl/test",
                json={
                    "scene_id": "smoke",
                    "vl_confirm_base_url": "http://vl.example.com/v1",
                    "vl_confirm_model": "/models/test-vl",
                    "smoke_vl_confirm_max_tokens": "64",
                    "smoke_vl_confirm_temperature": "0.7",
                    "smoke_vl_confirm_top_p": "0.9",
                    "smoke_vl_confirm_disable_thinking": "true",
                },
            )
        assert resp.status_code == 200
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_tokens"] == 64
        assert kwargs["temperature"] == 0.7
        assert kwargs["top_p"] == 0.9
        assert kwargs["disable_thinking"] is True

    async def test_vl_test_endpoint_sampling_falls_back_to_scene_settings(self, async_client: AsyncClient):
        await update_settings({"smoke_vl_confirm_max_tokens": "128"})
        with patch("backend.api.settings.VLConfirmClient") as mock_cls:
            mock_cls.return_value.complete = AsyncMock(return_value='{"connected": true}')
            resp = await async_client.post(
                "/api/settings/vl/test",
                json={
                    "scene_id": "smoke",
                    "vl_confirm_base_url": "http://vl.example.com/v1",
                    "vl_confirm_model": "/models/test-vl",
                },
            )
        assert resp.status_code == 200
        assert mock_cls.call_args.kwargs["max_tokens"] == 128

    async def test_update_mediamtx_rtsp_settings_rewrites_existing_source_urls(
        self,
        async_client: AsyncClient,
    ):
        source = await create_source(
            VideoSourceCreate(name="Cam1", rtsp_url="rtsp://localhost:8554/cam1")
        )

        resp = await async_client.put(
            "/api/settings",
            json={
                "mediamtx_rtsp_addr": "rtsp://gateway.example.com:9554/live",
                "mediamtx_username": "stream-user",
                "mediamtx_password": "stream-pass",
            },
        )

        assert resp.status_code == 200
        updated_source = await get_source(source.id)
        assert updated_source is not None
        assert (
            updated_source.rtsp_url
            == "rtsp://stream-user:stream-pass@gateway.example.com:9554/live/cam1"
        )

    async def test_update_shared_mediamtx_settings_syncs_default_gateway(
        self,
        async_client: AsyncClient,
    ):
        resp = await async_client.put(
            "/api/settings",
            json={
                "mediamtx_rtsp_addr": "rtsp://gateway.example.com:9554/live",
                "mediamtx_webrtc_addr": "https://gateway.example.com:8889/live",
                "mediamtx_username": "shared-user",
                "mediamtx_password": "shared-pass",
            },
        )

        assert resp.status_code == 200
        gateways_resp = await async_client.get("/api/video-gateways")
        assert gateways_resp.status_code == 200
        default_gateway = next(item for item in gateways_resp.json() if item["id"] == "default-mediamtx")
        assert default_gateway["rtsp_base_url"] == "rtsp://gateway.example.com:9554/live"
        assert default_gateway["webrtc_base_url"] == "https://gateway.example.com:8889/live"
        assert default_gateway["username"] == "shared-user"
        assert default_gateway["password"] == "shared-pass"

    async def test_update_active_plugin_rebinds_existing_sources(
        self,
        async_client: AsyncClient,
    ):
        source = await create_source(
            VideoSourceCreate(name="Cam1", rtsp_url="rtsp://localhost:8554/cam1")
        )

        resp = await async_client.put(
            "/api/settings",
            json={"active_plugin_id": "template"},
        )

        assert resp.status_code == 200
        assert resp.json()["active_plugin_id"] == "template"
        updated_source = await get_source(source.id)
        assert updated_source is not None
        assert updated_source.scene_id == "template"

    async def test_update_active_plugin_rejects_unknown_plugin(
        self,
        async_client: AsyncClient,
    ):
        resp = await async_client.put(
            "/api/settings",
            json={"active_plugin_id": "missing-plugin"},
        )

        assert resp.status_code == 422

    async def test_legacy_mediamtx_protocol_credentials_are_mapped_to_shared_fields(
        self,
        async_client: AsyncClient,
    ):
        resp = await async_client.put(
            "/api/settings",
            json={
                "mediamtx_rtsp_username": "legacy-user",
                "mediamtx_rtsp_password": "legacy-pass",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["mediamtx_username"] == "legacy-user"
        assert data["mediamtx_password"] == "legacy-pass"

    async def test_conflicting_legacy_mediamtx_credentials_are_rejected(
        self,
        async_client: AsyncClient,
    ):
        resp = await async_client.put(
            "/api/settings",
            json={
                "mediamtx_rtsp_username": "legacy-rtsp",
                "mediamtx_webrtc_username": "legacy-webrtc",
            },
        )

        assert resp.status_code == 422
        assert "must match" in resp.json()["detail"]


class TestVEngineClientAddresses:
    def test_build_addresses(self):
        from backend.vengine.client import AsyncVEngineClient

        addrs = AsyncVEngineClient._build_addresses({
            "vengine_host": "10.0.0.5",
            "detection_port": "8001",
            "classification_port": "8002",
            "action_port": "8003",
            "ocr_port": "8004",
            "upload_port": "8005",
        })
        assert addrs["detection"] == "10.0.0.5:8001"
        assert addrs["classification"] == "10.0.0.5:8002"
        assert addrs["action"] == "10.0.0.5:8003"
        assert addrs["ocr"] == "10.0.0.5:8004"
        assert addrs["upload"] == "10.0.0.5:8005"

    def test_build_addresses_defaults(self):
        from backend.vengine.client import AsyncVEngineClient

        addrs = AsyncVEngineClient._build_addresses({})
        assert addrs["detection"] == "localhost:50051"
        assert addrs["upload"] == "localhost:50050"

    def test_build_addresses_resolves_docker_internal_gateway(self, monkeypatch):
        from backend.vengine.client import AsyncVEngineClient

        monkeypatch.setattr(
            AsyncVEngineClient,
            "_detect_docker_host_gateway",
            staticmethod(lambda: "172.17.0.1"),
        )

        addrs = AsyncVEngineClient._build_addresses({
            "vengine_host": "docker.internal",
            "detection_port": "3139",
        })

        assert addrs["detection"] == "172.17.0.1:3139"
        assert addrs["upload"] == "172.17.0.1:50050"

    async def test_email_template_placeholders_endpoint(self, async_client: AsyncClient):
        resp = await async_client.get("/api/settings/email/template-placeholders")
        assert resp.status_code == 200
        placeholders = set(resp.json()["placeholders"])
        assert {"local_time", "source_name", "event_type", "event_label"} <= placeholders

    async def test_update_settings_refreshes_processor_manager_snapshot(
        self,
        async_client: AsyncClient,
    ):
        from backend.main import processor_manager

        assert processor_manager._app_settings["smoke_detection_model_name"] == "smoke-fire-detection"

        resp = await async_client.put(
            "/api/settings",
            json={"smoke_detection_model_name": "updated-model"},
        )

        assert resp.status_code == 200
        assert processor_manager._app_settings["smoke_detection_model_name"] == "updated-model"
