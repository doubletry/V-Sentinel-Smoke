from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from backend.auth.dependencies import require_permission
from backend.models.schemas import (
    ProcessorStartRequest,
    ProcessorStatus,
    ProcessorStopRequest,
    ProcessorPushToggleRequest,
)

router = APIRouter(prefix="/api/processor", tags=["processor"])


@router.post("/start", status_code=200)
async def start_processor(
    request: ProcessorStartRequest,
    _role: str = Depends(require_permission("sources:operate")),
) -> dict:
    """Start AI analysis processing for a video source.
    为视频源启动 AI 分析处理。"""
    from backend.main import processor_manager  # avoid circular imports at module level

    try:
        result = await processor_manager.start_processor(request.source_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.opt(exception=True).warning(
            "Failed to start processor: source={}", request.source_id
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop", status_code=200)
async def stop_processor(
    request: ProcessorStopRequest,
    _role: str = Depends(require_permission("sources:operate")),
) -> dict:
    """Stop AI analysis processing for a video source.
    停止视频源的 AI 分析处理。"""
    from backend.main import processor_manager

    result = await processor_manager.stop_processor(request.source_id)
    return result


@router.get("/status", response_model=list[ProcessorStatus])
async def get_status(
    _role: str = Depends(require_permission("sources:read")),
) -> list[ProcessorStatus]:
    """Get status of all running processors.
    获取所有运行中处理器的状态。"""
    from backend.main import processor_manager

    return processor_manager.get_all_status()


@router.post("/{source_id}/push-result-stream", status_code=200)
async def toggle_push_result_stream(
    source_id: str,
    request: ProcessorPushToggleRequest,
    _role: str = Depends(require_permission("sources:operate")),
) -> dict:
    """Enable or disable push at runtime without restarting analysis.
    运行时启用或禁用推流，无需重启分析进程。"""
    from backend.main import processor_manager

    try:
        result = await processor_manager.toggle_push_result_stream(source_id, request.enabled)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.opt(exception=True).warning(
            "Failed to toggle push result stream: source={}", source_id
        )
        raise HTTPException(status_code=500, detail=str(exc))
