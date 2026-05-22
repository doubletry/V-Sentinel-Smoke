from __future__ import annotations

import asyncio
import base64
import html
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from loguru import logger

from backend.db import database as db
from backend.notifications.email_config import (
    build_email_settings_smtp_config,
    has_email_settings_recipients,
)
from core.notification_client import (
    NotificationPayload,
    SmtpNotificationProvider,
    WebhookNotificationProvider,
)
from core.notification_template import (
    build_template_context,
    referenced_placeholders,
    render_template,
)

MAX_CONCURRENT_NOTIFICATION_DISPATCHES = 4


class NotificationDispatcher:
    """Dispatch scene events through configured notification policies.
    根据通知策略分发场景事件。"""

    def __init__(self) -> None:
        self._last_sent_at: dict[str, float] = {}
        self._background_tasks: set[asyncio.Task] = set()
        # Keep background notification fan-out bounded so bursts of scene events
        # do not overwhelm SMTP/Webhook delivery threads or starve analysis work.
        self._dispatch_semaphore = asyncio.Semaphore(MAX_CONCURRENT_NOTIFICATION_DISPATCHES)

    def schedule_event(self, event: dict[str, Any]) -> asyncio.Task:
        """Schedule one event delivery in the background.
        后台调度单次事件投递，避免阻塞分析链路。"""
        # Keep an event snapshot for the detached task so later mutations by the
        # caller cannot change the payload being delivered in the background.
        task = asyncio.create_task(self._send_event_in_background(dict(event)))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _send_event_in_background(self, event: dict[str, Any]) -> None:
        async with self._dispatch_semaphore:
            try:
                await self.send_event(event)
            except Exception:  # pragma: no cover - side-effect logging
                # Background dispatch is intentionally isolated from the
                # analysis path so notification failures never block frame
                # processing; emit a full stack trace for later diagnosis.
                logger.exception("Failed to dispatch background notification event")

    async def send_event(self, event: dict[str, Any], *, force: bool = False) -> list[dict[str, str]]:
        """Send one event to all enabled notification instances.
        将事件发送到所有已启用的通知实例。"""
        app_settings = await db.get_all_settings()
        source = await db.get_source(str(event.get("source_id") or ""))
        providers = {
            provider.id: provider
            for provider in await db.list_notification_providers()
            if provider.enabled
        }
        templates = {template.id: template for template in await db.list_notification_templates()}
        policy_overrides = await self._policy_overrides_for_source(source)
        settings_email_config = build_email_settings_smtp_config(app_settings)
        if not providers and self._legacy_settings_email_enabled(app_settings) and has_email_settings_recipients(settings_email_config):
            providers["default-email"] = SimpleNamespace(
                id="default-email",
                type="email",
                enabled=True,
                config={
                    **settings_email_config,
                    "subject_template": app_settings.get("email_event_subject_template", ""),
                    "body_template": app_settings.get("email_event_body_template", ""),
                },
            )
        if not providers:
            return []

        def build_payload(provider: Any, template_id: str | None = None) -> NotificationPayload:
            template = templates.get(str(template_id or ""))
            provider_config = dict(getattr(provider, "config", {}) or {})
            context = build_template_context(app_settings, self._enrich_event(event, source))
            subject_template = str(
                provider_config.get("subject_template")
                or (template.subject_template if template else "")
                or "{event_label} alert from {source_name}"
            )
            body_template = str(
                provider_config.get("body_template")
                or (template.body_template if template else "")
                or "{local_time} {event_label} {source_name}"
            )
            rendered_body = render_template(body_template, context)
            html_context = self._html_template_context(context)
            rendered_html_body = "<br>".join(render_template(body_template, html_context).splitlines())
            return NotificationPayload(
                subject=render_template(subject_template, context),
                body=rendered_body,
                html_body=rendered_html_body,
                context=context,
                attachments=self._build_attachments(event, body_template),
            )

        async def dispatch_provider(provider: Any) -> dict[str, str] | None:
            provider_id = str(getattr(provider, "id", ""))
            provider_config = dict(getattr(provider, "config", {}) or {})
            override = policy_overrides.get(provider_id, {})
            cooldown_seconds = self._cooldown_seconds(
                provider_config,
                override.get("cooldown_seconds"),
                event,
            )
            if not force and not self._should_send(provider_id, cooldown_seconds, event):
                return None
            payload = build_payload(provider, override.get("template_id"))
            try:
                result = await self._send_provider(provider.type, provider_config, payload)
            except Exception as exc:  # pragma: no cover - side-effect logging
                logger.warning(
                    "Failed to send notification via provider {}: {}",
                    provider_id,
                    exc,
                )
                result = {"status": "ERROR", "message": str(exc)}
            if result.get("status") == "SUCCESS":
                self._mark_sent(provider_id, event)
            return result

        results = await asyncio.gather(*(dispatch_provider(provider) for provider in providers.values()))
        return [result for result in results if result is not None]

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

    def _legacy_settings_email_enabled(self, app_settings: dict[str, Any]) -> bool:
        return str(app_settings.get("email_event_enabled", "true")).lower() in {"true", "1", "yes"}

    async def _policy_overrides_for_source(self, source: Any) -> dict[str, dict[str, Any]]:
        if source is None:
            return {}
        policy_ids = [str(item) for item in getattr(source, "notification_policy_ids", []) or []]
        if not policy_ids:
            return {}
        overrides: dict[str, dict[str, Any]] = {}
        # Policies are still honored as optional per-source overrides for
        # cooldown/template selection, while delivery fans out to all enabled
        # instances globally.
        policies = {
            policy.id: policy
            for policy in await db.list_notification_policies()
            if policy.id in set(policy_ids) and policy.enabled
        }
        for policy_id in policy_ids:
            policy = policies.get(policy_id)
            if policy is None:
                continue
            for provider_id in policy.provider_ids:
                overrides.setdefault(
                    str(provider_id),
                    {
                        "template_id": policy.template_id,
                        "cooldown_seconds": policy.cooldown_seconds,
                    },
                )
        return overrides

    def _cooldown_seconds(
        self,
        provider_config: dict[str, Any],
        policy_cooldown_seconds: Any,
        event: dict[str, Any],
    ) -> int:
        raw_value = event.get("cooldown_seconds", policy_cooldown_seconds)
        if raw_value in (None, ""):
            raw_value = provider_config.get("cooldown_seconds", 300)
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return 300

    def _should_send(self, policy_id: str, cooldown_seconds: int, event: dict[str, Any]) -> bool:
        now_ts = datetime.now(timezone.utc).timestamp()
        last_ts = self._last_sent_at.get(self._cooldown_key(policy_id, event), 0.0)
        try:
            cooldown = int(event.get("cooldown_seconds", cooldown_seconds))
        except (TypeError, ValueError):
            cooldown = int(cooldown_seconds)
        return now_ts - last_ts >= max(0, cooldown)

    def _mark_sent(self, policy_id: str, event: dict[str, Any]) -> None:
        self._last_sent_at[self._cooldown_key(policy_id, event)] = datetime.now(timezone.utc).timestamp()

    def _build_attachments(self, event: dict[str, Any], body_template: str) -> list[tuple[str, bytes, str]]:
        placeholders = referenced_placeholders(body_template)
        include_original = "original_image" in placeholders
        include_detected = "detected_image" in placeholders
        if not include_original and not include_detected:
            return []
        timestamp = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())[:19]
        safe_timestamp = timestamp.replace(":", "-")
        event_type = str(event.get("event_type") or "event").replace("/", "_")
        attachments: list[tuple[str, bytes, str]] = []
        seen_payloads: set[str] = set()
        image_keys: list[tuple[str, str]] = []
        if include_original:
            image_keys.append(("original_image_base64", "original"))
        if include_detected:
            image_keys.extend((("detected_image_base64", "detected"), ("image_base64", "detected")))
        for key, suffix in image_keys:
            image_base64 = str(event.get(key) or "").strip()
            if not image_base64 or image_base64 in seen_payloads:
                continue
            seen_payloads.add(image_base64)
            try:
                image_bytes = base64.b64decode(image_base64, validate=True)
            except Exception:
                continue
            attachments.append((f"{event_type}-{safe_timestamp}-{suffix}.jpg", image_bytes, "image/jpeg"))
        return attachments

    def _enrich_event(self, event: dict[str, Any], source: Any) -> dict[str, Any]:
        enriched = dict(event)
        if source is None:
            return enriched
        enriched.setdefault("source_rtsp_url", getattr(source, "rtsp_url", ""))
        enriched.setdefault("source_route_path", getattr(source, "route_path", ""))
        enriched.setdefault("source_remark", getattr(source, "source_remark", ""))
        enriched.setdefault("source_description", getattr(source, "source_remark", ""))
        return enriched

    def _html_template_context(self, context: dict[str, str]) -> dict[str, str]:
        passthrough = {"original_image", "detected_image"}
        return {
            key: (
                value
                if key in passthrough and str(value).startswith("<img ")
                else ("" if key in passthrough else html.escape(str(value)))
            )
            for key, value in context.items()
        }
