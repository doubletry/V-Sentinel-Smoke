# VL 大模型代理模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后台设置中选择 VL 请求的代理方式（不走代理 / 手动 / 系统代理），四个 VL 调用路径统一走 `build_vl_client` 工厂，消除环境变量代理劫持 VL 请求且无法关闭的问题。

**Architecture:** `core/vl_confirm.py` 新增 `build_vl_http_client(mode, url)`（按模式构造 httpx2 客户端）与 `build_vl_client(settings, scene_id, overrides)` 工厂；`VLConfirmClient` 增加可选 `http_client` 透传参数。两个 API 端点与两个 processor 全部改走工厂（端点 422 校验、processor 配置错误回退直连）。设置键 `vl_confirm_proxy_mode` / `vl_confirm_proxy_url` 走既有 app_settings 持久化，前端在 VL 全局区加下拉框 + 条件输入框。

**Tech Stack:** Python 3.11 + FastAPI + openai SDK 3.1.0（httpx2 2.10.0）+ loguru；前端 Vue 3 + Element Plus + vue-i18n；测试 pytest（asyncio_mode=auto）+ vitest。

**Spec:** `docs/superpowers/specs/2026-09-02-vl-proxy-mode-design.md`

## Global Constraints

- 日志消息用英文、loguru `{}` 占位符；日志中不得出现代理 URL（可能含凭据），只记录 mode。
- `vl_confirm_proxy_mode` 取值 `none`（默认）/ `manual` / `system`；键缺失或值非法一律按 `none` 宽松处理（与 `vl_sampling_kwargs` 的宽松解析惯例一致）。
- 白名单三处必须齐加（防"采样字段漏持久化"类 bug 复发）：`AppSettingsUpdate`、`PLUGIN_SETTING_KEYS`、`VlTestRequest`。
- `manual` 模式 URL 必须以 `http://` 或 `https://` 开头；空/非法时端点 422、processor WARNING + 回退直连。
- 运行测试：`uv run pytest -q`（工作目录仓库根）。已知环境性失败 `tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`（本地 .env 导致）忽略。
- ruff：`uv run ruff check core/ backend/ tests/` 不得新增错误。
- 提交风格：Conventional Commits（`feat(vl):` / `feat(settings):` / `feat(frontend):`），当前分支 `feat/logging-coverage`。
- 前端验证：`cd frontend && npm run test && npm run build`。

---

### Task 1: 客户端层 — `http_client` 参数 + `build_vl_http_client` + `build_vl_client` 工厂

**Files:**
- Modify: `core/vl_confirm.py`（imports、`VLConfirmClient.__init__`、新增两个函数 + 常量）
- Test: `tests/test_vl_confirm.py`（文件末尾追加）

**Interfaces:**
- Consumes: 现有 `vl_sampling_kwargs(settings, scene_id, overrides)`、`VLConfirmClient(base_url, api_key, model, timeout, **sampling)`
- Produces:
  - `build_vl_http_client(mode: str, url: str) -> httpx2.AsyncClient | None`（`system` → `None`；`manual` 非法 URL → `ValueError("VL manual proxy URL must start with http:// or https://")`；其余 → `trust_env=False` 直连客户端）
  - `build_vl_client(settings: dict[str, str], scene_id: str, overrides: dict[str, str | None] | None = None) -> VLConfirmClient`（合并顺序 overrides → settings → 默认值；默认 `base_url="http://localhost:30000/v1"`、`api_key="EMPTY"`、`model="/models/Mage-VL"`、`timeout=60`）
  - `VLConfirmClient` 新可选参数 `http_client: httpx2.AsyncClient | None = None`（None → SDK 默认客户端，现状行为）

- [ ] **Step 1: 写失败测试**

在 `tests/test_vl_confirm.py` 文件末尾追加（`VALID_COMPLETION`、`_free_port`、`_run_local_vl_server` 已存在于该文件，直接复用）：

