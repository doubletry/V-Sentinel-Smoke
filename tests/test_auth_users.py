from __future__ import annotations

from httpx import AsyncClient


class TestAuthBootstrapAndUsers:
    async def test_first_registration_creates_admin_and_closes_public_registration(
        self,
        async_client: AsyncClient,
    ):
        bootstrap_before = await async_client.get("/api/auth/bootstrap")
        assert bootstrap_before.status_code == 200
        assert bootstrap_before.json() == {"has_users": False, "registration_open": True}

        register_resp = await async_client.post(
            "/api/auth/register",
            json={"username": "root", "password": "root-secret"},
        )
        assert register_resp.status_code == 201
        payload = register_resp.json()
        assert payload["role"] == "admin"

        bootstrap_after = await async_client.get("/api/auth/bootstrap")
        assert bootstrap_after.status_code == 200
        assert bootstrap_after.json() == {"has_users": True, "registration_open": False}

        me_resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {payload['access_token']}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "root"
        assert me_resp.json()["role"] == "admin"
        assert "users:*" in me_resp.json()["permissions"]

    async def test_second_public_registration_is_rejected(self, async_client: AsyncClient):
        first = await async_client.post(
            "/api/auth/register",
            json={"username": "root", "password": "root-secret"},
        )
        assert first.status_code == 201

        second = await async_client.post(
            "/api/auth/register",
            json={"username": "another", "password": "another-secret"},
        )
        assert second.status_code == 403

    async def test_admin_can_create_user_and_user_can_login(self, async_client: AsyncClient):
        create_resp = await async_client.post(
            "/api/users",
            json={"username": "operator1", "password": "operator-secret", "role": "operator"},
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["role"] == "operator"

        list_resp = await async_client.get("/api/users")
        assert list_resp.status_code == 200
        assert any(item["username"] == "operator1" for item in list_resp.json())

        login_resp = await async_client.post(
            "/api/auth/login",
            json={"username": "operator1", "password": "operator-secret", "role": "operator"},
        )
        assert login_resp.status_code == 200

        me_resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {login_resp.json()['access_token']}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["role"] == "operator"
        assert "sources:operate" in me_resp.json()["permissions"]
