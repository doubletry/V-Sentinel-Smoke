"""Tests for the `user` role's reduced permission set.
`user` 角色权限收敛测试。"""
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
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "denied", "rtsp_url": "rtsp://localhost:8554/denied"},
        )
        assert resp.status_code == 403

    async def test_user_role_cannot_manage_users(self, async_client: AsyncClient):
        token = create_access_token(username="viewer", role="user")["access_token"]
        resp = await async_client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_user_role_cannot_update_settings(self, async_client: AsyncClient):
        token = create_access_token(username="viewer", role="user")["access_token"]
        resp = await async_client.put(
            "/api/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"site_title": "denied"},
        )
        assert resp.status_code == 403