```python
# --- Proxy mode: build_vl_http_client / build_vl_client ---


async def _always_ok(n: int):
    return VALID_COMPLETION


async def _start_recording_proxy() -> tuple[int, dict, object]:
    """TCP server that counts connections; reads the request then closes (black hole)."""
    import socket as _socket

    state = {"n": 0}

    async def handle(reader, writer):
        state["n"] += 1
        try:
            await reader.read(65536)
        except Exception:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    with _socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = await asyncio.start_server(handle, "127.0.0.1", port)
    return port, state, server


def test_build_vl_http_client_none_mode():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("none", "") is not None


def test_build_vl_http_client_empty_mode_is_direct():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("", "") is not None


def test_build_vl_http_client_unknown_mode_falls_back_to_direct():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("bogus", "") is not None


def test_build_vl_http_client_system_returns_none():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("system", "") is None


def test_build_vl_http_client_manual_invalid_url_raises():
    from core.vl_confirm import build_vl_http_client

    with pytest.raises(ValueError, match="http://"):
        build_vl_http_client("manual", "")
    with pytest.raises(ValueError):
        build_vl_http_client("manual", "ftp://10.0.0.1:3128")


def test_build_vl_http_client_manual_valid():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("manual", "http://10.0.0.1:3128") is not None
    assert build_vl_http_client("manual", "https://10.0.0.1:3129") is not None


def test_build_vl_client_merge_order():
    from core.vl_confirm import build_vl_client

    settings = {
        "vl_confirm_base_url": "http://saved/v1",
        "vl_confirm_model": "saved-model",
        "vl_confirm_timeout": "45",
        "smoke_vl_confirm_max_tokens": "100",
    }
    client = build_vl_client(settings, "smoke")
    assert client._base_url == "http://saved/v1"
    assert client._model == "saved-model"
    assert client._timeout == 45.0

    client2 = build_vl_client(
        settings, "smoke", overrides={"vl_confirm_base_url": "http://override/v1", "vl_confirm_timeout": "7"}
    )
    assert client2._base_url == "http://override/v1"
    assert client2._timeout == 7.0


def test_build_vl_client_defaults():
    from core.vl_confirm import build_vl_client

    client = build_vl_client({}, "smoke")
    assert client._base_url == "http://localhost:30000/v1"
    assert client._model == "/models/Mage-VL"
    assert client._api_key == "EMPTY"
    assert client._timeout == 60.0


def test_build_vl_client_manual_proxy_missing_url_raises():
    from core.vl_confirm import build_vl_client

    with pytest.raises(ValueError):
        build_vl_client({"vl_confirm_proxy_mode": "manual"}, "smoke")


async def test_vl_proxy_none_ignores_env_proxy(monkeypatch):
    """'none' must go direct even when HTTP_PROXY is set (regression guard)."""
    from core.vl_confirm import build_vl_client

    base_url, model_state = _run_local_vl_server(_always_ok)
    proxy_port, proxy_state, proxy_server = await _start_recording_proxy()
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy_port}")
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy_port}")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        client = build_vl_client(
            {"vl_confirm_base_url": base_url, "vl_confirm_proxy_mode": "none"}, "smoke"
        )
        await client.complete("data:image/jpeg;base64,abc", "ping")
        assert model_state["n"] == 1, "direct call must reach the model"
        assert proxy_state["n"] == 0, "env proxy must be ignored in 'none' mode"
    finally:
        proxy_server.close()
        await proxy_server.wait_closed()
        model_state["shutdown"]()


async def test_vl_proxy_manual_uses_configured_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    base_url, model_state = _run_local_vl_server(_always_ok)
    proxy_port, proxy_state, proxy_server = await _start_recording_proxy()
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    try:
        client = build_vl_client(
            {
                "vl_confirm_base_url": base_url,
                "vl_confirm_proxy_mode": "manual",
                "vl_confirm_proxy_url": f"http://127.0.0.1:{proxy_port}",
            },
            "smoke",
        )
        with pytest.raises(Exception):
            await client.complete("data:image/jpeg;base64,abc", "ping")
        assert model_state["n"] == 0, "manual mode must not hit the model directly"
        assert proxy_state["n"] >= 1, "request must be routed through the proxy"
    finally:
        proxy_server.close()
        await proxy_server.wait_closed()
        model_state["shutdown"]()


async def test_vl_proxy_system_uses_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    base_url, model_state = _run_local_vl_server(_always_ok)
    proxy_port, proxy_state, proxy_server = await _start_recording_proxy()
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy_port}")
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy_port}")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        client = build_vl_client(
            {"vl_confirm_base_url": base_url, "vl_confirm_proxy_mode": "system"}, "smoke"
        )
        with pytest.raises(Exception):
            await client.complete("data:image/jpeg;base64,abc", "ping")
        assert model_state["n"] == 0, "system mode must not hit the model directly"
        assert proxy_state["n"] >= 1, "request must be routed through the env proxy"
    finally:
        proxy_server.close()
        await proxy_server.wait_closed()
        model_state["shutdown"]()
```

