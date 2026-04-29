from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient


class TestFrontendFallbackRoutes:
    async def test_direct_frontend_route_serves_index_html(
        self,
        async_client: AsyncClient,
        monkeypatch,
        tmp_path: Path,
    ):
        from backend import main as main_module

        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        index_path = dist_dir / "index.html"
        index_path.write_text("<html><body>frontend</body></html>", encoding="utf-8")

        monkeypatch.setattr(main_module, "_frontend_dist", dist_dir)
        monkeypatch.setattr(main_module, "_frontend_index", index_path)

        resp = await async_client.get("/settings")

        assert resp.status_code == 200
        assert "frontend" in resp.text
