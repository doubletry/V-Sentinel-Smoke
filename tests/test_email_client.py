from __future__ import annotations

import pytest

from core.email_client import AsyncEmailClient


class TestAsyncEmailClient:
    def test_build_request_splits_addresses(self):
        client = AsyncEmailClient()
        request = client.build_request(
            {
                "email_from_address": "sender@example.com",
                "email_from_auth_code": "secret",
                "email_to_addresses": "a@example.com, b@example.com",
                "email_cc_addresses": "cc1@example.com, cc2@example.com",
            },
            subject="test",
            plain_text_body="hello",
        )
        assert list(request.to_addresses) == ["a@example.com", "b@example.com"]
        assert list(request.cc_addresses) == ["cc1@example.com", "cc2@example.com"]

    def test_build_request_requires_sender(self):
        client = AsyncEmailClient()
        with pytest.raises(ValueError):
            client.build_request(
                {
                    "email_from_auth_code": "secret",
                    "email_to_addresses": "a@example.com",
                },
                subject="test",
                plain_text_body="hello",
            )

    def test_product_name_drives_summary_subject(self):
        client = AsyncEmailClient()
        request = client.build_request(
            {
                "site_title": "My Sentinel",
                "email_from_address": "sender@example.com",
                "email_from_auth_code": "secret",
                "email_to_addresses": "a@example.com",
            },
            subject=f"{client._product_name({'site_title': 'My Sentinel'})} 每日总结 2026-01-01",
            plain_text_body="hello",
        )
        assert request.subject == "My Sentinel 每日总结 2026-01-01"

    def test_event_template_renders_context_and_attachment(self):
        client = AsyncEmailClient()
        request = client.build_event_email_request(
            {
                "site_title": "My Sentinel",
                "timezone": "Asia/Shanghai",
                "email_from_address": "sender@example.com",
                "email_from_auth_code": "secret",
                "email_to_addresses": "a@example.com",
                "email_event_subject_template": "{event_label} on {source_name}",
                "email_event_body_template": "{local_time} {event_type} {confidence_percent} {missing}",
            },
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "source_id": "s1",
                "source_name": "Cam1",
                "event_type": "smoke",
                "event_label": "烟雾",
                "labels": ["smoke"],
                "confidence": 0.875,
                "detection_count": 1,
                "frame_id": 2,
                "active_tracks": 1,
            },
        )
        assert request.subject == "烟雾 on Cam1"
        assert "2026-01-01 08:00:00 smoke 87.5% {missing}" in request.plain_text_body

    def test_available_template_placeholders(self):
        placeholders = set(AsyncEmailClient.available_template_placeholders())
        assert {"local_time", "source_name", "event_type", "event_label"} <= placeholders
