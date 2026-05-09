# 真实运行验证记录

验证时间：2026-05-09

## 运行环境

后端以真实 ASGI 服务方式启动，并托管已构建的前端静态文件：

```bash
DB_PATH=/tmp/vsentinel-runtime-screenshot.db \
V_SENTINEL_AUTH_SECRET=runtime-secret \
V_SENTINEL_ADMIN_PASSWORD=admin-secret \
V_SENTINEL_OPERATOR_PASSWORD=operator-secret \
V_SENTINEL_USER_PASSWORD=user-secret \
python -m uvicorn backend.main:app --host 127.0.0.1 --port 18080
```

启动日志确认：

- SQLite 数据库初始化完成。
- 前端来自 `frontend/dist`。
- `AnalysisAgent` 已启动。
- 服务监听 `http://127.0.0.1:18080`。

## 运行截图

截图来自真实运行服务，并在截图环境安装 CJK 字体以确保中文无乱码。为覆盖主要界面，
本次记录包含视频墙、设置、消息与处理日志多个页面。

### 视频墙

![真实运行视频墙截图](screenshots/runtime-video-wall.png)

### 设置页（平台设置分页）

![真实运行平台设置截图](screenshots/runtime-settings-platform.png)

### 设置页（插件设置分页）

![真实运行插件设置截图](screenshots/runtime-settings-plugin-smoke.png)

### 设置页（专家模式截图）

![真实运行设置页截图](screenshots/runtime-settings-expert-mode.png)

### 消息页

![真实运行消息页截图](screenshots/runtime-messages.png)

### 处理日志页

![真实运行处理日志页截图](screenshots/runtime-processing-logs.png)

## 接口冒烟检查

真实运行服务执行了以下检查：

- `GET /api/health`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/scenes`
- `POST /api/sources`，分别创建绑定 `smoke` 与 `template` 场景的视频源
- `GET /api/sources`
- `GET /api/notifications/providers`

这些接口覆盖健康检查、生产式 Bearer token 认证、场景模板、视频源场景绑定、
多源多插件并存、通知配置读取和空白数据库初始化链路。
