"""Notification providers for direct SMTP email and webhook delivery.
通知服务提供者：直接 SMTP 邮件与 Webhook 投递。"""

from __future__ import annotations

import asyncio
import json
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any
from urllib import request as urllib_request

from core.notification_template import render_template


def _split_addresses(raw: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [part for part in (segment.strip() for segment in str(raw or "").split(",")) if part]


@dataclass
class NotificationPayload:
    """Rendered notification content ready for provider delivery.
    已渲染、可交由通知服务投递的内容。"""

    subject: str
    body: str
    context: dict[str, Any] = field(default_factory=dict)
    html_body: str = ""
    attachments: list[tuple[str, bytes, str]] = field(default_factory=list)


class SmtpNotificationProvider:
    """Direct SMTP email provider for notification delivery.
    用于通知投递的直接 SMTP 邮件服务。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config)

    def _build_message(self, payload: NotificationPayload) -> EmailMessage:
        from_address = str(self.config.get("from_address") or "").strip()
        to_addresses = _split_addresses(self.config.get("to_addresses"))
        cc_addresses = _split_addresses(self.config.get("cc_addresses"))
        if not from_address:
            raise ValueError("SMTP from_address is required")
        if not (to_addresses or cc_addresses):
            raise ValueError("At least one SMTP recipient is required")

        message = EmailMessage()
        message["From"] = from_address
        message["To"] = ", ".join(to_addresses)
        if cc_addresses:
            message["Cc"] = ", ".join(cc_addresses)
        message["Subject"] = payload.subject
        message.set_content(payload.body)
        if payload.html_body:
            message.add_alternative(payload.html_body, subtype="html")
        for filename, data, content_type in payload.attachments:
            maintype, _, subtype = content_type.partition("/")
            message.add_attachment(
                data,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=filename,
            )
        return message

    def send_sync(self, payload: NotificationPayload) -> dict[str, str]:
        host = str(self.config.get("smtp_host") or "").strip()
        if not host:
            raise ValueError("SMTP host is required")
        port = int(self.config.get("smtp_port") or 587)
        username = str(self.config.get("smtp_username") or "").strip()
        password = str(self.config.get("smtp_password") or "")
        use_tls = str(self.config.get("use_tls", "true")).lower() in {"1", "true", "yes", "on"}
        message = self._build_message(payload)
        recipients = _split_addresses(self.config.get("to_addresses")) + _split_addresses(
            self.config.get("cc_addresses")
        )

        if use_tls:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if username:
                    smtp.login(username, password)
                smtp.send_message(message, to_addrs=recipients)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(message, to_addrs=recipients)
        return {"status": "SUCCESS", "message": "Email sent via SMTP"}

    async def send(self, payload: NotificationPayload) -> dict[str, str]:
        return await asyncio.to_thread(self.send_sync, payload)


class WebhookNotificationProvider:
    """JSON webhook provider for dictionary-based notification delivery.
    用于按字典 JSON 投递通知的 Webhook 服务。"""

    DEFAULT_PAYLOAD_TEMPLATE = {
        "site_title": "{site_title}",
        "event_type": "{event_type}",
        "event_label": "{event_label}",
        "message": "{message}",
        "timestamp": "{timestamp}",
        "local_time": "{local_time}",
        "timezone": "{timezone}",
        "source": {
            "id": "{source_id}",
            "name": "{source_name}",
            "route_path": "{source_route_path}",
            "remark": "{source_remark}",
        },
        "detection": {
            "labels": "{labels}",
            "confidence": "{confidence}",
            "confidence_percent": "{confidence_percent}",
        },
        "images": {
            "original_url": "{original_image_url}",
            "detected_url": "{detected_image_url}",
        },
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config)

    def _payload_template(self) -> dict[str, Any]:
        raw_template = self.config.get("payload_template")
        if raw_template is None:
            raw_template = self.config.get("payload")
        if raw_template in (None, ""):
            return dict(self.DEFAULT_PAYLOAD_TEMPLATE)
        if not isinstance(raw_template, dict):
            raise ValueError("Webhook payload_template must be a JSON object")
        return raw_template

    def _render_value(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, str):
            return render_template(value, context)
        if isinstance(value, list):
            return [self._render_value(item, context) for item in value]
        if isinstance(value, dict):
            rendered: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("Webhook payload_template keys must be strings")
                rendered[key] = self._render_value(item, context)
            return rendered
        return value

    def send_sync(self, payload: NotificationPayload) -> dict[str, str]:
        url = str(self.config.get("url") or "").strip()
        if not url:
            raise ValueError("Webhook url is required")
        method = str(self.config.get("method") or "POST").upper()
        headers = {
            "Content-Type": "application/json",
            **dict(self.config.get("headers") or {}),
        }
        body = json.dumps(self._render_value(self._payload_template(), payload.context), ensure_ascii=False).encode(
            "utf-8"
        )
        req = urllib_request.Request(url, data=body, headers=headers, method=method)
        with urllib_request.urlopen(req, timeout=10) as response:
            return {"status": "SUCCESS", "message": str(response.status)}

    async def send(self, payload: NotificationPayload) -> dict[str, str]:
        return await asyncio.to_thread(self.send_sync, payload)