同时把文件顶部 import 区补上 `asyncio`（`_start_recording_proxy` 用；若文件里还没有）：

```python
import asyncio
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_vl_confirm.py -k "http_client or proxy or merge_order or defaults" -q`
Expected: 全部 FAIL（`ImportError: cannot import name 'build_vl_http_client'` 等）

- [ ] **Step 3: 实现 `core/vl_confirm.py`**

3a. imports 区（文件头）：`import asyncio` 已存在则跳过；补 `TYPE_CHECKING`：

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx2
```

`AsyncOpenAI` 的 try/except 之后补 `DefaultAsyncHttpxClient` 的同等保护：

```python
try:
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient
except ImportError:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore[assignment]
    DefaultAsyncHttpxClient = None  # type: ignore[assignment]
```

3b. 常量 + `build_vl_http_client`（放在 `vl_sampling_kwargs` 之后、`encode_frame_as_data_url` 之前）：

```python
DEFAULT_VL_BASE_URL = "http://localhost:30000/v1"
DEFAULT_VL_API_KEY = "EMPTY"
DEFAULT_VL_MODEL = "/models/Mage-VL"
DEFAULT_VL_TIMEOUT = 60


def build_vl_http_client(mode: str, url: str) -> Any:
    """Build the httpx2 client for the given proxy mode.

    Returns ``None`` for ``system`` (the OpenAI SDK then builds its default
    client, which reads environment proxy variables). ``manual`` with a
    missing/malformed URL raises ``ValueError``. Unknown modes degrade to
    direct (``none``) — 宽松解析，未知值按直连处理。
    """
    if DefaultAsyncHttpxClient is None:
        raise RuntimeError("openai SDK is not installed")
    mode = str(mode or "").strip().lower()
    url = str(url or "").strip()
    if mode == "system":
        return None
    if mode == "manual":
        if not url.startswith(("http://", "https://")):
            raise ValueError("VL manual proxy URL must start with http:// or https://")
        return DefaultAsyncHttpxClient(proxy=url, trust_env=False)
    # "none" (default) and unknown values: direct, ignore environment proxies.
    return DefaultAsyncHttpxClient(trust_env=False)
```

3c. `VLConfirmClient.__init__` 加 `http_client` 参数（`disable_thinking` 之后）并透传：

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
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._timeout = float(timeout)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._disable_thinking = disable_thinking
        if AsyncOpenAI is None:
            raise RuntimeError("openai SDK is not installed")
        client_kwargs: dict[str, Any] = {}
        if http_client is not None:
            client_kwargs["http_client"] = http_client
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=self._timeout,
            **client_kwargs,
        )
```

注意：新增 `self._api_key = api_key`（工厂测试断言用；api_key 只存内存不进日志）。

3d. 工厂 `build_vl_client`（放在 `VLConfirmClient` 类之后）：

