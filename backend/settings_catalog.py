from __future__ import annotations

from copy import deepcopy


SETTINGS_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "id": "interface",
        "title_key": "settings.interface",
        "fields": (
            {
                "key": "ui_language",
                "default": "zh-CN",
                "input": "select",
                "options": ("zh-CN", "en-US"),
            },
            {"key": "timezone", "default": "Asia/Shanghai", "input": "text"},
            {"key": "site_title", "default": "V-Sentinel", "input": "text"},
            {
                "key": "site_description",
                "default": "AI Video Surveillance Analysis Platform",
                "input": "text",
            },
            {"key": "favicon_url", "default": "/favicon.ico", "input": "text"},
            {
                "key": "roi_tag_options",
                "default": '["person", "vehicle", "intrusion"]',
                "input": "json",
            },
        ),
    },
    {
        "id": "backend_service",
        "title_key": "settings.backendService",
        "fields": (
            {"key": "processor_plugin", "default": "smoke", "input": "text"},
            {"key": "max_pull_workers", "default": "20", "input": "number"},
            {"key": "max_push_workers", "default": "10", "input": "number"},
            {"key": "max_cpu_workers", "default": "16", "input": "number"},
        ),
    },
    {
        "id": "vengine_services",
        "title_key": "settings.vengineServices",
        "fields": (
            {"key": "vengine_host", "default": "localhost", "input": "text"},
            {"key": "detection_port", "default": "50051", "input": "number"},
            {"key": "detection_enabled", "default": "true", "input": "boolean"},
            {"key": "classification_port", "default": "50052", "input": "number"},
            {"key": "classification_enabled", "default": "false", "input": "boolean"},
            {"key": "action_port", "default": "50053", "input": "number"},
            {"key": "action_enabled", "default": "false", "input": "boolean"},
            {"key": "ocr_port", "default": "50054", "input": "number"},
            {"key": "ocr_enabled", "default": "false", "input": "boolean"},
            {"key": "upload_port", "default": "50050", "input": "number"},
            {"key": "upload_enabled", "default": "false", "input": "boolean"},
        ),
    },
    {
        "id": "mediamtx",
        "title_key": "settings.mediamtx",
        "fields": (
            {
                "key": "mediamtx_rtsp_addr",
                "default": "rtsp://localhost:8554",
                "input": "text",
            },
            {"key": "mediamtx_rtsp_username", "default": "", "input": "text"},
            {"key": "mediamtx_rtsp_password", "default": "", "input": "secret"},
            {
                "key": "mediamtx_webrtc_addr",
                "default": "http://localhost:8889",
                "input": "text",
            },
            {"key": "mediamtx_webrtc_username", "default": "", "input": "text"},
            {"key": "mediamtx_webrtc_password", "default": "", "input": "secret"},
        ),
    },
    {
        "id": "notifications",
        "title_key": "settings.emailNotifications",
        "fields": (
            {"key": "email_from_address", "default": "", "input": "text"},
            {"key": "email_from_auth_code", "default": "", "input": "secret"},
            {"key": "email_to_addresses", "default": "", "input": "text"},
            {"key": "email_cc_addresses", "default": "", "input": "text"},
            {"key": "email_port", "default": "50055", "input": "number"},
            {"key": "email_event_enabled", "default": "true", "input": "boolean"},
            {"key": "email_timed_enabled", "default": "false", "input": "boolean"},
            {
                "key": "email_event_subject_template",
                "default": "[{site_title}] {event_label} alert from {source_name}",
                "input": "text",
            },
            {
                "key": "email_event_body_template",
                "default": (
                    "Event: {event_label}\n"
                    "Time: {local_time} ({timezone})\n"
                    "Video source: {source_name} ({source_id})\n"
                    "Labels: {labels}\n"
                    "Highest confidence: {confidence_percent}\n"
                    "Detection count: {detection_count}\n"
                    "Frame ID: {frame_id}\n"
                    "Active tracks: {active_tracks}"
                ),
                "input": "textarea",
            },
            {
                "key": "message_retention_days",
                "default": "7",
                "input": "select",
                "options": ("1", "3", "7", "14", "30"),
            },
        ),
    },
    {
        "id": "smoke_scene",
        "title_key": "settings.smokeScene",
        "fields": (
            {
                "key": "smoke_detection_model_name",
                "default": "smoke-fire-detection",
                "input": "text",
            },
            {"key": "smoke_detection_model_version", "default": "", "input": "text"},
            {"key": "smoke_detection_confidence", "default": "0.35", "input": "number"},
            {"key": "smoke_detection_nms", "default": "0.7", "input": "number"},
            {"key": "smoke_min_confidence_smoke", "default": "0.35", "input": "number"},
            {"key": "smoke_min_confidence_fire", "default": "0.40", "input": "number"},
            {
                "key": "smoke_temporal_confirm_frames",
                "default": "3",
                "input": "number",
            },
            {
                "key": "smoke_temporal_confirm_window",
                "default": "2.0",
                "input": "number",
            },
            {"key": "smoke_max_miss_frames", "default": "5", "input": "number"},
            {"key": "smoke_alarm_hold_time", "default": "3.0", "input": "number"},
            {
                "key": "smoke_enable_appearance_filter",
                "default": "true",
                "input": "boolean",
            },
            {
                "key": "smoke_min_bbox_area_ratio",
                "default": "0.0005",
                "input": "number",
            },
            {
                "key": "smoke_max_bbox_area_ratio",
                "default": "0.60",
                "input": "number",
            },
            {"key": "smoke_min_aspect_ratio", "default": "0.2", "input": "number"},
            {"key": "smoke_max_aspect_ratio", "default": "8.0", "input": "number"},
            {
                "key": "smoke_motion_blur_max_speed",
                "default": "100.0",
                "input": "number",
            },
            {
                "key": "smoke_motion_blur_min_confidence",
                "default": "0.65",
                "input": "number",
            },
            {
                "key": "smoke_appearance_min_score",
                "default": "0.42",
                "input": "number",
            },
            {
                "key": "smoke_appearance_min_history",
                "default": "2",
                "input": "number",
            },
            {
                "key": "smoke_appearance_high_confidence_bypass",
                "default": "0.82",
                "input": "number",
            },
            {
                "key": "smoke_overexposed_ratio_threshold",
                "default": "0.18",
                "input": "number",
            },
            {
                "key": "smoke_white_object_ratio_threshold",
                "default": "0.62",
                "input": "number",
            },
            {
                "key": "smoke_hard_boundary_density_threshold",
                "default": "0.14",
                "input": "number",
            },
            {
                "key": "smoke_hard_laplacian_threshold",
                "default": "520.0",
                "input": "number",
            },
            {
                "key": "smoke_fast_motion_energy_threshold",
                "default": "0.16",
                "input": "number",
            },
            {
                "key": "smoke_static_confirm_frames",
                "default": "5",
                "input": "number",
            },
            {
                "key": "smoke_static_max_center_shift",
                "default": "10.0",
                "input": "number",
            },
            {
                "key": "smoke_static_max_area_change_ratio",
                "default": "0.08",
                "input": "number",
            },
            {"key": "smoke_iou_threshold", "default": "0.3", "input": "number"},
            {
                "key": "smoke_email_cooldown_seconds",
                "default": "300",
                "input": "number",
            },
        ),
    },
)


def _serialize_section(section: dict[str, object]) -> dict[str, object]:
    return {
        "id": section["id"],
        "title_key": section["title_key"],
        "fields": [dict(field) for field in section["fields"]],
    }


def get_default_app_settings() -> dict[str, str]:
    defaults: dict[str, str] = {}
    for section in SETTINGS_SECTIONS:
        for field in section["fields"]:
            defaults[str(field["key"])] = str(field["default"])
    return defaults


def serialize_settings_catalog() -> dict[str, object]:
    return {
        "defaults": get_default_app_settings(),
        "sections": [_serialize_section(section) for section in SETTINGS_SECTIONS],
    }


def clone_settings_defaults() -> dict[str, str]:
    return deepcopy(get_default_app_settings())
