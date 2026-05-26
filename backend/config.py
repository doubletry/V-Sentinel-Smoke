from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Minimal env-only settings: ports + DB path.
    最小化的仅环境变量配置：端口 + 数据库路径。

    All service addresses (V-Engine, MediaMTX) are stored in the database
    and managed via the Settings page in the web UI.
    所有服务地址（V-Engine、MediaMTX）存储在数据库中，通过 Web UI 设置页面管理。
    """

    model_config = SettingsConfigDict(env_file=".env")

    # Server ports (env-only) / 服务端口（仅环境变量）
    backend_port: int = 8000
    frontend_port: int = 3000

    # Database path (env-only) / 数据库路径（仅环境变量）
    db_path: str = "./v_sentinel.db"

    # App / 应用
    app_name: str = "V-Sentinel"


# Default values for DB-backed settings (used when no DB record exists)
# 数据库设置的默认值（当无数据库记录时使用）
DEFAULT_APP_SETTINGS: dict[str, str] = {
    # UI / 界面
    "ui_language": "zh-CN",
    "timezone": "Asia/Shanghai",
    "site_title": "V-Sentinel",
    "site_description": "AI Video Surveillance Analysis Platform",
    "favicon_url": "/favicon.ico",
    # Active processing plugin / 当前启用的处理插件
    "active_plugin_id": "smoke",
    # Shared V-Engine host / 共享 V-Engine 主机
    "vengine_host": "localhost",
    # Per-service ports / 各服务端口
    "detection_port": "50051",
    "classification_port": "50052",
    "action_port": "50053",
    "ocr_port": "50054",
    "upload_port": "50050",
    # Per-service enable/disable switches (JSON booleans as strings) / 各服务启用/禁用开关（字符串形式的布尔值）
    "detection_enabled": "true",
    "classification_enabled": "false",
    "action_enabled": "false",
    "ocr_enabled": "false",
    "upload_enabled": "false",
    # MediaMTX
    "mediamtx_rtsp_addr": "rtsp://localhost:8554",
    "mediamtx_webrtc_addr": "http://localhost:8889",
    "mediamtx_username": "",
    "mediamtx_password": "",
    # Email notifications / 邮件通知
    "email_from_address": "",
    "email_smtp_password": "",
    "email_to_addresses": "",
    "email_cc_addresses": "",
    "email_smtp_host": "",
    "email_smtp_port": "587",
    "email_smtp_use_tls": "true",
    "email_event_enabled": "true",
    "email_timed_enabled": "false",
    "email_event_subject_template": "[{site_title}] {event_label} alert from {source_name}",
    "email_event_body_template": "Event: {event_label}\nTime: {local_time} ({timezone})\nVideo source: {source_name} ({source_id})\nLabels: {labels}\nHighest confidence: {confidence_percent}\nDetection count: {detection_count}\nFrame ID: {frame_id}\nActive tracks: {active_tracks}",
    "message_retention_days": "7",
    # Smoke/fire scene / 烟火场景
    "smoke_detection_model_name": "smoke-fire-detection",
    "smoke_detection_model_version": "",
    "smoke_detection_confidence": "0.35",
    "smoke_detection_nms": "0.7",
    "smoke_min_confidence_smoke": "0.35",
    "smoke_min_confidence_fire": "0.40",
    "smoke_temporal_confirm_frames": "3",
    "smoke_temporal_confirm_window": "2.0",
    "smoke_max_miss_frames": "5",
    "smoke_min_bbox_area_ratio": "0.0005",
    "smoke_max_bbox_area_ratio": "0.60",
    "smoke_min_aspect_ratio": "0.2",
    "smoke_max_aspect_ratio": "8.0",
    "smoke_motion_blur_max_speed": "100.0",
    "smoke_motion_blur_min_confidence": "0.65",
    "smoke_enable_appearance_filter": "true",
    "smoke_appearance_min_score": "0.42",
    "smoke_appearance_min_history": "2",
    "smoke_appearance_high_confidence_bypass": "0.82",
    "smoke_overexposed_ratio_threshold": "0.18",
    "smoke_white_object_ratio_threshold": "0.62",
    "smoke_hard_boundary_density_threshold": "0.14",
    "smoke_hard_laplacian_threshold": "520.0",
    "smoke_fast_motion_energy_threshold": "0.16",
    "smoke_static_confirm_frames": "5",
    "smoke_static_max_center_shift": "10.0",
    "smoke_static_max_area_change_ratio": "0.08",
    "smoke_iou_threshold": "0.3",
    "smoke_alarm_hold_time": "3.0",
    # Fire door scene / 消防门场景
    "fire_door_classification_model_name": "fire-door-classification",
    "fire_door_classification_confidence": "0.50",
    "fire_door_open_labels": "open",
    "fire_door_closed_labels": "closed",
    "fire_door_alarm_labels": "open",
    "fire_door_temporal_confirm_frames": "1",
    "fire_door_temporal_confirm_window": "2.0",
    "fire_door_alarm_hold_time": "3.0",
    # Thread pool sizes / 线程池大小
    "max_pull_workers": "20",
    "max_push_workers": "10",
    "max_cpu_workers": "16",
    # Account expiration defaults per role (days; "0" or "" = never expires) /
    # 各角色账号有效期默认值（天；"0" 或空表示永不过期）
    "account_expiration_days_user": "0",
    "account_expiration_days_operator": "0",
    "account_expiration_days_admin": "0",
    # Login brute-force protection / 登录暴力破解防护
    "login_lockout_max_attempts": "5",
    "login_lockout_window_seconds": "300",
    "login_lockout_duration_seconds": "900",
    "login_lockout_trust_proxy": "false",
}


settings = Settings()