```python
def build_vl_client(
    settings: dict[str, str],
    scene_id: str,
    overrides: dict[str, str | None] | None = None,
) -> VLConfirmClient:
    """Build a VLConfirmClient from settings (and optional request overrides).

    Merge order per field: ``overrides`` -> ``settings`` -> defaults,
    matching the previous per-call-site behavior（四个调用点统一入口，
    防止构造点漂移）。``manual`` proxy 模式缺 URL 时抛 ``ValueError``，
    由调用方决定 422（端点）或回退直连（processor）。
    """

    def merged(key: str) -> str:
        override = (overrides or {}).get(key)
        if override is not None and str(override).strip():
            return str(override).strip()
        saved = settings.get(key)
        if saved is not None and str(saved).strip():
            return str(saved).strip()
        return ""

    base_url = merged("vl_confirm_base_url") or DEFAULT_VL_BASE_URL
    api_key = merged("vl_confirm_api_key") or DEFAULT_VL_API_KEY
    model = merged("vl_confirm_model") or DEFAULT_VL_MODEL
    try:
        timeout = max(1, int(float(merged("vl_confirm_timeout") or str(DEFAULT_VL_TIMEOUT))))
    except (TypeError, ValueError, OverflowError):
        timeout = DEFAULT_VL_TIMEOUT

    proxy_mode = merged("vl_confirm_proxy_mode") or "none"
    http_client = build_vl_http_client(proxy_mode, merged("vl_confirm_proxy_url"))
    client = VLConfirmClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        **vl_sampling_kwargs(settings, scene_id, overrides=overrides),
        http_client=http_client,
    )
    logger.info("VL client: proxy_mode={}", proxy_mode)
    return client
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_vl_confirm.py -q`
Expected: 全部 PASS（含既有 39 个用例零回归）

- [ ] **Step 5: 提交**

```bash
git add core/vl_confirm.py tests/test_vl_confirm.py
git commit -m "feat(vl): add proxy mode support to VLConfirmClient (none/manual/system)"
```

---

### Task 2: 后端接线 — 设置持久化 + 两个端点改走工厂

**Files:**
- Modify: `backend/models/schemas.py`（`AppSettingsUpdate` ~581 行后、`VlTestRequest` ~635 行后）
- Modify: `backend/api/settings.py`（`PLUGIN_SETTING_KEYS` ~74 行后、`/vl/test` 端点 253-304 行、import 第 12 行）
- Modify: `backend/api/messages.py`（`/vl-review` 客户端构造 176-182 行、import 第 31 行）
- Test: `tests/test_settings.py`（`TestSettingsAPI` 内追加 + 更新 2 个既有测试的 patch 目标）

**Interfaces:**
- Consumes: Task 1 的 `build_vl_client(settings, scene_id, overrides)`（`manual` 缺 URL → `ValueError`）
- Produces: 设置键 `vl_confirm_proxy_mode` / `vl_confirm_proxy_url` 可经 `PUT /api/settings` 持久化、operator 角色可写、`POST /api/settings/vl/test` 与 `POST /api/messages/{id}/vl-review` 均按模式路由

- [ ] **Step 1: 写失败测试**

1a. `tests/test_settings.py` 的 `TestSettingsAPI` 类中，在 `test_update_persists_vl_sampling_settings` 测试之后追加：

