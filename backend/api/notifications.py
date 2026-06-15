from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth.dependencies import require_permission
from backend.db import database as db
from backend.models.schemas import (
    NotificationPolicy,
    NotificationPolicyCreate,
    NotificationPolicyUpdate,
    NotificationProvider,
    NotificationProviderCreate,
    NotificationProviderUpdate,
    NotificationTemplate,
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
)
from core.notification_client import (
    NotificationPayload,
    SocketNotificationProvider,
    SmtpNotificationProvider,
    WebhookNotificationProvider,
)
from core.notification_template import build_template_context, render_template

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _set_audit_context_for_instance(
    request: Request,
    provider: NotificationProvider,
    detail: dict[str, object] | None = None,
) -> None:
    """Expose notification instance name and optional detail to audit middleware."""
    request.state.audit_resource_id = provider.name
    if detail is not None:
        request.state.audit_detail = json.dumps(detail, ensure_ascii=False)


@router.get("/providers", response_model=list[NotificationProvider])
async def list_providers(
    _role: str = Depends(require_permission("notifications:*")),
) -> list[NotificationProvider]:
    """List email/webhook notification providers.
    列出邮件与 Webhook 通知服务。"""
    return await db.list_notification_providers()


@router.get("/instances", response_model=list[NotificationProvider])
async def list_instances(
    _role: str = Depends(require_permission("notifications:*")),
) -> list[NotificationProvider]:
    """List notification instances.
    列出通知实例。"""
    return await db.list_notification_providers()


