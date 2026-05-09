"""Smoke/fire scene constants.
烟火场景常量。"""

SMOKE_LABEL = "smoke"
FIRE_LABEL = "fire"
SMOKE_FIRE_LABELS = {SMOKE_LABEL, FIRE_LABEL}
DEFAULT_DETECTION_MODEL = "smoke-fire-detection"
LABEL_TO_ZH = {
    SMOKE_LABEL: "烟雾",
    FIRE_LABEL: "火焰",
}
