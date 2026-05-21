from __future__ import annotations

import asyncio
import base64
import json
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import aiosqlite
from loguru import logger

from backend.config import DEFAULT_APP_SETTINGS, settings
from backend.models.schemas import ROI, ROICreate, UserAccount, VideoSource, VideoSourceCreate, VideoSourceUpdate
from backend.models.schemas import (
    NotificationPolicy,
    NotificationPolicyCreate,
    NotificationPolicyUpdate,
    NotificationProvider,
    NotificationProviderCreate,
    NotificationProviderUpdate,
    NotificationTemplate,
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
    SceneDefinition,
    VideoGateway,
    VideoGatewayCreate,
    VideoGatewayUpdate,
)


_DB_PATH = settings.db_path
DEFAULT_SCENE_ID = "smoke"

CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS video_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rtsp_url TEXT NOT NULL UNIQUE,
    route_path TEXT NOT NULL DEFAULT '',
    source_remark TEXT NOT NULL DEFAULT '',
    push_result_stream INTEGER NOT NULL DEFAULT 1,
    alarm_confidence_threshold REAL,
    scene_id TEXT NOT NULL DEFAULT 'smoke',
    notification_policy_ids TEXT NOT NULL DEFAULT '[]',
    desired_analysis_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

CREATE_ROIS_TABLE = """
CREATE TABLE IF NOT EXISTS rois (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES video_sources(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    points TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CREATE_ANALYSIS_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_messages (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_id TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    image_url TEXT,
    original_image_url TEXT,
    detected_image_url TEXT,
    false_positive INTEGER NOT NULL DEFAULT 0,
    image_base64 TEXT,
    created_at TEXT NOT NULL
);
"""

CREATE_SCENES_TABLE = """
CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    label_zh TEXT NOT NULL,
    label_en TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    required_services TEXT NOT NULL DEFAULT '[]',
    default_roi_tags TEXT NOT NULL DEFAULT '[]',
    event_types TEXT NOT NULL DEFAULT '[]',
    default_config TEXT NOT NULL DEFAULT '{}',
    expert_config_schema TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

CREATE_VIDEO_GATEWAYS_TABLE = """
CREATE TABLE IF NOT EXISTS video_gateways (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rtsp_base_url TEXT NOT NULL,
    webrtc_base_url TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""

CREATE_NOTIFICATION_PROVIDERS_TABLE = """
CREATE TABLE IF NOT EXISTS notification_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('email', 'webhook')),
    enabled INTEGER NOT NULL DEFAULT 1,
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

CREATE_NOTIFICATION_TEMPLATES_TABLE = """
CREATE TABLE IF NOT EXISTS notification_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    channel TEXT NOT NULL CHECK(channel IN ('email', 'webhook')),
    subject_template TEXT NOT NULL DEFAULT '',
    body_template TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

CREATE_NOTIFICATION_POLICIES_TABLE = """
CREATE TABLE IF NOT EXISTS notification_policies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    cooldown_seconds INTEGER NOT NULL DEFAULT 300,
    provider_ids TEXT NOT NULL DEFAULT '[]',
    template_id TEXT,
    created_at TEXT NOT NULL
);
"""

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'operator', 'admin')),
    created_at TEXT NOT NULL
);
"""

MESSAGE_IMAGE_URL_PREFIX = "/api/messages"
MESSAGE_IMAGE_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MESSAGE_IMAGE_FILENAME_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")

PRAGMA_FK = "PRAGMA foreign_keys = ON;"
PRAGMA_WAL = "PRAGMA journal_mode = WAL;"
PRAGMA_SYNCHRONOUS = "PRAGMA synchronous = NORMAL;"
PRAGMA_BUSY_TIMEOUT = "PRAGMA busy_timeout = 5000;"

_shared_db: aiosqlite.Connection | None = None
_shared_db_path: str | None = None
_shared_db_loop: asyncio.AbstractEventLoop | None = None
_db_lock_loop: asyncio.AbstractEventLoop | None = None
_db_init_lock: asyncio.Lock | None = None
_db_use_lock: asyncio.Lock | None = None


def _get_db_locks() -> tuple[asyncio.Lock, asyncio.Lock]:
    """Return loop-local locks for shared SQLite connection access.
    返回用于共享 SQLite 连接访问的事件循环局部锁。"""
    global _db_lock_loop, _db_init_lock, _db_use_lock

    loop = asyncio.get_running_loop()
    if _db_lock_loop is not loop or _db_init_lock is None or _db_use_lock is None:
        _db_lock_loop = loop
        _db_init_lock = asyncio.Lock()
        _db_use_lock = asyncio.Lock()
    return _db_init_lock, _db_use_lock


async def _configure_db_connection(db: aiosqlite.Connection) -> None:
    """Apply SQLite pragmas for correctness and concurrent-read performance.
    配置 SQLite pragma，以提升正确性和并发读性能。"""
    await db.execute(PRAGMA_FK)
    await db.execute(PRAGMA_WAL)
    await db.execute(PRAGMA_SYNCHRONOUS)
    await db.execute(PRAGMA_BUSY_TIMEOUT)
    await db.commit()


async def _close_shared_db_unlocked() -> None:
    """Close the shared database connection without reacquiring init lock.
    关闭共享数据库连接，不重复获取初始化锁。"""
    global _shared_db, _shared_db_path, _shared_db_loop

    if _shared_db is None:
        return

    try:
        await _shared_db.close()
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning("Failed to close shared SQLite connection: {}", exc)
    finally:
        _shared_db = None
        _shared_db_path = None
        _shared_db_loop = None


async def _get_shared_db() -> aiosqlite.Connection:
    """Return a reusable SQLite connection configured for this DB path.
    返回为当前 DB 路径配置好的可复用 SQLite 连接。"""
    global _shared_db, _shared_db_path, _shared_db_loop

    init_lock, _ = _get_db_locks()
    loop = asyncio.get_running_loop()
    async with init_lock:
        if _shared_db is not None and (
            _shared_db_path != _DB_PATH or _shared_db_loop is not loop
        ):
            await _close_shared_db_unlocked()

        if _shared_db is None:
            db = await aiosqlite.connect(_DB_PATH)
            db.row_factory = aiosqlite.Row
            await _configure_db_connection(db)
            _shared_db = db
            _shared_db_path = _DB_PATH
            _shared_db_loop = loop
            logger.info("Opened shared SQLite connection at {}", _DB_PATH)

        return _shared_db


@asynccontextmanager
async def _db_session() -> aiosqlite.Connection:
    """Serialize access through the shared SQLite connection.
    通过共享 SQLite 连接串行化数据库访问。"""
    db = await _get_shared_db()
    _, use_lock = _get_db_locks()
    async with use_lock:
        yield db


async def close_db() -> None:
    """Close the shared SQLite connection if one is open.
    如果共享 SQLite 连接已打开，则关闭它。"""
    init_lock, _ = _get_db_locks()
    async with init_lock:
        await _close_shared_db_unlocked()


async def init_db() -> None:
    """Create database tables if they don't exist.
    创建数据库表（如果不存在）。"""
    async with _db_session() as db:
        await db.execute(CREATE_SOURCES_TABLE)
        await db.execute(CREATE_ROIS_TABLE)
        await db.execute(CREATE_SETTINGS_TABLE)
        await db.execute(CREATE_ANALYSIS_MESSAGES_TABLE)
        await db.execute(CREATE_SCENES_TABLE)
        await db.execute(CREATE_VIDEO_GATEWAYS_TABLE)
        await db.execute(CREATE_NOTIFICATION_PROVIDERS_TABLE)
        await db.execute(CREATE_NOTIFICATION_TEMPLATES_TABLE)
        await db.execute(CREATE_NOTIFICATION_POLICIES_TABLE)
        await db.execute(CREATE_USERS_TABLE)
        await _ensure_column_exists(db, "video_sources", "route_path", "TEXT NOT NULL DEFAULT ''")
        await _ensure_column_exists(db, "video_sources", "source_remark", "TEXT NOT NULL DEFAULT ''")
        await _ensure_column_exists(db, "video_sources", "push_result_stream", "INTEGER NOT NULL DEFAULT 1")
        await _ensure_column_exists(db, "video_sources", "alarm_confidence_threshold", "REAL")
        await _ensure_column_exists(db, "video_sources", "scene_id", "TEXT NOT NULL DEFAULT 'smoke'")
        await _ensure_column_exists(
            db,
            "video_sources",
            "notification_policy_ids",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        await _ensure_column_exists(
            db,
            "video_sources",
            "desired_analysis_enabled",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await _ensure_column_exists(db, "analysis_messages", "image_url", "TEXT")
        await _ensure_column_exists(db, "analysis_messages", "original_image_url", "TEXT")
        await _ensure_column_exists(db, "analysis_messages", "detected_image_url", "TEXT")
        await _ensure_column_exists(
            db,
            "analysis_messages",
            "false_positive",
            "INTEGER NOT NULL DEFAULT 0",
        )
        for key, value in DEFAULT_APP_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await _seed_default_scene(db)
        await _seed_default_video_gateway(db)
        await _seed_default_notification_records(db)
        await db.commit()
    logger.info("Database initialized at {}", _DB_PATH)


def _now_iso() -> str:
    """Return current UTC time as an ISO 8601 string.
    返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


