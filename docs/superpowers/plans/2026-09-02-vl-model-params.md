# VL 模型采样参数（按插件独立）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端可按插件独立调整 VL 模型采样参数（max_tokens / temperature / top_p / 关闭思考），对复盘、连接测试、生产告警二次确认三处生效，smoke 与 fire_door 互不干扰。

**Architecture:** 在 `core/vl_confirm.py` 新增 `vl_sampling_kwargs()` 统一解析/合并参数（宽松解析，解析失败回退默认），`VLConfirmClient` 接受 4 个新采样参数并按值拼装 OpenAI 请求；三个调用点（两个处理器、复盘/测试端点）各自从本场景 `<scene>_vl_confirm_*` 设置读取；前端两个插件卡片各加 4 个字段，测试按钮携带 `scene_id` + 本卡片参数值。

**Tech Stack:** Python 3.11 / FastAPI / openai SDK（AsyncOpenAI）；Vue 3 / Pinia / Element Plus / vue-i18n；Vitest + jsdom。

## Global Constraints

- **宽松解析**（与现有 `vl_confirm_timeout` 处理一致）：任何解析失败静默回退默认值，绝不抛错/422。默认：`max_tokens=1024`（钳制 1–32768）、`temperature=0.0`（钳制 0–2）、`top_p` 空/非法 → 不发送（合法域 (0,1]）、`disable_thinking` 仅 `"true"`（大小写不敏感）为真。
- **合并顺序**：请求体覆盖 → 已保存 `<scene>_vl_confirm_*` 设置 → 默认值。
- **请求拼装**：`top_p is None` → 请求中**不出现** `top_p` 键；`disable_thinking=True` → 请求带 `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`（vLLM 私有，非 vLLM 服务端会 400，属显式选择）。
- **插件独立**：smoke 处理器/卡片只读 `smoke_*`，fire_door 只读 `fire_door_*`，两场景设置互不串用。
- **测试端点** `POST /api/settings/vl/test`：请求体 `scene_id` **必填**且必须为 `"smoke"` / `"fire_door"`，否则 422。
- **复盘端点** `POST /api/messages/{id}/vl-review`：既有错误语义（404/422/502）与"不改消息状态"约束不变。
- **i18n**：新增键必须同时加入 `zh-CN.js` 与 `en-US.js`，键名一致。
- **测试基线**：后端 `uv run pytest tests -q` = 425 passed + 1 既有失败（`tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`，勿修）；前端 `cd frontend && npx vitest run` = 74 passed + 2 既有失败（`src/utils/__tests__/settingsRoutes.test.js`，勿修）；`npm run build` 必须通过。
- 提交信息风格：`feat(vl): ...` / `feat(settings): ...` / `feat(messages): ...`（conventional commits，与分支历史一致）。

---

### Task 1: `core/vl_confirm.py` — 采样参数 + `vl_sampling_kwargs()`

**Files:**
- Modify: `core/vl_confirm.py`
- Test: `tests/test_vl_confirm.py`

**Interfaces:**
- Consumes: 无（基础层）
- Produces:
  - `vl_sampling_kwargs(settings: dict[str, str], scene_id: str, overrides: dict[str, str | None] | None = None) -> dict[str, Any]`，返回恰好 4 个键：`{"max_tokens": int, "temperature": float, "top_p": float | None, "disable_thinking": bool}`。overrides/settings 中的键名与保存的设置键完全相同（`<scene>_vl_confirm_max_tokens` 等）。
  - `VLConfirmClient(base_url, api_key, model, timeout=60, max_tokens=1024, temperature=0.0, top_p=None, disable_thinking=False)`。
  - `complete()` 行为：`max_tokens`/`temperature` 始终传给 `chat.completions.create`；`top_p is None` 不传；`disable_thinking=True` 追加 `extra_body`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_vl_confirm.py` 顶部 import 区（现有 `from core.vl_confirm import ...` 行）追加 `vl_sampling_kwargs`：

```python
from core.vl_confirm import (
    VLConfirmClient,
    VL_TEST_PROMPT,
    build_vl_image_data_url,
    build_vl_test_image_data_url,
    encode_frame_as_data_url,
    parse_vl_response,
    vl_sampling_kwargs,
)
```

（以文件现有 import 形式为准，仅确保 `vl_sampling_kwargs` 在列。）

在文件末尾追加：

```python
def test_vl_sampling_kwargs_defaults():
    kwargs = vl_sampling_kwargs({}, "smoke")
    assert kwargs == {"max_tokens": 1024, "temperature": 0.0, "top_p": None, "disable_thinking": False}


