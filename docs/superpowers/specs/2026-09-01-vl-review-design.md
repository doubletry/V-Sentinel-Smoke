# VL 复盘设计（连接测试 + 单消息复盘）

## 背景与问题

VL 大模型二次确认（`core/vl_confirm.py`）接入的是用户自管的 OpenAI 兼容后端（`vl_confirm_base_url/api_key/model/timeout`）。当前没有任何手段验证"接入的后台是否正确"，配置错了只能等真实告警时才发现（且 `confirm()` 失败静默 fail-open，问题被掩盖）。

同时，历史告警消息缺少"用当前配置重新问一次 VL 模型"的能力——误报判定存疑时无法低成本复核。

## 范围

- **做**：
  1. 设置页 VL 卡片加"测试连接"按钮：全链路测试（合成图 + 真实 `chat.completions` 调用）。
  2. 消息卡片加"VL 复盘"按钮（功能启用时可见，交互参照"再次发送通知"）：对该消息存档图片重跑一次 VL，**只展示结果，不改变消息状态**。
- **不做**：
  - 复盘不自动标记/清除误报（用户确认的 A 方案）；
  - 复盘不做 ROI 裁剪（消息未持久化 ROI 点，裁剪无法重建，发全图）；
  - 不做 VL 后端的"模型列表"等更多诊断接口。

## 约束

- 复用现有 `VLConfirmClient`（OpenAI 兼容）与 `parse_vl_response`，不引入新依赖。
- 权限沿用现有体系：设置测试走 `settings:*` | `settings:plugins`；消息复盘走 `messages:annotate`（与再次发送通知一致）。
- 两个端点都必须**显式暴露上游错误**（连接失败 / 401 / 模型不存在 / 超时），不能沿用 `confirm()` 的静默 fail-open。

## 设计

### 0. `core/vl_confirm.py` 扩展

- `VLConfirmClient` 新增公开方法 `async def complete(self, image_data_url: str, prompt: str) -> str`：
  返回模型原始文本；异常向上抛出（不吞）。
- `confirm()` 改为基于 `complete()` + `parse_vl_response()` 实现，对外行为不变（异常 → `None`，fail-open）。
- 新增 `build_vl_test_image_data_url() -> str`：用 numpy + cv2 生成确定性合成图（320×240，浅灰底 + 红色方块），复用现有 JPEG data URL 编码器。

### 1. 连接测试端点 `POST /api/settings/vl/test`

- 权限：`require_any_permission("settings:*", "settings:plugins")`；`backend/audit.py` 登记 `settings.vl_test`。
- 请求体（`VlTestRequest`，全可选，同 `EmailTestRequest` 模式）：`vl_confirm_base_url` / `vl_confirm_api_key` / `vl_confirm_model` / `vl_confirm_timeout`；缺省项用已保存设置合并。
- 处理：构造 `VLConfirmClient` → `complete(build_vl_test_image_data_url(), <固定测试提示词>)` → 计时。
  - 固定测试提示词：要求模型仅回复 `{"connected": true}` 的短指令（中英双语）。
- 成功：200 `{"status": "ok", "model", "latency_ms", "response"}`。
- 失败：`HTTPException(502)`，`detail` 携带具体上游原因（超时 / 连接拒绝 / 401 / 404 模型不存在等）。
- 前端（`Settings.vue`）：smoke、fire_door 两个 VL 卡片头部各加"测试连接"按钮（`testing` loading 态），payload 发**当前表单值**（未保存也能测，同邮箱测试）；成功 ElMessage 展示耗时 + 模型回复摘要，失败展示 detail。
- i18n：`settings.vlTestConnection` / `vlTestSuccess` / `vlTestFailed`（中英）。

### 2. 单消息复盘端点 `POST /api/messages/{message_id}/vl-review`

- 权限：`require_permission("messages:annotate")`；`backend/audit.py` 登记 `messages.vl_review`。
- 流程：
  1. 查消息，不存在 → 404。
  2. 由 `source_id` 查 `video_sources.scene_id`（源不存在 → 404）。
  3. 该场景 `<scene>_vl_confirm_enabled` 不为 `"true"` → 422（VL 未启用）。
   4. 取图：按 `<scene>_vl_confirm_image_source` 配置选 `kind="original"` 或 `"detected"`，走现有 `get_analysis_message_image_path()`；首选 kind 文件缺失时回退到另一种 kind；两者都缺失 → 404（图片已清理）。
  5. 读图 → RGB ndarray → JPEG data URL（全图）。
  6. prompt 用 `<scene>_vl_confirm_prompt`（为空时用与处理器相同的默认提示词）；`response_key` 用 `<scene>_vl_confirm_response_key`；端点配置用全局 `vl_confirm_*`。
  7. `raw = await client.complete(data_url, prompt)`；`verdict = parse_vl_response(raw, response_key)` → `confirmed` / `rejected` / `unknown`。
- 成功：200 `{"result", "raw_response", "latency_ms", "model"}`。
- 失败（上游错误）：`HTTPException(502)` + 具体原因。
- **不修改消息任何状态字段。**

### 3. 消息列表 API / WS 增加 `scene_id`

- `list_analysis_messages`：`LEFT JOIN video_sources`，item 增加 `scene_id`（coalesce 默认 `smoke`）。
- `AnalysisMessage` schema 增加 `scene_id: str = "smoke"`（向后兼容默认值）。
- WS 推送的消息 payload 同步携带 `scene_id`（落库时已知 source，一并写入）。
- 前端 `MessageList.vue` 卡片操作区加"VL 复盘"按钮：
  - 显示条件：`messages:annotate` 权限（与现有 `canAnnotateMessages` 一致）**且** 该消息 `scene_id` 对应插件的 `<scene>_vl_confirm_enabled === 'true'`（`MessageList` 已持有 `appSettingsStore`，直接判断）。
  - 点击 → emit 至 `Messages.vue` → 新 store action `vlReviewMessage(id)`（参照 `resendNotification`），per-message loading（参照 `resendingMessageIds`）。
  - 成功 → 对话框展示：判定（确认 / 误报 / 无法判定）+ 模型原始回复 + 耗时；失败 → ElMessage 错误。
- i18n：`messageList.vlReview`、复盘结果对话框各字段、三种判定文案（中英）。

## 验证

1. 后端单测（mock `VLConfirmClient.complete`）：
   - 测试端点：成功返回 ok + 原始回复；上游异常 → 502 且 detail 含原因；请求体覆盖保存值生效。
   - 复盘端点：成功三态（confirmed/rejected/unknown）；消息不存在 404；源不存在 404；VL 未启用 422；图片缺失 404；上游异常 502；不改消息状态（复核 `false_positive` 不变）。
   - 列表 API / WS item 含 `scene_id`。
2. 前端测试：store `vlReviewMessage` 调用与返回；`npm run build` 通过；既有测试无新增失败。
3. 手动 E2E（用户环境，真实 VL 后端）：设置页点"测试连接"→ 显示耗时与回复；smoke 场景启用 VL 后，消息卡片出现"VL 复盘"按钮 → 点击得到判定对话框；fire_door 场景消息无按钮（未启用时）。

## 风险与缓解

- VL 调用耗时（默认 60s 超时）：前端按钮 loading 态明确等待；axios 该请求不设短超时。
- 复盘与生产链路漂移：`complete()` 与生产 `confirm()` 同源，端点/解析逻辑完全复用，仅错误处理不同。
- `scene_id` 默认 `smoke`：与 `video_sources.scene_id` 的列默认值一致，历史数据无需迁移。
