from __future__ import annotations

from typing import TYPE_CHECKING

from backend.models.schemas import ROI
from backend.processing.base import BaseVideoProcessor
from core.fire_door.processor import FireDoorProcessor as _CoreFireDoorProcessor

if TYPE_CHECKING:
    from backend.api.ws import WSManager
    from backend.processing.agent import AnalysisAgent
    from backend.vengine.client import AsyncVEngineClient


class FireDoorProcessor(BaseVideoProcessor, _CoreFireDoorProcessor):
    """Backend adapter for the fire-door classification plugin."""

    def __init__(
        self,
        source_id: str,
        source_name: str,
        rtsp_url: str,
        rois: list[ROI],
        vengine_client: "AsyncVEngineClient",
        ws_manager: "WSManager",
        app_settings: dict[str, str],
        agent: "AnalysisAgent | None" = None,
        source_remark: str = "",
    ) -> None:
        super().__init__(
            source_id=source_id,
            source_name=source_name,
            rtsp_url=rtsp_url,
            rois=rois,
            vengine_client=vengine_client,
            ws_manager=ws_manager,
            app_settings=app_settings,
            agent=agent,
            source_remark=source_remark,
        )

