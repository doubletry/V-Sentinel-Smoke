from __future__ import annotations

from fastapi import FastAPI
from loguru import logger

from backend.db import database as db


async def update_runtime_settings(app: FastAPI, updates: dict[str, str]) -> dict[str, str]:
    previous_settings = await db.get_all_settings()
    result = await db.update_settings(updates)
    app.title = result.get("site_title") or app.title

    if "message_retention_days" in updates:
        try:
            await db.prune_analysis_messages(int(result.get("message_retention_days", "7")))
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid message retention days while pruning: {}", exc)

    mediamtx_rtsp_keys = {
        "mediamtx_rtsp_addr",
        "mediamtx_rtsp_username",
        "mediamtx_rtsp_password",
    }
    if mediamtx_rtsp_keys.intersection(updates):
        await db.rewrite_source_rtsp_urls(
            old_rtsp_base_address=previous_settings.get("mediamtx_rtsp_addr", ""),
            new_rtsp_base_address=result.get("mediamtx_rtsp_addr", ""),
            new_rtsp_username=result.get("mediamtx_rtsp_username", ""),
            new_rtsp_password=result.get("mediamtx_rtsp_password", ""),
        )

    await app.state.vengine_client.reconnect_from_settings(result)
    await app.state.email_client.reconnect_from_settings(result)
    app.state.processor_manager.update_app_settings(result)
    return result