```python
    async def test_update_persists_vl_proxy_settings(self, async_client: AsyncClient):
        payload = {
            "vl_confirm_proxy_mode": "manual",
            "vl_confirm_proxy_url": "http://10.0.0.1:3128",
        }
        resp = await async_client.put("/api/settings", json=payload)
        assert resp.status_code == 200
        for key, value in payload.items():
            assert resp.json()[key] == value
        got = await async_client.get("/api/settings")
        assert got.status_code == 200
        for key, value in payload.items():
            assert got.json()[key] == value

    async def test_plugin_role_can_update_vl_proxy_settings(self, async_client: AsyncClient):
        from backend.auth.security import create_access_token

        token = create_access_token(username="op-vl-proxy", role="operator")["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = await async_client.put(
            "/api/settings",
            json={"vl_confirm_proxy_mode": "system"},
            headers=headers,
        )
        assert resp.status_code == 200
        got = await async_client.get("/api/settings", headers=headers)
        assert got.json()["vl_confirm_proxy_mode"] == "system"

    async def test_vl_test_manual_proxy_missing_url_422(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/settings/vl/test",
            json={
                "scene_id": "smoke",
                "vl_confirm_base_url": "http://vl.example.com/v1",
                "vl_confirm_model": "/models/test-vl",
                "vl_confirm_proxy_mode": "manual",
            },
        )
        assert resp.status_code == 422
        assert "proxy" in resp.json()["detail"]

    async def test_vl_test_proxy_overrides_applied(self, async_client: AsyncClient):
        with patch("core.vl_confirm.build_vl_http_client") as mock_build:
            mock_build.return_value = None
            with patch("core.vl_confirm.VLConfirmClient") as mock_cls:
                mock_cls.return_value.complete = AsyncMock(return_value='{"connected": true}')
                resp = await async_client.post(
                    "/api/settings/vl/test",
                    json={
                        "scene_id": "smoke",
                        "vl_confirm_base_url": "http://vl.example.com/v1",
                        "vl_confirm_model": "/models/test-vl",
                        "vl_confirm_proxy_mode": "manual",
                        "vl_confirm_proxy_url": "http://10.0.0.1:3128",
                    },
                )
        assert resp.status_code == 200
        mock_build.assert_called_once_with("manual", "http://10.0.0.1:3128")
```

1b. 更新两个既有测试的 patch 目标（端点不再直接 import `VLConfirmClient`，工厂在 `core.vl_confirm` 内构造，故 patch 目标改为工厂所在模块；断言不变）：

`test_vl_test_endpoint_sampling_overrides_applied`（~300 行）：
- 旧：`with patch("backend.api.settings.VLConfirmClient") as mock_cls:`
- 新：`with patch("core.vl_confirm.VLConfirmClient") as mock_cls:`

`test_vl_test_endpoint_sampling_falls_back_to_scene_settings`（~322 行）：
- 旧：`with patch("backend.api.settings.VLConfirmClient") as mock_cls:`
- 新：`with patch("core.vl_confirm.VLConfirmClient") as mock_cls:`

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_settings.py -k "vl_proxy or proxy_overrides or sampling_overrides or sampling_falls" -q`
Expected: `test_update_persists_vl_proxy_settings` FAIL（KeyError：字段被 Pydantic 丢弃）；`test_vl_test_manual_proxy_missing_url_422` FAIL（现在恒 200/502 而非 422）；`test_vl_test_proxy_overrides_applied` FAIL（`build_vl_http_client` 不存在）；两个 sampling 测试 FAIL（patch 目标不存在）

- [ ] **Step 3: 实现后端**

3a. `backend/models/schemas.py` — `AppSettingsUpdate` 中 `vl_confirm_timeout: str | None = None`（~581 行）之后加：

```python
    vl_confirm_proxy_mode: str | None = None
    vl_confirm_proxy_url: str | None = None
```

`VlTestRequest` 中 `vl_confirm_timeout: str | None = None`（~635 行）之后加同样两行。

3b. `backend/api/settings.py`：

import（第 12 行）改为：

```python
from core.vl_confirm import VL_TEST_PROMPT, build_vl_client, build_vl_test_image_data_url
```

`PLUGIN_SETTING_KEYS` 中 `"vl_confirm_timeout",` 之后加：

```python
    "vl_confirm_proxy_mode",
    "vl_confirm_proxy_url",
```

`/vl/test` 端点（253-304 行）整体替换为：

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
    model = str(data.vl_confirm_model or app_settings.get("vl_confirm_model") or "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=422, detail="VL base URL and model are required")
    overrides = {
        key: value
        for key, value in data.model_dump().items()
        if key != "scene_id" and value is not None
    }
    try:
        client = build_vl_client(app_settings, data.scene_id, overrides=overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    started = time.monotonic()
    try:
        raw = await client.complete(build_vl_test_image_data_url(), VL_TEST_PROMPT)
    except Exception as exc:
        logger.opt(exception=True).warning(
            "VL connection test failed: scene={} model={} base_url={}",
            data.scene_id, model, base_url,
        )
        raise HTTPException(status_code=502, detail=f"VL request failed: {exc}")
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "VL connection test ok: scene={} model={} latency_ms={}",
        data.scene_id, model, latency_ms,
    )
    return {
        "status": "ok",
        "model": model,
        "latency_ms": latency_ms,
        "response": raw,
    }
```

