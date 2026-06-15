from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import require_permission
from backend.db import database as db
from backend.models.schemas import VideoGateway, VideoGatewayCreate, VideoGatewayUpdate

router = APIRouter(prefix="/api/video-gateways", tags=["video-gateways"])


@router.get("", response_model=list[VideoGateway])
async def list_video_gateways(
    _role: str = Depends(require_permission("gateways:*")),
) -> list[VideoGateway]:
    """List configured video gateways.
    列出已配置视频网关。"""
    return await db.list_video_gateways()


@router.post("", response_model=VideoGateway, status_code=201)
async def create_video_gateway(
    data: VideoGatewayCreate,
    _role: str = Depends(require_permission("gateways:*")),
) -> VideoGateway:
    """Create a video gateway with shared RTSP/WebRTC credentials.
    创建 RTSP/WebRTC 共享凭据的视频网关。"""
    return await db.create_video_gateway(data)


@router.put("/{gateway_id}", response_model=VideoGateway)
async def update_video_gateway(
    gateway_id: str,
    data: VideoGatewayUpdate,
    _role: str = Depends(require_permission("gateways:*")),
) -> VideoGateway:
    """Update a video gateway.
    更新视频网关。"""
    gateway = await db.update_video_gateway(gateway_id, data)
    if gateway is None:
        raise HTTPException(status_code=404, detail="Video gateway not found")
    return gateway
