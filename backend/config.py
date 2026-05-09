from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.settings_catalog import get_default_app_settings


class Settings(BaseSettings):
    """Minimal env-only settings: ports + DB path.
    最小化的仅环境变量配置：端口 + 数据库路径。

    All service addresses (V-Engine, MediaMTX) are stored in the database
    and managed via the Settings page in the web UI.
    所有服务地址（V-Engine、MediaMTX）存储在数据库中，通过 Web UI 设置页面管理。
    """

    model_config = SettingsConfigDict(env_file=".env")

    # Server ports (env-only) / 服务端口（仅环境变量）
    backend_port: int = 8000
    frontend_port: int = 3000

    # Database path (env-only) / 数据库路径（仅环境变量）
    db_path: str = "./v_sentinel.db"

    # App / 应用
    app_name: str = "V-Sentinel"


# Default values for DB-backed settings (used when no DB record exists)
# 数据库设置的默认值（当无数据库记录时使用）
DEFAULT_APP_SETTINGS: dict[str, str] = get_default_app_settings()


settings = Settings()
