"""Tests for account login expiration with role-based defaults.
角色级默认账号登录有效期测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient


class TestAccountExpiration:
    async def test_role_default_applied_on_create(self, async_client: AsyncClient):
        await async_client.put(
            "/api/settings",
            json={"account_expiration_days_operator": "30"},
        )
        resp = await async_client.post(
            "/api/users",
            json={"username": "op1", "password": "pw", "role": "operator"},
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    async def test_zero_days_means_never_expires(self, async_client: AsyncClient):
        await async_client.put(
            "/api/settings",
            json={"account_expiration_days_user": "0"},
        )
        resp = await async_client.post(
            "/api/users",
            json={"username": "u1", "password": "pw", "role": "user"},
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is None

    async def test_per_user_override_wins(self, async_client: AsyncClient):
        await async_client.put(
            "/api/settings",
            json={"account_expiration_days_operator": "30"},
        )
        explicit = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        resp = await async_client.post(
            "/api/users",
            json={
                "username": "op2",
                "password": "pw",
                "role": "operator",
                "expires_at": explicit,
            },
        )
        assert resp.status_code == 201
        # Returned timestamp should be the explicit override (UTC normalized).
        body = resp.json()
        assert body["expires_at"] is not None
        # Coarse check: within 5 days.
        dt = datetime.fromisoformat(body["expires_at"])
        delta_days = (dt - datetime.now(timezone.utc)).days
        assert 4 <= delta_days <= 6

    async def test_expired_account_cannot_login_or_use_token(
        self, async_client: AsyncClient
    ):
        await async_client.post(
            "/api/users",
            json={"username": "expsoon", "password": "pw", "role": "operator"},
        )
        # Log in while still valid.
        login = await async_client.post(
            "/api/auth/login", json={"username": "expsoon", "password": "pw"}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        # Admin sets expiration to past.
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        patch = await async_client.patch(
            "/api/users/expsoon", json={"expires_at": past}
        )
        assert patch.status_code == 200
        assert patch.json()["expired"] is True

        # Existing token rejected.
        me = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 401

        # Login rejected.
        relogin = await async_client.post(
            "/api/auth/login", json={"username": "expsoon", "password": "pw"}
        )
        assert relogin.status_code == 401

    async def test_clear_expires_at(self, async_client: AsyncClient):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        await async_client.post(
            "/api/users",
            json={
                "username": "u3",
                "password": "pw",
                "role": "operator",
                "expires_at": future,
            },
        )
        resp = await async_client.patch(
            "/api/users/u3", json={"clear_expires_at": True}
        )
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None
