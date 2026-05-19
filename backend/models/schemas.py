from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator


def _has_text(value: str | None) -> bool:
    return bool(str(value or "").strip())


class ROIPoint(BaseModel):
    """A single normalized coordinate point for an ROI.
    ROI 的单个归一化坐标点。"""

    x: float  # normalized 0-1 / 归一化 0-1
    y: float  # normalized 0-1 / 归一化 0-1


class ROICreate(BaseModel):
    """Schema for creating a new Region of Interest.
    创建新感兴趣区域的模式。"""

    type: Literal["polygon", "rectangle"]
    points: list[ROIPoint]
    tag: str = ""


class ROI(ROICreate):
    """Persisted ROI with a unique identifier.
    带唯一标识符的已持久化 ROI。"""

    id: str


class VideoSourceCreate(BaseModel):
    """Schema for creating a new video source.
    创建新视频源的模式。"""

    name: str
    rtsp_url: str | None = None
    route_path: str | None = None
    scene_id: str = "smoke"
    notification_policy_ids: list[str] = []

    @model_validator(mode="after")
    def validate_source_address(self) -> "VideoSourceCreate":
        has_rtsp = _has_text(self.rtsp_url)
        has_route = _has_text(self.route_path)
        if has_rtsp and has_route:
            raise ValueError("Use either rtsp_url or route_path, not both")
        if not has_rtsp and not has_route:
            raise ValueError("Either rtsp_url or route_path is required")
        return self


class VideoSourceUpdate(BaseModel):
    """Schema for partially updating a video source.
    部分更新视频源的模式。"""

    name: str | None = None
    rtsp_url: str | None = None
    route_path: str | None = None
    scene_id: str | None = None
    notification_policy_ids: list[str] | None = None
    rois: list[ROICreate] | None = None

    @model_validator(mode="after")
    def validate_source_address(self) -> "VideoSourceUpdate":
        has_rtsp = _has_text(self.rtsp_url)
        has_route = _has_text(self.route_path)
        if has_rtsp and has_route:
            raise ValueError("Use either rtsp_url or route_path, not both")
        return self


class VideoSource(BaseModel):
    """Full video source model with ROIs and metadata.
    包含 ROI 和元数据的完整视频源模型。"""

    id: str
    name: str
    rtsp_url: str
    route_path: str = ""
    scene_id: str = "smoke"
    notification_policy_ids: list[str] = []
    rois: list[ROI] = []
    created_at: str


class SceneDefinition(BaseModel):
    """Scene plugin metadata exposed to backend/frontend.
    暴露给后端和前端的场景插件元数据。"""

    id: str
    label_zh: str
    label_en: str
    description: str = ""
    required_services: list[str] = []
    default_roi_tags: list[str] = []
    event_types: list[str] = []
    default_config: dict[str, Any] = {}
    expert_config_schema: dict[str, Any] = {}


class VideoGatewayCreate(BaseModel):
    """Create a video gateway such as MediaMTX.
    创建视频网关（例如 MediaMTX）。"""

    name: str
    rtsp_base_url: str
    webrtc_base_url: str
    username: str = ""
    password: str = ""
    enabled: bool = True


class VideoGatewayUpdate(BaseModel):
    """Partial update for a video gateway.
    视频网关局部更新。"""

    name: str | None = None
    rtsp_base_url: str | None = None
    webrtc_base_url: str | None = None
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None


class VideoGateway(VideoGatewayCreate):
    """Persisted video gateway.
    已持久化的视频网关。"""

    id: str
    created_at: str


NotificationProviderType = Literal["email", "webhook"]


class NotificationProviderCreate(BaseModel):
    """Create an email/webhook notification provider.
    创建邮件或 Webhook 通知服务。"""

    name: str
    type: NotificationProviderType
    enabled: bool = True
    config: dict[str, Any] = {}


class NotificationProviderUpdate(BaseModel):
    """Partial notification provider update.
    通知服务局部更新。"""

    name: str | None = None
    type: NotificationProviderType | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class NotificationProvider(NotificationProviderCreate):
    """Persisted notification provider.
    已持久化的通知服务。"""

    id: str
    created_at: str


