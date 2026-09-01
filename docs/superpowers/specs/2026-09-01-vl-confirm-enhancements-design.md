# VL 二次确认功能增强设计

> 前序设计：`2026-08-17-vl-confirm-design.md`（VL 二次确认基础功能）

## 概述

对现有 VL 二次确认功能做三项增强：

1. **输入图像可配置**：VL 确认输入可选择「原图 / 检测图」×「整图 / ROI 裁剪」共 4 种组合，按插件配置。
2. **过滤消息留痕**：VL 否决（判定为误报）的告警不再直接丢弃，照常入库并通过 WS 推送到消息页，同时标记为误报（`false_positive=1`）；仅抑制通知（邮件/webhook 不发）。消息页筛选扩展为三态：有效告警（默认视图）/ 全部 / 只看误报。
3. **按插件开启**：VL 确认开关从全局 `vl_confirm_enabled` 改为按插件的 `{plugin}_vl_confirm_enabled`；全局 key 一次性迁移后废弃。

## 核心设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 图像选项配置级别 | 按插件（`{plugin}_vl_confirm_image_source` / `{plugin}_vl_confirm_image_crop`） | 与现有 `{plugin}_vl_confirm_prompt` 等场景级设置风格一致，不同场景可各配各的 |
| VL 开关迁移 | 一次性迁移后废弃全局 `vl_confirm_enabled` | 用户确认；`init_db` 幂等 SQL 把全局值复制进各插件级开关后删除全局 key |
| 过滤消息通知 | 仅抑制通知 | 用户确认；过滤目的即不打扰，但消息留痕 |
| 过滤消息存储 | 复用现有 `false_positive` 单字段 | 不区分误报来源（VL 自动 vs 手动标记），不加新列 |
| 默认视图 | 「有效告警」（`false_positive=0`） | 用户确认；与旧行为一致（旧行为下过滤消息根本不可见） |
| 过滤消息图片导出 | 不自动导出到 `false_positives/` | 手动标记才导出；避免 VL 过滤量大时磁盘膨胀 |
| 消息 level / 文本 | 保持 `"alert"` 与原文本不变 | 前端已有误报标签区分，改动最小 |
| fail-open 行为 | 不变 | VL 返回 None（错误/不可解析）时正常告警、正常通知、不误报标记 |
| 设置热更新 | 沿用现状（仅对新启动的处理器生效） | 与所有现有设置行为一致 |

## 新增 / 变更 Settings 字段

所有字段遵循现有 `dict[str, str]` 约定。

### 新增（按插件，默认值保持当前行为）

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `smoke_vl_confirm_enabled` | `"false"` | smoke 插件 VL 开关 |
| `smoke_vl_confirm_image_source` | `"original"` | `original`（原图）/ `annotated`（检测图） |
| `smoke_vl_confirm_image_crop` | `"roi"` | `roi`（ROI 裁剪）/ `full`（整图） |
| `fire_door_vl_confirm_enabled` | `"false"` | fire_door 插件 VL 开关 |
| `fire_door_vl_confirm_image_source` | `"original"` | 同上 |
| `fire_door_vl_confirm_image_crop` | `"roi"` | 同上 |

### 保持全局（VL 服务端点共享）

`vl_confirm_base_url` / `vl_confirm_api_key` / `vl_confirm_model` / `vl_confirm_timeout`（不变）。

### 废弃

`vl_confirm_enabled` 从 `DEFAULT_APP_SETTINGS`、settings API 白名单、`AppSettingsUpdate` schema、前端中移除。

**一次性迁移**（`init_db` 内幂等 SQL，先于默认值播种）：

```sql
-- 每个插件级 key 各执行一次（INSERT OR REPLACE：全局 key 迁移后即删除，
-- REPLACE 最多生效一次，同时修复"新代码先初始化过一次"的升级场景）
INSERT OR REPLACE INTO app_settings (key, value)
SELECT 'smoke_vl_confirm_enabled', value FROM app_settings WHERE key = 'vl_confirm_enabled';
INSERT OR REPLACE INTO app_settings (key, value)
SELECT 'fire_door_vl_confirm_enabled', value FROM app_settings WHERE key = 'vl_confirm_enabled';
DELETE FROM app_settings WHERE key = 'vl_confirm_enabled';
```

效果：老部署升级后，原来全局开着则两个插件都继承开启；全局 key 不再出现在任何配置读取中。

## core 层改动

### `core/vl_confirm.py`

新增纯函数 helper：

```python
def build_vl_image_data_url(
    frame: np.ndarray,
    annotated_frame: np.ndarray | None,
    image_source: str,   # "original" | "annotated"（未知值回退 original）
    image_crop: str,     # "roi" | "full"（未知值回退 roi）
    roi_points: list[dict] | None,
) -> str:
```

- `image_source == "annotated"` 且 `annotated_frame` 非空 → 用检测图，否则回退原图。
- `image_crop == "full"` → `crop_roi_image(selected, None)`（整图）；否则 `crop_roi_image(selected, roi_points)`。
- 复用现有 `crop_roi_image`（`roi_points=None/空` 即整图编码），不改动其行为。

