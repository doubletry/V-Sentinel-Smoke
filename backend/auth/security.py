from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from backend.auth.roles import ROLE_PERMISSIONS
from backend.db import database as db

_PROCESS_SECRET = secrets.token_urlsafe(32)
_TOKEN_TTL_HOURS = 8
_PASSWORD_ITERATIONS = 600_000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _auth_secret() -> str:
    """Return the HMAC secret used to sign API tokens.
    返回用于签名 API token 的 HMAC 密钥。

    Production deployments should set ``V_SENTINEL_AUTH_SECRET``. If it is not
    set, a process-local random secret is used so tokens are still signed but
    automatically expire on process restart.
    生产部署应设置 ``V_SENTINEL_AUTH_SECRET``。未设置时会使用进程内随机密钥，
    token 仍有签名保护，但服务重启后会全部失效。
    """
    return os.getenv("V_SENTINEL_AUTH_SECRET") or _PROCESS_SECRET


def _role_password(role: str) -> str:
    env_name = f"V_SENTINEL_{role.upper()}_PASSWORD"
    return os.getenv(env_name, "")


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-SHA256.
    使用 PBKDF2-SHA256 哈希明文密码。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${_PASSWORD_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash.
    校验明文密码是否匹配已存储 PBKDF2 哈希。"""
    try:
        algorithm, iterations, salt_b64, digest_b64 = str(password_hash or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def _sign(payload_b64: str) -> str:
    digest = hmac.new(_auth_secret().encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_access_token(*, username: str, role: str) -> dict[str, str]:
    """Create a signed bearer token for an authenticated role.
    为已认证角色创建签名 Bearer token。"""
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Invalid role")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_TTL_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": int(expires_at.timestamp()),
        "nonce": secrets.token_urlsafe(12),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    token = f"{payload_b64}.{_sign(payload_b64)}"
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role,
        "expires_at": expires_at.isoformat(),
    }


def authenticate_role(username: str, password: str, role: str) -> dict[str, str]:
    """Authenticate against environment-provided role passwords.
    使用环境变量提供的角色密码完成认证。"""
    normalized_role = role.strip().lower()
    if normalized_role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    expected_password = _role_password(normalized_role)
    if not expected_password:
        raise HTTPException(status_code=503, detail=f"Password for role '{normalized_role}' is not configured")
    if not hmac.compare_digest(password, expected_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_access_token(username=username.strip() or normalized_role, role=normalized_role)


async def authenticate_user(username: str, password: str, role: str) -> dict[str, str]:
    """Authenticate against registered users first, then legacy env passwords.
    优先使用已注册用户认证，其次回退到旧环境变量密码认证。"""
    normalized_username = str(username or "").strip()
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    record = await db.get_user_auth_record(normalized_username)
    if record is not None:
        record_username, password_hash, stored_role = record
        if stored_role != normalized_role:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not verify_password(password, password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return create_access_token(username=record_username, role=stored_role)

    return authenticate_role(normalized_username, password, normalized_role)


def verify_access_token(token: str) -> dict[str, Any]:
    """Verify and decode a signed bearer token.
    校验并解码签名 Bearer token。"""
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    expected_signature = _sign(payload_b64)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token payload") from exc
    role = str(payload.get("role") or "")
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=401, detail="Invalid token role")
    exp = int(payload.get("exp") or 0)
    if exp < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload
