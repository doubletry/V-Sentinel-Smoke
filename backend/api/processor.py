from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import require_permission
from backend.models.schemas import (
    ProcessorStartRequest,
    ProcessorStatus,
    ProcessorStopRequest,
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
