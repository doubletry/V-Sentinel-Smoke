from __future__ import annotations

from fastapi import APIRouter, HTTPException

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

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/providers", response_model=list[NotificationProvider])
async def list_providers() -> list[NotificationProvider]:
    """List email/webhook notification providers.
    列出邮件与 Webhook 通知服务。"""
    return await db.list_notification_providers()


@router.post("/providers", response_model=NotificationProvider, status_code=201)
async def create_provider(data: NotificationProviderCreate) -> NotificationProvider:
    """Create an email or webhook notification provider.
    创建邮件或 Webhook 通知服务。"""
    return await db.create_notification_provider(data)


@router.put("/providers/{provider_id}", response_model=NotificationProvider)
async def update_provider(
    provider_id: str,
    data: NotificationProviderUpdate,
) -> NotificationProvider:
    """Update a notification provider.
    更新通知服务。"""
    provider = await db.update_notification_provider(provider_id, data)
    if provider is None:
        raise HTTPException(status_code=404, detail="Notification provider not found")
    return provider


@router.get("/templates", response_model=list[NotificationTemplate])
async def list_templates() -> list[NotificationTemplate]:
    """List notification templates.
    列出通知模板。"""
    return await db.list_notification_templates()


@router.post("/templates", response_model=NotificationTemplate, status_code=201)
async def create_template(data: NotificationTemplateCreate) -> NotificationTemplate:
    """Create a notification template.
    创建通知模板。"""
    return await db.create_notification_template(data)


@router.put("/templates/{template_id}", response_model=NotificationTemplate)
async def update_template(
    template_id: str,
    data: NotificationTemplateUpdate,
) -> NotificationTemplate:
    """Update a notification template.
    更新通知模板。"""
    template = await db.update_notification_template(template_id, data)
    if template is None:
        raise HTTPException(status_code=404, detail="Notification template not found")
    return template


@router.get("/policies", response_model=list[NotificationPolicy])
async def list_policies() -> list[NotificationPolicy]:
    """List notification policies.
    列出通知策略。"""
    return await db.list_notification_policies()


@router.post("/policies", response_model=NotificationPolicy, status_code=201)
async def create_policy(data: NotificationPolicyCreate) -> NotificationPolicy:
    """Create a notification policy.
    创建通知策略。"""
    return await db.create_notification_policy(data)


@router.put("/policies/{policy_id}", response_model=NotificationPolicy)
async def update_policy(policy_id: str, data: NotificationPolicyUpdate) -> NotificationPolicy:
    """Update a notification policy.
    更新通知策略。"""
    policy = await db.update_notification_policy(policy_id, data)
    if policy is None:
        raise HTTPException(status_code=404, detail="Notification policy not found")
    return policy