3c. `backend/api/messages.py`：

import（第 31 行）改为：

```python
from core.vl_confirm import build_vl_client, encode_frame_as_data_url, parse_vl_response
```

`/vl-review` 端点中客户端构造块（176-182 行）替换为：

```python
    try:
        client = build_vl_client(settings_map, scene_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
```

（该函数里原有的 base_url/model 提取与 422 校验、图片加载逻辑保持不变。）

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_settings.py tests/test_messages.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/models/schemas.py backend/api/settings.py backend/api/messages.py tests/test_settings.py
git commit -m "feat(settings): persist VL proxy settings and route both VL endpoints via factory"
```

---

### Task 3: Processor 接线 — 两个 processor 改走工厂（配置错误回退直连）

**Files:**
- Modify: `core/smoke/processor.py`（import 第 24 行、客户端构造 191-201 行）
- Modify: `core/fire_door/processor.py`（import 第 25 行、客户端构造 270-280 行）
- Test: `tests/test_smoke.py`、`tests/test_fire_door.py`（14 处 patch 目标更新 + 各加 1 个回退测试）

**Interfaces:**
- Consumes: Task 1 的 `build_vl_client(settings, scene_id, overrides)`
- Produces: processor 的 VL 自动确认按 `vl_confirm_proxy_*` 设置路由；`manual` 缺 URL 时 WARNING + 回退直连（`confirm()` 既有失败开放语义不变）

注意：既有测试 patch 的是 processor 模块命名空间里的名字（`from core.vl_confirm import VLConfirmClient` 的绑定）。Step 2 让 processor 改走工厂后，该绑定消失，14 处 patch 目标必须同步改为 `core.vl_confirm.VLConfirmClient`（工厂在 `core/vl_confirm.py` 模块内引用该类，patch 模块名生效）。

- [ ] **Step 1: 写失败测试（回退行为）**

`tests/test_smoke.py` 文件末尾追加（`_vl_processor`、`_decode_data_url`、`logger` 等已存在于该文件）：

```python
async def test_vl_manual_proxy_misconfigured_falls_back_to_direct():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    processor.app_settings["vl_confirm_proxy_mode"] = "manual"
    processor.app_settings["vl_confirm_proxy_url"] = ""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client) as mock_cls:
            result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
    finally:
        logger.remove(sink_id)

    assert len(result.messages) == 1
    assert mock_cls.call_count == 1  # 首次构造抛 ValueError，仅回退路径构造一次
    fallbacks = [r for r in records if "falling back to direct" in r["message"]]
    assert fallbacks
    assert "Cam1" in fallbacks[0]["message"]
