from __future__ import annotations

import base64
import html
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.db import database as db
from core.notification_client import (
    NotificationPayload,
    SmtpNotificationProvider,
    WebhookNotificationProvider,
)
from core.notification_template import build_template_context, render_template


class NotificationDispatcher:
    """Dispatch scene events through configured notification policies.
    根据通知策略分发场景事件。"""

    def __init__(self) -> None:
        self._last_sent_at: dict[str, float] = {}

    async def send_event(self, event: dict[str, Any], *, force: bool = False) -> list[dict[str, str]]:
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

        def build_payload(template_id: str | None) -> NotificationPayload:
            template = templates.get(str(template_id or ""))
            context = build_template_context(app_settings, self._enrich_event(event, source))
            subject_template = template.subject_template if template else "{event_label} alert from {source_name}"
            body_template = template.body_template if template else "{local_time} {event_label} {source_name}"
            rendered_body = render_template(body_template, context)
            html_context = self._html_template_context(context)
            return NotificationPayload(
                subject=render_template(subject_template, context),
                body=rendered_body,
                html_body="<br>".join(render_template(body_template, html_context).splitlines()),
                context=context,
                attachments=self._build_attachments(event),
            )

        results: list[dict[str, str]] = []
        attempted_provider_ids: set[str] = set()
        for policy_id in policy_ids:
            policy = policies.get(policy_id)
            if policy is None or not policy.enabled:
                continue
            if not force and not self._should_send(policy_id, policy.cooldown_seconds, event):
                continue
            payload = build_payload(policy.template_id)
            for provider_id in policy.provider_ids:
                provider = providers.get(provider_id)
                if provider is None or not provider.enabled:
                    continue
                attempted_provider_ids.add(provider_id)
                try:
                    results.append(await self._send_provider(provider.type, provider.config, payload))
                except Exception as exc:  # pragma: no cover - side-effect logging
                    logger.warning(
                        "Failed to send notification via provider {}: {}",
                        provider_id,
                        exc,
                    )
                    results.append({"status": "ERROR", "message": str(exc)})
            self._mark_sent(policy_id, event)
        if force and not any(result.get("status") == "SUCCESS" for result in results):
            payload = build_payload(None)
            fallback_providers = [
                provider
                for provider_id, provider in providers.items()
                if provider.enabled and provider_id not in attempted_provider_ids
            ]
            for provider in fallback_providers:
                try:
                    results.append(await self._send_provider(provider.type, provider.config, payload))
                except Exception as exc:  # pragma: no cover - side-effect logging
                    logger.warning(
                        "Failed to send manual notification via fallback provider {}: {}",
                        provider.id,
                        exc,
                    )
                    results.append({"status": "ERROR", "message": str(exc)})
            if not fallback_providers and not attempted_provider_ids:
                legacy_email_config = self._legacy_email_config(app_settings)
                if legacy_email_config:
                    try:
                        results.append(await self._send_provider("email", legacy_email_config, payload))
                    except Exception as exc:  # pragma: no cover - side-effect logging
                        logger.warning("Failed to send manual notification via legacy email settings: {}", exc)
                        results.append({"status": "ERROR", "message": str(exc)})
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
        try:
            cooldown = int(event.get("cooldown_seconds", cooldown_seconds))
        except (TypeError, ValueError):
            cooldown = int(cooldown_seconds)
        return now_ts - last_ts >= max(0, cooldown)

    def _mark_sent(self, policy_id: str, event: dict[str, Any]) -> None:
        self._last_sent_at[self._cooldown_key(policy_id, event)] = datetime.now(timezone.utc).timestamp()

    def _build_attachments(self, event: dict[str, Any]) -> list[tuple[str, bytes, str]]:
        timestamp = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())[:19]
        safe_timestamp = timestamp.replace(":", "-")
        event_type = str(event.get("event_type") or "event").replace("/", "_")
        attachments: list[tuple[str, bytes, str]] = []
        seen_payloads: set[str] = set()
        for key, suffix in (
            ("original_image_base64", "original"),
            ("detected_image_base64", "detected"),
            ("image_base64", "image"),
        ):
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

    def _legacy_email_config(self, app_settings: dict[str, str]) -> dict[str, Any] | None:
        smtp_host = str(app_settings.get("email_smtp_host") or "").strip()
        from_address = str(app_settings.get("email_from_address") or "").strip()
        to_addresses = str(app_settings.get("email_to_addresses") or "").strip()
        cc_addresses = str(app_settings.get("email_cc_addresses") or "").strip()
        if not smtp_host or not from_address or not (to_addresses or cc_addresses):
            return None
        return {
            "smtp_host": smtp_host,
            "smtp_port": str(app_settings.get("email_smtp_port") or "587"),
            "smtp_username": str(app_settings.get("email_smtp_username") or "").strip(),
            "smtp_password": str(app_settings.get("email_smtp_password") or ""),
            "from_address": from_address,
            "to_addresses": to_addresses,
            "cc_addresses": cc_addresses,
            "use_tls": str(app_settings.get("email_smtp_use_tls", "true")).lower() in {"1", "true", "yes", "on"},
        }

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
