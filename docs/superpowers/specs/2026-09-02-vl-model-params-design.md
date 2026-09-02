# VL 模型采样参数设计（按插件独立）

## 背景

VL 复盘 / 连接测试 / 生产告警二次确认共用 `VLConfirmClient.complete()`，此前 `max_tokens=1024, temperature=0` 硬编码，且思考（thinking）行为不受控（vLLM + Qwen3 类思考模型会先输出 reasoning 再给答案，导致延迟与截断问题）。

需求：前端可按插件独立调整模型采样参数，参数对**复盘、连接测试、生产告警二次确认**三处全局生效，`smoke` 与 `fire_door` 两插件互不干扰。

## 设置项

每场景（`scene` ∈ `smoke` / `fire_door`）新增 4 个应用设置键，与现有 `<scene>_vl_confirm_*` 同族：

| 键 | 类型 | 默认 | 约束 |
|---|---|---|---|
| `<scene>_vl_confirm_max_tokens` | 字符串化的 int | `1024` | 解析失败 → 1024；钳制 1–32768 |
| `<scene>_vl_confirm_temperature` | 字符串化的 float | `0` | 解析失败 → 0；钳制 0–2 |
| `<scene>_vl_confirm_top_p` | 字符串化的 float | 空（不发送） | 空或解析失败 → 不发送；发送时钳制 (0,1] |
| `<scene>_vl_confirm_disable_thinking` | `"true"` / `"false"` | `false` | 为 `"true"` 时发送 `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` |

- 存量数据库无这些键时按默认值处理（读取处用 `or 默认`），**无数据库迁移**。
- 后端解析采用宽松策略（与现有 `vl_confirm_timeout` 处理一致）：任何解析失败回退默认值，不阻塞请求。

## 后端

### 1. `core/vl_confirm.py`

`VLConfirmClient.__init__` 增加 4 个可选参数：

```python
def __init__(self, base_url, api_key, model, timeout=60,
             max_tokens=1024, temperature=0.0, top_p=None, disable_thinking=False):
```

`complete()` 按值拼装请求 kwargs：

- `max_tokens`、`temperature` 始终发送；
- `top_p is None` → 不发送；
- `disable_thinking=True` → 追加 `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`（vLLM 私有参数；非 vLLM 服务端会返回 400，属显式选择的代价，错误原样上抛）。

`confirm()`（生产管线入口）签名不变，行为继承 `complete()`。

### 2. 调用点（三处各自读取**本场景**设置）

- **生产管线**：`core/smoke/processor.py` 读 `smoke_vl_confirm_*`，`core/fire_door/processor.py` 读 `fire_door_vl_confirm_*`，构造 client 时传入。插件独立性在此保证。
- **复盘端点** `POST /api/messages/{message_id}/vl-review`：已有 `scene_id`（来自源），读取对应场景的 4 个参数构造 client。
- **测试端点** `POST /api/settings/vl/test`：
  - 请求体新增**必填** `scene_id: str`（必须为 `smoke` / `fire_door`；缺失或非法 → 422。前后端同版本发布，旧请求体不再支持）及 4 个可选参数覆盖字段；
  - 合并顺序：**请求体 → 已保存 `<scene>_` 设置 → 默认值**（沿用现有 base_url/model 的合并模式，保证"未保存也能测"）；
  - 提示词仍用固定 `VL_TEST_PROMPT`（连通性测试语义不变）。

## 前端

### 设置页（`Settings.vue` 两个插件 VL 卡片）

在现有「启用 / 图片来源 / 裁剪 / 提示词 / 响应键」之后各加 4 个字段：

- `max_tokens`：`el-input-number`，min 1 max 32768；
- `temperature`：`el-input-number`，min 0 max 2 step 0.1；
- `top_p`：`el-input-number`，min 0.01 max 1 step 0.1，**允许留空**（空 = 不发送，用模型默认）；
- `关闭思考`：`el-switch`，附提示"适用于 vLLM + Qwen3 等思考模型，可显著降低延迟"。

表单新增 8 个键（`<scene>_vl_confirm_max_tokens` / `_temperature` / `_top_p` / `_disable_thinking`），加入保存/回填的设置键清单。

两个卡片的「测试连接」按钮 payload 增加：`scene_id`（`smoke` / `fire_door`）+ 本卡片当前 4 个参数值（发表单值，与 base_url 等同模式）。

共享端点区（base_url / api_key / model / timeout）保持不变。

### API / store

- `settingsApi.testVl` 透传扩展后的请求体（无需改签名）；
- `appSettingsStore.testVl` 透传 payload；
- 保存流程自动覆盖新键（form 已含）。

## i18n

`settings` 段新增（中英各一套）：

- `vlMaxTokens`、`vlTemperature`、`vlTopP`、`vlDisableThinking`（4 个字段标签）
- `vlDisableThinkingHint`（思考开关提示）
- `vlTopPHint`（"留空 = 使用模型默认值"）

## 错误处理

- 参数解析失败 → 静默回退默认值（不产生 422）；
- `disable_thinking` 开 + 非 vLLM 服务端 → 上游 400，错误信息经现有 502/错误链原样展示；
- 其余错误语义（404/422/502）不变。

## 测试

1. `tests/test_vl_confirm.py`：
   - client 参数透传：`create()` 收到 `max_tokens` / `temperature`；
   - `top_p=None` 不传、`top_p=0.9` 传入；
   - `disable_thinking=True` → `extra_body` 含 `chat_template_kwargs.enable_thinking == False`；`False` → 无 `extra_body`。
2. `tests/test_settings.py`（测试端点）：
   - 既有 3 个 vl/test 用例的请求体需补 `"scene_id": "smoke"`（字段改为必填后，否则全部 422）；
   - 请求体携带 `scene_id` + 参数覆盖，client 按合并结果构造；
   - `scene_id` 非法（如 `"foo"`）或缺失 → 422（两个用例）。
3. `tests/test_messages.py`（复盘端点）：client 收到本场景参数（mock client 构造断言）。
4. 处理器独立性：改 `smoke_vl_confirm_max_tokens` 后 smoke 处理器构造 client 用新值、fire_door 处理器仍用默认/自身值（两用例）。
5. 前端：`npm run build` 通过；既有 vitest 套件无新增失败。
6. 手动 E2E（用户环境，真实 vLLM）：
   - 设置页调 smoke 的 `max_tokens` 为极小值（如 64）→ 测试连接返回截断内容/失败，fire_door 卡片同参数正常 → 独立性验证；
   - 开 `关闭思考` → 测试耗时明显下降（预期 ~0.3s vs ~1.7s）；
   - 复盘结果对话框不受影响。

## 非目标

- 不改 `vl_confirm_base_url/api_key/model/timeout` 的共享语义；
- 不新增其他采样参数（frequency_penalty / repetition_penalty / seed 等）；
- 不做非 vLLM 服务端对 `enable_thinking` 的自动降级。
