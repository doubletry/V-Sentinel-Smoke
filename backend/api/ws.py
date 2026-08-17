from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from backend.auth.security import verify_access_token
from backend.db.database import build_analysis_message_image_url, materialize_message_image
from backend.models.schemas import AnalysisMessage

router = APIRouter()


class WSManager:
    """WebSocket connection manager for real-time message broadcasting.
    用于实时消息广播的 WebSocket 连接管理器。"""

    def __init__(
        self,
        persist_message: Callable[[AnalysisMessage], Awaitable[str | None]] | None = None,
    ) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._persist_message = persist_message

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.
        接受并注册新的 WebSocket 连接。"""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(
            "WebSocket client connected. Total: {}", len(self._connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active set.
        从活跃连接集合中移除 WebSocket 连接。"""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(
            "WebSocket client disconnected. Total: {}", len(self._connections)
        )

    @staticmethod
    def _resolve_image_urls(message: AnalysisMessage) -> None:
        """Normalise incoming image fields into the canonical ``*_url`` fields.
        将传入的多种图片字段归一化为标准 ``*_url`` 字段。

        Supports three input shapes from different processors:
        支持不同处理器的三种输入格式：

        1. ``detected_image_url``  (already a URL)
        2. ``detected_image_base64``  (inline base64)
        3. ``image_base64`` / ``image_url``  (legacy fallback)

        After this call, base64 fields are cleared once materialised.
        """
        # ── Detected image: prefer explicit URL, then base64, then legacy fallback ──
        # 检测图：优先使用显式 URL，其次 base64，最后从旧版字段回退
        if not message.detected_image_url:
            if message.detected_image_base64:
                message.detected_image_url = materialize_message_image(
                    message.detected_image_base64,
                    timestamp=message.timestamp,
                )
            elif message.image_base64:
                message.detected_image_base64 = message.image_base64
                message.detected_image_url = materialize_message_image(
                    message.detected_image_base64,
                    timestamp=message.timestamp,
                )
            elif message.image_url:
                message.detected_image_url = message.image_url

        # Clear base64 once materialised / URL 化后清除 base64
        if message.detected_image_url:
            message.detected_image_base64 = None

        # ── Original image / 原图 ──
        if message.original_image_base64 and not message.original_image_url:
            message.original_image_url = materialize_message_image(
                message.original_image_base64,
                timestamp=message.timestamp,
            )
            if message.original_image_url:
                message.original_image_base64 = None

        # ── Canonical shortcuts / 标准快捷字段 ──
        message.image_url = message.detected_image_url or message.image_url
        message.image_base64 = (
            None if message.detected_image_url
            else (message.detected_image_base64 or message.image_base64)
        )

    async def broadcast(self, message: AnalysisMessage) -> None:
        """Send a message to all connected WebSocket clients.
        向所有已连接的 WebSocket 客户端发送消息。"""
        self._resolve_image_urls(message)

        # Persist to DB / 持久化到数据库
        message_id: str | None = None
        if self._persist_message is not None:
            message_id = await self._persist_message(message)
        if message_id:
            message.id = message_id

        # Override URLs with public API URLs / 用公共 API URL 覆盖
        if message_id and message.detected_image_url:
            public_url = build_analysis_message_image_url(message_id)
            message.detected_image_url = public_url
            message.image_url = public_url
        if message_id and message.original_image_url:
            message.original_image_url = build_analysis_message_image_url(
                message_id,
                kind="original",
            )

        # Broadcast to all clients / 广播到所有客户端
        payload = message.model_dump_json()
        dead: list[WebSocket] = []
        async with self._lock:
            connections = set(self._connections)
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


@router.websocket("/ws/messages")
async def ws_messages_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time analysis message streaming.
    用于实时分析消息推送的 WebSocket 端点。

    Requires a valid Bearer token passed as the ``token`` query parameter.
    需要通过 ``token`` 查询参数传递有效的 Bearer 令牌。

    Example / 示例::

        ws://host/ws/messages?token=<access_token>
    """
    from backend.main import ws_manager  # avoid circular imports / 避免循环导入

    # ── Authenticate via query parameter / 通过查询参数认证 ──
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        verify_access_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can send pings / 保持连接活跃；客户端可发送 ping
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)
