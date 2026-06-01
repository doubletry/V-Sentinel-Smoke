"""Tests for audit log APIs and middleware."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

from backend.auth.security import create_access_token


class TestAuditLogs:
    async def test_operator_can_view_filtered_audit_logs(
        self, async_client: AsyncClient
    ):
        operator_token = create_access_token(
            username="ops-audit", role="operator"
        )["access_token"]
        operator_headers = {"Authorization": "Bearer " + operator_token}

        start_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        login_resp = await async_client.post(
            "/api/auth/login",
            headers={"Authorization": ""},
            json={
                "username": "failed-audit",
                "password": "wrong-secret",
                "role": "operator",
            },
        )
        assert login_resp.status_code == 401

        stop_resp = await async_client.post(
            "/api/processor/stop",
            headers=operator_headers,
            json={"source_id": "camera-a"},
        )
        assert stop_resp.status_code == 200

        logout_resp = await async_client.post(
            "/api/auth/logout",
            headers=operator_headers,
        )
        assert logout_resp.status_code == 200

        end_time = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()

        success_resp = await async_client.get(
            "/api/access/audit-logs",
            headers=operator_headers,
            params={
                "username": "ops-audit",
                "operation_type": "auth.logout",
                "result": "SUCCESS",
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        assert success_resp.status_code == 200
        success_data = success_resp.json()
        assert success_data["operation_types"]
        assert any(item == "auth.logout" for item in success_data["operation_types"])
        assert len(success_data["items"]) == 1
        assert success_data["items"][0]["username"] == "ops-audit"
        assert success_data["items"][0]["operation_type"] == "auth.logout"
        assert success_data["items"][0]["result"] == "SUCCESS"

        failure_resp = await async_client.get(
            "/api/access/audit-logs",
            headers=operator_headers,
            params={
                "username": "failed-audit",
                "operation_type": "auth.login",
                "result": "FAILURE",
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        assert failure_resp.status_code == 200
        failure_data = failure_resp.json()
        assert len(failure_data["items"]) == 1
        assert failure_data["items"][0]["username"] == "failed-audit"
        assert failure_data["items"][0]["operation_type"] == "auth.login"
        assert failure_data["items"][0]["result"] == "FAILURE"

    async def test_user_role_cannot_view_audit_logs(self, async_client: AsyncClient):
        user_token = create_access_token(username="viewer", role="user")["access_token"]
        resp = await async_client.get(
            "/api/access/audit-logs",
            headers={"Authorization": "Bearer " + user_token},
        )
        assert resp.status_code == 403
