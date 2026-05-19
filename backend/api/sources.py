from __future__ import annotations

import re
from urllib.parse import quote

import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response

from backend.auth.dependencies import require_permission
from backend.db import database as db
from backend.models.schemas import (
    VideoSource,
    VideoSourceCreate,
    VideoSourceUpdate,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.post("", response_model=VideoSource, status_code=201)
async def create_source(
    source: VideoSourceCreate,
    _role: str = Depends(require_permission("sources:operate")),
) -> VideoSource:
    """Create a new video source.
    创建新的视频源。"""
    try:
        return await db.create_source(source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(
                status_code=409, detail="A source with this RTSP URL already exists"
            )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("", response_model=list[VideoSource])
async def list_sources() -> list[VideoSource]:
    """List all video sources.
    列出所有视频源。"""
    return await db.list_sources()


@router.get("/by-rtsp", response_model=VideoSource)
async def get_source_by_rtsp(rtsp_url: str) -> VideoSource:
    """Get a video source by its RTSP URL.
    按 RTSP URL 获取视频源。"""
    source = await db.get_source_by_rtsp(rtsp_url)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.get("/{source_id}", response_model=VideoSource)
async def get_source(source_id: str) -> VideoSource:
    """Get a single video source with its ROIs.
    获取单个视频源及其 ROI。"""
    source = await db.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=VideoSource)
async def update_source(
    source_id: str,
    data: VideoSourceUpdate,
    _role: str = Depends(require_permission("sources:operate")),
) -> VideoSource:
    """Update a video source (name, rtsp_url, and/or ROIs).
    更新视频源（名称、RTSP URL 和/或 ROI）。"""
    try:
        source = await db.update_source(source_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    _role: str = Depends(require_permission("sources:operate")),
) -> None:
    """Delete a video source.
    删除视频源。"""
    deleted = await db.delete_source(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")


# ── ROI Import / Export (YAML) / ROI 导入/导出 (YAML) ──────────────────────────


@router.get("/{source_id}/rois/export")
async def export_rois_yaml(source_id: str) -> Response:
    """Export ROIs for a video source as a downloadable YAML file.
    将视频源的 ROI 导出为可下载的 YAML 文件。"""
    source = await db.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    rois_data = [
        {
            "type": roi.type,
            "tag": roi.tag,
            "points": [{"x": round(p.x, 6), "y": round(p.y, 6)} for p in roi.points],
        }
        for roi in source.rois
    ]
    payload = {
        "source_name": source.name,
        "rois": rois_data,
    }
    yaml_content = yaml.dump(payload, allow_unicode=True, sort_keys=False)
    # Build an ASCII-safe fallback filename for the header, while preserving the
    # UTF-8 filename via RFC 5987.
    # 构建 ASCII 安全的回退文件名，并通过 RFC 5987 保留 UTF-8 文件名。
    utf8_filename = f"{source.name or 'rois'}_rois.yaml"
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", source.name).strip() or "rois"
    ascii_filename = f"{safe_name}_rois.yaml"
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_filename}"; '
                f"filename*=UTF-8''{quote(utf8_filename)}"
            )
        },
    )


@router.post("/{source_id}/rois/import")
async def import_rois_yaml(
    source_id: str,
    file: UploadFile = File(...),
    _role: str = Depends(require_permission("sources:operate")),
) -> VideoSource:
    """Import ROIs from a YAML file into a video source.
    从 YAML 文件导入 ROI 到视频源。

    Validates that every ``tag`` in the YAML is present in the source scene's
    plugin-owned ``default_roi_tags``. Rejects the import if any tag is unknown.
    验证 YAML 中的每个标签是否存在于视频源场景插件自己的
    ``default_roi_tags`` 中，如有未知标签则拒绝导入。
    """
    source = await db.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    # Read and parse YAML / 读取并解析 YAML
    try:
        raw = await file.read()
        data = yaml.safe_load(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML file: {exc}")

    if not isinstance(data, dict) or "rois" not in data:
        raise HTTPException(
            status_code=400,
            detail='YAML must contain a top-level "rois" list',
        )

    rois_raw = data["rois"]
    if not isinstance(rois_raw, list):
        raise HTTPException(status_code=400, detail='"rois" must be a list')

    # ROI tags are owned by the bound scene/plugin, not global platform settings.
    # ROI 标签由当前绑定的场景/插件拥有，而不是平台全局设置。
    scene = await db.get_scene(source.scene_id)
    valid_tags = set(scene.default_roi_tags if scene else [])

    # Validate each ROI entry / 验证每个 ROI 条目
    validated_rois: list[dict] = []
    for idx, roi in enumerate(rois_raw):
        if not isinstance(roi, dict):
            raise HTTPException(
                status_code=400,
                detail=f"ROI at index {idx} is not an object",
            )
        roi_type = roi.get("type", "polygon")
        if roi_type not in ("polygon", "rectangle"):
            raise HTTPException(
                status_code=400,
                detail=f'ROI at index {idx}: type must be "polygon" or "rectangle"',
            )
        tag = str(roi.get("tag", "")).strip()
        if not tag:
            raise HTTPException(
                status_code=400,
                detail=f"ROI at index {idx}: tag is required",
            )
        if tag not in valid_tags:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'ROI at index {idx}: tag "{tag}" is not in the '
                    f"scene '{source.scene_id}' ROI tag options: {sorted(valid_tags)}"
                ),
            )
        points = roi.get("points", [])
        if not isinstance(points, list) or len(points) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"ROI at index {idx}: must have at least 2 points",
            )
        validated_points = []
        for pidx, p in enumerate(points):
            if not isinstance(p, dict) or "x" not in p or "y" not in p:
                raise HTTPException(
                    status_code=400,
                    detail=f"ROI {idx}, point {pidx}: must have x and y",
                )
            validated_points.append({"x": float(p["x"]), "y": float(p["y"])})
        validated_rois.append(
            {"type": roi_type, "tag": tag, "points": validated_points}
        )

    # Update source with imported ROIs / 使用导入的 ROI 更新视频源
    update_data = VideoSourceUpdate(rois=validated_rois)
    updated_source = await db.update_source(source_id, update_data)
    if updated_source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return updated_source
