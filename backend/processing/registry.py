from __future__ import annotations

from typing import Type

from backend.processing.base import BaseVideoProcessor
from backend.processing.example import ExampleProcessor
from backend.processing.fire_door import FireDoorProcessor
from backend.processing.smoke import SmokeFireProcessor
from backend.processing.template import TemplateSceneProcessor


PROCESSOR_PLUGINS: dict[str, Type[BaseVideoProcessor]] = {
    "example": ExampleProcessor,
    "fire_door": FireDoorProcessor,
    "smoke": SmokeFireProcessor,
    "template": TemplateSceneProcessor,
}

def resolve_processor_class(plugin_name: str) -> Type[BaseVideoProcessor]:
    """Resolve a processor plugin name to its backend adapter class.
    将处理器插件名称解析为对应的 backend 适配类。"""
    try:
        return PROCESSOR_PLUGINS[plugin_name]
    except KeyError as exc:
        available = ", ".join(sorted(PROCESSOR_PLUGINS))
        raise ValueError(
            f"Unknown processor plugin: {plugin_name}. Available: {available}"
        ) from exc