NotificationTemplateChannel = Literal["email", "webhook"]


class NotificationTemplateCreate(BaseModel):
    """Create a reusable notification template.
    创建可复用通知模板。"""

    name: str
    channel: NotificationTemplateChannel
    subject_template: str = ""
    body_template: str = ""


class NotificationTemplateUpdate(BaseModel):
    """Partial notification template update.
    通知模板局部更新。"""

    name: str | None = None
    channel: NotificationTemplateChannel | None = None
    subject_template: str | None = None
    body_template: str | None = None


class NotificationTemplate(NotificationTemplateCreate):
    """Persisted notification template.
    已持久化的通知模板。"""

    id: str
    created_at: str


class NotificationPolicyCreate(BaseModel):
    """Create a notification policy that can fan out to providers.
    创建可分发到多个通知服务的通知策略。"""

    name: str
    enabled: bool = True
    cooldown_seconds: int = 300
    provider_ids: list[str] = []
    template_id: str | None = None


class NotificationPolicyUpdate(BaseModel):
    """Partial notification policy update.
    通知策略局部更新。"""

    name: str | None = None
    enabled: bool | None = None
    cooldown_seconds: int | None = None
    provider_ids: list[str] | None = None
    template_id: str | None = None


class NotificationPolicy(NotificationPolicyCreate):
    """Persisted notification policy.
    已持久化的通知策略。"""

    id: str
    created_at: str


UserRole = Literal["user", "operator", "admin"]


class RoleInfo(BaseModel):
    """Role and permission metadata for the three-level RBAC model.
    三级权限模型的角色与权限元数据。"""

    role: UserRole
    label_zh: str
    label_en: str
    permissions: list[str]


class AuthLoginRequest(BaseModel):
    """Login payload for role-based API access.
    角色 API 访问的登录载荷。"""

    username: str
    password: str
    role: UserRole


class AuthRegisterRequest(BaseModel):
    """Public bootstrap registration payload for the very first admin.
    首个管理员的公开初始化注册载荷。"""

    username: str
    password: str


class AuthTokenResponse(BaseModel):
    """Signed bearer token returned after login.
    登录后返回的签名 Bearer token。"""

    access_token: str
    token_type: str = "bearer"
    role: UserRole
    expires_at: str


class CurrentUser(BaseModel):
    """Authenticated principal returned by /api/auth/me.
    /api/auth/me 返回的已认证主体。"""

    username: str
    role: UserRole
    permissions: list[str] = []


class AuthBootstrapStatus(BaseModel):
    """Expose whether public bootstrap registration is still available.
    暴露公开初始化注册是否仍可用。"""

    has_users: bool
    registration_open: bool


class UserAccountCreate(BaseModel):
    """Admin-created user account payload.
    管理员创建用户账号的载荷。"""

    username: str
    password: str
    role: UserRole


class UserAccount(BaseModel):
    """Persisted user account metadata returned to the frontend.
    返回给前端的已持久化用户账号元数据。"""

    username: str
    role: UserRole
    created_at: str


class ProcessorStartRequest(BaseModel):
    """Request body to start processing for a specific video source.
    启动指定视频源处理的请求体。"""

    source_id: str


class ProcessorStopRequest(BaseModel):
    """Request body to stop processing for a specific video source.
    停止指定视频源处理的请求体。"""

    source_id: str


class ProcessorStatus(BaseModel):
    """Status of a running or stopped processor.
    处理器的运行或停止状态。"""

    source_id: str
    source_name: str
    rtsp_url: str
    status: str  # "running", "stopped", "error" / 运行中、已停止、错误
    started_at: str | None = None


class AnalysisMessage(BaseModel):
    """Real-time analysis message broadcast via WebSocket.
    通过 WebSocket 广播的实时分析消息。"""

    id: str | None = None
    timestamp: str
    source_name: str
    source_id: str
    level: str  # "info", "warning", "alert" / 信息、警告、告警
    message: str
    image_url: str | None = None
    image_base64: str | None = None
    original_image_url: str | None = None
    original_image_base64: str | None = None
    detected_image_url: str | None = None
    detected_image_base64: str | None = None
    false_positive: bool = False


