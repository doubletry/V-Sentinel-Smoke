from __future__ import annotations

import pytest
from httpx import AsyncClient

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

    async def test_get_missing_scene_returns_404(self, async_client: AsyncClient):
        resp = await async_client.get("/api/scenes/missing")
        assert resp.status_code == 404


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
