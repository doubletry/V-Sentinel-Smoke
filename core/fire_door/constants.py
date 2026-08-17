"""Fire safety door classification constants."""
from __future__ import annotations

DEFAULT_CLASSIFICATION_MODEL = "fire-door-classification"
FIRE_DOOR_ROI_TAG = "fire_door"
DEFAULT_OPEN_LABELS = ("open",)
DEFAULT_CLOSED_LABELS = ("closed",)
DEFAULT_ALARM_LABELS = ("open",)

DEFAULT_VL_CONFIRM_PROMPT = (
    "This image was flagged as a potential OPEN door. Verify the detection. "
    "A door is OPEN if the door panel is visibly separated from the frame, "
    "showing a clear gap or opening (you can see a darker space behind/beside the panel). "
    "A door is CLOSED if the panel is flush within the frame with no visible opening. "
    "Only confirm OPEN if you can clearly see the gap. "
    'Reply with ONLY: {"open": true} or {"open": false}.'
)
DEFAULT_VL_CONFIRM_RESPONSE_KEY = "open"