class PaginatedMessagesResponse(BaseModel):
    """Paginated persisted analysis messages.
    持久化分析消息的分页响应。"""

    items: list[AnalysisMessage]
    page: int
    page_size: int
    total: int
    total_pages: int


class AppSettingsUpdate(BaseModel):
    """Partial update for app settings (all fields optional).
    部分更新应用设置（所有字段可选）。"""

    ui_language: str | None = None
    timezone: str | None = None
    site_title: str | None = None
    site_description: str | None = None
    favicon_url: str | None = None

    vengine_host: str | None = None
    detection_port: str | None = None
    classification_port: str | None = None
    action_port: str | None = None
    ocr_port: str | None = None
    upload_port: str | None = None
    # Per-service enable/disable switches / 各服务启用/禁用开关
    detection_enabled: str | None = None
    classification_enabled: str | None = None
    action_enabled: str | None = None
    ocr_enabled: str | None = None
    upload_enabled: str | None = None

    mediamtx_rtsp_addr: str | None = None
    mediamtx_webrtc_addr: str | None = None
    mediamtx_username: str | None = None
    mediamtx_password: str | None = None
    # Legacy per-protocol aliases are still accepted on input so existing
    # deployments can roll forward without a breaking API change.
    # 仍兼容旧的按协议拆分字段输入，便于现有部署平滑升级。
    mediamtx_rtsp_username: str | None = None
    mediamtx_rtsp_password: str | None = None
    mediamtx_webrtc_username: str | None = None
    mediamtx_webrtc_password: str | None = None
    email_from_address: str | None = None
    email_smtp_password: str | None = None
    email_to_addresses: str | None = None
    email_cc_addresses: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: str | None = None
    email_smtp_use_tls: str | None = None
    email_event_enabled: str | None = None
    email_timed_enabled: str | None = None
    email_event_subject_template: str | None = None
    email_event_body_template: str | None = None
    message_retention_days: str | None = None

    smoke_detection_model_name: str | None = None
    smoke_detection_model_version: str | None = None
    smoke_detection_confidence: str | None = None
    smoke_detection_nms: str | None = None
    smoke_min_confidence_smoke: str | None = None
    smoke_min_confidence_fire: str | None = None
    smoke_temporal_confirm_frames: str | None = None
    smoke_temporal_confirm_window: str | None = None
    smoke_max_miss_frames: str | None = None
    smoke_min_bbox_area_ratio: str | None = None
    smoke_max_bbox_area_ratio: str | None = None
    smoke_min_aspect_ratio: str | None = None
    smoke_max_aspect_ratio: str | None = None
    smoke_motion_blur_max_speed: str | None = None
    smoke_motion_blur_min_confidence: str | None = None
    smoke_enable_appearance_filter: str | None = None
    smoke_appearance_min_score: str | None = None
    smoke_appearance_min_history: str | None = None
    smoke_appearance_high_confidence_bypass: str | None = None
    smoke_overexposed_ratio_threshold: str | None = None
    smoke_white_object_ratio_threshold: str | None = None
    smoke_hard_boundary_density_threshold: str | None = None
    smoke_hard_laplacian_threshold: str | None = None
    smoke_fast_motion_energy_threshold: str | None = None
    smoke_static_confirm_frames: str | None = None
    smoke_static_max_center_shift: str | None = None
    smoke_static_max_area_change_ratio: str | None = None
    smoke_iou_threshold: str | None = None
    smoke_alarm_hold_time: str | None = None
    smoke_email_cooldown_seconds: str | None = None
    max_pull_workers: str | None = None
    max_push_workers: str | None = None
    max_cpu_workers: str | None = None


class EmailTestRequest(BaseModel):
    """Payload for testing email configuration without saving first.
    用于在不先保存的情况下测试邮件配置的载荷。"""

    vengine_host: str | None = None
    email_from_address: str | None = None
    email_smtp_password: str | None = None
    email_to_addresses: str | None = None
    email_cc_addresses: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: str | None = None
    email_smtp_use_tls: str | None = None
