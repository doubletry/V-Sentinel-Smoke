"""Tests for anti-brute-force login lockout (IP block / unblock).
登录暴力破解防护（IP 封锁/解封）测试。"""
from __future__ import annotations

from httpx import AsyncClient


class TestLoginLockout:
    async def test_failures_trigger_block_and_unblock_clears_it(
        self, async_client: AsyncClient
    ):
        # Tighten threshold so the test runs quickly.
        await async_client.put(
            "/api/settings",
            json={
                "login_lockout_max_attempts": "3",
                "login_lockout_window_seconds": "300",
                "login_lockout_duration_seconds": "0",
            },
        )
        # Create a real user so the 401 path returns from authenticate_user.
        await async_client.post(
            "/api/users",
            json={"username": "victim", "password": "correct", "role": "operator"},
        )

        for _ in range(3):
            resp = await async_client.post(
                "/api/auth/login",
                json={"username": "victim", "password": "wrong"},
            )
            assert resp.status_code in (401, 403)

        # After 3 failures the IP should be blocked even with correct credentials.
        blocked = await async_client.post(
            "/api/auth/login",
            json={"username": "victim", "password": "correct"},
        )
        assert blocked.status_code == 403
        body = blocked.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        assert isinstance(detail, dict)
        assert detail.get("code") == "IP_BLOCKED"

        # Admin lists blocked IPs.
        list_resp = await async_client.get("/api/access/blocked-ips")
        assert list_resp.status_code == 200
        ips = [item["ip"] for item in list_resp.json()]
        assert ips, "expected at least one blocked IP"

        # Admin unblocks the IP — subsequent correct login succeeds.
        unblock = await async_client.delete(f"/api/access/blocked-ips/{ips[0]}")
        assert unblock.status_code == 204

        ok = await async_client.post(
            "/api/auth/login",
            json={"username": "victim", "password": "correct"},
        )
        assert ok.status_code == 200

    async def test_successful_login_resets_failure_counter(
        self, async_client: AsyncClient
    ):
        await async_client.put(
            "/api/settings",
            json={
                "login_lockout_max_attempts": "3",
                "login_lockout_window_seconds": "300",
            },
        )
        await async_client.post(
            "/api/users",
            json={"username": "vic2", "password": "right", "role": "operator"},
        )
        # Two failures then one success.
        for _ in range(2):
            r = await async_client.post(
                "/api/auth/login",
                json={"username": "vic2", "password": "wrong"},
            )
            assert r.status_code in (401, 403)
        ok = await async_client.post(
            "/api/auth/login",
            json={"username": "vic2", "password": "right"},
        )
        assert ok.status_code == 200

        # Now two more failures should NOT trip the lockout (counter cleared).
        for _ in range(2):
            r = await async_client.post(
                "/api/auth/login",
                json={"username": "vic2", "password": "wrong"},
            )
            assert r.status_code == 401

    async def test_admin_can_manually_block_ip(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/access/blocked-ips",
            json={"ip": "192.0.2.99", "reason": "test"},
        )
        assert resp.status_code == 201
        assert resp.json()["ip"] == "192.0.2.99"

        list_resp = await async_client.get("/api/access/blocked-ips")
        assert any(item["ip"] == "192.0.2.99" for item in list_resp.json())
