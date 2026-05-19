from __future__ import annotations

from backend.models.schemas import RoleInfo


ROLE_PERMISSIONS: dict[str, list[str]] = {
    "user": [
        "sources:read",
        "video:watch",
        "messages:read",
    ],
    "operator": [
        "sources:read",
        "sources:operate",
        "video:watch",
        "messages:read",
        "messages:annotate",
    ],
    "admin": [
        "sources:*",
        "scenes:*",
        "gateways:*",
        "notifications:*",
        "settings:*",
        "users:*",
        "video:watch",
        "messages:*",
    ],
}


def list_roles() -> list[RoleInfo]:
    """Return the built-in three-level RBAC role catalog.
    返回内置三级权限角色目录。"""
    return [
        RoleInfo(
            role="user",
            label_zh="用户",
            label_en="User",
            permissions=ROLE_PERMISSIONS["user"],
        ),
        RoleInfo(
            role="operator",
            label_zh="操作员",
            label_en="Operator",
            permissions=ROLE_PERMISSIONS["operator"],
        ),
        RoleInfo(
            role="admin",
            label_zh="管理员",
            label_en="Administrator",
            permissions=ROLE_PERMISSIONS["admin"],
        ),
    ]
