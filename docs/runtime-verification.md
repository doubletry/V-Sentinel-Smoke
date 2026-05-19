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

### 设置页（平台设置分页，MediaMTX 共享账号密码）

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
- `PUT /api/settings`，写入 MediaMTX RTSP / WebRTC 地址和共享账号密码
- `GET /api/scenes`
- `POST /api/sources`，分别创建绑定 `smoke` 与 `template` 场景的视频源
- `GET /api/sources`
- `GET /api/notifications/providers`

这些接口覆盖健康检查、生产式 Bearer token 认证、场景模板、视频源场景绑定、
多源多插件并存、通知配置读取、MediaMTX 共享认证配置和空白数据库初始化链路。

## MediaMTX 共享认证真实验证（2026-05-19）

本轮额外使用真实 MediaMTX 1.18.2 做了共享账号密码联调验证，确认 RTSP 与 WebRTC/WHEP 共用同一套认证信息：

- 使用 `shared-user / shared-pass` 启动 MediaMTX 内部认证。
- 使用 `ffmpeg` 将 `testsrc` 实时发布到 `rtsp://shared-user:shared-pass@127.0.0.1:8554/cam1`。
- 使用 `ffprobe rtsp://127.0.0.1:8554/cam1` 验证无认证访问返回 `401 Unauthorized`。
- 使用 `ffprobe rtsp://shared-user:shared-pass@127.0.0.1:8554/cam1` 验证共享认证可以成功读取 `h264` 流。
- 使用 `POST http://127.0.0.1:8889/cam1/whep` 验证无认证访问返回 `401 Unauthorized`。
- 使用同一组 Basic Auth 凭据再次请求 WHEP，MediaMTX 返回 `400 Bad Request` 且报 `invalid SDP`，说明请求已通过认证并进入真实 WHEP SDP 校验阶段。
- 将应用设置更新为上述共享凭据后，`POST /api/sources` 创建 `route_path=cam1` 的视频源，服务端实际保存的地址为 `rtsp://shared-user:shared-pass@127.0.0.1:8554/cam1`。

## MediaMTX 结果流与 FPS 真实验证（2026-05-19）

本轮又补充了真实 25fps 输入源与结果流推送验证：

- 使用真实 MediaMTX 1.18.2 和 `ffmpeg testsrc=size=640x360:rate=25` 发布 `cam25` 输入流。
- 使用最小透传处理器读取 `cam25` 并持续输出 `cam25_processed` 结果流。
- 处理器日志确认 `source FPS 25.000`，并按 `publish FPS 25.000` 推流。
- MediaMTX 日志确认后台处理器已成功向 `cam25_processed` 发布 H.264 结果流。
- 使用 `ffprobe` 读取 `rtsp://shared-user:shared-pass@127.0.0.1:8554/cam25_processed`，返回：
  - `codec_name = h264`
  - `width = 640`
  - `height = 360`
  - `avg_frame_rate = 25/1`
  - `r_frame_rate = 25/1`

这说明结果画面已经实际推送到 MediaMTX，同时 25fps 输入不会再被错误推成 50fps 结果流。
