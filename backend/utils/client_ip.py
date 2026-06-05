from __future__ import annotations

import ipaddress

from fastapi import Request


def _normalize_ip(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return ""


def client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            normalized = _normalize_ip(first)
            if normalized:
                return normalized
        real_ip = request.headers.get("x-real-ip")
        normalized = _normalize_ip(real_ip)
        if normalized:
            return normalized
    if request.client is not None and request.client.host:
        normalized = _normalize_ip(request.client.host)
        if normalized:
            return normalized
    return ""