### `core/smoke/processor.py` / `core/fire_door/processor.py`

- `_vl_confirm_enabled()` 改读插件级 key（`smoke_vl_confirm_enabled` / `fire_door_vl_confirm_enabled`）。
- `_vl_confirm_alert(...)` 增参 `annotated` 帧；读取两个图像选项设置；调用 `build_vl_image_data_url` 生成输入图。
- VL 否决时不再清空 `confirmed` / `alert_items`，改为置 `vl_rejected = True`：
  - 消息照常构建并 `append` 到 `result.messages`，且带 `"false_positive": True`；
  - **跳过** `result.extra["email_event"]` / `["smoke_event"]` / `["fire_door_event"]` 的赋值 → 通知调度器收不到 event，通知被抑制；
  - `result.detections` 与推流画面不受影响（现状即如此）。
- 消息链路无需其他改动：`AnalysisMessage` 已含 `false_positive`；`WSManager.broadcast` 持久化时已写入 `analysis_messages.false_positive`。

## 后端 API / DB 改动

| 文件 | 改动 |
|------|------|
| `backend/db/database.py` | `init_db` 增加上述一次性迁移；`list_analysis_messages` 的 `false_positive_only: bool` 改为 `false_positive_filter: str`（`"all"` 默认 \| `"only"` → `false_positive=1` \| `"exclude"` → `false_positive=0`） |
| `backend/api/messages.py` | `GET /api/messages` 的 `false_positive_only` query 参数改为 `false_positive_filter: str = "all"`（`"all"` 默认保持 API 向后兼容） |
| `backend/config.py` | `DEFAULT_APP_SETTINGS` 移除 `vl_confirm_enabled`，新增 6 个插件级 key |
| `backend/api/settings.py` | `PLUGIN_SETTING_KEYS`：+6 新 key，−`vl_confirm_enabled` |
| `backend/models/schemas.py` | `AppSettingsUpdate`：+6 新字段，−`vl_confirm_enabled` |

`analysis_messages` 表结构零改动（`false_positive` 列已存在）。

## 前端改动

| 文件 | 改动 |
|------|------|
| `frontend/src/stores/message.js` | `falsePositiveOnly: boolean` → `falsePositiveFilter: 'exclude' \| 'all' \| 'only'`（默认 `'exclude'`）；`fetchMessages` 传 `false_positive_filter`；WS `onmessage` 本地过滤与 `applyFalsePositiveFilterToLocalMessages` 按三态改写（mark/unmark 后同样按当前模式重过滤本地列表） |
| `frontend/src/views/Messages.vue` | 误报 `el-switch` 改为三态控件（`el-radio-group`：有效告警 / 全部 / 只看误报） |
| `frontend/src/views/Settings.vue` | 各插件 VL 区块：开关改绑插件级 enabled key；新增两个下拉（图像来源：原图/检测图；裁剪方式：ROI 裁剪/整图）；`SMOKE_PLUGIN_SETTING_KEYS` / `FIRE_DOOR_PLUGIN_SETTING_KEYS` 加入各自 3 个新 key；全局 VL key 列表移除 `vl_confirm_enabled`；表单默认值同步 |
| `frontend/src/i18n/locales/zh-CN.js` / `en-US.js` | 新增：三态筛选项、VL 图像来源/裁剪方式设置项及提示文案 |

三态筛选语义（前端 + 后端一致）：

| 模式 | 参数值 | 展示 |
|------|--------|------|
| 有效告警（默认） | `exclude` | 仅 `false_positive=0` 的有效告警 |
| 全部 | `all` | 全部消息 |
| 只看误报 | `only` | 仅 `false_positive=1`（含 VL 自动标记与手动标记） |

行为说明：默认视图下，手动标记误报的消息会从列表消失（切「只看误报」可见）；WS 实时推送的消息同样按当前模式决定是否上屏。

## 测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_vl_confirm.py` | `build_vl_image_data_url` 的 4 组合 + 未知值回退 |
| `tests/test_smoke.py` / `tests/test_fire_door.py` | VL 否决 → 消息保留且 `false_positive=True`、无 `email_event`；VL 确认/fail-open → 正常告警 + `email_event`；插件级开关关闭跳过 VL；图像选项生效 |
| `tests/test_messages.py` | `false_positive_filter` 三态查询 |
| `tests/test_settings.py` | 新 key 白名单/默认值、`vl_confirm_enabled` 迁移 |
| `frontend/src/stores/__tests__/message.test.js` | 三态过滤（fetch 参数、WS 本地过滤、mark/unmark 后重过滤） |

## 实施步骤

1. 后端：`database.py` 迁移 + `list_analysis_messages` 参数；`config.py` / `schemas.py` / `settings.py` 设置项。
2. core：`vl_confirm.py` helper；smoke / fire_door 处理器。
3. 前端：store → Messages.vue → Settings.vue → i18n。
4. 测试全量跑通（`pytest` + 前端单测）。
