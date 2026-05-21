from __future__ import annotations

from typing import Any


def build_email_settings_smtp_config(settings: dict[str, Any]) -> dict[str, Any]:
    """Build SMTP provider config from DB-backed email settings."""
    from_address = str(settings.get("email_from_address") or "").strip()
    use_tls = str(settings.get("email_smtp_use_tls", "true")).lower() in {"1", "true", "yes", "on"}
    return {
        "smtp_host": settings.get("email_smtp_host") or settings.get("vengine_host", ""),
        "smtp_port": settings.get("email_smtp_port") or "587",
        "smtp_username": from_address,
        "smtp_password": settings.get("email_smtp_password", ""),
        "from_address": from_address,
        "to_addresses": settings.get("email_to_addresses", ""),
        "cc_addresses": settings.get("email_cc_addresses", ""),
        "use_tls": use_tls,
    }


def has_email_settings_recipients(config: dict[str, Any]) -> bool:
    """Return whether SMTP config has enough addressing information to send."""
    return bool(
        str(config.get("smtp_host") or "").strip()
        and str(config.get("from_address") or "").strip()
        and (
            str(config.get("to_addresses") or "").strip()
            or str(config.get("cc_addresses") or "").strip()
        )
    )
