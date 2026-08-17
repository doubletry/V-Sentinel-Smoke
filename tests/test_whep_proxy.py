"""Tests for the server-side WHEP proxy path handling."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from backend.api.whep_proxy import _build_whep_url, _validate_stream_path


def test_validate_accepts_single_segment():
    assert _validate_stream_path("cam1") == "cam1"


def test_validate_accepts_two_segments():
    assert _validate_stream_path("factory/cam-1") == "factory/cam-1"


def test_validate_accepts_three_segments():
    assert _validate_stream_path("owner/machine/channel") == "owner/machine/channel"


def test_validate_accepts_processed_suffix():
    assert _validate_stream_path("factory/cam-1_processed") == "factory/cam-1_processed"


def test_validate_accepts_ip_address_segment():
    assert _validate_stream_path("huotai/zhongkong/10.37.192.5") == "huotai/zhongkong/10.37.192.5"


def test_validate_rejects_dot_segment():
    with pytest.raises(HTTPException) as exc:
        _validate_stream_path("factory/../secret")
    assert exc.value.status_code == 400


def test_validate_rejects_dotdot_segment():
    with pytest.raises(HTTPException) as exc:
        _validate_stream_path("factory/..")
    assert exc.value.status_code == 400


def test_build_whep_url_preserves_ip_segment():
    assert (
        _build_whep_url("http://localhost:8889", "huotai/zhongkong/10.37.192.5")
        == "http://localhost:8889/huotai/zhongkong/10.37.192.5/whep"
    )


def test_validate_rejects_invalid_segment():
    with pytest.raises(HTTPException) as exc:
        _validate_stream_path("bad path")
    assert exc.value.status_code == 400


def test_validate_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        _validate_stream_path("///")
    assert exc.value.status_code == 400


def test_build_whep_url_preserves_segments():
    assert (
        _build_whep_url("http://localhost:8889", "factory/cam-1")
        == "http://localhost:8889/factory/cam-1/whep"
    )


def test_build_whep_url_trailing_slash_base():
    assert (
        _build_whep_url("http://localhost:8889/", "cam1")
        == "http://localhost:8889/cam1/whep"
    )


async def test_delete_returns_204_without_body(async_client, monkeypatch):
    from backend.api import whep_proxy
    import httpx as httpx_lib

    async def fake_proxy(method, url, username, password, body=None, content_type=None):
        return httpx_lib.Response(204, content=b"unexpected upstream body")

    monkeypatch.setattr(whep_proxy, "_proxy_to_mediamtx", fake_proxy)

    resp = await async_client.delete(
        "/api/video/huotai/zhongkong/10.37.192.5/whep-session/sess-1"
    )
    assert resp.status_code == 204
    assert resp.content == b""


async def test_patch_discards_body_on_204(async_client, monkeypatch):
    from backend.api import whep_proxy
    import httpx as httpx_lib

    async def fake_proxy(method, url, username, password, body=None, content_type=None):
        return httpx_lib.Response(204, content=b"unexpected upstream body")

    monkeypatch.setattr(whep_proxy, "_proxy_to_mediamtx", fake_proxy)

    resp = await async_client.patch(
        "/api/video/huotai/zhongkong/10.37.192.5/whep-session/sess-1",
        content=b"v=0\r\n",
    )
    assert resp.status_code == 204
    assert resp.content == b""
