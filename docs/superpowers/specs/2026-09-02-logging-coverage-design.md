# VL 复判全链路日志 + 关键缺日志补全设计

日期：2026-09-02
状态：已获用户批准

## 背景与问题

项目日志配置为单一 stderr sink、级别 INFO（`backend/main.py:41-42`）。排查发现 VL 大模型
复判链路在成功与失败两条路径上都没有可观测的日志：

1. **告警自动二次确认**（`core/vl_confirm.py:262-279` `VLConfirmClient.confirm`）
   - 成功路径只写 `logger.debug("VL confirm raw response: {}", raw)`，INFO sink 下永远不可见。
   - 失败路径写 `logger.warning("VL confirm failed", exc_info=True)`。`exc_info` 是标准
     `logging` 的参数，**loguru 会静默忽略**（已用项目 venv 的 loguru 0.7.3 实测：只打印
     一行消息，无任何异常详情）。VL 服务端返回的错误体、状态码全部丢失。
2. **手动复判** `POST /api/messages/{id}/vl-review`（`backend/api/messages.py:183-186`）
   失败直接抛 502，服务端零日志。
3. **连接测试** `POST /api/settings/vl/test`（`backend/api/settings.py:272-275`）同样零日志。
4. 两个 processor 中 VL 拒报（告警被标记误报）无任何日志。

此外全仓审计发现一批关键缺日志点（静默吞异常、gRPC 非 OK 响应被丢弃、API 5xx 零日志、
安全事件、WHEP 上游失败、审计中间件无保护、日志中泄露 RTSP 凭据）。

## 目标

- VL 复判三条路径（自动确认、手动复判、连接测试）在成功与失败时都记录 VL 模型的
  响应/错误详情，默认日志级别（INFO）可见。
- 补齐关键运维/安全日志，消除"无声失败"。
- 日志中不得出现密钥；对含凭据的 RTSP URL 脱敏。
- 纯增量：不改变任何业务行为（唯一例外是 §2.1 的三处异常保护，属"让失败可见"）。

## 设计

### 1. VL 复判全链路

#### 1.1 `core/vl_confirm.py` — `VLConfirmClient`

- `__init__`：保存 `self._base_url`（不含密钥，可安全记录）。
- `complete()`：
  - 成功：
    - `logger.info("VL request ok: model={} latency_ms={}", self._model, latency_ms)`
    - `logger.info("VL raw response: {}", raw)`（完整原始响应）
  - 失败（`except Exception as exc`）：
    - `logger.opt(exception=True).warning("VL request failed: model={} base_url={} error={}", self._model, self._base_url, exc)`
    - OpenAI SDK 异常（`APIStatusError` 等）的 `str(exc)` 自带上游状态码与错误体。
- `confirm()`：
  - 删除无效的 `exc_info=True`。
  - 成功：`logger.info("VL confirm verdict={}", verdict)`（True / False / None）。
  - 失败：`logger.warning("VL confirm failed, failing open: model={}", self._model)`
    （异常栈已由 `complete()` 记录，不重复打印）。

#### 1.2 两个 processor 的 VL 结果分支

`core/smoke/processor.py`（`_vl_confirm_alert` 调用处，约 117-123 行）与
`core/fire_door/processor.py`（约 172-176 行），在取得 `vl_result` 后：

- `vl_result is False`：
  `logger.warning("Alarm rejected by VL confirm, marked false positive: source={}", self.source_name)`
- `vl_result is True`：
  `logger.info("Alarm confirmed by VL confirm: source={}", self.source_name)`

#### 1.3 `backend/api/messages.py::review_message_with_vl`（约 182-195 行）

- 成功：`logger.info("VL re-review ok: message_id={} verdict={} latency_ms={}", message_id, result, latency_ms)`
- 失败：`logger.opt(exception=True).warning("VL re-review failed: message_id={} model={}", message_id, model)`，随后照旧抛 502。

#### 1.4 `backend/api/settings.py::test_vl_settings`（约 271-281 行）

- 成功：`logger.info("VL connection test ok: scene={} model={} latency_ms={}", data.scene_id, model, latency_ms)`
- 失败：`logger.opt(exception=True).warning("VL connection test failed: scene={} model={} base_url={}", data.scene_id, model, base_url)`，随后照旧抛 502。

### 2. 其他关键缺日志（按审计优先级）

#### 2.1 静默吞异常（DB 故障会无声杀死分析流水线）

- `core/base_processor.py:818-822`（`_wait_for_processing_slot`）：帧任务异常不再
  `pass`；`CancelledError` 跳过，其余 `logger.warning("Frame task failed: source={}", self.source_id)` 带异常。
- `core/base_processor.py:841`（`_process_frame_item`）：`_handle_result` 包 try/except，
  `logger.opt(exception=True).error("Failed to handle frame result: source={}", self.source_id)`。
- `backend/api/ws.py:106`（`WSManager.broadcast` 的持久化调用）：包 try/except，
  `logger.opt(exception=True).error("Failed to persist analysis message: {}", message.id)`，
  失败不阻断广播。

#### 2.2 `core/vengine_client.py` gRPC 非 OK 响应被丢弃（7 处）

`detect` / `classify` / `ocr` / `recognize_action` / `upload_image` / `upload_video` /
`list_models`：`status_code != STATUS_OK` 时
`logger.warning("{} gRPC non-OK: status={} error={}", service, status_code, error_message)`。

防刷屏：实例级状态记录每个服务最近一次 (status, error) 与时间戳；同一服务相同错误
60 秒内只记一次（变化或超窗才记）。