def test_vl_sampling_kwargs_scene_isolation():
    settings = {
        "smoke_vl_confirm_max_tokens": "256",
        "smoke_vl_confirm_disable_thinking": "true",
        "fire_door_vl_confirm_max_tokens": "512",
    }
    assert vl_sampling_kwargs(settings, "smoke")["max_tokens"] == 256
    assert vl_sampling_kwargs(settings, "smoke")["disable_thinking"] is True
    assert vl_sampling_kwargs(settings, "fire_door")["max_tokens"] == 512
    assert vl_sampling_kwargs(settings, "fire_door")["disable_thinking"] is False


def test_vl_sampling_kwargs_overrides_take_precedence():
    kwargs = vl_sampling_kwargs(
        {"smoke_vl_confirm_max_tokens": "256", "smoke_vl_confirm_temperature": "0.5"},
        "smoke",
        overrides={"smoke_vl_confirm_max_tokens": "64", "smoke_vl_confirm_top_p": "0.9"},
    )
    assert kwargs["max_tokens"] == 64
    assert kwargs["temperature"] == 0.5
    assert kwargs["top_p"] == 0.9
    assert kwargs["disable_thinking"] is False


def test_vl_sampling_kwargs_lenient_parsing():
    settings = {
        "smoke_vl_confirm_max_tokens": "abc",
        "smoke_vl_confirm_temperature": "-3",
        "smoke_vl_confirm_top_p": "1.5",
        "smoke_vl_confirm_disable_thinking": "TRUE",
    }
    kwargs = vl_sampling_kwargs(settings, "smoke")
    assert kwargs["max_tokens"] == 1024
    assert kwargs["temperature"] == 0.0
    assert kwargs["top_p"] is None
    assert kwargs["disable_thinking"] is True

    clamped = vl_sampling_kwargs(
        {
            "smoke_vl_confirm_max_tokens": "0",
            "smoke_vl_confirm_temperature": "5",
            "smoke_vl_confirm_top_p": "0.9",
        },
        "smoke",
    )
    assert clamped["max_tokens"] == 1
    assert clamped["temperature"] == 2.0
    assert clamped["top_p"] == 0.9


def test_vl_sampling_kwargs_extreme_values_do_not_raise():
    kwargs = vl_sampling_kwargs(
        {
            "smoke_vl_confirm_max_tokens": "1e400",
            "smoke_vl_confirm_temperature": "1e400",
            "smoke_vl_confirm_top_p": "1e400",
        },
        "smoke",
    )
    assert kwargs["max_tokens"] == 32768
    assert kwargs["temperature"] == 2.0
    assert kwargs["top_p"] is None


