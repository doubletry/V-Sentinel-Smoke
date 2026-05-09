from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.db import database as db
from core.email_client import AsyncEmailClient
from core.notification_client import (
    NotificationPayload,
    SmtpNotificationProvider,
    WebhookNotificationProvider,
)


class NotificationDispatcher:
    """Dispatch scene events through configured notification policies.
    根据通知策略分发场景事件。"""

    def __init__(self) -> None:
        self._last_sent_at: dict[str, float] = {}

    async def send_event(self, event: dict[str, Any]) -> list[dict[str, str]]:
        """Send one event to the source-bound policies or the default policy.
        将事件发送到视频源绑定策略；未绑定时使用默认策略。"""
        app_settings = await db.get_all_settings()
        if str(app_settings.get("email_event_enabled", "true")).lower() not in {"true", "1", "yes"}:
            return []

        source = await db.get_source(str(event.get("source_id") or ""))
        policy_ids = list(source.notification_policy_ids) if source else []
        if not policy_ids:
            policy_ids = ["default-alert-policy"]

        policies = {
            policy.id: policy
            for policy in await db.list_notification_policies()
            if policy.id in set(policy_ids)
        }
        providers = {provider.id: provider for provider in await db.list_notification_providers()}
        templates = {template.id: template for template in await db.list_notification_templates()}

        results: list[dict[str, str]] = []
        for policy_id in policy_ids:
            policy = policies.get(policy_id)
            if policy is None or not policy.enabled:
                continue
            if not self._should_send(policy_id, policy.cooldown_seconds, event):
                continue
            template = templates.get(str(policy.template_id or ""))
            context = AsyncEmailClient._template_context(app_settings, event)
            subject_template = template.subject_template if template else "{event_label} alert from {source_name}"
            body_template = template.body_template if template else "{local_time} {event_label} {source_name}"
            payload = NotificationPayload(
                subject=AsyncEmailClient.render_template(subject_template, context),
                body=AsyncEmailClient.render_template(body_template, context),
                html_body="<br>".join(
                    AsyncEmailClient.render_template(body_template, context).splitlines()
                ),
                context=context,
                attachments=self._build_attachments(event),
            )
            for provider_id in policy.provider_ids:
                provider = providers.get(provider_id)
                if provider is None or not provider.enabled:
                    continue
                try:
                    results.append(await self._send_provider(provider.type, provider.config, payload))
                except Exception as exc:  # pragma: no cover - side-effect logging
                    logger.warning(
                        "Failed to send notification via provider {}: {}",
                        provider_id,
                        exc,
                    )
            self._mark_sent(policy_id, event)
        return results

    async def _send_provider(
        self,
        provider_type: str,
        config: dict[str, Any],
        payload: NotificationPayload,
    ) -> dict[str, str]:
        if provider_type == "email":
            return await SmtpNotificationProvider(config).send(payload)
        if provider_type == "webhook":
            return await WebhookNotificationProvider(config).send(payload)
        raise ValueError(f"Unsupported notification provider type: {provider_type}")

    def _cooldown_key(self, policy_id: str, event: dict[str, Any]) -> str:
        event_type = str(event.get("event_type") or event.get("label") or "event")
        return f"{policy_id}:{event.get('source_id', '')}:{event_type}"

    def _should_send(self, policy_id: str, cooldown_seconds: int, event: dict[str, Any]) -> bool:
        now_ts = datetime.now(timezone.utc).timestamp()
        last_ts = self._last_sent_at.get(self._cooldown_key(policy_id, event), 0.0)
        return now_ts - last_ts >= max(0, int(cooldown_seconds))

    def _mark_sent(self, policy_id: str, event: dict[str, Any]) -> None:
        self._last_sent_at[self._cooldown_key(policy_id, event)] = datetime.now(timezone.utc).timestamp()

    def _build_attachments(self, event: dict[str, Any]) -> list[tuple[str, bytes, str]]:
        image_base64 = str(event.get("image_base64") or "").strip()
        if not image_base64:
            return []
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except Exception:
            return []
        timestamp = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())[:19]
        safe_timestamp = timestamp.replace(":", "-")
        event_type = str(event.get("event_type") or "event").replace("/", "_")
        return [(f"{event_type}-{safe_timestamp}.jpg", image_bytes, "image/jpeg")]
