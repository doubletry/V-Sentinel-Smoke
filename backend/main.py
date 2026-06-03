from __future__ import annotations

import asyncio
import re
import sys
from contextlib import asynccontextmanager, suppress
import os
from pathlib import Path
from pathlib import PurePosixPath

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from loguru import logger

from backend.audit import audit_request
from backend.api import access as access_router
from backend.api import auth as auth_router
from backend.api import notifications as notifications_router
from backend.api import processor as processor_router
from backend.api import messages as messages_router
from backend.api import scenes as scenes_router
from backend.api import settings as settings_router
from backend.api import sources as sources_router
from backend.api import users as users_router
from backend.api import video_gateways as video_gateways_router
from backend.api import ws as ws_module
from backend.config import settings
from backend.db.database import (
    close_db,
    get_all_settings,
    init_db,
    save_analysis_message,
)
from backend.notifications.dispatcher import NotificationDispatcher
from backend.processing.manager import ProcessorManager
from backend.vengine.client import AsyncVEngineClient

# Configure loguru / 配置 loguru 日志
logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True)

# Module-level singletons (accessed by API routers) / 模块级单例（供 API 路由使用）
ws_manager: ws_module.WSManager
vengine_client: AsyncVEngineClient
notification_dispatcher: NotificationDispatcher
processor_manager: ProcessorManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and teardown resources.
    应用生命周期：初始化与销毁资源。"""
    global ws_manager, vengine_client, notification_dispatcher, processor_manager

    logger.info("Starting {} ...", settings.app_name)

    # Initialize WebSocket manager / 初始化 WebSocket 管理器
    async def _persist_message(message) -> str:
        return await save_analysis_message(message.model_dump())

    ws_manager = ws_module.WSManager(persist_message=_persist_message)

    # Initialize database / 初始化数据库
    await init_db()

    # Initialize V-Engine async gRPC client (addresses from DB settings)
    # 初始化 V-Engine 异步 gRPC 客户端（地址来自数据库设置）
    app_settings = await get_all_settings()
    app.title = app_settings.get("site_title") or settings.app_name
    vengine_client = AsyncVEngineClient(settings)
    await vengine_client.connect(app_settings)
    notification_dispatcher = NotificationDispatcher()

    # Store on app.state for dependency-injection in API routes / 存储到 app.state 以便 API 路由依赖注入
    app.state.vengine_client = vengine_client
    app.state.notification_dispatcher = notification_dispatcher

    # Initialize ProcessorManager (includes AnalysisAgent) / 初始化处理器管理器（含分析代理）
    processor_manager = ProcessorManager(
        vengine_client=vengine_client,
        ws_manager=ws_manager,
        app_settings=app_settings,
        notification_dispatcher=notification_dispatcher,
    )
    app.state.processor_manager = processor_manager
    await processor_manager.start_agent()
    restore_processors_task = asyncio.create_task(processor_manager.restore_desired_processors())
    app.state.restore_processors_task = restore_processors_task

    logger.info("{} started successfully", settings.app_name)
    yield

    # ── Shutdown / 关闭 ─────────────────────────────────────────────────
    logger.info("Shutting down {} ...", settings.app_name)

    restore_processors_task.cancel()
    with suppress(asyncio.CancelledError):
        await restore_processors_task
    await processor_manager.stop_all()
    await processor_manager.stop_agent()
    await vengine_client.close()
    await close_db()

    logger.info("{} shutdown complete", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="AI Video Surveillance Analysis Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(audit_request)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(sources_router.router)
app.include_router(scenes_router.router)
app.include_router(video_gateways_router.router)
app.include_router(notifications_router.router)
app.include_router(access_router.router)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(processor_router.router)
app.include_router(messages_router.router)
app.include_router(settings_router.router)
app.include_router(ws_module.router)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint.
    健康检查端点。"""
    return {"status": "ok", "app": app.title}


# ── Static files (production: serve built frontend) / 静态文件（生产环境：托管构建后的前端） ──
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
_frontend_index = _frontend_dist / "index.html"
_BASE_TAG_RE = re.compile(r"<base\b[^>]*>", re.IGNORECASE)
_HEAD_TAG_RE = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)
_SAFE_BASE_PATH_RE = re.compile(r"^/(?:[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)?$")


def _normalize_base_path(value: str | None) -> str:
    text = str(value or "").strip()
    if not text or text == "/":
        return ""
    prefixed = text if text.startswith("/") else f"/{text}"
    normalized = prefixed.rstrip("/")
    if not _SAFE_BASE_PATH_RE.fullmatch(normalized):
        return ""
    return normalized


def _frontend_base_path() -> str:
    return _normalize_base_path(os.environ.get("VITE_APP_BASE_PATH") or os.environ.get("APP_BASE_PATH"))


def _render_frontend_index() -> str:
    if not _frontend_index.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    html = _frontend_index.read_text(encoding="utf-8")
    base_path = _frontend_base_path()
    base_href = f"{base_path}/" if base_path else "/"
    base_tag = f'<base href="{base_href}" />'
    if _BASE_TAG_RE.search(html):
        html = _BASE_TAG_RE.sub(base_tag, html, count=1)
    else:
        def _insert_base_tag(match: re.Match[str]) -> str:
            return f"{match.group(0)}{base_tag}"

        html, count = _HEAD_TAG_RE.subn(_insert_base_tag, html, count=1)
        if count == 0:
            raise HTTPException(status_code=500, detail="Invalid frontend index")
    return html


def _resolve_frontend_asset(full_path: str) -> Path | None:
    requested = str(full_path or "").strip()
    if not requested or "\\" in requested:
        return None
    pure_path = PurePosixPath("/" + requested.lstrip("/"))
    safe_parts = [part for part in pure_path.parts if part not in {"", "/"}]
    if not safe_parts or any(part in {".", ".."} for part in safe_parts):
        return None
    candidate = _frontend_dist.resolve().joinpath(*safe_parts).resolve()
    try:
        candidate.relative_to(_frontend_dist.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


if _frontend_index.is_file():
    logger.info("Serving frontend from {}", _frontend_dist)


@app.get("/", include_in_schema=False)
async def frontend_index() -> Response:
    return HTMLResponse(_render_frontend_index())


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str) -> Response:
    if full_path in {"docs", "redoc", "openapi.json"} or full_path.startswith(("api/", "ws/")):
        raise HTTPException(status_code=404, detail="Not Found")
    if not _frontend_index.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    asset_path = _resolve_frontend_asset(full_path)
    if asset_path is not None:
        return FileResponse(asset_path)
    if "." in Path(full_path).name:
        raise HTTPException(status_code=404, detail="Not Found")

    return HTMLResponse(_render_frontend_index())
