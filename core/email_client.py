"""Async gRPC client for the email service.
邮件服务的异步 gRPC 客户端。"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from string import Formatter
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import grpc.aio

from core.constants import EMAIL_PORT
from core.proto import email_pb2, email_pb2_grpc

EMAIL_TEMPLATE_PLACEHOLDERS: tuple[str, ...] = (
    "site_title",
    "timestamp",
    "local_time",
    "timezone",
    "source_id",
    "source_name",
    "event_type",
    "event_label",
    "labels",
    "confidence",
    "confidence_percent",
    "detection_count",
    "frame_id",
    "active_tracks",
)

DEFAULT_EVENT_EMAIL_SUBJECT_TEMPLATE = "[{site_title}] {event_label} alert from {source_name}"
DEFAULT_EVENT_EMAIL_BODY_TEMPLATE = """Event: {event_label}
Time: {local_time} ({timezone})
Video source: {source_name} ({source_id})
Labels: {labels}
Highest confidence: {confidence_percent}
Detection count: {detection_count}
Frame ID: {frame_id}
Active tracks: {active_tracks}
"""


class _SafeTemplateValues(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class AsyncEmailClient:
    """Async gRPC client for email delivery and test-email checks.
    用于邮件投递与测试邮件校验的异步 gRPC 客户端。"""

    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._stub: email_pb2_grpc.EmailServiceStub | None = None
        self._address: str | None = None

    @staticmethod
    def _product_name(app_settings: dict[str, str]) -> str:
        return str(app_settings.get("site_title") or "V-Sentinel").strip() or "V-Sentinel"

    @staticmethod
    def _build_address(app_settings: dict[str, str]) -> str:
        host = app_settings.get("email_host") or app_settings.get("vengine_host", "localhost")
        port = app_settings.get("email_port", EMAIL_PORT)
        return f"{host}:{port}"

    @staticmethod
    def _split_addresses(raw: str | None) -> list[str]:
        return [part for part in (segment.strip() for segment in str(raw or "").split(",")) if part]

    @staticmethod
    def available_template_placeholders() -> list[str]:
        return list(EMAIL_TEMPLATE_PLACEHOLDERS)

    async def connect(self, app_settings: dict[str, str]) -> None:
        address = self._build_address(app_settings)
        if self._channel is not None and self._address == address:
            return
        await self.close()
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = email_pb2_grpc.EmailServiceStub(self._channel)
        self._address = address

    async def reconnect_from_settings(self, app_settings: dict[str, str]) -> None:
        await self.connect(app_settings)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        self._channel = None
        self._stub = None
        self._address = None

    async def send_email(self, request: email_pb2.SendEmailRequest) -> dict[str, str]:
        if self._stub is None:
            raise RuntimeError("Email client is not connected")
        response = await self._stub.SendEmail(request)
        return {"status": response.status, "message": response.message, "email_id": response.email_id}

    def build_request(
        self,
        app_settings: dict[str, str],
        *,
        subject: str,
        plain_text_body: str,
        html_body: str = "",
        overrides: dict[str, Any] | None = None,
        attachments: list[email_pb2.Attachment] | None = None,
    ) -> email_pb2.SendEmailRequest:
        merged = dict(app_settings)
        if overrides:
            merged.update({k: str(v) for k, v in overrides.items() if v is not None})

        from_address = str(merged.get("email_from_address", "")).strip()
        from_auth_code = str(merged.get("email_from_auth_code", "")).strip()
        to_addresses = self._split_addresses(merged.get("email_to_addresses"))
        cc_addresses = self._split_addresses(merged.get("email_cc_addresses"))

        if not from_address:
            raise ValueError("Sender email address is required (email_from_address)")
        if not from_auth_code:
            raise ValueError("Sender password/auth code is required (email_from_auth_code)")
        if not (to_addresses or cc_addresses):
            raise ValueError("At least one recipient is required (email_to_addresses or email_cc_addresses)")

        return email_pb2.SendEmailRequest(
            from_address=from_address,
            from_auth_code=from_auth_code,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            subject=subject,
            plain_text_body=plain_text_body,
            html_body=html_body or plain_text_body.replace("\n", "<br>"),
            attachments=attachments or [],
        )

    async def send_test_email(
        self,
        app_settings: dict[str, str],
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        request = self.build_request(
            app_settings,
            subject=f"{self._product_name(app_settings)} 邮件配置测试",
            plain_text_body=f"这是一封来自 {self._product_name(app_settings)} 的测试邮件，用于验证邮件配置是否正确。",
            overrides=overrides,
        )
        return await self.send_email(request)

    @classmethod
    def _template_context(
        cls, app_settings: dict[str, str], event: dict[str, Any]
    ) -> dict[str, str]:
        timezone_name = str(app_settings.get("timezone") or "UTC")
        try:
            tzinfo = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone_name = "UTC"
            tzinfo = timezone.utc
        timestamp = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            local_time = parsed.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            local_time = timestamp
        confidence = cls._safe_float(event.get("confidence"))
        labels_raw = event.get("labels") or event.get("event_type") or "event"
        if isinstance(labels_raw, (list, tuple, set)):
            labels = ", ".join(str(item) for item in labels_raw)
        else:
            labels = str(labels_raw)
        event_type = str(event.get("event_type") or labels).strip() or "event"
        return {
            "site_title": cls._product_name(app_settings),
            "timestamp": timestamp,
            "local_time": local_time,
            "timezone": timezone_name,
            "source_id": str(event.get("source_id") or ""),
            "source_name": str(event.get("source_name") or ""),
            "event_type": event_type,
            "event_label": str(event.get("event_label") or event_type.upper()),
            "labels": labels,
            "confidence": f"{confidence:.4f}",
            "confidence_percent": f"{confidence * 100:.1f}%",
            "detection_count": str(event.get("detection_count") or 0),
            "frame_id": str(event.get("frame_id") or ""),
            "active_tracks": str(event.get("active_tracks") or ""),
        }

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def render_template(template: str, context: dict[str, str]) -> str:
        return Formatter().vformat(template, (), _SafeTemplateValues(context))

    def build_event_email_request(
        self,
        app_settings: dict[str, str],
        event: dict[str, Any],
        attachments: list[email_pb2.Attachment] | None = None,
    ) -> email_pb2.SendEmailRequest:
        context = self._template_context(app_settings, event)
        subject_template = str(
            app_settings.get("email_event_subject_template")
            or DEFAULT_EVENT_EMAIL_SUBJECT_TEMPLATE
        )
        body_template = str(
            app_settings.get("email_event_body_template")
            or DEFAULT_EVENT_EMAIL_BODY_TEMPLATE
        )
        subject = self.render_template(subject_template, context)
        plain_text_body = self.render_template(body_template, context)
        html_body = "<br>".join(html.escape(line) for line in plain_text_body.splitlines())
        return self.build_request(
            app_settings,
            subject=subject,
            plain_text_body=plain_text_body,
            html_body=html_body,
            attachments=attachments,
        )

    async def send_event_email(
        self,
        app_settings: dict[str, str],
        event: dict[str, Any],
        attachments: list[email_pb2.Attachment] | None = None,
    ) -> dict[str, str]:
        request = self.build_event_email_request(app_settings, event, attachments)
        return await self.send_email(request)
