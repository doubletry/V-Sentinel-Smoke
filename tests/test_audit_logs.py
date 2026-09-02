"""Tests for audit log APIs and middleware."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from httpx import AsyncClient
from loguru import logger

from backend.auth.security import create_access_token
from backend.db import database as db


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

        await db.create_audit_log(
            username="ops-audit",
            role="operator",
            ip="127.0.0.1",
            operation_type="auth.logout",
            resource_type="auth",
            resource_id="ops-audit",
            method="POST",
            path="/api/auth/logout",
            result="SUCCESS",
            status_code=200,
            detail="legacy logout entry",
        )

        end_time = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()

        success_resp = await async_client.get(
            "/api/access/audit-logs",
            headers=operator_headers,
            params={
                "username": "ops-audit",
                "operation_type": "processor.stop",
                "result": "SUCCESS",
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        assert success_resp.status_code == 200
        success_data = success_resp.json()
        assert success_data["operation_types"]
        assert "processor.stop" in success_data["operation_types"]
        assert "auth.logout" not in success_data["operation_types"]
        assert len(success_data["items"]) == 1
        assert success_data["items"][0]["username"] == "ops-audit"
        assert success_data["items"][0]["operation_type"] == "processor.stop"
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

    async def test_request_succeeds_when_audit_write_fails(self, async_client: AsyncClient):
        import backend.audit as audit_mod

        async def failing_create(**kwargs):
            raise RuntimeError("audit db down")

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="ERROR")
        try:
            with patch.object(audit_mod.db, "create_audit_log", new=failing_create):
                resp = await async_client.put(
                    "/api/settings", json={"site_title": "AuditFail"}
                )
        finally:
            logger.remove(sink_id)

        assert resp.status_code == 200  # 审计故障不得破坏正常请求
        assert any("Failed to write audit log" in r["message"] for r in records)
