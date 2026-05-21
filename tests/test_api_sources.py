"""Tests for the Sources REST API endpoints."""
from __future__ import annotations

from urllib.parse import quote

import pytest
from httpx import AsyncClient

from backend.db.database import build_source_rtsp_url


class TestHealthEndpoint:
    async def test_health(self, async_client: AsyncClient):
        resp = await async_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "V-Sentinel"


class TestCreateSource:
    async def test_create_success(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        resp = await async_client.post("/api/sources", json=sample_source_data)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == sample_source_data["name"]
        assert data["rtsp_url"] == sample_source_data["rtsp_url"]
        assert "id" in data
        assert data["rois"] == []

    async def test_create_duplicate(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        await async_client.post("/api/sources", json=sample_source_data)
        resp = await async_client.post("/api/sources", json=sample_source_data)
        assert resp.status_code == 409

    async def test_create_missing_field(self, async_client: AsyncClient):
        resp = await async_client.post("/api/sources", json={"name": "x"})
        assert resp.status_code == 422

    async def test_create_from_route_path_uses_current_settings(self, async_client: AsyncClient):
        settings_resp = await async_client.put(
            "/api/settings",
            json={
                "mediamtx_rtsp_addr": "rtsp://gateway.example.com:9554/live",
                "mediamtx_username": "stream-user",
                "mediamtx_password": "stream-pass",
            },
        )
        assert settings_resp.status_code == 200

        resp = await async_client.post(
            "/api/sources",
            json={"name": "Route Camera", "route_path": "cam1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["rtsp_url"] == build_source_rtsp_url(
            "rtsp://gateway.example.com:9554/live",
            "cam1",
            username="stream-user",
            password="stream-pass",
        )

    async def test_create_uses_active_plugin_setting(self, async_client: AsyncClient):
        settings_resp = await async_client.put(
            "/api/settings",
            json={"active_plugin_id": "template"},
        )
        assert settings_resp.status_code == 200

        resp = await async_client.post(
            "/api/sources",
            json={
                "name": "Route Camera",
                "route_path": "cam-template",
            },
        )

        assert resp.status_code == 201
        assert resp.json()["scene_id"] == "template"

    async def test_create_with_stream_and_threshold_settings(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/sources",
            json={
                "name": "Door Camera",
                "route_path": "door-camera",
                "push_result_stream": False,
                "alarm_confidence_threshold": 0.86,
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["push_result_stream"] is False
        assert data["alarm_confidence_threshold"] == 0.86

    async def test_create_rejects_invalid_alarm_threshold(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/sources",
            json={
                "name": "Door Camera",
                "route_path": "door-invalid",
                "alarm_confidence_threshold": 1.5,
            },
        )

        assert resp.status_code == 422

    async def test_create_rejects_mismatched_scene_id(self, async_client: AsyncClient):
        settings_resp = await async_client.put(
            "/api/settings",
            json={"active_plugin_id": "template"},
        )
        assert settings_resp.status_code == 200

        resp = await async_client.post(
            "/api/sources",
            json={
                "name": "Route Camera",
                "route_path": "cam-template",
                "scene_id": "smoke",
            },
        )

        assert resp.status_code == 422
        assert "scene_id must match active_plugin_id" in resp.json()["detail"]


class TestListSources:
    async def test_list_empty(self, async_client: AsyncClient):
        resp = await async_client.get("/api/sources")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_multiple(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        await async_client.post("/api/sources", json=sample_source_data)
        await async_client.post(
            "/api/sources",
            json={"name": "Cam2", "rtsp_url": "rtsp://localhost:8554/cam2"},
        )
        resp = await async_client.get("/api/sources")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetSource:
    async def test_get_existing(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]
        resp = await async_client.get(f"/api/sources/{source_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == source_id

    async def test_get_not_found(self, async_client: AsyncClient):
        resp = await async_client.get("/api/sources/nonexistent-id")
        assert resp.status_code == 404


class TestGetSourceByRtsp:
    async def test_by_rtsp(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        await async_client.post("/api/sources", json=sample_source_data)
        resp = await async_client.get(
            "/api/sources/by-rtsp",
            params={"rtsp_url": sample_source_data["rtsp_url"]},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == sample_source_data["name"]

    async def test_by_rtsp_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(
            "/api/sources/by-rtsp", params={"rtsp_url": "rtsp://missing"}
        )
        assert resp.status_code == 404


class TestUpdateSource:
    async def test_update_name(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]
        resp = await async_client.put(
            f"/api/sources/{source_id}", json={"name": "Updated Name"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_stream_and_threshold_settings(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]

        resp = await async_client.put(
            f"/api/sources/{source_id}",
            json={
                "push_result_stream": False,
                "alarm_confidence_threshold": 0.74,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["push_result_stream"] is False
        assert data["alarm_confidence_threshold"] == 0.74

    async def test_update_with_rois(
        self,
        async_client: AsyncClient,
        sample_source_data: dict,
        sample_roi_data: list,
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]
        resp = await async_client.put(
            f"/api/sources/{source_id}",
            json={"rois": sample_roi_data},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rois"]) == 1
        assert data["rois"][0]["tag"] == "zone-A"

    async def test_update_not_found(self, async_client: AsyncClient):
        resp = await async_client.put(
            "/api/sources/nope", json={"name": "X"}
        )
        assert resp.status_code == 404

    async def test_update_route_path_uses_current_settings(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]

        settings_resp = await async_client.put(
            "/api/settings",
            json={
                "mediamtx_rtsp_addr": "rtsp://gateway.example.com:9554/base",
                "mediamtx_username": "stream-user",
                "mediamtx_password": "stream-pass",
            },
        )
        assert settings_resp.status_code == 200

        resp = await async_client.put(
            f"/api/sources/{source_id}",
            json={"route_path": "cam2"},
        )
        assert resp.status_code == 200
        assert resp.json()["rtsp_url"] == build_source_rtsp_url(
            "rtsp://gateway.example.com:9554/base",
            "cam2",
            username="stream-user",
            password="stream-pass",
        )

    async def test_update_rejects_mismatched_scene_id(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]

        settings_resp = await async_client.put(
            "/api/settings",
            json={"active_plugin_id": "template"},
        )
        assert settings_resp.status_code == 200

        resp = await async_client.put(
            f"/api/sources/{source_id}",
            json={"scene_id": "smoke"},
        )
        assert resp.status_code == 422
        assert "scene_id must match active_plugin_id" in resp.json()["detail"]


class TestDeleteSource:
    async def test_delete_existing(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]
        resp = await async_client.delete(f"/api/sources/{source_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp2 = await async_client.get(f"/api/sources/{source_id}")
        assert resp2.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient):
        resp = await async_client.delete("/api/sources/missing")
        assert resp.status_code == 404


class TestROIExport:
    async def test_export_empty_rois(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]
        resp = await async_client.get(f"/api/sources/{source_id}/rois/export")
        assert resp.status_code == 200
        assert "application/x-yaml" in resp.headers["content-type"]
        import yaml

        data = yaml.safe_load(resp.content)
        assert data["rois"] == []

    async def test_export_with_rois(
        self,
        async_client: AsyncClient,
        sample_source_data: dict,
        sample_roi_data: list,
    ):
        create_resp = await async_client.post("/api/sources", json=sample_source_data)
        source_id = create_resp.json()["id"]
        await async_client.put(
            f"/api/sources/{source_id}", json={"rois": sample_roi_data}
        )
        resp = await async_client.get(f"/api/sources/{source_id}/rois/export")
        assert resp.status_code == 200
        import yaml

        data = yaml.safe_load(resp.content)
        assert len(data["rois"]) == 1
        assert data["rois"][0]["tag"] == "zone-A"

    async def test_export_with_unicode_source_name_uses_utf8_filename_header(
        self, async_client: AsyncClient
    ):
        create_resp = await async_client.post(
            "/api/sources",
            json={"name": "测试摄像头", "rtsp_url": "rtsp://localhost:8554/unicode"},
        )
        source_id = create_resp.json()["id"]

        resp = await async_client.get(f"/api/sources/{source_id}/rois/export")

        assert resp.status_code == 200
        content_disposition = resp.headers["content-disposition"]
        assert 'filename="______rois.yaml"' in content_disposition
        assert (
            f"filename*=UTF-8''{quote('测试摄像头_rois.yaml')}"
            in content_disposition
        )

    async def test_export_not_found(self, async_client: AsyncClient):
        resp = await async_client.get("/api/sources/missing/rois/export")
        assert resp.status_code == 404


class TestROIImport:
    async def _create_source(self, client, data):
        resp = await client.post("/api/sources", json=data)
        return resp.json()["id"]

    async def test_import_valid_yaml(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        """Import ROIs with tags that match the source scene's ROI tags."""
        source_id = await self._create_source(async_client, sample_source_data)

        # The default smoke scene owns smoke_zone and fire_zone ROI tags.
        yaml_content = (
            "rois:\n"
            "  - type: rectangle\n"
            '    tag: "smoke_zone"\n'
            "    points:\n"
            "      - {x: 0.1, y: 0.1}\n"
            "      - {x: 0.9, y: 0.1}\n"
            "      - {x: 0.9, y: 0.9}\n"
            "      - {x: 0.1, y: 0.9}\n"
        )
        resp = await async_client.post(
            f"/api/sources/{source_id}/rois/import",
            files={"file": ("rois.yaml", yaml_content, "application/x-yaml")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rois"]) == 1
        assert data["rois"][0]["tag"] == "smoke_zone"

    async def test_import_invalid_tag(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        """Reject import when tag is not in the source scene's ROI tags."""
        source_id = await self._create_source(async_client, sample_source_data)

        yaml_content = (
            "rois:\n"
            "  - type: rectangle\n"
            '    tag: "unknown_tag"\n'
            "    points:\n"
            "      - {x: 0.1, y: 0.1}\n"
            "      - {x: 0.9, y: 0.9}\n"
        )
        resp = await async_client.post(
            f"/api/sources/{source_id}/rois/import",
            files={"file": ("rois.yaml", yaml_content, "application/x-yaml")},
        )
        assert resp.status_code == 400
        assert "unknown_tag" in resp.json()["detail"]

    async def test_import_missing_tag(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        source_id = await self._create_source(async_client, sample_source_data)

        yaml_content = (
            "rois:\n"
            "  - type: polygon\n"
            "    points:\n"
            "      - {x: 0.1, y: 0.1}\n"
            "      - {x: 0.5, y: 0.1}\n"
            "      - {x: 0.3, y: 0.8}\n"
        )
        resp = await async_client.post(
            f"/api/sources/{source_id}/rois/import",
            files={"file": ("rois.yaml", yaml_content, "application/x-yaml")},
        )
        assert resp.status_code == 400
        assert "tag is required" in resp.json()["detail"]

    async def test_import_invalid_yaml(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        source_id = await self._create_source(async_client, sample_source_data)

        resp = await async_client.post(
            f"/api/sources/{source_id}/rois/import",
            files={"file": ("rois.yaml", "not: [valid: yaml: {{", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_import_no_rois_key(
        self, async_client: AsyncClient, sample_source_data: dict
    ):
        source_id = await self._create_source(async_client, sample_source_data)

        resp = await async_client.post(
            f"/api/sources/{source_id}/rois/import",
            files={"file": ("rois.yaml", "data: 123\n", "application/x-yaml")},
        )
        assert resp.status_code == 400
        assert "rois" in resp.json()["detail"]

    async def test_import_source_not_found(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/sources/nonexistent/rois/import",
            files={"file": ("rois.yaml", "rois: []\n", "application/x-yaml")},
        )
        assert resp.status_code == 404