async def _ensure_column_exists(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    """Add a missing SQLite column for lightweight schema migrations.
    为轻量级 SQLite 迁移补充缺失列。"""
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        rows = await cursor.fetchall()
    if any(str(row[1]) == column_name for row in rows):
        return
    await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


async def _seed_default_scene(db: aiosqlite.Connection) -> None:
    """Seed the built-in smoke/fire scene for blank databases.
    为全新数据库写入内置烟火场景。"""
    now = _now_iso()
    await db.execute(
        "INSERT OR IGNORE INTO scenes "
        "(id, label_zh, label_en, description, required_services, default_roi_tags, "
        "event_types, default_config, expert_config_schema, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "smoke",
            "烟火检测",
            "Smoke/Fire Detection",
            "Detects smoke and fire with temporal post-processing.",
            _json_dumps(["detection"]),
            _json_dumps(["smoke_zone", "fire_zone"]),
            _json_dumps(["smoke", "fire"]),
            _json_dumps(
                {
                    "smoke_detection_model_name": DEFAULT_APP_SETTINGS["smoke_detection_model_name"],
                    "smoke_detection_confidence": DEFAULT_APP_SETTINGS["smoke_detection_confidence"],
                    "smoke_detection_nms": DEFAULT_APP_SETTINGS["smoke_detection_nms"],
                }
            ),
            _json_dumps(
                {
                    "expert_mode": True,
                    "groups": ["model", "temporal", "false_positive_filters"],
                }
            ),
            now,
        ),
    )
    await db.execute(
        "INSERT OR IGNORE INTO scenes "
        "(id, label_zh, label_en, description, required_services, default_roi_tags, "
        "event_types, default_config, expert_config_schema, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "fire_door",
            "消防门检测",
            "Fire Door Detection",
            "Classifies one or more fire-door ROIs and alerts when a configured open state is confirmed.",
            _json_dumps(["classification"]),
            _json_dumps(["fire_door"]),
            _json_dumps(["fire_door_open"]),
            _json_dumps(
                {
                    "fire_door_classification_model_name": DEFAULT_APP_SETTINGS["fire_door_classification_model_name"],
                    "fire_door_classification_confidence": DEFAULT_APP_SETTINGS["fire_door_classification_confidence"],
                    "fire_door_alarm_labels": DEFAULT_APP_SETTINGS["fire_door_alarm_labels"],
                }
            ),
            _json_dumps({"expert_mode": True, "groups": ["model", "labels", "temporal", "notifications"]}),
            now,
        ),
    )
    await db.execute(
        "INSERT OR IGNORE INTO scenes "
        "(id, label_zh, label_en, description, required_services, default_roi_tags, "
        "event_types, default_config, expert_config_schema, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "template",
            "场景开发模板",
            "Scene Development Template",
            "Runnable backend template showing frame access, custom processing, results, notifications, and persistence.",
            _json_dumps([]),
            _json_dumps(["template_zone"]),
            _json_dumps(["normal_area", "bright_area"]),
            _json_dumps({}),
            _json_dumps({"expert_mode": True, "groups": ["custom_processing", "notifications"]}),
            now,
        ),
    )
    await db.execute(
        "UPDATE scenes SET default_config = ? "
        "WHERE id = ? AND default_config IN (?, ?)",
        (
            _json_dumps({}),
            "template",
            _json_dumps({"brightness_threshold": 200}),
            _json_dumps({"brighten_threshold": 200}),
        ),
    )


async def _seed_default_video_gateway(db: aiosqlite.Connection) -> None:
    """Seed the default MediaMTX gateway with shared credentials.
    使用共享凭据写入默认 MediaMTX 网关。"""
    now = _now_iso()
    username = DEFAULT_APP_SETTINGS.get("mediamtx_username", "")
    password = DEFAULT_APP_SETTINGS.get("mediamtx_password", "")
    await db.execute(
        "INSERT OR IGNORE INTO video_gateways "
        "(id, name, rtsp_base_url, webrtc_base_url, username, password, enabled, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "default-mediamtx",
            "Default MediaMTX",
            DEFAULT_APP_SETTINGS["mediamtx_rtsp_addr"],
            DEFAULT_APP_SETTINGS["mediamtx_webrtc_addr"],
            username,
            password,
            1,
            now,
        ),
    )


async def _seed_default_notification_records(db: aiosqlite.Connection) -> None:
    """Seed disabled email/webhook notification placeholders for blank databases.
    为全新数据库写入默认禁用的邮件与 Webhook 通知占位记录。"""
    now = _now_iso()
    await db.execute(
        "INSERT OR IGNORE INTO notification_providers "
        "(id, name, type, enabled, config, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "default-email",
            "Default SMTP Email",
            "email",
            0,
            _json_dumps(
                {
                    "smtp_host": "",
                    "smtp_port": "587",
                    "smtp_username": "",
                    "smtp_password": "",
                    "from_address": "",
                    "to_addresses": [],
                    "cc_addresses": [],
                    "use_tls": True,
                }
            ),
            now,
        ),
    )
    await db.execute(
        "INSERT OR IGNORE INTO notification_providers "
        "(id, name, type, enabled, config, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "default-webhook",
            "Default Webhook",
            "webhook",
            0,
            _json_dumps({"url": "", "method": "POST", "headers": {}}),
            now,
        ),
    )
    await db.execute(
        "INSERT OR IGNORE INTO notification_templates "
        "(id, name, channel, subject_template, body_template, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "default-event-email",
            "Default Event Email",
            "email",
            DEFAULT_APP_SETTINGS["email_event_subject_template"],
            DEFAULT_APP_SETTINGS["email_event_body_template"],
            now,
        ),
    )
    await db.execute(
        "INSERT OR IGNORE INTO notification_policies "
        "(id, name, enabled, cooldown_seconds, provider_ids, template_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "default-alert-policy",
            "Default Alert Policy",
            1,
            int(DEFAULT_APP_SETTINGS["smoke_email_cooldown_seconds"]),
            _json_dumps(["default-email"]),
            "default-event-email",
            now,
        ),
    )


def get_message_image_dir() -> Path:
    """Return the filesystem directory used for persisted message thumbnails.
    返回持久化消息缩略图使用的文件系统目录。"""
    return Path(_DB_PATH).resolve().parent / "message_thumbnails"


def get_false_positive_dir() -> Path:
    """Return the filesystem directory used for exported false-positive images.
    返回导出的误报图片目录。"""
    return Path(_DB_PATH).resolve().parent / "false_positives"


def build_analysis_message_image_url(message_id: str, *, kind: str = "detected") -> str:
    safe_kind = "original" if str(kind).strip().lower() == "original" else "detected"
    return f"{MESSAGE_IMAGE_URL_PREFIX}/{message_id}/images/{safe_kind}"


def _message_image_path_from_stored_value(image_value: str) -> Path | None:
    text = str(image_value or "").strip().strip("/")
    if not text:
        return None
    if text.startswith("api/messages/images/"):
        text = text[len("api/messages/images/") :]
    elif text.startswith("message-images/"):
        text = text[len("message-images/") :]
    parts = text.split("/")
    if len(parts) != 2:
        return None
    day, filename = parts
    return resolve_message_image_path(day, filename)


