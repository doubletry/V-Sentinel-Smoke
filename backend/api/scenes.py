from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import require_permission
from backend.db import database as db
from backend.models.schemas import SceneDefinition

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.get("", response_model=list[SceneDefinition])
async def list_scenes(
    _role: str = Depends(require_permission("sources:read")),
) -> list[SceneDefinition]:
    """List available processing scenes.
    列出可用处理场景。"""
    return await db.list_scenes()


@router.get("/{scene_id}", response_model=SceneDefinition)
async def get_scene(
    scene_id: str,
    _role: str = Depends(require_permission("sources:read")),
) -> SceneDefinition:
    """Get one processing scene definition.
    获取单个处理场景定义。"""
    scene = await db.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene
