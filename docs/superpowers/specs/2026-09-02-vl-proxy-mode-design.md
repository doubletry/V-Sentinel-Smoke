# VL 大模型代理模式设计

日期：2026-09-02
状态：已获用户批准

## 背景与问题

用户报告：消息页 VL 复盘时快时慢（700ms ~ 几十秒），慢的时候模型服务端收不到请求，
怀疑请求走了环境变量代理。

已用项目 venv 实测证实机制（本地模型服务器 + 黑洞代理实验）：

- openai SDK 3.1.0 默认构造的 httpx2 客户端 `trust_env=True`（默认值），
  `proxy=None` 时 httpx2 调用 `get_environment_proxies()`
  （`urllib.request.getproxies()`）**自动读取 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`
  环境变量**。
- 实验结果：
  - `HTTP_PROXY` 指向不可达代理时：VL 调用挂满整个超时预算（`timeout=3s` 时 3.3s 超时），
    **模型服务器收到 0 个请求，代理收到 1 个连接**。
  - 清除环境变量后：同一调用 0.0s 成功，模型收到请求。
- 结论：部署环境若存在企业代理环境变量且模型服务器 IP 不在 `NO_PROXY` 内，
  所有 VL 调用（自动确认、复盘、连接测试）都会被代理截走，代理够不到模型时
  表现为"几十秒后失败/模型无请求"。当前代码无法关闭或覆盖该行为。

## 目标

- 后台设置中选择 VL 请求的代理方式，三选一：
  1. **不走代理**（默认；升级后现有部署默认直连）
  2. **手动设置**（用户填代理 URL）
  3. **走系统代理**（维持现状：读环境变量）
- 四种调用路径（自动确认 ×2、手动复盘、连接测试）行为一致，不允许再次出现
  构造点漂移。
- 配置错误不杀死告警链路（自动确认路径失败开放）。
- 开启复判后，实时画面（标注帧推流）不得被 VL 调用阻塞；消息与通知语义保持不变。

## 设计

### 1. 设置键（全局，与 `vl_confirm_base_url` 同组）

| 键 | 取值 | 默认 |
|---|---|---|
| `vl_confirm_proxy_mode` | `none` / `manual` / `system` | 键缺失或值非法 → 按 `none` |
| `vl_confirm_proxy_url` | 如 `http://10.0.0.1:3128`，仅 `manual` 使用 | `""` |

- 无需 DB 迁移（`app_settings` 为键值表，无 schema）。
- 白名单检查项（防上次"采样字段漏持久化"类 bug 复发），三处都要加：
  1. `backend/models/schemas.py` `AppSettingsUpdate`（保存模型）
  2. `backend/api/settings.py` `PLUGIN_SETTING_KEYS`（operator 权限白名单）
  3. `backend/models/schemas.py` `VlTestRequest`（先测后存载荷）

### 2. 客户端层（`core/vl_confirm.py`）

#### 2.1 `VLConfirmClient`

- `__init__` 增加可选参数 `http_client: httpx2.AsyncClient | None = None`，
  透传给 `AsyncOpenAI(http_client=...)`；不传则维持现状（SDK 默认客户端）。
- 既有位置/关键字参数签名不变，现有调用与测试零改动。

#### 2.2 工厂 `build_vl_client(settings, scene_id, overrides=None) -> VLConfirmClient`

- 字段合并顺序与现有调用点完全一致：`overrides → settings → 默认值`：
  - `vl_confirm_base_url` 默认 `http://localhost:30000/v1`（processor 现状）
  - `vl_confirm_api_key` 默认 `EMPTY`
  - `vl_confirm_model` 默认 `/models/Mage-VL`
  - `vl_confirm_timeout` 默认 `60`（解析规则沿用现有 `int(float(...))` 失败回退 60）
  - 采样参数沿用 `vl_sampling_kwargs(settings, scene_id, overrides)`
  - 代理：`vl_confirm_proxy_mode` / `vl_confirm_proxy_url`（同样支持 overrides）
- 代理客户端构造（用 `openai.DefaultAsyncHttpxClient`，保持 SDK 的超时/连接池默认值）：
  - `none` → `DefaultAsyncHttpxClient(trust_env=False)`（彻底忽略环境变量代理；
    副作用：亦不读 `SSL_CERT_FILE/DIR`，可接受）
  - `manual` → `DefaultAsyncHttpxClient(proxy=<url>, trust_env=False)`（行为确定；
    URL 必须以 `http://` 或 `https://` 开头，否则视为非法）
  - `system` → 不传 `http_client`（SDK 默认：读环境变量，即当前行为）

#### 2.3 四个调用点改走工厂

| 调用点 | 改法 |
|---|---|
| `core/smoke/processor.py` `_vl_confirm_alert`（§3 改造后为后台任务体） | try `build_vl_client(self.app_settings, "smoke")`，`ValueError` → WARNING + 回退 `none` |
| `core/fire_door/processor.py` `_vl_confirm_alert`（同上） | try `build_vl_client(self.app_settings, "fire_door")`，同上 |
| `backend/api/messages.py:176`（vl-review） | 先按现状 422 校验 base_url/model，再 `build_vl_client(settings_map, scene_id)` |
| `backend/api/settings.py:278`（vl/test） | 先按现状 422 校验，再 `build_vl_client(app_settings, data.scene_id, overrides=<请求体全部 vl_confirm_* 字段>)` |

### 3. 实时推流与 VL 复判解耦

**问题**：当前每帧流水线为 `process_frame`（内含 `await _vl_confirm_alert`，最长
`vl_confirm_timeout`=60s）→ `agent.submit`（WS 广播消息 + 通知）→ 推流入队。
开启复判后，VL 一慢，整帧流水线（含实时画面推流、处理槽位）被卡住。

**目标**：推流立即入队，不等 VL；消息与通知的语义与到达时机与现状一致
（结论到达后才广播/发通知），`false_positive` 标记在持久化前已确定。

**设计**：

1. **`core/base_processor.py`** 新增可覆写钩子
   `async def finalize_result(self, result) -> None`（默认 no-op）。
2. **`backend/processing/base.py`** `_handle_result` 重排：
   - 先 `await super()._handle_result(frame, result)`（推流入队，毫秒级）；
   - 再派一个**脱离帧处理槽位的后台任务** `_dispatch_result(result)`：
     `await self.finalize_result(result)`（等 VL 结论，受客户端总超时上限约束）
     → `agent.submit(...)`（或无 agent 时的直接广播，沿用现有转换逻辑）。
   - 后台任务记入 `self._dispatch_tasks`（set + done 回调清理）；
     `stop()` 覆写：先 cancel 所有 `_dispatch_tasks` 再 `super().stop()`。
   - `_dispatch_result` 整体 try/except 记 ERROR（不让分发失败影响推流）。
3. **场景 processor**（smoke/fire_door，改法对称）：
   - `process_frame` 不再 await VL：告警且复判开启时
     `task = asyncio.create_task(self._vl_confirm_alert(...))`，与告警上下文
     （frame/annotated/confirmed 等引用 + 该 task）一起存
     `result.extra["pending_alert"]`，立即返回；
     告警且复判关闭：`pending_alert` 不含 task，其余同。
   - 告警消息/邮件事件的构建整体移入 `finalize_result(result)`：
     `vl_result = await task`（无 task 则为 None）→ `vl_rejected = vl_result is False`
     → 按现有代码构建消息（`false_positive`）与 `email_event`（拒报时不附加）。
   - 既有日志不变：拒报 WARNING `Alarm rejected by VL confirm...`、
     确认 INFO `Alarm confirmed by VL confirm...`（移入 `finalize_result`）。
   - 场景 `__init__` 增加 `self._pending_vl_tasks: set[asyncio.Task]`（create_task 时登记，
     done 回调移除）；覆写 `stop()`：cancel 挂起 VL 任务后再 `super().stop()`
     （MRO 链：backend base → 场景 core → core base）。
4. **已知权衡**：不同帧的 VL 结论可能乱序完成 → 消息列表短暂乱序
   （按时间戳展示，影响很小）。

### 4. 错误处理

- **端点**（vl/test、vl-review）：`manual` 模式但 URL 为空/非法 →
  `HTTPException(422, detail=...)`，明确说明手动代理地址缺失或格式错误。
- **processor**（自动确认）：`manual` 模式但 URL 为空/非法 →
  `logger.warning("VL manual proxy misconfigured ({}), falling back to direct: source={}", ...)`
  并回退 `none` 直连；`confirm()` 本身已有失败开放语义。
- **升级行为变化**：键缺失 = `none` = 直连。依赖环境变量代理的既有部署需手动切
  `system`（PR 说明中注明；部署机可用 `docker exec <容器> env | grep -i proxy` 自查）。

### 5. 前端（`frontend/src/views/Settings.vue`）

- 全局 VL 配置区（base_url/model/timeout 所在处）新增：
  - "代理模式" `el-select`：不走代理（默认）/ 手动设置 / 走系统代理
  - "代理地址" 输入框：仅 manual 模式显示（placeholder 示例 `http://10.0.0.1:3128`）
- 两键加入 `VL_CONFIRM_GLOBAL_KEYS`（保存与还原清单）；`testVlConfig` 测试载荷同样携带
  （先测后存，与 base_url/timeout 一致）。
- 保存载荷经 `pickFormValues` 走既有 `saveSection` 流程，无新机制。
- i18n：`zh-CN` / `en-US` 各加标签与（manual 时）提示文案。

### 6. 日志

- 工厂每次构造时 `logger.info("VL client: proxy_mode={}", mode)`（客户端每次调用都新建，
  与现有 `VL request ok` INFO 频率一致；不记录代理 URL，避免泄露其中可能含的凭据）。
- 端点成功/失败日志沿用现有（`VL connection test ok/failed`、`VL re-review ok/failed`）。

### 7. 测试

1. **工厂三模式路由**（复用本地 uvicorn 模型服务器 + 录制型代理的既有模式）：
   - `none`：即使环境设置了 `HTTP_PROXY`（指向录制代理），模型服务器收到请求、
     代理收到 0 个连接。
   - `manual`：模型收到 0 个请求，代理收到 1 个连接（URL 被实际使用）。
   - `system`：环境 `HTTP_PROXY` 指向录制代理时，代理收到 1 个连接。
   - 环境清理：测试内 `monkeypatch.setenv` / 结束后恢复，避免污染其他用例。
2. **manual 非法 URL**：空 URL / 非 http(s) 前缀 → 端点 422；processor 回退直连并
   记录 WARNING。
3. **持久化**：`PUT /api/settings` 带两键 → 响应与 `GET` 均包含（上次漏字段 bug 的回归模式）。
4. **vl/test overrides**：请求体带 `vl_confirm_proxy_mode=manual` + URL（settings 中
   无该值）→ patch 工厂使用的 `DefaultAsyncHttpxClient` 符号，断言其被以
   `proxy=<请求体 URL>` 构造（overrides 优先于 settings）。
5. **全量回归**：`uv run pytest -q` + `uv run ruff check` 零新增。
6. **推流与复判解耦**（§3 的回归测试）：
   - 场景 processor（smoke/fire_door）：VL 判定被门控（gate）挂起时，
     `process_frame` 仍立即返回，`result.extra["vl_confirm_task"]` 未完成、
     `annotated_frame` 已就绪、`messages` 为空；放行 gate 后 `finalize_result`
     产出消息（`false_positive` 正确、确认时附 `email_event`）。
   - backend 处理器：`_process_frame_item` 返回时推流队列已有帧、
     `ws_manager.broadcast` 尚未调用；放行 gate 后广播发生（1 次）。
   - `stop()`：挂起中的 dispatch/VL 任务被 cancel，无未处理异常。

### 8. 不做（YAGNI）

- 不做 per-scene 代理（VL 后端是全局共享端点）。
- 不做代理健康检查/自动切换。
- 不改其他 HTTP 客户端（邮件 SMTP、WHEP 代理等）的代理行为。
- 不在 `none`/`manual` 模式下尝试保留 `NO_PROXY` 语义（行为确定优先）。