def _normalize_stored_message_image_value(image_value: str | None) -> str | None:
    path = _message_image_path_from_stored_value(str(image_value or ""))
    if path is None:
        return None
    return f"{path.parent.name}/{path.name}"


def _normalize_bool_db_value(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_list(value: object) -> list:
    """Parse a JSON list stored in SQLite; return [] on invalid input.
    解析 SQLite 中保存的 JSON 列表，非法输入返回空列表。"""
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: object) -> dict:
    """Parse a JSON object stored in SQLite; return {} on invalid input.
    解析 SQLite 中保存的 JSON 对象，非法输入返回空对象。"""
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _message_image_path_from_url(image_url: str) -> Path | None:
    return _message_image_path_from_stored_value(image_url)


def resolve_message_image_path(day: str, filename: str) -> Path | None:
    """Resolve one validated message-image path inside the thumbnail directory.
    解析缩略图目录中的单个已校验消息图片路径。"""
    safe_day = str(day or "").strip()
    safe_filename = str(filename or "").strip()
    if not safe_day or not safe_filename:
        return None
    if not MESSAGE_IMAGE_DAY_RE.fullmatch(safe_day):
        return None
    if not MESSAGE_IMAGE_FILENAME_RE.fullmatch(safe_filename):
        return None
    root = get_message_image_dir().resolve()
    candidate = (root / safe_day / safe_filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def materialize_message_image(image_base64: str | None, *, timestamp: str = "") -> str | None:
    """Persist one base64 message image to disk and return its stored path.
    将单条消息的 base64 图片落盘并返回其存储路径。"""
    payload = str(image_base64 or "").strip()
    if not payload:
        return None
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:
        logger.warning("Failed to decode message image payload: {}", exc)
        return None
    day = str(timestamp or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    directory = get_message_image_dir() / day
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    file_path = directory / filename
    file_path.write_bytes(raw)
    return f"{day}/{filename}"


def export_false_positive_images(
    message_id: str,
    *,
    timestamp: str,
    original_image_url: str | None = None,
    detected_image_url: str | None = None,
) -> list[str]:
    """Copy original/detected images into the false-positive export directory.
    将原图/检测图复制到误报导出目录。"""
    exported: list[str] = []
    day = str(timestamp or "")[:10].strip()
    if not MESSAGE_IMAGE_DAY_RE.fullmatch(day):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_dir = get_false_positive_dir() / day
    target_dir.mkdir(parents=True, exist_ok=True)
    export_basename = uuid.uuid4().hex

    original_path = _message_image_path_from_url(str(original_image_url or ""))
    if original_path is not None and original_path.is_file():
        destination = target_dir / f"{export_basename}.jpg"
        shutil.copy2(original_path, destination)
        exported.append(str(destination))

    detected_path = _message_image_path_from_url(str(detected_image_url or ""))
    if detected_path is not None and detected_path.is_file():
        destination = target_dir / f"{export_basename}_detected.jpg"
        shutil.copy2(detected_path, destination)
        exported.append(str(destination))

    return exported


def _delete_message_image(image_url: str | None) -> None:
    """Best-effort deletion of a persisted message thumbnail.
    尽力删除持久化消息缩略图。"""
    path = _message_image_path_from_url(str(image_url or ""))
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to delete persisted message image {}: {}", path, exc)


def _message_retention_cutoff_iso(retention_days_raw: str | int) -> str:
    """Convert retention-days input into a UTC cutoff timestamp.
    将保留天数输入转换为 UTC 截止时间戳。"""
    try:
        safe_days = min(30, max(1, int(retention_days_raw)))
    except (TypeError, ValueError):
        safe_days = 7
    return (datetime.now(timezone.utc) - timedelta(days=safe_days)).isoformat()


async def _get_rois_for_source(db: aiosqlite.Connection, source_id: str) -> list[ROI]:
    """Fetch all ROIs for a given source from the database.
    从数据库获取指定视频源的所有 ROI。"""
    async with db.execute(
        "SELECT id, type, points, tag FROM rois WHERE source_id = ? ORDER BY created_at",
        (source_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    result: list[ROI] = []
    for row in rows:
        roi_id, roi_type, points_json, tag = row
        points = json.loads(points_json)
        result.append(ROI(id=roi_id, type=roi_type, points=points, tag=tag))
    return result


async def _get_rois_for_sources(
    db: aiosqlite.Connection, source_ids: list[str]
) -> dict[str, list[ROI]]:
    """Fetch ROIs for multiple sources in one query to avoid N+1 list loading."""
    if not source_ids:
        return {}
    result: dict[str, list[ROI]] = {source_id: [] for source_id in source_ids}
    for offset in range(0, len(source_ids), 900):
        chunk = source_ids[offset : offset + 900]
        placeholders = ",".join("?" for _ in chunk)
        async with db.execute(
            f"SELECT source_id, id, type, points, tag FROM rois "
            f"WHERE source_id IN ({placeholders}) ORDER BY source_id, created_at",
            chunk,
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            source_id, roi_id, roi_type, points_json, tag = row
            points = json.loads(points_json)
            result.setdefault(source_id, []).append(
                ROI(id=roi_id, type=roi_type, points=points, tag=tag)
            )
    return result


def _row_to_source(row: tuple, rois: list[ROI]) -> VideoSource:
    """Convert a database row and ROI list to a VideoSource model.
    将数据库行与 ROI 列表转换为 VideoSource 模型。"""
    if hasattr(row, "keys"):
        row_keys = set(row.keys())
        source_id = row["id"]
        name = row["name"]
        rtsp_url = row["rtsp_url"]
        route_path = row["route_path"] if "route_path" in row_keys else ""
        source_remark = row["source_remark"] if "source_remark" in row_keys else ""
        push_result_stream = row["push_result_stream"] if "push_result_stream" in row_keys else 1
        alarm_confidence_threshold = (
            row["alarm_confidence_threshold"] if "alarm_confidence_threshold" in row_keys else None
        )
        scene_id = row["scene_id"] if "scene_id" in row_keys else DEFAULT_SCENE_ID
        notification_policy_ids = (
            row["notification_policy_ids"] if "notification_policy_ids" in row_keys else "[]"
        )
        desired_analysis_enabled = (
            row["desired_analysis_enabled"] if "desired_analysis_enabled" in row_keys else 0
        )
        created_at = row["created_at"]
    else:
        (
            source_id,
            name,
            rtsp_url,
            route_path,
            source_remark,
            push_result_stream,
            alarm_confidence_threshold,
            scene_id,
            notification_policy_ids,
            desired_analysis_enabled,
            created_at,
        ) = row
    return VideoSource(
        id=source_id,
        name=name,
        rtsp_url=rtsp_url,
        route_path=str(route_path or ""),
        source_remark=str(source_remark or ""),
        push_result_stream=(
            str(push_result_stream).strip().lower()
            not in {"0", "false", "no", "off"}
        ),
        alarm_confidence_threshold=(
            float(alarm_confidence_threshold)
            if alarm_confidence_threshold is not None
            else None
        ),
        scene_id=str(scene_id or DEFAULT_SCENE_ID),
        notification_policy_ids=[str(item) for item in _json_list(notification_policy_ids)],
        desired_analysis_enabled=_normalize_bool_db_value(desired_analysis_enabled),
        rois=rois,
        created_at=created_at,
    )


async def _get_setting_from_db(
    db: aiosqlite.Connection,
    key: str,
    default: str = "",
) -> str:
    async with db.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (key,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return default
    return str(row[0] or default)


def _shared_mediamtx_credentials_from_settings(
    settings: dict[str, str] | None,
) -> tuple[str, str]:
    """Resolve one shared MediaMTX username/password pair from current settings.
    从当前设置中解析一套共享的 MediaMTX 用户名/密码。"""
    source = settings or {}
    username = str(
        source.get("mediamtx_username")
        or source.get("mediamtx_rtsp_username")
        or source.get("mediamtx_webrtc_username")
        or DEFAULT_APP_SETTINGS.get("mediamtx_username", "")
    )
    password = str(
        source.get("mediamtx_password")
        or source.get("mediamtx_rtsp_password")
        or source.get("mediamtx_webrtc_password")
        or DEFAULT_APP_SETTINGS.get("mediamtx_password", "")
    )
    return username, password


async def _get_shared_mediamtx_credentials_from_db(
    db: aiosqlite.Connection,
) -> tuple[str, str]:
    """Resolve one shared MediaMTX username/password pair from the database.
    从数据库中解析一套共享的 MediaMTX 用户名/密码。"""
    username = await _get_setting_from_db(
        db,
        "mediamtx_username",
        DEFAULT_APP_SETTINGS.get("mediamtx_username", ""),
    )
    password = await _get_setting_from_db(
        db,
        "mediamtx_password",
        DEFAULT_APP_SETTINGS.get("mediamtx_password", ""),
    )
    legacy_rtsp_username = await _get_setting_from_db(
        db,
        "mediamtx_rtsp_username",
        DEFAULT_APP_SETTINGS.get("mediamtx_username", ""),
    )
    legacy_webrtc_username = await _get_setting_from_db(
        db,
        "mediamtx_webrtc_username",
        DEFAULT_APP_SETTINGS.get("mediamtx_username", ""),
    )
    legacy_rtsp_password = await _get_setting_from_db(
        db,
        "mediamtx_rtsp_password",
        DEFAULT_APP_SETTINGS.get("mediamtx_password", ""),
    )
    legacy_webrtc_password = await _get_setting_from_db(
        db,
        "mediamtx_webrtc_password",
        DEFAULT_APP_SETTINGS.get("mediamtx_password", ""),
    )
    resolved_username = (
        username
        if str(username).strip()
        else (legacy_rtsp_username or legacy_webrtc_username)
    )
    resolved_password = (
        password
        if str(password).strip()
        else (legacy_rtsp_password or legacy_webrtc_password)
    )
    return resolved_username, resolved_password


async def _get_active_plugin_id_from_db(db: aiosqlite.Connection) -> str:
    """Resolve the globally active processing plugin.
    解析当前全局启用的处理插件。"""
    plugin_id = await _get_setting_from_db(
        db,
        "active_plugin_id",
        DEFAULT_APP_SETTINGS.get("active_plugin_id", DEFAULT_SCENE_ID),
    )
    return str(plugin_id or DEFAULT_SCENE_ID).strip() or DEFAULT_SCENE_ID


async def _resolve_source_rtsp_url(
    db: aiosqlite.Connection,
    *,
    rtsp_url: str | None = None,
    route_path: str | None = None,
) -> str:
    route = _normalize_route_path(route_path)
    if route:
        rtsp_base_address = await _get_setting_from_db(
            db,
            "mediamtx_rtsp_addr",
            DEFAULT_APP_SETTINGS.get("mediamtx_rtsp_addr", ""),
        )
        rtsp_username, rtsp_password = await _get_shared_mediamtx_credentials_from_db(db)
        resolved_rtsp_url = build_source_rtsp_url(
            rtsp_base_address,
            route,
            username=rtsp_username,
            password=rtsp_password,
        )
        if not resolved_rtsp_url:
            raise ValueError("MediaMTX RTSP base address is not configured")
        return resolved_rtsp_url
    return str(rtsp_url or "").strip()


def _normalize_base_address(value: str | None) -> str:
    return str(value or "").strip().rstrip("/")


def _normalize_route_path(value: str | None) -> str:
    return str(value or "").strip().strip("/")


def _compose_netloc_with_auth(
    parsed_base,
    username: str | None = None,
    password: str | None = None,
) -> str:
    host = parsed_base.hostname or ""
    if not host:
        return parsed_base.netloc
    port = f":{parsed_base.port}" if parsed_base.port is not None else ""
    auth_username = str(username or "").strip()
    auth_password = str(password or "")
    if not auth_username:
        return f"{host}{port}"
    auth = quote(auth_username, safe="")
    if auth_password:
        auth += f":{quote(auth_password, safe='')}"
    return f"{auth}@{host}{port}"


def build_source_rtsp_url(
    rtsp_base_address: str,
    route_path: str,
    *,
    username: str | None = None,
    password: str | None = None,
) -> str:
    base = _normalize_base_address(rtsp_base_address)
    route = _normalize_route_path(route_path)
    if not base or not route:
        return ""

    parsed_base = urlsplit(base)
    if parsed_base.scheme and parsed_base.netloc:
        base_path = parsed_base.path.rstrip("/")
        full_path = f"{base_path}/{route}" if base_path else f"/{route}"
        return urlunsplit(
            (
                parsed_base.scheme,
                _compose_netloc_with_auth(parsed_base, username, password),
                full_path,
                parsed_base.query,
                parsed_base.fragment,
            )
        )

    auth_username = str(username or "").strip()
    auth_password = str(password or "")
    auth = ""
    if auth_username:
        auth = auth_username if not auth_password else f"{auth_username}:{auth_password}"
        auth = f"{auth}@"
    return f"{auth}{base}/{route}"


def extract_source_route_path(
    rtsp_url: str,
    rtsp_base_address: str | None = None,
) -> str:
    full = str(rtsp_url or "").strip()
    if not full:
        return ""

    parsed_full = urlsplit(full)
    full_path = _normalize_route_path(parsed_full.path if parsed_full.scheme else full)
    base = _normalize_base_address(rtsp_base_address)
    if not base:
        return full_path

    parsed_base = urlsplit(base)
    if (
        parsed_full.scheme
        and parsed_base.scheme
        and parsed_full.scheme == parsed_base.scheme
        and parsed_full.hostname == parsed_base.hostname
        and parsed_full.port == parsed_base.port
    ):
        base_path = _normalize_route_path(parsed_base.path)
        if base_path and full_path.startswith(f"{base_path}/"):
            return _normalize_route_path(full_path[len(base_path) + 1 :])
        if not base_path:
            return full_path
    return full_path


async def create_source(source: VideoSourceCreate) -> VideoSource:
    """Insert a new video source into the database.
    向数据库插入新的视频源。"""
    source_id = str(uuid.uuid4())
    created_at = _now_iso()
    async with _db_session() as db:
        active_plugin_id = await _get_active_plugin_id_from_db(db)
        if "scene_id" in source.model_fields_set:
            requested_scene_id = str(source.scene_id or "").strip() or DEFAULT_SCENE_ID
            if requested_scene_id != active_plugin_id:
                raise ValueError(
                    f"scene_id must match active_plugin_id '{active_plugin_id}'"
                )
        route_path = _normalize_route_path(source.route_path) or extract_source_route_path(
            str(source.rtsp_url or ""),
            await _get_setting_from_db(db, "mediamtx_rtsp_addr", DEFAULT_APP_SETTINGS.get("mediamtx_rtsp_addr", "")),
        )
        resolved_rtsp_url = await _resolve_source_rtsp_url(
            db,
            rtsp_url=source.rtsp_url,
            route_path=source.route_path,
        )
        await db.execute(
            "INSERT INTO video_sources "
            "(id, name, rtsp_url, route_path, source_remark, push_result_stream, "
            "alarm_confidence_threshold, scene_id, notification_policy_ids, desired_analysis_enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                source.name,
                resolved_rtsp_url,
                route_path,
                source.source_remark,
                1 if source.push_result_stream else 0,
                source.alarm_confidence_threshold,
                active_plugin_id,
                _json_dumps(source.notification_policy_ids),
                0,
                created_at,
            ),
        )
        await db.commit()
    return VideoSource(
        id=source_id,
        name=source.name,
        rtsp_url=resolved_rtsp_url,
        route_path=route_path,
        source_remark=source.source_remark,
        push_result_stream=source.push_result_stream,
        alarm_confidence_threshold=source.alarm_confidence_threshold,
        scene_id=active_plugin_id,
        notification_policy_ids=source.notification_policy_ids,
        desired_analysis_enabled=False,
        rois=[],
        created_at=created_at,
    )


async def get_source(source_id: str) -> VideoSource | None:
    """Retrieve a single video source by ID, or None if not found.
    按 ID 获取单个视频源，未找到则返回 None。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, rtsp_url, route_path, source_remark, push_result_stream, "
            "alarm_confidence_threshold, scene_id, notification_policy_ids, desired_analysis_enabled, created_at "
            "FROM video_sources WHERE id = ?",
            (source_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        rois = await _get_rois_for_source(db, source_id)
    return _row_to_source(row, rois)


async def get_source_by_rtsp(rtsp_url: str) -> VideoSource | None:
    """Retrieve a video source by its RTSP URL, or None if not found.
    按 RTSP URL 获取视频源，未找到则返回 None。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, rtsp_url, route_path, source_remark, push_result_stream, "
            "alarm_confidence_threshold, scene_id, notification_policy_ids, desired_analysis_enabled, created_at "
            "FROM video_sources WHERE rtsp_url = ?",
            (rtsp_url,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        rois = await _get_rois_for_source(db, row[0])
    return _row_to_source(row, rois)


async def list_sources() -> list[VideoSource]:
    """List all video sources ordered by creation time.
    按创建时间列出所有视频源。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, rtsp_url, route_path, source_remark, push_result_stream, "
            "alarm_confidence_threshold, scene_id, notification_policy_ids, desired_analysis_enabled, created_at "
            "FROM video_sources ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
        source_ids = [str(row["id"] if hasattr(row, "keys") else row[0]) for row in rows]
        rois_by_source = await _get_rois_for_sources(db, source_ids)
        sources: list[VideoSource] = []
        for row in rows:
            source_id = str(row["id"] if hasattr(row, "keys") else row[0])
            rois = rois_by_source.get(source_id, [])
            sources.append(_row_to_source(row, rois))
    return sources


async def update_source(source_id: str, data: VideoSourceUpdate) -> VideoSource | None:
    """Update a video source's fields and/or ROIs.
    更新视频源的字段和/或 ROI。"""
    async with _db_session() as db:
        active_plugin_id = await _get_active_plugin_id_from_db(db)
        if data.scene_id is not None:
            requested_scene_id = str(data.scene_id or "").strip() or DEFAULT_SCENE_ID
            if requested_scene_id != active_plugin_id:
                raise ValueError(
                    f"scene_id must match active_plugin_id '{active_plugin_id}'"
                )
        fields: list[str] = []
        values: list[str] = []
        if data.name is not None:
            fields.append("name = ?")
            values.append(data.name)
        if data.source_remark is not None:
            fields.append("source_remark = ?")
            values.append(data.source_remark)
        if data.push_result_stream is not None:
            fields.append("push_result_stream = ?")
            values.append(1 if data.push_result_stream else 0)
        if "alarm_confidence_threshold" in data.model_fields_set:
            fields.append("alarm_confidence_threshold = ?")
            values.append(data.alarm_confidence_threshold)
        if data.route_path is not None:
            fields.append("rtsp_url = ?")
            route_path = _normalize_route_path(data.route_path)
            values.append(
                await _resolve_source_rtsp_url(db, rtsp_url=None, route_path=route_path)
            )
            fields.append("route_path = ?")
            values.append(route_path)
        elif data.rtsp_url is not None:
            fields.append("rtsp_url = ?")
            values.append(data.rtsp_url)
            fields.append("route_path = ?")
            values.append(
                extract_source_route_path(
                    data.rtsp_url,
                    await _get_setting_from_db(
                        db,
                        "mediamtx_rtsp_addr",
                        DEFAULT_APP_SETTINGS.get("mediamtx_rtsp_addr", ""),
                    ),
                )
            )
        if data.notification_policy_ids is not None:
            fields.append("notification_policy_ids = ?")
            values.append(_json_dumps(data.notification_policy_ids))
        if fields:
            values.append(source_id)
            await db.execute(
                f"UPDATE video_sources SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        scene_changed = False
        async with db.execute(
            "SELECT scene_id FROM video_sources WHERE id = ?",
            (source_id,),
        ) as cursor:
            current_scene_row = await cursor.fetchone()
        if current_scene_row is not None and str(current_scene_row[0] or "") != active_plugin_id:
            await db.execute(
                "UPDATE video_sources SET scene_id = ? WHERE id = ?",
                (active_plugin_id, source_id),
            )
            scene_changed = True
        if data.rois is not None:
            await _save_rois_in_db(db, source_id, data.rois)
        elif scene_changed:
            # ROI coordinates and tags are scene/plugin-specific. When a source
            # switches scene without an explicit ROI replacement, clear the old
            # ROI set so the new plugin cannot consume stale labels.
            # ROI 坐标与标签属于场景/插件配置。视频源切换场景且未显式提交新 ROI 时，
            # 清空旧 ROI，避免新插件误用旧标签。
            await db.execute("DELETE FROM rois WHERE source_id = ?", (source_id,))
        await db.commit()
        async with db.execute(
            "SELECT id, name, rtsp_url, route_path, source_remark, push_result_stream, "
            "alarm_confidence_threshold, scene_id, notification_policy_ids, desired_analysis_enabled, created_at "
            "FROM video_sources WHERE id = ?",
            (source_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        rois = await _get_rois_for_source(db, source_id)
    return _row_to_source(row, rois)


async def set_source_desired_analysis_enabled(source_id: str, enabled: bool) -> bool:
    """Persist whether a source should be restored after process restart."""
    async with _db_session() as db:
        cursor = await db.execute(
            "UPDATE video_sources SET desired_analysis_enabled = ? WHERE id = ?",
            (1 if enabled else 0, source_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def list_desired_analysis_sources() -> list[VideoSource]:
    """List sources that should be automatically restarted after app startup."""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, rtsp_url, route_path, source_remark, push_result_stream, "
            "alarm_confidence_threshold, scene_id, notification_policy_ids, desired_analysis_enabled, created_at "
            "FROM video_sources WHERE desired_analysis_enabled = 1 ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
        source_ids = [str(row["id"] if hasattr(row, "keys") else row[0]) for row in rows]
        rois_by_source = await _get_rois_for_sources(db, source_ids)
        sources: list[VideoSource] = []
        for row in rows:
            source_id = str(row["id"] if hasattr(row, "keys") else row[0])
            sources.append(_row_to_source(row, rois_by_source.get(source_id, [])))
    return sources


async def update_all_sources_scene(scene_id: str) -> int:
    """Bind all sources to the active scene and clear stale ROI data.
    将所有视频源绑定到当前启用场景，并清空旧 ROI 数据。"""
    next_scene_id = str(scene_id or DEFAULT_SCENE_ID).strip()
    async with _db_session() as db:
        async with db.execute(
            "SELECT id FROM video_sources WHERE scene_id != ?",
            (next_scene_id,),
        ) as cursor:
            changed_source_ids = [str(row[0]) for row in await cursor.fetchall()]
        if not changed_source_ids:
            return 0
        await db.executemany(
            "UPDATE video_sources SET scene_id = ? WHERE id = ?",
            [(next_scene_id, source_id) for source_id in changed_source_ids],
        )
        await db.executemany(
            "DELETE FROM rois WHERE source_id = ?",
            [(source_id,) for source_id in changed_source_ids],
        )
        await db.commit()
        return len(changed_source_ids)


async def delete_source(source_id: str) -> bool:
    """Delete a video source by ID. Returns True if a row was deleted.
    按 ID 删除视频源。如果删除了记录则返回 True。"""
    async with _db_session() as db:
        cursor = await db.execute(
            "DELETE FROM video_sources WHERE id = ?", (source_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def _save_rois_in_db(
    db: aiosqlite.Connection, source_id: str, rois: list[ROICreate]
) -> None:
    """Replace all ROIs for a source within an existing transaction.
    在已有事务内替换指定源的所有 ROI。"""
    await db.execute("DELETE FROM rois WHERE source_id = ?", (source_id,))
    now = _now_iso()
    for roi in rois:
        roi_id = str(uuid.uuid4())
        points_json = json.dumps([p.model_dump() for p in roi.points])
        await db.execute(
            "INSERT INTO rois (id, source_id, type, points, tag, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (roi_id, source_id, roi.type, points_json, roi.tag, now),
        )


async def save_rois(source_id: str, rois: list[ROICreate]) -> list[ROI]:
    """Save ROIs for a source (replaces existing ROIs).
    保存视频源的 ROI（替换现有 ROI）。"""
    async with _db_session() as db:
        await _save_rois_in_db(db, source_id, rois)
        await db.commit()
        return await _get_rois_for_source(db, source_id)


async def get_rois(source_id: str) -> list[ROI]:
    """Get all ROIs for a given source.
    获取指定视频源的所有 ROI。"""
    async with _db_session() as db:
        return await _get_rois_for_source(db, source_id)


def _row_to_scene(row: tuple) -> SceneDefinition:
    return SceneDefinition(
        id=row[0],
        label_zh=row[1],
        label_en=row[2],
        description=row[3],
        required_services=[str(item) for item in _json_list(row[4])],
        default_roi_tags=[str(item) for item in _json_list(row[5])],
        event_types=[str(item) for item in _json_list(row[6])],
        default_config=_json_dict(row[7]),
        expert_config_schema=_json_dict(row[8]),
    )


async def list_scenes() -> list[SceneDefinition]:
    """List registered scene definitions.
    列出已注册场景定义。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, label_zh, label_en, description, required_services, "
            "default_roi_tags, event_types, default_config, expert_config_schema "
            "FROM scenes ORDER BY id"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_scene(row) for row in rows]


async def get_scene(scene_id: str) -> SceneDefinition | None:
    """Get one scene definition.
    获取单个场景定义。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, label_zh, label_en, description, required_services, "
            "default_roi_tags, event_types, default_config, expert_config_schema "
            "FROM scenes WHERE id = ?",
            (scene_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_scene(row) if row else None


def _row_to_video_gateway(row: tuple) -> VideoGateway:
    return VideoGateway(
        id=row[0],
        name=row[1],
        rtsp_base_url=row[2],
        webrtc_base_url=row[3],
        username=row[4],
        password=row[5],
        enabled=_normalize_bool_db_value(row[6]),
        created_at=row[7],
    )


async def list_video_gateways() -> list[VideoGateway]:
    """List video gateways.
    列出视频网关。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, rtsp_base_url, webrtc_base_url, username, password, enabled, created_at "
            "FROM video_gateways ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_video_gateway(row) for row in rows]


async def create_video_gateway(data: VideoGatewayCreate) -> VideoGateway:
    """Create a video gateway with shared RTSP/WebRTC credentials.
    创建使用 RTSP/WebRTC 共享凭据的视频网关。"""
    gateway_id = str(uuid.uuid4())
    created_at = _now_iso()
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO video_gateways "
            "(id, name, rtsp_base_url, webrtc_base_url, username, password, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                gateway_id,
                data.name,
                data.rtsp_base_url,
                data.webrtc_base_url,
                data.username,
                data.password,
                1 if data.enabled else 0,
                created_at,
            ),
        )
        await db.commit()
    return VideoGateway(id=gateway_id, created_at=created_at, **data.model_dump())


async def update_video_gateway(gateway_id: str, data: VideoGatewayUpdate) -> VideoGateway | None:
    """Update a video gateway.
    更新视频网关。"""
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    async with _db_session() as db:
        if updates:
            fields = []
            values: list[object] = []
            for key, value in updates.items():
                fields.append(f"{key} = ?")
                values.append(1 if key == "enabled" and value else 0 if key == "enabled" else value)
            values.append(gateway_id)
            await db.execute(
                f"UPDATE video_gateways SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await db.commit()
        async with db.execute(
            "SELECT id, name, rtsp_base_url, webrtc_base_url, username, password, enabled, created_at "
            "FROM video_gateways WHERE id = ?",
            (gateway_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_video_gateway(row) if row else None


def _row_to_notification_provider(row: tuple) -> NotificationProvider:
    return NotificationProvider(
        id=row[0],
        name=row[1],
        type=row[2],
        enabled=_normalize_bool_db_value(row[3]),
        config=_json_dict(row[4]),
        created_at=row[5],
    )


async def list_notification_providers() -> list[NotificationProvider]:
    """List notification providers.
    列出通知服务。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, type, enabled, config, created_at "
            "FROM notification_providers ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_notification_provider(row) for row in rows]


async def create_notification_provider(data: NotificationProviderCreate) -> NotificationProvider:
    provider_id = str(uuid.uuid4())
    created_at = _now_iso()
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO notification_providers (id, name, type, enabled, config, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                provider_id,
                data.name,
                data.type,
                1 if data.enabled else 0,
                _json_dumps(data.config),
                created_at,
            ),
        )
        await db.commit()
    return NotificationProvider(id=provider_id, created_at=created_at, **data.model_dump())


async def update_notification_provider(
    provider_id: str,
    data: NotificationProviderUpdate,
) -> NotificationProvider | None:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    async with _db_session() as db:
        if updates:
            fields = []
            values: list[object] = []
            for key, value in updates.items():
                fields.append(f"{key} = ?")
                if key == "enabled":
                    values.append(1 if value else 0)
                elif key == "config":
                    values.append(_json_dumps(value))
                else:
                    values.append(value)
            values.append(provider_id)
            await db.execute(
                f"UPDATE notification_providers SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await db.commit()
        async with db.execute(
            "SELECT id, name, type, enabled, config, created_at "
            "FROM notification_providers WHERE id = ?",
            (provider_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_notification_provider(row) if row else None


def _row_to_notification_template(row: tuple) -> NotificationTemplate:
    return NotificationTemplate(
        id=row[0],
        name=row[1],
        channel=row[2],
        subject_template=row[3],
        body_template=row[4],
        created_at=row[5],
    )


async def list_notification_templates() -> list[NotificationTemplate]:
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, channel, subject_template, body_template, created_at "
            "FROM notification_templates ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_notification_template(row) for row in rows]


async def create_notification_template(data: NotificationTemplateCreate) -> NotificationTemplate:
    template_id = str(uuid.uuid4())
    created_at = _now_iso()
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO notification_templates "
            "(id, name, channel, subject_template, body_template, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                template_id,
                data.name,
                data.channel,
                data.subject_template,
                data.body_template,
                created_at,
            ),
        )
        await db.commit()
    return NotificationTemplate(id=template_id, created_at=created_at, **data.model_dump())


async def update_notification_template(
    template_id: str,
    data: NotificationTemplateUpdate,
) -> NotificationTemplate | None:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    async with _db_session() as db:
        if updates:
            values = [*updates.values(), template_id]
            await db.execute(
                f"UPDATE notification_templates SET {', '.join(f'{key} = ?' for key in updates)} "
                "WHERE id = ?",
                values,
            )
            await db.commit()
        async with db.execute(
            "SELECT id, name, channel, subject_template, body_template, created_at "
            "FROM notification_templates WHERE id = ?",
            (template_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_notification_template(row) if row else None


def _row_to_notification_policy(row: tuple) -> NotificationPolicy:
    return NotificationPolicy(
        id=row[0],
        name=row[1],
        enabled=_normalize_bool_db_value(row[2]),
        cooldown_seconds=int(row[3]),
        provider_ids=[str(item) for item in _json_list(row[4])],
        template_id=row[5],
        created_at=row[6],
    )


async def list_notification_policies() -> list[NotificationPolicy]:
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, name, enabled, cooldown_seconds, provider_ids, template_id, created_at "
            "FROM notification_policies ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_notification_policy(row) for row in rows]


async def create_notification_policy(data: NotificationPolicyCreate) -> NotificationPolicy:
    policy_id = str(uuid.uuid4())
    created_at = _now_iso()
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO notification_policies "
            "(id, name, enabled, cooldown_seconds, provider_ids, template_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                policy_id,
                data.name,
                1 if data.enabled else 0,
                data.cooldown_seconds,
                _json_dumps(data.provider_ids),
                data.template_id,
                created_at,
            ),
        )
        await db.commit()
    return NotificationPolicy(id=policy_id, created_at=created_at, **data.model_dump())


async def update_notification_policy(
    policy_id: str,
    data: NotificationPolicyUpdate,
) -> NotificationPolicy | None:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    async with _db_session() as db:
        if updates:
            fields = []
            values: list[object] = []
            for key, value in updates.items():
                fields.append(f"{key} = ?")
                if key == "enabled":
                    values.append(1 if value else 0)
                elif key == "provider_ids":
                    values.append(_json_dumps(value))
                else:
                    values.append(value)
            values.append(policy_id)
            await db.execute(
                f"UPDATE notification_policies SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await db.commit()
        async with db.execute(
            "SELECT id, name, enabled, cooldown_seconds, provider_ids, template_id, created_at "
            "FROM notification_policies WHERE id = ?",
            (policy_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_notification_policy(row) if row else None


def _row_to_user_account(row: tuple) -> UserAccount:
    return UserAccount(username=row[0], role=row[1], created_at=row[2])


async def count_users() -> int:
    """Return the number of registered platform accounts.
    返回已注册的平台账号数量。"""
    async with _db_session() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
    return int(row[0] if row else 0)


async def list_users() -> list[UserAccount]:
    """List registered accounts ordered by creation time.
    按创建时间列出已注册账号。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT username, role, created_at FROM users ORDER BY created_at, username"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_user_account(row) for row in rows]


async def get_user_auth_record(username: str) -> tuple[str, str, str] | None:
    """Return ``(username, password_hash, role)`` for authentication.
    返回认证所需的 ``(username, password_hash, role)``。"""
    normalized_username = str(username or "").strip()
    async with _db_session() as db:
        async with db.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (normalized_username,),
        ) as cursor:
            row = await cursor.fetchone()
    return (str(row[0]), str(row[1]), str(row[2])) if row else None


async def create_user_account(*, username: str, role: str, password_hash: str) -> UserAccount:
    """Persist a new user account with a precomputed password hash.
    使用预先计算的密码哈希持久化新用户账号。"""
    normalized_username = str(username or "").strip()
    created_at = _now_iso()
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (normalized_username, password_hash, role, created_at),
        )
        await db.commit()
    return UserAccount(username=normalized_username, role=role, created_at=created_at)


async def create_first_user_account(*, username: str, password_hash: str) -> UserAccount:
    """Create the bootstrap admin account only when the user table is empty.
    仅当用户表为空时创建初始化管理员账号。"""
    normalized_username = str(username or "").strip()
    created_at = _now_iso()
    async with _db_session() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
        if int(row[0] if row else 0) > 0:
            raise ValueError("Public registration is closed")
        await db.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (normalized_username, password_hash, "admin", created_at),
        )
        await db.commit()
    return UserAccount(username=normalized_username, role="admin", created_at=created_at)


async def update_user_password_hash(*, username: str, password_hash: str) -> bool:
    """Update a registered user's password hash.
    更新已注册用户的密码哈希。"""
    normalized_username = str(username or "").strip()
    async with _db_session() as db:
        cursor = await db.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash, normalized_username),
        )
        await db.commit()
    return int(cursor.rowcount or 0) > 0


async def get_all_settings() -> dict[str, str]:
    """Return all app settings as a key→value dict.
    以键→值字典形式返回所有应用设置。"""
    async with _db_session() as db:
        async with db.execute("SELECT key, value FROM app_settings") as cursor:
            rows = await cursor.fetchall()
    settings = {row[0]: row[1] for row in rows}
    username, password = _shared_mediamtx_credentials_from_settings(settings)
    settings["mediamtx_username"] = username
    settings["mediamtx_password"] = password
    return settings


async def get_setting(key: str) -> str | None:
    """Return a single setting value, or None if not found.
    返回单个设置值，未找到则返回 None。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


def _normalize_shared_mediamtx_credential_update(
    normalized_data: dict[str, str],
    *,
    shared_key: str,
    rtsp_key: str,
    webrtc_key: str,
) -> None:
    """Normalize shared MediaMTX credential updates and keep legacy aliases synced.
    规范化共享 MediaMTX 凭据更新，并同步旧别名字段。"""
    if shared_key not in normalized_data:
        if rtsp_key in normalized_data:
            normalized_data[shared_key] = normalized_data[rtsp_key]
        elif webrtc_key in normalized_data:
            normalized_data[shared_key] = normalized_data[webrtc_key]
    if shared_key in normalized_data:
        normalized_data[rtsp_key] = normalized_data[shared_key]
        normalized_data[webrtc_key] = normalized_data[shared_key]


async def update_settings(data: dict[str, str]) -> dict[str, str]:
    """Update multiple settings at once. Returns all settings after update.
    批量更新设置。返回更新后的所有设置。"""
    normalized_data = dict(data)
    _normalize_shared_mediamtx_credential_update(
        normalized_data,
        shared_key="mediamtx_username",
        rtsp_key="mediamtx_rtsp_username",
        webrtc_key="mediamtx_webrtc_username",
    )
    _normalize_shared_mediamtx_credential_update(
        normalized_data,
        shared_key="mediamtx_password",
        rtsp_key="mediamtx_rtsp_password",
        webrtc_key="mediamtx_webrtc_password",
    )

    async with _db_session() as db:
        for key, value in normalized_data.items():
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        await db.commit()
    return await get_all_settings()


async def sync_default_video_gateway_from_settings(settings: dict[str, str]) -> None:
    """Keep the seeded default MediaMTX gateway aligned with app settings.
    保持默认 MediaMTX 网关记录与应用设置一致。"""
    username, password = _shared_mediamtx_credentials_from_settings(settings)
    now = _now_iso()
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO video_gateways "
            "(id, name, rtsp_base_url, webrtc_base_url, username, password, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, "
            "rtsp_base_url = excluded.rtsp_base_url, "
            "webrtc_base_url = excluded.webrtc_base_url, "
            "username = excluded.username, "
            "password = excluded.password, "
            "enabled = excluded.enabled",
            (
                "default-mediamtx",
                "Default MediaMTX",
                settings.get("mediamtx_rtsp_addr", DEFAULT_APP_SETTINGS["mediamtx_rtsp_addr"]),
                settings.get("mediamtx_webrtc_addr", DEFAULT_APP_SETTINGS["mediamtx_webrtc_addr"]),
                username,
                password,
                1,
                now,
            ),
        )
        await db.commit()


async def rewrite_source_rtsp_urls(
    *,
    old_rtsp_base_address: str,
    new_rtsp_base_address: str,
    new_rtsp_username: str = "",
    new_rtsp_password: str = "",
) -> int:
    """Rewrite persisted source RTSP URLs when the MediaMTX base changes.
    当 MediaMTX 基地址变更时，重写已保存的视频源 RTSP URL。

    ``old_rtsp_base_address`` is only used to extract each source's existing
    route path before rebuilding the URL with the new base address and
    credentials.
    ``old_rtsp_base_address`` 仅用于从现有 URL 中提取原路由路径，然后再用新的
    基地址和认证信息重新拼装 URL。"""
    async with _db_session() as db:
        async with db.execute("SELECT id, rtsp_url FROM video_sources ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()

        updated_count = 0
        for source_id, current_rtsp_url in rows:
            route_path = extract_source_route_path(
                str(current_rtsp_url or ""),
                old_rtsp_base_address,
            )
            next_rtsp_url = build_source_rtsp_url(
                new_rtsp_base_address,
                route_path,
                username=new_rtsp_username,
                password=new_rtsp_password,
            )
            if not next_rtsp_url or next_rtsp_url == current_rtsp_url:
                continue
            await db.execute(
                "UPDATE video_sources SET rtsp_url = ?, route_path = ? WHERE id = ?",
                (next_rtsp_url, route_path, source_id),
            )
            updated_count += 1

        await db.commit()
    return updated_count


async def prune_analysis_messages(retention_days: int) -> None:
    """Delete messages older than the configured retention window.
    删除超过保留期的历史消息。"""
    cutoff = _message_retention_cutoff_iso(retention_days)
    async with _db_session() as db:
        async with db.execute(
            "SELECT image_url, original_image_url, detected_image_url "
            "FROM analysis_messages WHERE created_at < ?",
            (cutoff,),
        ) as cursor:
            rows = await cursor.fetchall()
        await db.execute(
            "DELETE FROM analysis_messages WHERE created_at < ?",
            (cutoff,),
        )
        await db.commit()
    for row in rows:
        if not row:
            continue
        _delete_message_image(row[0])
        _delete_message_image(row[1])
        _delete_message_image(row[2])


async def save_analysis_message(message: dict[str, str | None]) -> str:
    """Persist one analysis message and prune expired records.
    持久化一条分析消息并清理过期记录。"""
    message_id = str(uuid.uuid4())
    created_at = str(message.get("timestamp") or _now_iso())
    detected_image_url = _normalize_stored_message_image_value(
        message.get("detected_image_url") or message.get("image_url")
    )
    if detected_image_url is None:
        detected_image_url = materialize_message_image(
            message.get("detected_image_base64") or message.get("image_base64"),
            timestamp=created_at,
        )
    original_image_url = _normalize_stored_message_image_value(
        message.get("original_image_url")
    )
    if original_image_url is None:
        original_image_url = materialize_message_image(
            message.get("original_image_base64"),
            timestamp=created_at,
        )
    false_positive = 1 if _normalize_bool_db_value(message.get("false_positive")) else 0
    async with _db_session() as db:
        await db.execute(
            "INSERT INTO analysis_messages "
            "("
            "id, timestamp, source_name, source_id, level, message, "
            "image_url, original_image_url, detected_image_url, false_positive, image_base64, created_at"
            ") "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                str(message.get("timestamp") or created_at),
                str(message.get("source_name") or ""),
                str(message.get("source_id") or ""),
                str(message.get("level") or "info"),
                str(message.get("message") or ""),
                None,
                original_image_url,
                detected_image_url,
                false_positive,
                None,
                created_at,
            ),
        )
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("message_retention_days",),
        ) as cursor:
            row = await cursor.fetchone()
        retention_days = 7
        if row is not None:
            retention_days = row[0]
        cutoff = _message_retention_cutoff_iso(retention_days)
        async with db.execute(
            "SELECT image_url, original_image_url, detected_image_url "
            "FROM analysis_messages WHERE created_at < ?",
            (cutoff,),
        ) as cursor:
            expired_rows = await cursor.fetchall()
        await db.execute(
            "DELETE FROM analysis_messages WHERE created_at < ?",
            (cutoff,),
        )
        await db.commit()
    for row in expired_rows:
        if not row:
            continue
        _delete_message_image(row[0])
        _delete_message_image(row[1])
        _delete_message_image(row[2])
    return message_id


MAX_VISIBLE_MESSAGE_PAGES = 20


async def list_analysis_messages(
    *,
    limit: int | None = None,
    page: int = 1,
    page_size: int = 20,
    source_id: str | None = None,
    false_positive_only: bool = False,
) -> dict[str, object]:
    """List persisted analysis messages ordered newest-first.
    按时间倒序列出持久化分析消息。"""
    safe_page = max(1, int(page))
    safe_size = min(100, max(1, int(page_size)))
    if limit is not None:
        safe_page = 1
        safe_size = min(100, max(1, int(limit)))
    where_clauses: list[str] = []
    query_values: list[object] = []
    if source_id:
        where_clauses.append("source_id = ?")
        query_values.append(source_id)
    if false_positive_only:
        where_clauses.append("false_positive = 1")
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    async with _db_session() as db:
        count_query = f"SELECT COUNT(*) FROM analysis_messages{where_sql}"
        async with db.execute(count_query, tuple(query_values)) as cursor:
            total = int((await cursor.fetchone())[0])
        total_pages = (total + safe_size - 1) // safe_size if total else 0
        if limit is not None:
            visible_total_pages = 1 if total else 0
            visible_total = min(total, safe_size)
        else:
            visible_total_pages = min(total_pages, MAX_VISIBLE_MESSAGE_PAGES)
            visible_total = min(total, visible_total_pages * safe_size)
        safe_page = min(safe_page, visible_total_pages) if visible_total_pages else 1
        offset = (safe_page - 1) * safe_size
        listing_query = (
            "SELECT id, timestamp, source_name, source_id, level, message, image_url, "
            "original_image_url, detected_image_url, image_base64, false_positive "
            f"FROM analysis_messages{where_sql} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        async with db.execute(listing_query, (*query_values, safe_size, offset)) as cursor:
            rows = await cursor.fetchall()
    items = [
        {
            "id": row[0],
            "timestamp": row[1],
            "source_name": row[2],
            "source_id": row[3],
            "level": row[4],
            "message": row[5],
            "image_url": build_analysis_message_image_url(row[0]) if row[8] or row[6] else None,
            "image_base64": row[9],
            "original_image_url": build_analysis_message_image_url(row[0], kind="original") if row[7] else None,
            "detected_image_url": build_analysis_message_image_url(row[0]) if row[8] or row[6] else None,
            "false_positive": bool(row[10]),
        }
        for row in rows
    ]
    return {
        "items": items,
        "page": safe_page,
        "page_size": safe_size,
        "total": visible_total,
        "total_pages": visible_total_pages,
    }


def _read_message_image_base64(stored_url: str | None) -> str:
    path = _message_image_path_from_stored_value(stored_url)
    if path is None or not path.is_file():
        return ""
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception as exc:  # pragma: no cover - best effort resend enrichment
        logger.warning("Failed to read message image {} for resend: {}", path, exc)
        return ""


async def get_analysis_message_for_notification(message_id: str) -> dict[str, object] | None:
    """Return one persisted message enriched for manual notification resend."""
    async with _db_session() as db:
        async with db.execute(
            "SELECT id, timestamp, source_name, source_id, level, message, "
            "image_url, original_image_url, detected_image_url, false_positive "
            "FROM analysis_messages WHERE id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    (
        row_id,
        timestamp,
        source_name,
        source_id,
        level,
        message,
        legacy_image_url,
        original_image_url,
        detected_image_url,
        false_positive,
    ) = row
    detected_stored_url = detected_image_url or legacy_image_url
    return {
        "id": row_id,
        "timestamp": timestamp,
        "source_name": source_name,
        "source_id": source_id,
        "level": level,
        "message": message,
        "event_type": level or "message",
        "event_label": message or str(level or "message").upper(),
        "labels": [level] if level else [],
        "image_url": build_analysis_message_image_url(row_id) if detected_stored_url else "",
        "detected_image_url": build_analysis_message_image_url(row_id) if detected_stored_url else "",
        "original_image_url": (
            build_analysis_message_image_url(row_id, kind="original") if original_image_url else ""
        ),
        "image_base64": _read_message_image_base64(detected_stored_url),
        "detected_image_base64": _read_message_image_base64(detected_stored_url),
        "original_image_base64": _read_message_image_base64(original_image_url),
        "false_positive": bool(false_positive),
        "manual_resend": True,
    }


async def mark_analysis_message_false_positive(message_id: str) -> dict[str, object] | None:
    """Flag one persisted message as false positive and export its images.
    将单条已持久化消息标记为误报并导出图片。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT timestamp, original_image_url, detected_image_url, image_url, false_positive "
            "FROM analysis_messages WHERE id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        timestamp, original_image_url, detected_image_url, legacy_image_url, false_positive = row
        if not _normalize_bool_db_value(false_positive):
            await db.execute(
                "UPDATE analysis_messages SET false_positive = 1 WHERE id = ?",
                (message_id,),
            )
            await db.commit()
        exported = export_false_positive_images(
            message_id,
            timestamp=str(timestamp or ""),
            original_image_url=original_image_url,
            detected_image_url=detected_image_url or legacy_image_url,
        )
    return {
        "id": message_id,
        "false_positive": True,
        "exported_files": exported,
    }


async def unmark_analysis_message_false_positive(message_id: str) -> dict[str, object] | None:
    """Clear the false-positive flag for one persisted message.
    清除单条已持久化消息的误报标记。"""
    async with _db_session() as db:
        cursor = await db.execute(
            "UPDATE analysis_messages SET false_positive = 0 WHERE id = ?",
            (message_id,),
        )
        await db.commit()
    if cursor.rowcount <= 0:
        return None
    return {
        "id": message_id,
        "false_positive": False,
        "exported_files": [],
    }


async def get_analysis_message_image_path(message_id: str, *, kind: str = "detected") -> Path | None:
    """Resolve one persisted original/detected image path for a message ID.
    解析单条消息 ID 对应的原图或检测图路径。"""
    async with _db_session() as db:
        async with db.execute(
            "SELECT image_url, original_image_url, detected_image_url FROM analysis_messages WHERE id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    selected = row[1] if str(kind).strip().lower() == "original" else (row[2] or row[0])
    return _message_image_path_from_stored_value(selected)
