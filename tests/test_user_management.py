"""Tests for admin user management (delete / ban / reset password).
管理员用户管理（删除/封禁/重置密码）测试。"""
from __future__ import annotations

from httpx import AsyncClient

from backend.auth.security import create_access_token


class TestUserManagement:
    async def test_admin_can_delete_user(self, async_client: AsyncClient):
        create_resp = await async_client.post(
            "/api/users",
            json={"username": "victim", "password": "pw", "role": "operator"},
        )
        assert create_resp.status_code == 201

        delete_resp = await async_client.delete("/api/users/victim")
        assert delete_resp.status_code == 204

        list_resp = await async_client.get("/api/users")
        assert all(item["username"] != "victim" for item in list_resp.json())

    async def test_admin_cannot_delete_self(self, async_client: AsyncClient):
        resp = await async_client.delete("/api/users/test-admin")
        assert resp.status_code == 400

    async def test_cannot_delete_last_admin(self, async_client: AsyncClient):
        # Create an explicit admin via API and then try to delete it while
        # there is only one admin in the DB.
        await async_client.post(
            "/api/users",
            json={"username": "soleadmin", "password": "pw", "role": "admin"},
        )
        resp = await async_client.delete("/api/users/soleadmin")
        assert resp.status_code == 400

    async def test_ban_user_blocks_login_and_active_token(
        self, async_client: AsyncClient
    ):
        # Create operator and log them in.
        await async_client.post(
            "/api/users",
            json={"username": "opban", "password": "pw", "role": "operator"},
        )
        login = await async_client.post(
            "/api/auth/login",
            json={"username": "opban", "password": "pw"},
        )
        assert login.status_code == 200
        op_token = login.json()["access_token"]

        # Token works before ban.
        me_ok = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {op_token}"},
        )
        assert me_ok.status_code == 200

        # Admin bans the operator.
        patch = await async_client.patch(
            "/api/users/opban", json={"is_banned": True}
        )
        assert patch.status_code == 200
        assert patch.json()["is_banned"] is True

        # Existing token now rejected mid-session.
        me_blocked = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {op_token}"},
        )
        assert me_blocked.status_code == 401

        # Subsequent login rejected.
        relogin = await async_client.post(
            "/api/auth/login",
            json={"username": "opban", "password": "pw"},
        )
        assert relogin.status_code == 401

        # Unban restores access.
        await async_client.patch("/api/users/opban", json={"is_banned": False})
        re_ok = await async_client.post(
            "/api/auth/login",
            json={"username": "opban", "password": "pw"},
        )
        assert re_ok.status_code == 200

    async def test_admin_cannot_ban_self(self, async_client: AsyncClient):
        # Persist the admin account first (conftest's test-admin only has a token).
        await async_client.post(
            "/api/users",
            json={"username": "test-admin", "password": "pw", "role": "admin"},
        )
        resp = await async_client.patch(
            "/api/users/test-admin", json={"is_banned": True}
        )
        assert resp.status_code == 400

    async def test_admin_reset_password_replaces_credentials(
        self, async_client: AsyncClient
    ):
        await async_client.post(
            "/api/users",
            json={"username": "alice", "password": "old-pw", "role": "operator"},
        )
        resp = await async_client.post(
            "/api/users/alice/password",
            json={"new_password": "new-pw"},
        )
        assert resp.status_code == 200

        old = await async_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "old-pw"},
        )
        assert old.status_code == 401

        new = await async_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "new-pw"},
        )
        assert new.status_code == 200

    async def test_admin_can_update_role(self, async_client: AsyncClient):
        await async_client.post(
            "/api/users",
            json={"username": "promote", "password": "pw", "role": "user"},
        )
        resp = await async_client.patch(
            "/api/users/promote", json={"role": "operator"}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "operator"
