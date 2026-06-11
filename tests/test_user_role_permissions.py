"""Tests for reduced role permission sets.
角色权限收敛测试。"""
from __future__ import annotations

from httpx import AsyncClient

from backend.auth.security import create_access_token


class TestUserRolePermissions:
    async def test_user_role_lacks_video_watch(self, async_client: AsyncClient):
        resp = await async_client.get("/api/access/roles")
        roles = {item["role"]: item for item in resp.json()}
        assert "video:watch" not in roles["user"]["permissions"]
        assert "sources:operate" not in roles["user"]["permissions"]
        assert "messages:read" in roles["user"]["permissions"]

    async def test_user_role_cannot_operate_sources(self, async_client: AsyncClient):
        token = create_access_token(username="viewer", role="user")["access_token"]
        resp = await async_client.post(
            "/api/sources",
            headers={"Authorization": " ".join(("Bearer", token))},
            json={"name": "denied", "rtsp_url": "rtsp://localhost:8554/denied"},
        )
        assert resp.status_code == 403

    async def test_user_role_cannot_manage_users(self, async_client: AsyncClient):
        token = create_access_token(username="viewer", role="user")["access_token"]
        resp = await async_client.get(
            "/api/users",
            headers={"Authorization": " ".join(("Bearer", token))},
        )
        assert resp.status_code == 403

    async def test_user_role_cannot_update_settings(self, async_client: AsyncClient):
        token = create_access_token(username="viewer", role="user")["access_token"]
        resp = await async_client.put(
            "/api/settings",
            headers={"Authorization": " ".join(("Bearer", token))},
            json={"site_title": "denied"},
        )
        assert resp.status_code == 403


class TestOperatorRolePermissions:
    async def test_operator_role_matches_admin_except_for_management_exclusions(
        self,
        async_client: AsyncClient,
    ):
        resp = await async_client.get("/api/access/roles")
        roles = {item["role"]: item for item in resp.json()}
        operator_permissions = set(roles["operator"]["permissions"])

        assert "users:*" not in operator_permissions
        assert "settings:*" not in operator_permissions
        assert {"settings:notifications", "settings:plugins"} <= operator_permissions
        assert {
            "sources:*",
            "scenes:*",
            "gateways:*",
            "notifications:*",
            "audit:read",
            "video:watch",
            "messages:*",
        } <= operator_permissions

    async def test_operator_cannot_manage_users(self, async_client: AsyncClient):
        token = create_access_token(username="operator", role="operator")["access_token"]
        resp = await async_client.get(
            "/api/users",
            headers={"Authorization": " ".join(("Bearer", token))},
        )
        assert resp.status_code == 403

    async def test_operator_cannot_update_site_or_vengine_settings(
        self,
        async_client: AsyncClient,
    ):
        token = create_access_token(username="operator", role="operator")["access_token"]
        for payload in (
            {"site_title": "denied"},
            {"vengine_host": "10.0.0.1"},
            {"max_pull_workers": "30"},
        ):
            resp = await async_client.put(
                "/api/settings",
                headers={"Authorization": " ".join(("Bearer", token))},
                json=payload,
            )
            assert resp.status_code == 403

    async def test_operator_can_update_notification_and_plugin_settings(
        self,
        async_client: AsyncClient,
    ):
        token = create_access_token(username="operator", role="operator")["access_token"]
        headers = {"Authorization": " ".join(("Bearer", token))}

        notification_resp = await async_client.put(
            "/api/settings",
            headers=headers,
            json={"message_retention_days": "15"},
        )
        assert notification_resp.status_code == 200
        assert notification_resp.json()["message_retention_days"] == "15"

        plugin_resp = await async_client.put(
            "/api/settings",
            headers=headers,
            json={"smoke_detection_confidence": "0.45"},
        )
        assert plugin_resp.status_code == 200
        assert plugin_resp.json()["smoke_detection_confidence"] == "0.45"