`load_model` / `unload_model` / `list_models` / `health_check` 的 `stub is None` 分支
（4 处）：`logger.warning("V-Engine service '{}' not connected", service)`。

#### 2.3 连接建立可观测性（`core/vengine_client.py`）

- `connect()` 的 INFO 日志加入 `service → host:port` 地址映射（`_build_addresses` 结果）。
- `_normalize_service_host`（约 117-129 行）：Docker 别名无法解析时
  `logger.warning("Could not resolve Docker host alias '{}', using it as-is", host)`。

#### 2.4 API 层异常转 HTTP 错误但零日志

- `backend/api/processor.py:30-31`（start）、`73-74`（toggle push）：
  `logger.opt(exception=True).warning(...)` 带 source_id。
- `backend/api/sources.py:32-37`（create_source 通用 500）：`logger.opt(exception=True).warning(...)`。
- `backend/api/notifications.py:186-187`（test_instance 失败）：
  `logger.warning("Notification instance test failed: provider={} error={}", ...)`。

#### 2.5 安全事件

- `backend/api/auth.py:67-81` 暴力破解封 IP：
  `logger.warning("IP {} blocked for {}s after {} failed login attempts", ...)`。
- `backend/api/ws.py:150-158` WS 坏 token 断开（4001）：
  `logger.warning("WS client rejected: invalid token, ip={}", client_ip)`。

#### 2.6 WHEP 代理上游失败（`backend/api/whep_proxy.py`）

- `whep_offer`：超时 504 补 `WARNING`（当前只有 RequestError 分支有日志）；上游非 2xx
  补 `WARNING`（401/403 属凭据错误，必须可见）。
- `whep_patch`：超时与上游非 2xx 补 `WARNING`。
- `whep_delete`：上游失败不再静默（当前恒返 204），补 `WARNING`。

#### 2.7 审计中间件 `backend/audit.py`（当前零日志）

- 文件加 `from loguru import logger`。
- `write_audit_log` 的两次调用点（成功路径 257-262、异常路径 246-255）包 try/except，
  `logger.opt(exception=True).error("Failed to write audit log: {} {}", method, path)`，
  防止审计写库失败吞掉原始异常或把 200 变 500。

#### 2.8 关闭 / 恢复路径

- `backend/processing/manager.py:172-185`（`_stop_all_processors` / `stop_all`）：
  停止失败的 processor 逐个 `logger.opt(exception=True).warning("Failed to stop processor: source={}", ...)`；
  结束日志改为如实报告（有失败时 WARNING 汇总）。
- `restore_desired_processors`（135-154）：函数体顶层 try/except +
  `logger.opt(exception=True).error("Failed to restore desired processors")`
  （当前任务异常会中断 main.py 的整个关机流程）；结束补
  `logger.info("Restored {}/{} desired processors", ok, total)`。
- `core/base_processor.py:366-372`（`_frame_reader` 非主动退出，如重连次数耗尽）：
  `logger.error("Frame reader exited unexpectedly: source={}", self.source_id)`。
  仅加日志，不改 status 状态机（状态机修复另开任务）。

#### 2.9 RTSP URL 脱敏（日志泄密）

- `core/base_processor.py` 增加模块级助手 `redact_url(url: str) -> str`，将
  `scheme://user:pass@host` 中的 userinfo 密码段替换为 `***`。
- 替换 8 处直接打印 URL 的日志：266 / 351 / 354 / 388（`self.rtsp_url`）与
  1184 / 1199 / 1216 / 1224（push `rtsp_url`）。

#### 2.10 运维可观测补漏

- `core/base_processor.py` ffmpeg 推流首次启动/重启（`_push_frame`，约 1145-1180 行）：
  `logger.info("ffmpeg push started for {}: {}x{} @ {} fps, bitrate {}", ...)`。
- `core/base_processor.py::set_push_result_stream`（约 1382-1390 行）运行时开关：
  `logger.info("Push result stream {} for source={}", enabled, self.source_id)`。
- `backend/api/settings.py::update_settings`：`logger.info("Settings updated, changed keys: {}", sorted(changed_keys))`
  （只记键名，绝不记值；含敏感键）。

## 明确不做（YAGNI）

- DEBUG 提升 INFO（ffprobe 缺失、publisher lag、draw error 等）。
- 文件日志 sink / 日志轮转。
- DB 迁移日志、`core/runner.py` 信号日志、`core/notification_client.py` DEBUG 日志。
- `core/analysis_agent.py` 聚合循环健壮性修复（补日志后失败已可见，行为修复另开任务）。
- `_frame_reader` 退出后 status 卡在 "running" 的状态机修复（仅加日志）。

## 测试与验证

1. 新增回归测试（`tests/test_vl_confirm.py`，loguru 内存 sink 模式）：
   - `confirm()` 失败时日志**包含异常详情**（防 `exc_info` 回归）且消息为 warning 级别；
   - `complete()` 成功时日志包含完整原始响应。
2. 新增 `redact_url` 单元测试（含/不含 userinfo、空串）。
3. 运行：
   - 相关子集：`pytest tests/test_vl_confirm.py tests/test_smoke.py tests/test_messages.py tests/test_vengine_client.py`
   - 全量：`pytest`
   - lint：`ruff check`

## 影响面

约 15 个文件、60-80 行日志代码，纯增量；唯一行为变化是 §2.1 的三处异常保护
（让失败可见且不杀流水线），不改变正常路径语义。