```

`tests/test_fire_door.py` 文件末尾追加：

```python
async def test_vl_manual_proxy_misconfigured_falls_back_to_direct():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    processor.app_settings["vl_confirm_proxy_mode"] = "manual"
    processor.app_settings["vl_confirm_proxy_url"] = ""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client):
            result = await processor.process_frame(
                frame, b"frame", frame.shape,
                [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
            )
    finally:
        logger.remove(sink_id)

    assert len(result.messages) == 1
    fallbacks = [r for r in records if "falling back to direct" in r["message"]]
    assert fallbacks
    assert "DoorCam" in fallbacks[0]["message"]
```

Run: `uv run pytest tests/test_smoke.py tests/test_fire_door.py -k "proxy_misconfigured" -q`
Expected: 2 FAILED（processor 尚未处理 ValueError，`process_frame` 抛错或无回退日志）

- [ ] **Step 2: 实现 processor 接线**

`core/smoke/processor.py`：

import（第 24 行）改为：

```python
from core.vl_confirm import build_vl_client, build_vl_image_data_url
```

客户端构造块（191-201 行）替换为：

```python
        try:
            client = build_vl_client(self.app_settings, "smoke")
        except ValueError as exc:
            logger.warning(
                "VL proxy misconfigured ({}), falling back to direct: source={}",
                exc,
                self.source_name,
            )
            client = build_vl_client(
                self.app_settings, "smoke", overrides={"vl_confirm_proxy_mode": "none"}
            )
        return await client.confirm(image_data_url, prompt, response_key)
```

`core/fire_door/processor.py`：

import（第 25 行）改为：

```python
from core.vl_confirm import build_vl_client, build_vl_image_data_url
```

客户端构造块（270-280 行）替换为：

```python
        try:
            client = build_vl_client(self.app_settings, "fire_door")
        except ValueError as exc:
            logger.warning(
                "VL proxy misconfigured ({}), falling back to direct: source={}",
                exc,
                self.source_name,
            )
            client = build_vl_client(
                self.app_settings, "fire_door", overrides={"vl_confirm_proxy_mode": "none"}
            )
        return await client.confirm(image_data_url, prompt, response_key)
```

（`logger` 在两个文件中均已 import；`self.source_name` 已存在。）

- [ ] **Step 3: 更新 14 处既有测试的 patch 目标**

processor 不再 import `VLConfirmClient`，旧 patch 目标（processor 模块命名空间）已不存在。

对 `tests/test_smoke.py` 全文替换（7 处）：
- 旧：`patch("core.smoke.processor.VLConfirmClient"`
- 新：`patch("core.vl_confirm.VLConfirmClient"`

对 `tests/test_fire_door.py` 全文替换（7 处）：
- 旧：`patch("core.fire_door.processor.VLConfirmClient"`
- 新：`patch("core.vl_confirm.VLConfirmClient"`

（断言不变：工厂以关键字参数构造 `VLConfirmClient`，`call_args.kwargs` 仍含 `max_tokens`/`disable_thinking` 等。）

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_smoke.py tests/test_fire_door.py -q`
Expected: 全部 PASS（含 14 个更新 patch 目标的既有用例 + 2 个新回退测试）

- [ ] **Step 5: 提交**

```bash
git add core/smoke/processor.py core/fire_door/processor.py tests/test_smoke.py tests/test_fire_door.py
git commit -m "feat(vl): route processor VL confirm through build_vl_client with direct fallback"
```

---

### Task 4: 前端 — 设置 UI + 保存/测试载荷 + i18n

**Files:**
- Modify: `frontend/src/views/Settings.vue`（`VL_CONFIRM_GLOBAL_KEYS` 1367-1372 行、模板 850-852 行后、表单默认值 ~1685 行、`testVlConfig` 2280-2290 行）
- Modify: `frontend/src/i18n/locales/zh-CN.js`（~640 行后）
- Modify: `frontend/src/i18n/locales/en-US.js`（~640 行后）

**Interfaces:**
- Consumes: 既有 `saveSection`/`pickFormValues`（键经 `VL_CONFIRM_GLOBAL_KEYS` 自动进保存载荷）、`testVlConfig` 显式载荷
- Produces: 表单字段 `form.vl_confirm_proxy_mode`（`'none'`/`'manual'`/`'system'`）与 `form.vl_confirm_proxy_url`（string），随保存/测试载荷提交

- [ ] **Step 1: 改 `frontend/src/views/Settings.vue`**

1a. `VL_CONFIRM_GLOBAL_KEYS`（1367-1372 行）改为：

```js
const VL_CONFIRM_GLOBAL_KEYS = [
  'vl_confirm_base_url',
  'vl_confirm_api_key',
  'vl_confirm_model',
  'vl_confirm_timeout',
  'vl_confirm_proxy_mode',
  'vl_confirm_proxy_url',
]
```

1b. 模板中 `vl_confirm_timeout` 表单项（850-852 行）之后插入：

```html
                      <el-form-item :label="t('settings.vlConfirmProxyMode')">
                        <el-select v-model="form.vl_confirm_proxy_mode">
                          <el-option :label="t('settings.vlConfirmProxyModeNone')" value="none" />
                          <el-option :label="t('settings.vlConfirmProxyModeManual')" value="manual" />
                          <el-option :label="t('settings.vlConfirmProxyModeSystem')" value="system" />
                        </el-select>
                        <p class="form-hint">{{ t('settings.vlConfirmProxyModeHint') }}</p>
                      </el-form-item>
                      <el-form-item v-if="form.vl_confirm_proxy_mode === 'manual'" :label="t('settings.vlConfirmProxyUrl')">
                        <el-input v-model="form.vl_confirm_proxy_url" placeholder="http://10.0.0.1:3128" />
                      </el-form-item>
```

1c. 表单默认值对象中 `vl_confirm_timeout: '60',`（~1685 行）之后加：

```js
  vl_confirm_proxy_mode: 'none',
  vl_confirm_proxy_url: '',
```

1d. `testVlConfig` 载荷（2280-2290 行）中 `vl_confirm_timeout: form.value.vl_confirm_timeout,` 之后加：

```js
      vl_confirm_proxy_mode: form.value.vl_confirm_proxy_mode,
      vl_confirm_proxy_url: form.value.vl_confirm_proxy_url,
```

- [ ] **Step 2: 改 i18n**

`frontend/src/i18n/locales/zh-CN.js` 的 `vlConfirmTimeout: '超时时间（秒）',`（640 行）之后加：

```js
    vlConfirmProxyMode: '代理模式',
    vlConfirmProxyModeNone: '不走代理',
    vlConfirmProxyModeManual: '手动设置',
    vlConfirmProxyModeSystem: '走系统代理',
    vlConfirmProxyModeHint: 'VL 请求如何出网：不走代理（默认，局域网模型直连）/ 手动指定代理 / 读取系统环境变量代理',
    vlConfirmProxyUrl: '代理地址',
```

`frontend/src/i18n/locales/en-US.js` 的 `vlConfirmTimeout: 'Timeout (seconds)',`（640 行）之后加：

```js
    vlConfirmProxyMode: 'Proxy Mode',
    vlConfirmProxyModeNone: 'No proxy',
    vlConfirmProxyModeManual: 'Manual',
    vlConfirmProxyModeSystem: 'System proxy',
    vlConfirmProxyModeHint: 'How VL requests go out: direct (default, for LAN models) / manual proxy / system environment proxies',
    vlConfirmProxyUrl: 'Proxy URL',
```

- [ ] **Step 3: 验证**

Run: `cd frontend && npm run test && npm run build`
Expected: vitest 全绿（既有 `vlTimeout.test.js` 等）；vite build 成功无模板/JS 错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/Settings.vue frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat(frontend): add VL proxy mode (none/manual/system) to settings UI"
```

---

### Task 5: 全量验证 + 推送

**Files:** 无新改动（仅验证与推送；发现小问题就地修复并单独提交）

- [ ] **Step 1: 后端全量测试**

Run: `uv run pytest -q`
Expected: 全绿；唯一允许失败为已知环境性 `tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`（本地 .env 导致，干净检出通过）

- [ ] **Step 2: ruff**

Run: `uv run ruff check core/ backend/ tests/`
Expected: 不新增错误（基线 32 条，全在改动文件之外的既有项）

- [ ] **Step 3: 前端验证**

Run: `cd frontend && npm run test && npm run build`
Expected: 全绿

- [ ] **Step 4: 推送（更新 PR #18）**

```bash
git push origin feat/logging-coverage
```

Expected: 推送成功（如遇代理 502 瞬时错误，等待后重试）；PR #18 自动更新。

- [ ] **Step 5: 向用户汇报**

说明：部署后默认"不走代理"（直连）；原依赖环境变量代理的部署需在设置里切"走系统代理"；手动代理 URL 仅 manual 模式生效。部署机自查命令 `docker exec <容器> env | grep -i proxy` 写入 PR 描述补充。