@router.post("/providers", response_model=NotificationProvider, status_code=201)
async def create_provider(
    request: Request,
    data: NotificationProviderCreate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationProvider:
    """Create an email or webhook notification provider.
    创建邮件或 Webhook 通知服务。"""
    provider = await db.create_notification_provider(data)
    _set_audit_context_for_instance(request, provider)
    return provider


@router.post("/instances", response_model=NotificationProvider, status_code=201)
async def create_instance(
    request: Request,
    data: NotificationProviderCreate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationProvider:
    """Create a notification instance.
    创建通知实例。"""
    provider = await db.create_notification_provider(data)
    _set_audit_context_for_instance(request, provider)
    return provider


@router.put("/providers/{provider_id}", response_model=NotificationProvider)
async def update_provider(
    request: Request,
    provider_id: str,
    data: NotificationProviderUpdate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationProvider:
    """Update a notification provider.
    更新通知服务。"""
    provider = await db.update_notification_provider(provider_id, data)
    if provider is None:
        raise HTTPException(status_code=404, detail="Notification provider not found")
    _set_audit_context_for_instance(request, provider)
    return provider


@router.put("/instances/{provider_id}", response_model=NotificationProvider)
async def update_instance(
    request: Request,
    provider_id: str,
    data: NotificationProviderUpdate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationProvider:
    """Update a notification instance.
    更新通知实例。"""
    provider = await db.update_notification_provider(provider_id, data)
    if provider is None:
        raise HTTPException(status_code=404, detail="Notification instance not found")
    _set_audit_context_for_instance(request, provider)
    return provider


def _build_test_payload(app_settings: dict[str, str], provider: NotificationProvider) -> NotificationPayload:
    """Build a sample notification payload for the per-instance test action.
    为单个通知实例的测试动作构造示例消息。"""
    site_title = str(app_settings.get("site_title") or "V-Sentinel")
    now_iso = datetime.now(timezone.utc).isoformat()
    sample_event = {
        "source_id": "test-source",
        "source_name": "Test Source",
        "event_type": "test",
        "event_label": "Test Notification",
        "message": f"Test notification triggered for instance {provider.name}.",
        "timestamp": now_iso,
    }
    context = build_template_context(app_settings, sample_event)
    subject = f"{site_title} 通知配置测试 / Notification test"
    body = (
        f"这是一封来自 {site_title} 的通知测试。\n"
        f"This is a test notification from {site_title}.\n\n"
        f"Instance: {provider.name}\n"
        f"Type: {provider.type}\n"
        f"Local time: {context.get('local_time', '')} ({context.get('timezone', '')})\n"
    )
    if provider.type == "email":
        config = dict(provider.config or {})
        subject_template = str(config.get("subject_template") or "")
        body_template = str(config.get("body_template") or "")
        if subject_template:
            subject = render_template(subject_template, context)
        if body_template:
            body = render_template(body_template, context)
    return NotificationPayload(subject=subject, body=body, context=context)


@router.post("/instances/{instance_id}/test")
async def test_instance(
    request: Request,
    instance_id: str,
    _role: str = Depends(require_permission("notifications:*")),
) -> dict[str, str]:
    """Send a test notification through one persisted notification instance.
    通过一个已持久化的通知实例发送测试通知。

    The persisted configuration is used so the result reflects what the
    backend will actually send for real alarm events. 使用已持久化的配置，
    以确保测试结果与后端真实告警时发送的内容一致。"""
    providers = await db.list_notification_providers()
    provider = next((item for item in providers if item.id == instance_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="Notification instance not found")
    _set_audit_context_for_instance(request, provider)
    app_settings = await db.get_all_settings()
    payload = _build_test_payload(app_settings, provider)
    config = dict(provider.config or {})
    try:
        if provider.type == "email":
            result = await SmtpNotificationProvider(config).send(payload)
        elif provider.type == "webhook":
            result = await WebhookNotificationProvider(config).send(payload)
        elif provider.type == "socket":
            result = await SocketNotificationProvider(config).send(payload)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported notification instance type: {provider.type}",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface provider errors to the UI
        raise HTTPException(status_code=400, detail=str(exc) or exc.__class__.__name__) from exc
    audit_detail = {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "provider_type": provider.type,
        "status": result.get("status", ""),
        "message": result.get("message", ""),
    }
    if result.get("response"):
        audit_detail["response"] = result["response"]
    _set_audit_context_for_instance(request, provider, audit_detail)
    return result


@router.get("/templates", response_model=list[NotificationTemplate])
async def list_templates(
    _role: str = Depends(require_permission("notifications:*")),
) -> list[NotificationTemplate]:
    """List notification templates.
    列出通知模板。"""
    return await db.list_notification_templates()


@router.post("/templates", response_model=NotificationTemplate, status_code=201)
async def create_template(
    data: NotificationTemplateCreate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationTemplate:
    """Create a notification template.
    创建通知模板。"""
    return await db.create_notification_template(data)


@router.put("/templates/{template_id}", response_model=NotificationTemplate)
async def update_template(
    template_id: str,
    data: NotificationTemplateUpdate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationTemplate:
    """Update a notification template.
    更新通知模板。"""
    template = await db.update_notification_template(template_id, data)
    if template is None:
        raise HTTPException(status_code=404, detail="Notification template not found")
    return template


@router.get("/policies", response_model=list[NotificationPolicy])
async def list_policies(
    _role: str = Depends(require_permission("notifications:*")),
) -> list[NotificationPolicy]:
    """List notification policies.
    列出通知策略。"""
    return await db.list_notification_policies()


@router.post("/policies", response_model=NotificationPolicy, status_code=201)
async def create_policy(
    data: NotificationPolicyCreate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationPolicy:
    """Create a notification policy.
    创建通知策略。"""
    return await db.create_notification_policy(data)


@router.put("/policies/{policy_id}", response_model=NotificationPolicy)
async def update_policy(
    policy_id: str,
    data: NotificationPolicyUpdate,
    _role: str = Depends(require_permission("notifications:*")),
) -> NotificationPolicy:
    """Update a notification policy.
    更新通知策略。"""
    policy = await db.update_notification_policy(policy_id, data)
    if policy is None:
        raise HTTPException(status_code=404, detail="Notification policy not found")
    return policy
