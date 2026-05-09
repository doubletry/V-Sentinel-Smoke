from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.models.schemas import (
    ProcessorPluginInfo,
    ProcessorStartRequest,
    ProcessorStatus,
    ProcessorStopRequest,
)
from backend.processing.log_buffer import processing_log_buffer
from backend.processing.registry import list_processor_plugins

router = APIRouter(prefix="/api/processor", tags=["processor"])


@router.post("/start", status_code=200)
async def start_processor(payload: ProcessorStartRequest, request: Request) -> dict:
    """Start AI analysis processing for a video source.
    为视频源启动 AI 分析处理。"""
    try:
        result = await request.app.state.processor_manager.start_processor(
            payload.source_id
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop", status_code=200)
async def stop_processor(payload: ProcessorStopRequest, request: Request) -> dict:
    """Stop AI analysis processing for a video source.
    停止视频源的 AI 分析处理。"""
    result = await request.app.state.processor_manager.stop_processor(payload.source_id)
    return result


@router.post("/start-all", status_code=200)
async def start_all_processors(request: Request) -> dict:
    """Start AI analysis for all configured sources.
    为所有已配置的视频源启动 AI 分析。"""
    result = await request.app.state.processor_manager.start_all_processors()
    return result


@router.post("/stop-all", status_code=200)
async def stop_all_processors(request: Request) -> dict:
    """Stop AI analysis for all running sources.
    停止所有正在运行的视频源 AI 分析。"""
    result = await request.app.state.processor_manager.stop_all_processors()
    return result


@router.get("/status", response_model=list[ProcessorStatus])
async def get_status(request: Request) -> list[ProcessorStatus]:
    """Get status of all running processors.
    获取所有运行中处理器的状态。"""
    return request.app.state.processor_manager.get_all_status()


@router.get("/plugins", response_model=list[ProcessorPluginInfo])
async def get_processor_plugins() -> list[ProcessorPluginInfo]:
    """Get available processor plugins with display metadata.
    获取可用处理器插件及其展示元数据。"""
    return list_processor_plugins()


@router.get("/logs")
async def get_processing_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> dict:
    """Get paginated runtime logs produced by backend processing modules.
    获取后台处理模块产生的分页运行日志。"""
    return processing_log_buffer.list(page=page, page_size=page_size)
