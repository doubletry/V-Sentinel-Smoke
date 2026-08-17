# VL 大模型二次确认功能设计

## 概述

为降低 fire-door 等场景的误报率，引入 VL（Vision-Language）大模型对报警进行二次确认。该功能为通用能力，所有场景插件均可使用，通过修改 prompt 适配不同场景。

## 核心设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 确认时序 | 阻塞式 | 报警先经 VL 确认，确认后才触发通知，大幅减少误报 |
| 依赖方式 | 添加 `openai` SDK | 与 demo 一致，代码简洁 |
| 错误处理 | Fail-open | VL 调用失败时仍触发报警，避免漏报 |
| 响应解析 | JSON 字段提取 + 关键词回退 | 精确且鲁棒 |
| 设置类型 | 全部 string | 遵循项目现有 `dict[str, str]` 约定 |
| 默认状态 | 关闭 | 用户可选择启用 |

## 架构

```
┌─────────────────────────────────────────────────────┐
│              Frontend (Settings.vue)                 │
│  每个场景插件对话框中增加 "VL 二次确认" 配置区域      │
│  - 全局: enabled, base_url, api_key, model, timeout  │
│  - 场景级: prompt, response_key                      │
└──────────────────────┬──────────────────────────────┘
                       │ PUT /api/settings
                       ▼
┌─────────────────────────────────────────────────────┐
│              Backend (app_settings DB)                │
│  vl_confirm_enabled, vl_confirm_base_url,            │
│  vl_confirm_api_key, vl_confirm_model,               │
│  vl_confirm_timeout,                                 │
│  {scene}_vl_confirm_prompt,                          │
│  {scene}_vl_confirm_response_key                     │
└──────────────────────┬──────────────────────────────┘
                       │ app_settings dict
                       ▼
┌─────────────────────────────────────────────────────┐
│           core/vl_confirm.py (新模块)                 │
│  VLConfirmClient: 异步 openai 客户端封装              │
│  crop_roi_image(): ROI 裁剪 + base64 编码            │
│  parse_vl_response(): JSON 响应解析                   │
└──────────────────────┬──────────────────────────────┘
                       │ 被各场景 processor 调用
                       ▼
┌─────────────────────────────────────────────────────┐
│  core/fire_door/processor.py  (及其他场景 processor)  │
│  报警检测 → VL 二次确认 → 确认/抑制报警               │
└─────────────────────────────────────────────────────┘
```

## 新增 Settings 字段

所有字段遵循现有 `dict[str, str]` 约定。

### 全局字段（所有场景共享）

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `vl_confirm_enabled` | `"false"` | 全局启用/禁用开关 |
| `vl_confirm_base_url` | `"http://localhost:30000/v1"` | OpenAI 兼容 API Base URL |
| `vl_confirm_api_key` | `"EMPTY"` | API Key |
| `vl_confirm_model` | `"/models/Mage-VL"` | 模型名称 |
| `vl_confirm_timeout` | `"60"` | 请求超时秒数 |

### 场景级字段（每个场景独立）

| 字段模式 | 说明 |
|----------|------|
| `{scene_id}_vl_confirm_prompt` | 该场景的 VL 提示词 |
| `{scene_id}_vl_confirm_response_key` | 响应 JSON 中要提取的布尔字段名 |

### fire_door 场景默认值

- `fire_door_vl_confirm_prompt`: 沿用 demo 中的 DEFAULT_PROMPT
- `fire_door_vl_confirm_response_key`: `"open"`

### smoke 场景默认值

- `smoke_vl_confirm_prompt`: 针对烟火检测的确认提示词
- `smoke_vl_confirm_response_key`: `"smoke"`

## core/vl_confirm.py 模块设计

### parse_vl_response()

解析模型输出，返回 True/False/None：
1. 去除 markdown 代码块，`json.loads()` 解析，提取 `response_key` 字段
2. 正则搜索 `"{response_key}": true|false`
3. 回退到独立 `true` / `false` 关键词
4. 无法判断返回 `None`

### crop_roi_image()

根据 ROI 裁剪图像，返回 JPEG data URL：
- `roi_points` 为 None 或空：返回完整帧
- 2 点（矩形）：直接裁剪
- 3+ 点（多边形）：裁剪最小外接矩形，多边形外区域用灰色填充

### VLConfirmClient

异步封装 `openai.AsyncOpenAI`，`confirm()` 发送图片 + prompt，返回解析结果。

## 错误处理

| 场景 | 行为 |
|------|------|
| VL 返回 `true` | 确认报警，继续通知 |
| VL 返回 `false` | 拒绝报警，抑制通知 |
| VL 返回无法解析 / 超时 / 错误 | 视为 `None`，fail-open 保留报警 |
| `vl_confirm_enabled` 为 `"false"` | 跳过 VL 确认，直接报警 |

## 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `pyproject.toml` | 添加 `openai>=1.0.0` 依赖 |
| `core/vl_confirm.py` | **新建** — VL 客户端、图片裁剪、响应解析 |
| `core/fire_door/processor.py` | 报警后调用 VL 确认 |
| `core/fire_door/constants.py` | 添加 VL 默认 prompt 和 response_key |
| `backend/config.py` | `DEFAULT_APP_SETTINGS` 添加新字段默认值 |
| `backend/models/schemas.py` | `AppSettingsUpdate` 添加新字段 |
| `backend/api/settings.py` | `PLUGIN_SETTING_KEYS` 添加新字段 |
| `frontend/src/views/Settings.vue` | 插件对话框添加 VL 配置 UI |
| `frontend/src/i18n/locales/zh-CN.js` | 添加中文翻译 |
| `frontend/src/i18n/locales/en-US.js` | 添加英文翻译 |

## 依赖

新增：`openai>=1.0.0`（提供 `AsyncOpenAI` 客户端）
