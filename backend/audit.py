from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

from backend.auth.dependencies import _extract_bearer_token, _resolve_token_payload
from backend.auth.security import verify_access_token
from backend.db import database as db
from backend.utils.client_ip import client_ip

AUDIT_OPERATION_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("POST", "/api/access/blocked-ips"): ("access.block_ip", "access"),
    ("DELETE", "/api/access/blocked-ips/{ip}"): ("access.unblock_ip", "access"),
    ("POST", "/api/auth/login"): ("auth.login", "auth"),
    ("POST", "/api/auth/password"): ("auth.change_password", "auth"),
    ("POST", "/api/auth/register"): ("auth.register", "auth"),
    ("POST", "/api/messages/batch-delete"): ("messages.batch_delete", "messages"),
    ("DELETE", "/api/messages/{message_id}"): ("messages.delete", "messages"),
    ("POST", "/api/messages/{message_id}/false-positive"): ("messages.mark_false_positive", "messages"),
    ("DELETE", "/api/messages/{message_id}/false-positive"): ("messages.unmark_false_positive", "messages"),
    ("POST", "/api/messages/{message_id}/resend-notification"): ("messages.resend_notification", "messages"),
    ("POST", "/api/notifications/instances"): ("notifications.instances.create", "notifications.instances"),
    ("PUT", "/api/notifications/instances/{provider_id}"): ("notifications.instances.update", "notifications.instances"),
    ("POST", "/api/notifications/instances/{instance_id}/test"): ("notifications.instances.test", "notifications.instances"),
    ("POST", "/api/notifications/policies"): ("notifications.policies.create", "notifications.policies"),
    ("PUT", "/api/notifications/policies/{policy_id}"): ("notifications.policies.update", "notifications.policies"),
    ("POST", "/api/notifications/providers"): ("notifications.providers.create", "notifications.providers"),
    ("PUT", "/api/notifications/providers/{provider_id}"): ("notifications.providers.update", "notifications.providers"),
    ("POST", "/api/notifications/templates"): ("notifications.templates.create", "notifications.templates"),
    ("PUT", "/api/notifications/templates/{template_id}"): ("notifications.templates.update", "notifications.templates"),
    ("POST", "/api/processor/start"): ("processor.start", "processor"),
    ("POST", "/api/processor/stop"): ("processor.stop", "processor"),
    ("POST", "/api/settings/email/test"): ("settings.email_test", "settings"),
    ("PUT", "/api/settings"): ("settings.update", "settings"),
    ("POST", "/api/sources"): ("sources.create", "sources"),
    ("PUT", "/api/sources/{source_id}"): ("sources.update", "sources"),
    ("DELETE", "/api/sources/{source_id}"): ("sources.delete", "sources"),
    ("GET", "/api/sources/{source_id}/rois/export"): ("sources.export_rois", "sources"),
    ("POST", "/api/sources/{source_id}/rois/import"): ("sources.import_rois", "sources"),
    ("POST", "/api/users"): ("users.create", "users"),
    ("PATCH", "/api/users/{username}"): ("users.update", "users"),
    ("DELETE", "/api/users/{username}"): ("users.delete", "users"),
    ("POST", "/api/users/{username}/password"): ("users.reset_password", "users"),
    ("POST", "/api/video-gateways"): ("video_gateways.create", "video_gateways"),
    ("PUT", "/api/video-gateways/{gateway_id}"): ("video_gateways.update", "video_gateways"),
}

RESOURCE_ID_KEYS = (
    "username",
    "source_id",
    "message_id",
    "provider_id",
    "instance_id",
    "template_id",
    "policy_id",
    "gateway_id",
    "ip",
)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", "")
    if route_path:
        return str(route_path)
    return request.url.path


def _should_buffer_body(request: Request) -> bool:
    content_type = str(request.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return False
    try:
        content_length = int(request.headers.get("content-length") or "0")
    except ValueError:
        content_length = 0
    return content_length <= 65536


def _rebuild_request(request: Request, body: bytes) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive)


