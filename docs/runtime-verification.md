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

截图来自真实运行页面 `/settings`，并在截图环境安装 CJK 字体以确保中文无乱码。

![真实运行设置页截图](screenshots/runtime-settings-expert-mode.png)

## 接口冒烟检查

真实运行服务执行了以下检查：

- `GET /api/health`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/scenes`
- `POST /api/sources`，创建绑定 `template` 场景的视频源
- `GET /api/sources`
- `GET /api/notifications/providers`

这些接口覆盖健康检查、生产式 Bearer token 认证、场景模板、视频源场景绑定、
通知配置读取和空白数据库初始化链路。
