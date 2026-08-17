from __future__ import annotations

import re
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger

from backend.auth.dependencies import current_user, require_permission
from backend.db import database as db
from backend.models.schemas import CurrentUser

router = APIRouter(prefix="/api/video", tags=["whep-proxy"])

_MEDIAMTX_TIMEOUT = 15.0
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _build_mediamtx_creds(settings: dict[str, str]) -> tuple[str, str, str]:
    webrtc_base = str(settings.get("mediamtx_webrtc_addr") or "")
    username = str(settings.get("mediamtx_username") or "")
    password = str(settings.get("mediamtx_password") or "")
    return webrtc_base, username, password


def _build_whep_url(webrtc_base: str, stream_path: str) -> str:
    base = webrtc_base.rstrip("/")
    return f"{base}/{quote(stream_path, safe='')}/whep"


def _validate_stream_path(stream_path: str) -> str:
    segments = [s for s in stream_path.split("/") if s]
    if len(segments) != 3:
        raise HTTPException(
            status_code=400,
            detail="stream_path must be three segments: owner/machine/channel",
        )
    for segment in segments:
        if not _PATH_SEGMENT_RE.match(segment):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path segment: {segment}",
            )
    return "/".join(segments)


async def _proxy_to_mediamtx(
    method: str,
    url: str,
    username: str,
    password: str,
    body: bytes | None = None,
    content_type: str | None = None,
) -> httpx.Response:
    auth = httpx.BasicAuth(username, password) if username else None
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    async with httpx.AsyncClient(timeout=httpx.Timeout(_MEDIAMTX_TIMEOUT)) as client:
        return await client.request(method, url, headers=headers, content=body, auth=auth)


@router.post("/{stream_path:path}/whep-offer")
async def whep_offer(
    stream_path: str,
    request: Request,
    _me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_permission("video:watch")),
) -> Response:
    normalized_path = _validate_stream_path(stream_path)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="SDP offer body is required")

    app_settings = await db.get_all_settings()
    webrtc_base, username, password = _build_mediamtx_creds(app_settings)
    if not webrtc_base:
        raise HTTPException(status_code=502, detail="WebRTC gateway address is not configured")

    whep_url = _build_whep_url(webrtc_base, normalized_path)
    logger.debug("WHEP proxy POST {} (user={})", normalized_path, _me.username)

    try:
        upstream = await _proxy_to_mediamtx(
            "POST",
            whep_url,
            username,
            password,
            body=body,
            content_type="application/sdp",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream WHEP request timed out")
    except httpx.RequestError as exc:
        logger.warning("WHEP proxy POST {} failed: {}", normalized_path, exc)
        raise HTTPException(status_code=502, detail="Upstream WHEP request failed")

    if upstream.status_code == 404:
        raise HTTPException(status_code=404, detail="Stream not found")
    if upstream.status_code == 401 or upstream.status_code == 403:
        raise HTTPException(status_code=502, detail="Upstream authentication failed")
    if upstream.status_code != 201:
        raise HTTPException(status_code=502, detail=f"Upstream WHEP error: {upstream.status_code}")

    response = Response(
        content=upstream.content,
        status_code=200,
        media_type="application/sdp",
    )
    location = upstream.headers.get("location", "")
    if location:
        response.headers["X-Whep-Session-Location"] = location
    return response


@router.patch("/{stream_path:path}/whep-session/{session_id}")
async def whep_patch(
    stream_path: str,
    session_id: str,
    request: Request,
    _me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_permission("video:watch")),
) -> Response:
    normalized_path = _validate_stream_path(stream_path)
    body = await request.body()

    app_settings = await db.get_all_settings()
    webrtc_base, username, password = _build_mediamtx_creds(app_settings)
    if not webrtc_base:
        raise HTTPException(status_code=502, detail="WebRTC gateway address is not configured")

    whep_url = _build_whep_url(webrtc_base, normalized_path)
    # MediaMTX session URL uses the WHEP session ID
    session_url = f"{whep_url}/{quote(session_id, safe='')}"

    try:
        upstream = await _proxy_to_mediamtx(
            "PATCH",
            session_url,
            username,
            password,
            body=body,
            content_type=request.headers.get("Content-Type", "application/trickle-ice-sdpfrag"),
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream WHEP PATCH timed out")
    except httpx.RequestError as exc:
        logger.warning("WHEP proxy PATCH {}/{} failed: {}", normalized_path, session_id, exc)
        raise HTTPException(status_code=502, detail="Upstream WHEP PATCH failed")

    return Response(content=upstream.content, status_code=upstream.status_code)


@router.delete("/{stream_path:path}/whep-session/{session_id}")
async def whep_delete(
    stream_path: str,
    session_id: str,
    _me: CurrentUser = Depends(current_user),
    _role: str = Depends(require_permission("video:watch")),
) -> Response:
    normalized_path = _validate_stream_path(stream_path)

    app_settings = await db.get_all_settings()
    webrtc_base, username, password = _build_mediamtx_creds(app_settings)
    if not webrtc_base:
        raise HTTPException(status_code=502, detail="WebRTC gateway address is not configured")

    whep_url = _build_whep_url(webrtc_base, normalized_path)
    session_url = f"{whep_url}/{quote(session_id, safe='')}"

    try:
        upstream = await _proxy_to_mediamtx(
            "DELETE",
            session_url,
            username,
            password,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream WHEP DELETE timed out")
    except httpx.RequestError as exc:
        logger.warning("WHEP proxy DELETE {}/{} failed: {}", normalized_path, session_id, exc)
        raise HTTPException(status_code=502, detail="Upstream WHEP DELETE failed")

    return Response(content=upstream.content, status_code=204)