def _body_dict(body: bytes) -> dict[str, object]:
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fallback_operation(method: str, route_path: str) -> tuple[str, str]:
    parts = [part for part in route_path.split("/") if part and part != "api"]
    literal_parts = [part for part in parts if not part.startswith("{")]
    if not literal_parts:
        return f"api.{method.lower()}", "api"
    resource_type = ".".join(literal_parts[:-1] or literal_parts[:1])
    action = {
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
        "GET": "read",
    }.get(method, method.lower())
    if method == "POST" and len(literal_parts) > 1:
        action = literal_parts[-1].replace("-", "_")
    return f"{resource_type}.{action}", resource_type


def _extract_resource_id(request: Request, payload: dict[str, object], operation_type: str) -> str:
    for key in RESOURCE_ID_KEYS:
        value = request.path_params.get(key)
        if value:
            return str(value)
    for key in ("source_id", "username", "ip", "id", "name"):
        value = payload.get(key)
        if value:
            return str(value)
    if operation_type.startswith("auth.") and payload.get("username"):
        return str(payload["username"])
    return ""


def _extract_response_detail(response: Response) -> str:
    body = getattr(response, "body", None)
    if not isinstance(body, (bytes, bytearray)) or not body:
        return ""
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return ""
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            message = detail.get("message") or detail.get("code")
            if isinstance(message, str):
                return message
        status = payload.get("status")
        if isinstance(status, str):
            return status
    return ""


def _exception_detail(exc: Exception) -> str:
    return exc.__class__.__name__


def _state_text(request: Request, name: str) -> str:
    """Return a stripped string from a request state attribute."""
    value = getattr(request.state, name, "")
    return str(value or "").strip()


async def _resolve_actor(
    request: Request,
    payload: dict[str, object],
    operation_type: str,
) -> tuple[str, str]:
    authorization = request.headers.get("authorization")
    if authorization:
        try:
            token_payload = await _resolve_token_payload(authorization)
            return str(token_payload.get("sub") or ""), str(token_payload.get("role") or "")
        except Exception:
            try:
                token_payload = verify_access_token(_extract_bearer_token(authorization))
                return str(token_payload.get("sub") or ""), str(token_payload.get("role") or "")
            except Exception:
                pass
    username = str(payload.get("username") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    if not role and operation_type == "auth.register":
        role = "admin"
    return username, role


async def write_audit_log(
    request: Request,
    *,
    response: Response | None = None,
    status_code: int,
    payload: dict[str, object] | None = None,
    detail: str = "",
) -> None:
    route_path = _route_template(request)
    method = request.method.upper()
    operation_type, resource_type = AUDIT_OPERATION_MAP.get(
        (method, route_path),
        _fallback_operation(method, route_path),
    )
    should_audit = request.url.path.startswith("/api/") and (
        (method, route_path) in AUDIT_OPERATION_MAP or method in {"POST", "PUT", "PATCH", "DELETE"}
    )
    if not should_audit:
        return

    body_payload = payload or {}
    username, role = await _resolve_actor(request, body_payload, operation_type)
    settings_map = await db.get_all_settings()
    ip = client_ip(request, _truthy(settings_map.get("login_lockout_trust_proxy")))
    response_detail = _extract_response_detail(response) if response is not None else ""
    summary = str(detail or _state_text(request, "audit_detail") or response_detail or "").strip()
    resource_id = _state_text(request, "audit_resource_id") or _extract_resource_id(
        request, body_payload, operation_type
    )
    await db.create_audit_log(
        username=username,
        role=role,
        ip=ip,
        operation_type=operation_type,
        resource_type=resource_type,
        resource_id=resource_id,
        method=method,
        path=request.url.path,
        result="SUCCESS" if 200 <= status_code < 400 else "FAILURE",
        status_code=status_code,
        detail=summary,
    )


async def audit_request(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    body_bytes = b""
    payload: dict[str, object] = {}
    working_request = request
    if _should_buffer_body(request):
        body_bytes = await request.body()
        payload = _body_dict(body_bytes)
        working_request = _rebuild_request(request, body_bytes)

    try:
        response = await call_next(working_request)
    except Exception as exc:
        await write_audit_log(
            working_request,
            status_code=500,
            payload=payload,
            detail=_exception_detail(exc),
        )
        raise

    await write_audit_log(
        working_request,
        response=response,
        status_code=response.status_code,
        payload=payload,
    )
    return response
