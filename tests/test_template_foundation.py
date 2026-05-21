from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch
from httpx import AsyncClient

from backend.db.database import (
    create_notification_policy,
    create_notification_provider,
    create_source,
    update_settings,
)
from backend.models.schemas import (
    NotificationPolicyCreate,
    NotificationProviderCreate,
    VideoSourceCreate,
)
from backend.auth.security import create_access_token
from backend.notifications.dispatcher import NotificationDispatcher
from core.notification_client import NotificationPayload, SmtpNotificationProvider


class TestSceneFoundation:
    async def test_default_smoke_scene_is_seeded(self, async_client: AsyncClient):
        resp = await async_client.get("/api/scenes")
        assert resp.status_code == 200
        scenes = resp.json()
        smoke = next(item for item in scenes if item["id"] == "smoke")
        assert smoke["label_zh"] == "烟火检测"
        assert smoke["required_services"] == ["detection"]
        assert "smoke" in smoke["event_types"]
        template = next(item for item in scenes if item["id"] == "template")
        assert template["label_zh"] == "场景开发模板"
        assert "bright_area" in template["event_types"]
        assert template["default_config"] == {}

    async def test_get_missing_scene_returns_404(self, async_client: AsyncClient):
        resp = await async_client.get("/api/scenes/missing")
        assert resp.status_code == 404

    async def test_source_persists_single_scene_binding(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/sources",
            json={
                "name": "Scene Camera",
                "route_path": "scene-cam",
                "scene_id": "smoke",
                "notification_policy_ids": ["default-alert-policy"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["scene_id"] == "smoke"
        assert data["route_path"] == "scene-cam"
        assert data["notification_policy_ids"] == ["default-alert-policy"]


class TestVideoGatewayFoundation:
    async def test_default_gateway_uses_shared_credentials(self, async_client: AsyncClient):
        resp = await async_client.get("/api/video-gateways")
        assert resp.status_code == 200
        gateway = resp.json()[0]
        assert gateway["id"] == "default-mediamtx"
        assert gateway["rtsp_base_url"].startswith("rtsp://")
        assert gateway["webrtc_base_url"].startswith("http://")
        assert "username" in gateway
        assert "password" in gateway

    async def test_create_and_update_gateway(self, async_client: AsyncClient):
        create_resp = await async_client.post(
            "/api/video-gateways",
            json={
                "name": "Factory MediaMTX",
                "rtsp_base_url": "rtsp://media.example.com:8554",
                "webrtc_base_url": "https://media.example.com/whep",
                "username": "shared-user",
                "password": "shared-pass",
            },
        )
        assert create_resp.status_code == 201
        gateway_id = create_resp.json()["id"]

        update_resp = await async_client.put(
            f"/api/video-gateways/{gateway_id}",
            json={"enabled": False},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["enabled"] is False


class TestNotificationFoundation:
    async def test_default_notification_records_are_seeded(self, async_client: AsyncClient):
        providers_resp = await async_client.get("/api/notifications/providers")
        templates_resp = await async_client.get("/api/notifications/templates")
        policies_resp = await async_client.get("/api/notifications/policies")

        assert providers_resp.status_code == 200
        assert templates_resp.status_code == 200
        assert policies_resp.status_code == 200

        provider_types = {item["type"] for item in providers_resp.json()}
        assert provider_types == {"email", "webhook"}
        assert templates_resp.json()[0]["channel"] == "email"
        assert policies_resp.json()[0]["provider_ids"] == ["default-email"]

    async def test_create_email_provider_and_policy(self, async_client: AsyncClient):
        provider_resp = await async_client.post(
            "/api/notifications/providers",
            json={
                "name": "Ops SMTP",
                "type": "email",
                "enabled": True,
                "config": {
                    "smtp_host": "smtp.example.com",
                    "smtp_port": "587",
                    "from_address": "sender@example.com",
                    "to_addresses": ["ops@example.com"],
                },
            },
        )
        assert provider_resp.status_code == 201
        provider_id = provider_resp.json()["id"]

        policy_resp = await async_client.post(
            "/api/notifications/policies",
            json={
                "name": "Ops Alerts",
                "provider_ids": [provider_id],
                "cooldown_seconds": 60,
            },
        )
        assert policy_resp.status_code == 201
        assert policy_resp.json()["provider_ids"] == [provider_id]


class TestRbacFoundation:
    async def test_three_roles_are_exposed(self, async_client: AsyncClient):
        resp = await async_client.get("/api/access/roles")
        assert resp.status_code == 200
        roles = {item["role"]: item for item in resp.json()}
        assert set(roles) == {"user", "operator", "admin"}
        assert "video:watch" in roles["user"]["permissions"]
        assert "sources:operate" in roles["operator"]["permissions"]
        assert "users:*" in roles["admin"]["permissions"]

    async def test_user_cannot_update_admin_settings(self, async_client: AsyncClient):
        token = create_access_token(username="u", role="user")["access_token"]
        resp = await async_client.put(
            "/api/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"site_title": "Denied"},
        )
        assert resp.status_code == 403

    async def test_operator_can_create_source_but_user_cannot(self, async_client: AsyncClient):
        user_token = create_access_token(username="u", role="user")["access_token"]
        operator_token = create_access_token(username="op", role="operator")["access_token"]
        denied = await async_client.post(
            "/api/sources",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"name": "Denied", "rtsp_url": "rtsp://localhost:8554/denied"},
        )
        assert denied.status_code == 403

        allowed = await async_client.post(
            "/api/sources",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"name": "Allowed", "rtsp_url": "rtsp://localhost:8554/allowed"},
        )
        assert allowed.status_code == 201

    async def test_login_returns_signed_token_and_me(self, async_client: AsyncClient):
        login_resp = await async_client.post(
            "/api/auth/login",
            json={"username": "operator1", "password": "operator-secret", "role": "operator"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        me_resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json() == {
            "username": "operator1",
            "role": "operator",
            "permissions": [
                "sources:read",
                "sources:operate",
                "video:watch",
                "messages:read",
                "messages:annotate",
            ],
        }

    async def test_mutation_requires_bearer_token(self, async_client: AsyncClient):
        resp = await async_client.put(
            "/api/settings",
            headers={"Authorization": ""},
            json={"site_title": "Denied"},
        )
        assert resp.status_code == 401


class TestSmtpNotificationProvider:
    def test_smtp_message_requires_sender(self):
        provider = SmtpNotificationProvider({"to_addresses": ["ops@example.com"]})
        with pytest.raises(ValueError, match="from_address"):
            provider._build_message(NotificationPayload(subject="Alert", body="Body"))

    def test_smtp_message_builds_recipients_and_html(self):
        provider = SmtpNotificationProvider(
            {
                "from_address": "sender@example.com",
                "to_addresses": "a@example.com,b@example.com",
                "cc_addresses": ["cc@example.com"],
            }
        )
        message = provider._build_message(
            NotificationPayload(subject="Alert", body="Plain", html_body="<b>Plain</b>")
        )
        assert message["From"] == "sender@example.com"
        assert message["To"] == "a@example.com, b@example.com"
        assert message["Cc"] == "cc@example.com"
        assert message["Subject"] == "Alert"


class TestNotificationDispatcher:
    async def test_dispatcher_uses_source_bound_policy(self, init_db):
        provider = await create_notification_provider(
            NotificationProviderCreate(
                name="SMTP",
                type="email",
                enabled=True,
                config={
                    "smtp_host": "smtp.example.com",
                    "from_address": "sender@example.com",
                    "to_addresses": ["ops@example.com"],
                },
            )
        )
        policy = await create_notification_policy(
            NotificationPolicyCreate(
                name="Policy",
                cooldown_seconds=0,
                provider_ids=[provider.id],
            )
        )
        source = await create_source(
            VideoSourceCreate(
                name="Cam",
                rtsp_url="rtsp://localhost:8554/cam",
                notification_policy_ids=[policy.id],
            )
        )

        dispatcher = NotificationDispatcher()
        with patch(
            "core.notification_client.SmtpNotificationProvider.send",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": "sent"}),
        ) as send:
            results = await dispatcher.send_event(
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "source_id": source.id,
                    "source_name": source.name,
                    "event_type": "smoke",
                    "event_label": "Smoke",
                }
            )

        assert results == [{"status": "SUCCESS", "message": "sent"}]
        send.assert_awaited_once()
        payload = send.await_args.args[0]
        assert payload.body.endswith("Smoke Cam")
        assert payload.html_body.endswith("Smoke Cam")

    async def test_dispatcher_escapes_html_body_lines(self, init_db):
        provider = await create_notification_provider(
            NotificationProviderCreate(
                name="SMTP",
                type="email",
                enabled=True,
                config={
                    "smtp_host": "smtp.example.com",
                    "from_address": "sender@example.com",
                    "to_addresses": ["ops@example.com"],
                },
            )
        )
        policy = await create_notification_policy(
            NotificationPolicyCreate(
                name="Policy",
                cooldown_seconds=0,
                provider_ids=[provider.id],
            )
        )
        source = await create_source(
            VideoSourceCreate(
                name="Cam <A>",
                rtsp_url="rtsp://localhost:8554/cam",
                notification_policy_ids=[policy.id],
            )
        )

        dispatcher = NotificationDispatcher()
        with patch(
            "core.notification_client.SmtpNotificationProvider.send",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": "sent"}),
        ) as send:
            await dispatcher.send_event(
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "source_id": source.id,
                    "source_name": source.name,
                    "event_type": "smoke<script>",
                    "event_label": "Smoke & Fire",
                }
            )

        payload = send.await_args.args[0]
        assert payload.body.endswith("Smoke & Fire Cam <A>")
        assert payload.html_body.endswith("Smoke &amp; Fire Cam &lt;A&gt;")
        assert "<A>" not in payload.html_body

    async def test_dispatcher_force_bypasses_cooldown(self, init_db):
        provider = await create_notification_provider(
            NotificationProviderCreate(
                name="SMTP",
                type="email",
                enabled=True,
                config={
                    "smtp_host": "smtp.example.com",
                    "from_address": "sender@example.com",
                    "to_addresses": ["ops@example.com"],
                },
            )
        )
        policy = await create_notification_policy(
            NotificationPolicyCreate(
                name="Policy",
                cooldown_seconds=3600,
                provider_ids=[provider.id],
            )
        )
        source = await create_source(
            VideoSourceCreate(
                name="Cam",
                rtsp_url="rtsp://localhost:8554/cam",
                notification_policy_ids=[policy.id],
            )
        )
        event = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "source_id": source.id,
            "source_name": source.name,
            "event_type": "smoke",
            "event_label": "Smoke",
        }

        dispatcher = NotificationDispatcher()
        with patch(
            "core.notification_client.SmtpNotificationProvider.send",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": "sent"}),
        ) as send:
            await dispatcher.send_event(event)
            skipped = await dispatcher.send_event(event)
            forced = await dispatcher.send_event(event, force=True)

        assert skipped == []
        assert forced == [{"status": "SUCCESS", "message": "sent"}]
        assert send.await_count == 2

    async def test_dispatcher_force_uses_enabled_provider_without_source_policy(self, init_db):
        await create_notification_provider(
            NotificationProviderCreate(
                name="SMTP",
                type="email",
                enabled=True,
                config={
                    "smtp_host": "smtp.example.com",
                    "from_address": "sender@example.com",
                    "to_addresses": ["ops@example.com"],
                },
            )
        )

        dispatcher = NotificationDispatcher()
        with patch(
            "core.notification_client.SmtpNotificationProvider.send",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": "sent"}),
        ) as send:
            results = await dispatcher.send_event(
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "source_id": "persisted-source",
                    "source_name": "Persisted Cam",
                    "event_type": "message",
                    "event_label": "Persisted alert",
                },
                force=True,
            )

        assert results == [{"status": "SUCCESS", "message": "sent"}]
        send.assert_awaited_once()

    async def test_dispatcher_force_uses_legacy_email_settings_when_no_provider_enabled(self, init_db):
        await update_settings(
            {
                "email_smtp_host": "smtp.example.com",
                "email_from_address": "sender@example.com",
                "email_smtp_password": "test-password-do-not-use",
                "email_to_addresses": "ops@example.com",
            }
        )

        dispatcher = NotificationDispatcher()
        with patch.object(
            dispatcher,
            "_send_provider",
            new=AsyncMock(return_value={"status": "SUCCESS", "message": "sent"}),
        ) as send_provider:
            results = await dispatcher.send_event(
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "source_id": "persisted-source",
                    "source_name": "Persisted Cam",
                    "event_type": "message",
                    "event_label": "Persisted alert",
                },
                force=True,
            )

        assert results == [{"status": "SUCCESS", "message": "sent"}]
        send_provider.assert_awaited_once()
        provider_type, config, payload = send_provider.await_args.args
        assert provider_type == "email"
        assert config["smtp_username"] == "sender@example.com"
        assert config["smtp_password"] == "test-password-do-not-use"
        assert config["use_tls"] is True
        assert payload.subject == "Persisted alert alert from Persisted Cam"