async def test_complete_passes_sampling_kwargs():
    client = VLConfirmClient(
        "http://localhost:30000/v1", "EMPTY", "/models/Mage-VL",
        max_tokens=256, temperature=0.5, top_p=0.9,
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    kwargs = client._client.chat.completions.create.await_args.kwargs
    assert kwargs["max_tokens"] == 256
    assert kwargs["temperature"] == 0.5
    assert kwargs["top_p"] == 0.9
    assert "extra_body" not in kwargs


async def test_complete_omits_top_p_when_none():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    assert "top_p" not in client._client.chat.completions.create.await_args.kwargs


async def test_complete_disable_thinking_sends_extra_body():
    client = VLConfirmClient(
        "http://localhost:30000/v1", "EMPTY", "/models/Mage-VL",
        disable_thinking=True,
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    await client.complete("data:image/jpeg;base64,abc", "Ping")

    kwargs = client._client.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_vl_confirm.py -q`
Expected: 新增 8 个用例 FAIL（`ImportError: cannot import name 'vl_sampling_kwargs'` 或 `TypeError: __init__() got an unexpected keyword argument 'max_tokens'`），既有 28 个 PASS。

- [ ] **Step 3: 实现 `core/vl_confirm.py`**

3a. 在 `parse_vl_response` 函数之后、`encode_frame_as_data_url` 之前插入：

```python
DEFAULT_VL_MAX_TOKENS = 1024
DEFAULT_VL_TEMPERATURE = 0.0
VL_MAX_TOKENS_LIMIT = 32768


def _parse_float(raw: object, default: float) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError, OverflowError):
        return default


def vl_sampling_kwargs(
    settings: dict[str, str],
    scene_id: str,
    overrides: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build VLConfirmClient sampling kwargs from per-scene settings.
    从场景级设置构建 VL 采样参数。

    Merge order: ``overrides`` (request body) -> saved
    ``<scene>_vl_confirm_*`` settings -> defaults. 宽松解析：解析失败
    回退默认值，不抛错。
    """

    def merged(key: str) -> str:
        override = (overrides or {}).get(key)
        if override is not None and str(override).strip():
            return str(override).strip()
        saved = settings.get(key)
        if saved is not None and str(saved).strip():
            return str(saved).strip()
        return ""

    prefix = f"{scene_id}_vl_confirm_"

    max_tokens = int(
        _parse_float(
            merged(prefix + "max_tokens") or str(DEFAULT_VL_MAX_TOKENS),
            DEFAULT_VL_MAX_TOKENS,
        )
    )
    max_tokens = max(1, min(max_tokens, VL_MAX_TOKENS_LIMIT))

    temperature = _parse_float(
        merged(prefix + "temperature") or str(DEFAULT_VL_TEMPERATURE),
        DEFAULT_VL_TEMPERATURE,
    )
    temperature = max(0.0, min(temperature, 2.0))

    top_p: float | None = None
    raw_top_p = merged(prefix + "top_p")
    if raw_top_p:
        parsed = _parse_float(raw_top_p, 0.0)
        if 0 < parsed <= 1:
            top_p = parsed

    disable_thinking = merged(prefix + "disable_thinking").lower() == "true"

    return {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "disable_thinking": disable_thinking,
    }
```

3b. `VLConfirmClient.__init__` 改为（保留现有 `AsyncOpenAI` 构造）：

```python
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        top_p: float | None = None,
        disable_thinking: bool = False,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._disable_thinking = disable_thinking
        if AsyncOpenAI is None:
            raise RuntimeError("openai SDK is not installed")
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=float(timeout),
        )
```

3c. `complete()` 中构造请求部分改为：

```python
        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if self._top_p is not None:
            create_kwargs["top_p"] = self._top_p
        if self._disable_thinking:
            create_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        response = await self._client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content or ""
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_vl_confirm.py -q`
Expected: 36 passed（既有 28 + 新增 8），输出干净。

- [ ] **Step 5: 提交**

```bash
git add core/vl_confirm.py tests/test_vl_confirm.py
git commit -m "feat(vl): add per-scene sampling params to VLConfirmClient"
```

---

### Task 2: 生产管线 — 两个处理器接入本场景参数

**Files:**
- Modify: `core/smoke/processor.py`（import 行 + `_vl_confirm_alert` 内 client 构造）
- Modify: `core/fire_door/processor.py`（同上）
- Test: `tests/test_smoke.py`、`tests/test_fire_door.py`

**Interfaces:**
- Consumes: Task 1 的 `vl_sampling_kwargs(settings, scene_id)`（无 overrides）。
- Produces: 处理器构造 `VLConfirmClient` 时以 kwargs 形式传入 `max_tokens/temperature/top_p/disable_thinking`（取自 `self.app_settings` 中本场景键）。

- [ ] **Step 1: 写失败测试**

1a. `tests/test_smoke.py` 末尾追加：

```python
async def test_vl_sampling_params_from_smoke_settings_only():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = SmokeFireProcessor(
        source_id="s1",
        source_name="Cam1",
        rtsp_url="",
        rois=[],
        vengine_client=vengine,
        app_settings={
            "smoke_temporal_confirm_frames": "1",
            "smoke_enable_appearance_filter": "false",
            "smoke_vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "smoke_vl_confirm_max_tokens": "256",
            "smoke_vl_confirm_temperature": "0.5",
            "smoke_vl_confirm_top_p": "0.9",
            "smoke_vl_confirm_disable_thinking": "true",
            "fire_door_vl_confirm_max_tokens": "32",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.smoke.processor.VLConfirmClient") as mock_cls:
        result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

    assert len(result.messages) == 1
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_tokens"] == 256
    assert kwargs["temperature"] == 0.5
    assert kwargs["top_p"] == 0.9
    assert kwargs["disable_thinking"] is True
```

1b. `tests/test_fire_door.py` 末尾追加（复用文件既有 `_processor(vengine, settings=...)` 工厂）：

```python
async def test_vl_sampling_params_from_fire_door_settings_only():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(
        vengine,
        settings={
            "fire_door_vl_confirm_enabled": "true",
            "vl_confirm_base_url": "http://localhost:30000/v1",
            "vl_confirm_api_key": "EMPTY",
            "vl_confirm_model": "/models/Mage-VL",
            "fire_door_vl_confirm_max_tokens": "512",
            "fire_door_vl_confirm_disable_thinking": "true",
            "smoke_vl_confirm_max_tokens": "256",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("core.fire_door.processor.VLConfirmClient") as mock_cls:
        result = await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )

    assert len(result.messages) == 1
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_tokens"] == 512
    assert kwargs["disable_thinking"] is True
    assert kwargs["top_p"] is None
    assert kwargs["temperature"] == 0.0
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_smoke.py tests/test_fire_door.py -q -k sampling`
Expected: 2 failed（`KeyError: 'max_tokens'`——client 尚未接收采样参数）。

- [ ] **Step 3: 实现**

3a. `core/smoke/processor.py` import 行（现有 `from core.vl_confirm import VLConfirmClient, build_vl_image_data_url`）改为：

```python
from core.vl_confirm import VLConfirmClient, build_vl_image_data_url, vl_sampling_kwargs
```

3b. `core/smoke/processor.py` `_vl_confirm_alert` 中 client 构造改为：

```python
        client = VLConfirmClient(
            base_url=str(
                self.app_settings.get("vl_confirm_base_url")
                or "http://localhost:30000/v1"
            ),
            api_key=str(self.app_settings.get("vl_confirm_api_key") or "EMPTY"),
            model=str(self.app_settings.get("vl_confirm_model") or "/models/Mage-VL"),
            timeout=self._setting_int("vl_confirm_timeout", 60),
            **vl_sampling_kwargs(self.app_settings, "smoke"),
        )
```

3c. `core/fire_door/processor.py` 同样：import 行加 `vl_sampling_kwargs`（以该文件现有 `from core.vl_confirm import ...` 行为准追加）；`_vl_confirm_alert` 中 client 构造同样追加一行 `**vl_sampling_kwargs(self.app_settings, "fire_door"),`（其余参数行保持不变）。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_smoke.py tests/test_fire_door.py -q`
Expected: 全绿（含新增 2 个用例），无既有失败。

- [ ] **Step 5: 提交**

```bash
git add core/smoke/processor.py core/fire_door/processor.py tests/test_smoke.py tests/test_fire_door.py
git commit -m "feat(vl): pass per-scene sampling params in alarm pipeline"
```

---

### Task 3: 复盘端点接入本场景参数

**Files:**
- Modify: `backend/api/messages.py`（import + `review_message_with_vl` 中 client 构造）
- Test: `tests/test_messages.py`（`TestVlReviewEndpoint` 类内追加）

**Interfaces:**
- Consumes: Task 1 的 `vl_sampling_kwargs(settings, scene_id)`。
- Produces: 复盘端点构造 `VLConfirmClient` 时传入本场景采样参数；响应/错误语义不变。

- [ ] **Step 1: 写失败测试**

`tests/test_messages.py` 的 `TestVlReviewEndpoint` 类内（`test_vl_review_upstream_error_502` 之后）追加：

```python
    async def test_vl_review_uses_scene_sampling_settings(self, async_client: AsyncClient, init_db):
        source = await self._create_source()
        message_id = await self._save_message_with_image(source.id)
        await update_settings({
            "smoke_vl_confirm_enabled": "true",
            "smoke_vl_confirm_max_tokens": "128",
            "smoke_vl_confirm_temperature": "0.5",
            "smoke_vl_confirm_disable_thinking": "true",
        })

        with patch("backend.api.messages.VLConfirmClient") as mock_cls:
            mock_cls.return_value.complete = AsyncMock(return_value='{"smoke": true}')
            resp = await async_client.post(f"/api/messages/{message_id}/vl-review")

        assert resp.status_code == 200
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_tokens"] == 128
        assert kwargs["temperature"] == 0.5
        assert kwargs["disable_thinking"] is True
        assert kwargs.get("top_p") is None
```

（`patch` / `AsyncMock` / `update_settings` 均已在该文件导入；`self._create_source` / `self._save_message_with_image` 为该类既有辅助方法。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_messages.py -q -k sampling_settings`
Expected: 1 failed（`KeyError: 'max_tokens'`）。

- [ ] **Step 3: 实现**

3a. `backend/api/messages.py` 的 `from core.vl_confirm import ...` 行追加 `vl_sampling_kwargs`（以现有行为准）。

3b. `review_message_with_vl` 中 client 构造改为：

```python
    client = VLConfirmClient(
        base_url=base_url,
        api_key=str(settings_map.get("vl_confirm_api_key") or "EMPTY").strip() or "EMPTY",
        model=model,
        timeout=timeout,
        **vl_sampling_kwargs(settings_map, scene_id),
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_messages.py -q`
Expected: 全绿（含新增用例）。

- [ ] **Step 5: 提交**

```bash
git add backend/api/messages.py tests/test_messages.py
git commit -m "feat(messages): apply per-scene sampling params in VL review"
```

---

### Task 4: 测试端点 — `scene_id` 必填 + 参数覆盖

**Files:**
- Modify: `backend/models/schemas.py`（`VlTestRequest`）
- Modify: `backend/api/settings.py`（`test_vl_settings`）
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1 的 `vl_sampling_kwargs(settings, scene_id, overrides=...)`。
- Produces: `VlTestRequest`（`scene_id: str` 必填 + 4 个全局覆盖 + 8 个场景参数覆盖，均可选 `str | None`）；端点 422 校验 `scene_id ∈ {"smoke","fire_door"}`；client 按「请求体 → 已保存设置 → 默认」合并采样参数。

- [ ] **Step 1: 写失败测试**

1a. 更新既有 3 个 vl/test 用例的请求体（`tests/test_settings.py` ~214-254 行），各加一行 `"scene_id": "smoke",`：
- `test_vl_test_endpoint_ok`：json 首位加 `"scene_id": "smoke",`
- `test_vl_test_endpoint_missing_model_rejected`：`json={"scene_id": "smoke", "vl_confirm_base_url": "http://x/v1"}`
- `test_vl_test_endpoint_upstream_error_502`：json 首位加 `"scene_id": "smoke",`

1b. 在该 3 个用例之后追加：

```python
    async def test_vl_test_endpoint_missing_scene_rejected(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/settings/vl/test",
            json={"vl_confirm_base_url": "http://x/v1"},
        )
        assert resp.status_code == 422

    async def test_vl_test_endpoint_invalid_scene_rejected(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/settings/vl/test",
            json={"scene_id": "foo", "vl_confirm_base_url": "http://x/v1"},
        )
        assert resp.status_code == 422

    async def test_vl_test_endpoint_sampling_overrides_applied(self, async_client: AsyncClient):
        with patch("backend.api.settings.VLConfirmClient") as mock_cls:
            mock_cls.return_value.complete = AsyncMock(return_value='{"connected": true}')
            resp = await async_client.post(
                "/api/settings/vl/test",
                json={
                    "scene_id": "smoke",
                    "vl_confirm_base_url": "http://vl.example.com/v1",
                    "vl_confirm_model": "/models/test-vl",
                    "smoke_vl_confirm_max_tokens": "64",
                    "smoke_vl_confirm_temperature": "0.7",
                    "smoke_vl_confirm_top_p": "0.9",
                    "smoke_vl_confirm_disable_thinking": "true",
                },
            )
        assert resp.status_code == 200
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["max_tokens"] == 64
        assert kwargs["temperature"] == 0.7
        assert kwargs["top_p"] == 0.9
        assert kwargs["disable_thinking"] is True

    async def test_vl_test_endpoint_sampling_falls_back_to_scene_settings(self, async_client: AsyncClient):
        await update_settings({"smoke_vl_confirm_max_tokens": "128"})
        with patch("backend.api.settings.VLConfirmClient") as mock_cls:
            mock_cls.return_value.complete = AsyncMock(return_value='{"connected": true}')
            resp = await async_client.post(
                "/api/settings/vl/test",
                json={
                    "scene_id": "smoke",
                    "vl_confirm_base_url": "http://vl.example.com/v1",
                    "vl_confirm_model": "/models/test-vl",
                },
            )
        assert resp.status_code == 200
        assert mock_cls.call_args.kwargs["max_tokens"] == 128
```

（`patch` / `AsyncMock` / `update_settings` 已在 `tests/test_settings.py` 导入。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_settings.py -q -k vl_test`
Expected:
- 更新后的 3 个既有用例仍 PASS（旧 schema 无 `scene_id` 字段，pydantic 默认忽略多余键，行为不变）——它们的作用是防止实现后回归（实现后 `scene_id` 必填，缺了会 422）。
- `test_vl_test_endpoint_missing_scene_rejected` FAIL（旧端点不校验 scene_id，真实请求 `http://x/v1` 失败 → 502 ≠ 422）。
- `test_vl_test_endpoint_invalid_scene_rejected` FAIL（同上，502 ≠ 422）。
- `test_vl_test_endpoint_sampling_overrides_applied` / `test_vl_test_endpoint_sampling_falls_back_to_scene_settings` FAIL（`KeyError: 'max_tokens'`，client 未接收采样参数）。

即 RED 状态：4 failed，既有 3 个 PASS。

- [ ] **Step 3: 实现**

3a. `backend/models/schemas.py` 的 `VlTestRequest` 改为：

```python
class VlTestRequest(BaseModel):
    """Payload for testing the VL backend without saving first.
    用于在不先保存的情况下测试 VL 后端的载荷。"""

    scene_id: str
    vl_confirm_base_url: str | None = None
    vl_confirm_api_key: str | None = None
    vl_confirm_model: str | None = None
    vl_confirm_timeout: str | None = None
    smoke_vl_confirm_max_tokens: str | None = None
    smoke_vl_confirm_temperature: str | None = None
    smoke_vl_confirm_top_p: str | None = None
    smoke_vl_confirm_disable_thinking: str | None = None
    fire_door_vl_confirm_max_tokens: str | None = None
    fire_door_vl_confirm_temperature: str | None = None
    fire_door_vl_confirm_top_p: str | None = None
    fire_door_vl_confirm_disable_thinking: str | None = None
```

3b. `backend/api/settings.py`：`from core.vl_confirm import ...` 行追加 `vl_sampling_kwargs`（以现有行为准）；`test_vl_settings` 函数体改为：

```python
@router.post("/vl/test")
async def test_vl_settings(
    data: VlTestRequest,
    _role: str = Depends(require_any_permission("settings:*", "settings:plugins")),
) -> dict[str, object]:
    """Run a full connection test against the configured VL backend.
    使用当前或传入的设置对 VL 后端做一次全链路连接测试。"""
    if data.scene_id not in ("smoke", "fire_door"):
        raise HTTPException(status_code=422, detail="scene_id must be 'smoke' or 'fire_door'")
    app_settings = await db.get_all_settings()
    base_url = str(data.vl_confirm_base_url or app_settings.get("vl_confirm_base_url") or "").strip()
    api_key = str(data.vl_confirm_api_key or app_settings.get("vl_confirm_api_key") or "").strip()
    model = str(data.vl_confirm_model or app_settings.get("vl_confirm_model") or "").strip()
    timeout_raw = str(data.vl_confirm_timeout or app_settings.get("vl_confirm_timeout") or "60")
    if not base_url or not model:
        raise HTTPException(status_code=422, detail="VL base URL and model are required")
    try:
        timeout = max(1, int(float(timeout_raw)))
    except (ValueError, OverflowError):
        timeout = 60
    sampling_overrides = {
        key: value
        for key, value in data.model_dump().items()
        if key.startswith(f"{data.scene_id}_vl_confirm_") and value is not None
    }
    client = VLConfirmClient(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        model=model,
        timeout=timeout,
        **vl_sampling_kwargs(app_settings, data.scene_id, overrides=sampling_overrides),
    )
    started = time.monotonic()
    try:
        raw = await client.complete(build_vl_test_image_data_url(), VL_TEST_PROMPT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VL request failed: {exc}")
    return {
        "status": "ok",
        "model": model,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "response": raw,
    }
```

（注意：`except ValueError` 顺带扩为 `except (ValueError, OverflowError)`——`float("1e400")` 得 `inf`，`int(inf)` 抛 `OverflowError`，属既有 500 隐患，一并修掉。）

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_settings.py -q`
Expected: 全绿（含新增 4 个用例）。

- [ ] **Step 5: 提交**

```bash
git add backend/models/schemas.py backend/api/settings.py tests/test_settings.py
git commit -m "feat(settings): scope VL test endpoint to scene with sampling overrides"
```

---

### Task 5: 前端 — 两个插件卡片 4 参数 + 测试按钮携带 scene

**Files:**
- Modify: `frontend/src/views/Settings.vue`（form 默认值、3 个键清单、2 处模板、`testVlConfig`）
- Modify: `frontend/src/i18n/locales/zh-CN.js`、`frontend/src/i18n/locales/en-US.js`（settings 段 6 个新键）

**Interfaces:**
- Consumes: Task 4 的 `VlTestRequest`（`scene_id` + `<scene>_vl_confirm_*` 覆盖）。
- Produces: 表单 8 个字符串键 `smoke_vl_confirm_{max_tokens,temperature,top_p,disable_thinking}` / `fire_door_vl_confirm_{...}`；`testVl` payload 含 `scene_id` 与 4 个参数值。

- [ ] **Step 1: form 默认值**

`Settings.vue` 的 `const form = ref({` 内，`smoke_vl_confirm_response_key: 'smoke',`（~1641 行）之后插入：

```js
  smoke_vl_confirm_max_tokens: '1024',
  smoke_vl_confirm_temperature: '0',
  smoke_vl_confirm_top_p: '',
  smoke_vl_confirm_disable_thinking: 'false',
  fire_door_vl_confirm_max_tokens: '1024',
  fire_door_vl_confirm_temperature: '0',
  fire_door_vl_confirm_top_p: '',
  fire_door_vl_confirm_disable_thinking: 'false',
```

- [ ] **Step 2: 键清单（3 处）**

2a. `SMOKE_PLUGIN_SETTING_KEYS`（~1447 行，`'smoke_vl_confirm_response_key',` 之后）追加：

```js
  'smoke_vl_confirm_max_tokens',
  'smoke_vl_confirm_temperature',
  'smoke_vl_confirm_top_p',
  'smoke_vl_confirm_disable_thinking',
```

2b. `FIRE_DOOR_PLUGIN_SETTING_KEYS`（~1465 行，`'fire_door_vl_confirm_response_key',` 之后）追加：

```js
  'fire_door_vl_confirm_max_tokens',
  'fire_door_vl_confirm_temperature',
  'fire_door_vl_confirm_top_p',
  'fire_door_vl_confirm_disable_thinking',
```

2c. `PROCESSOR_RESTART_SETTING_KEYS`（~1341 行，`'smoke_vl_confirm_response_key',` 之后）追加全部 8 个键（与 2a/2b 相同的 8 行）。

- [ ] **Step 3: 模板 — smoke 卡片**

smoke VL 卡片中 `smoke_vl_confirm_response_key` 的 `el-form-item`（~870-872 行）之后、`</div>`（settings-form-grid 闭合）之前插入：

```html
                      <el-form-item :label="t('settings.vlMaxTokens')">
                        <el-input v-model="form.smoke_vl_confirm_max_tokens" placeholder="1024" />
                      </el-form-item>
                      <el-form-item :label="t('settings.vlTemperature')">
                        <el-input v-model="form.smoke_vl_confirm_temperature" placeholder="0" />
                      </el-form-item>
                      <el-form-item :label="t('settings.vlTopP')">
                        <el-input v-model="form.smoke_vl_confirm_top_p" />
                        <p class="form-hint">{{ t('settings.vlTopPHint') }}</p>
                      </el-form-item>
                      <el-form-item :label="t('settings.vlDisableThinking')" class="form-grid-span-full">
                        <div class="field-stack switch-field-stack">
                          <el-switch v-model="form.smoke_vl_confirm_disable_thinking" active-value="true" inactive-value="false" />
                          <p class="form-hint">{{ t('settings.vlDisableThinkingHint') }}</p>
                        </div>
                      </el-form-item>
```

- [ ] **Step 4: 模板 — fire_door 卡片**

fire_door VL 卡片中 `fire_door_vl_confirm_response_key` 的 `el-form-item`（~999-1002 行）之后插入与 Step 3 完全相同的 4 个 `el-form-item`，仅把 `v-model` 的 `smoke_` 前缀替换为 `fire_door_`。

- [ ] **Step 5: `testVlConfig` payload**

`testVlConfig`（~2219 行）中 `const payload = {` 改为：

```js
    const scene = currentPluginScene.value?.id || 'smoke'
    const payload = {
      scene_id: scene,
      vl_confirm_base_url: form.value.vl_confirm_base_url,
      vl_confirm_api_key: form.value.vl_confirm_api_key,
      vl_confirm_model: form.value.vl_confirm_model,
      vl_confirm_timeout: form.value.vl_confirm_timeout,
      [`${scene}_vl_confirm_max_tokens`]: form.value[`${scene}_vl_confirm_max_tokens`],
      [`${scene}_vl_confirm_temperature`]: form.value[`${scene}_vl_confirm_temperature`],
      [`${scene}_vl_confirm_top_p`]: form.value[`${scene}_vl_confirm_top_p`],
      [`${scene}_vl_confirm_disable_thinking`]: form.value[`${scene}_vl_confirm_disable_thinking`],
    }
```

（`currentPluginScene` 为既有 computed（~1672 行）；两个按钮分别只渲染在对应插件卡片内，故点击时 `currentPluginScene.value.id` 即本卡片场景。）

- [ ] **Step 6: i18n**

6a. `frontend/src/i18n/locales/zh-CN.js` settings 段 `vlConfirmResponseKey: '响应字段名',`（~643 行）之后插入：

```js
    vlMaxTokens: '最大生成 Token (max_tokens)',
    vlTemperature: '采样温度 (temperature)',
    vlTopP: '核采样 (top_p)',
    vlTopPHint: '留空 = 使用模型默认值（0-1）',
    vlDisableThinking: '关闭思考模式',
    vlDisableThinkingHint: '适用于 vLLM + Qwen3 等思考模型，可显著降低延迟；非 vLLM 服务端不支持',
```

6b. `frontend/src/i18n/locales/en-US.js` settings 段 `vlConfirmResponseKey: 'Response Key',`（~643 行）之后插入：

```js
    vlMaxTokens: 'Max Tokens',
    vlTemperature: 'Temperature',
    vlTopP: 'Top P',
    vlTopPHint: 'Leave empty to use the model default (0-1)',
    vlDisableThinking: 'Disable Thinking',
    vlDisableThinkingHint: 'For thinking models (e.g. vLLM + Qwen3); significantly reduces latency. Not supported by non-vLLM servers',
```

- [ ] **Step 7: 验证**

Run: `cd frontend && npx vitest run`
Expected: 74 passed + 2 既有失败（settingsRoutes），无新增失败。
Run: `cd frontend && npm run build`
Expected: 构建成功，无模板/编译错误。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/views/Settings.vue frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat(settings): add per-scene VL sampling params to plugin cards"
```

---

### Task 6: 全量回归

**Files:** 无代码改动（纯验证）

- [ ] **Step 1: 后端全量**

Run: `uv run pytest tests -q`
Expected: 440 passed + 1 既有失败（`tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`）。
（基线 425 + 新增 15 个用例：Task 1 × 8 + Task 2 × 2 + Task 3 × 1 + Task 4 × 4 = 440。）

- [ ] **Step 2: 前端全量 + 构建**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 74 passed + 2 既有失败；构建成功。

- [ ] **Step 3: 手动 E2E 清单（用户环境，真实 vLLM，由用户执行）**

- 设置页 smoke 卡片：`max_tokens` 改为 `64` → 点「测试连接」→ 回复被截断或判定失败；fire_door 卡片保持 `1024` → 测试正常 → 验证插件独立。
- 打开 smoke 的「关闭思考」→ 测试连接耗时应明显下降（~0.3s vs ~1.7s 量级）。
- `top_p` 填 `0.9` 保存 → 复盘请求应携带 `top_p`（可查 vLLM 日志）；清空 → 不携带。
- 消息页 VL 复盘：结果对话框正常，消息状态不被修改。
- 保存任一插件的采样参数 → 触发处理器重启 → 生产告警二次确认按新参数运行（vLLM 日志核对）。
