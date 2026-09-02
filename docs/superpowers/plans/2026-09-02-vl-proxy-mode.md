# VL 代理模式 + 推流/复判解耦 + 即时告警横幅 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ① VL 请求支持代理模式（不走代理/手动/系统代理）集中构造；② 开启复判后实时画面（标注帧推流）不再被 VL 调用阻塞，消息与通知语义不变。

**Architecture:** `core/vl_confirm.py` 新增 `build_vl_http_client` / `build_vl_client` 工厂，4 个调用点（2 个 processor 的 `_vl_confirm_alert`、2 个 API 端点）统一改走工厂。流水线解耦：`process_frame` 立即返回（告警时把 VL 任务存 `result.extra["pending_alert"]`），backend 基类 `_handle_result` 先推流入队、再派脱离帧槽位的后台任务 `finalize_result`（等 VL 结论、构建消息）→ `agent.submit`（广播+通知）。即时告警横幅：告警**上升沿**把告警文本放入 `pending_alert["alert_text"]`，`_dispatch_result` 在等 VL **之前**经 `WSManager.send_notification`（不入库）广播 `alert_notify`；前端全局 WS + App.vue 顶部流式横幅（新替换旧、5s 自动隐藏）。

**Tech Stack:** Python 3.11 / openai SDK 3.1.0 / httpx2 2.10.0 / FastAPI / loguru / pytest（`asyncio_mode=auto`）/ Vue 3 + Element Plus。

**Spec:** `docs/superpowers/specs/2026-09-02-vl-proxy-mode-design.md`

## Global Constraints

- 分支 `feat/logging-coverage`（PR #18 开放，未合并）；Conventional Commits；**只 commit，不 push**（最后任务统一推送）。
- 日志：英文消息、loguru `{}` 占位、异常用 `logger.opt(exception=True)`（loguru 忽略 `exc_info=True`）。
- 代理 URL 可能含凭据 → 日志只记 mode，不记 URL。
- 设置键合并顺序：`overrides → settings → 默认值`（与现有调用点一致）。
- 解耦语义：推流立即入队；消息/通知仍在 VL 结论后（与现状一致）；`false_positive` 在持久化前确定。
- 已知环境性失败（不计入回归）：`tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`（本地未跟踪 `.env` 的 `VITE_APP_BASE_PATH=/smoke`）。
- Ruff 基线 32 条错误；要求 0 新增（改动文件必须 0 错误）。

---

### Task 1: 客户端层 —— `http_client` 参数 + 两个工厂

**Files:**
- Modify: `core/vl_confirm.py`
- Test: `tests/test_vl_confirm.py`

**Interfaces:**
- Produces:
  - `build_vl_http_client(mode: str, url: str) -> httpx2.AsyncClient | None`（`system` → None；`manual` 非法 → `ValueError("VL manual proxy URL must start with http:// or https://")`）
  - `build_vl_client(settings: dict, scene_id: str, overrides: dict | None = None) -> VLConfirmClient`
  - 模块级符号：`DEFAULT_VL_BASE_URL` / `DEFAULT_VL_API_KEY` / `DEFAULT_VL_MODEL`（值同现有默认）
  - `VLConfirmClient(..., http_client=None)` 关键字参数
- Consumes: `vl_sampling_kwargs(settings, scene_id, overrides=None)`（已存在，`core/vl_confirm.py`）

- [ ] **Step 1: 写失败测试**

`tests/test_vl_confirm.py` 顶部 import 区补 `import asyncio`。文件末尾追加：

```python
# ── proxy mode / 代理模式 ────────────────────────────────────────────────────


async def _start_recording_proxy(handler, state):
    from uvicorn import Config, Server

    class _ProxyHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            try:
                handler(self.path)
            except Exception:
                pass
            body = json.dumps(VALID_COMPLETION).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), _ProxyHandler)
    config = Config(
        app=server,
        host="127.0.0.1",
        port=server.server_address[1],
        log_level="error",
        lifespan="off",
    )
    uvicorn_server = Server(config)
    task = asyncio.create_task(uvicorn_server.serve())
    while not uvicorn_server.started:
        await asyncio.sleep(0.01)
    state.update(
        url=f"http://127.0.0.1:{server.server_address[1]}",
        shutdown=lambda: (uvicorn_server.should_exit := True),
    )
    return task


def test_build_vl_http_client_none_mode_ignores_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_http_client

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    client = build_vl_http_client("none", "")
    assert client is not None
    assert client._trust_env is False
    assert not any("AsyncHTTPProxy" in repr(vars(t).get("_pool", "")) for t in client._mounts.values())
    monkeypatch.delenv("HTTP_PROXY")
    monkeypatch.delenv("http_proxy")


def test_build_vl_http_client_unknown_mode_behaves_like_none():
    from core.vl_confirm import build_vl_http_client

    client = build_vl_http_client("bogus", "")
    assert client is not None
    assert client._trust_env is False


def test_build_vl_http_client_manual_requires_scheme():
    from core.vl_confirm import build_vl_http_client

    with pytest.raises(ValueError, match="http:// or https://"):
        build_vl_http_client("manual", "")
    with pytest.raises(ValueError, match="http:// or https://"):
        build_vl_http_client("manual", "ftp://10.0.0.1:21")


def test_build_vl_http_client_manual_sets_proxy():
    from core.vl_confirm import build_vl_http_client

    client = build_vl_http_client("manual", "http://10.0.0.1:3128")
    assert client is not None
    assert client._trust_env is False
    # 代理挂载存在（httpx2 代理 transport 的池是 AsyncHTTPProxy）
    assert any("AsyncHTTPProxy" in repr(vars(t).get("_pool", "")) for t in client._mounts.values())


def test_build_vl_http_client_system_returns_none():
    from core.vl_confirm import build_vl_http_client

    assert build_vl_http_client("system", "") is None
    assert build_vl_http_client("", "") is not None


def test_build_vl_client_merge_order_and_defaults():
    from core.vl_confirm import build_vl_client

    settings = {
        "vl_confirm_base_url": "http://settings-host/v1",
        "vl_confirm_api_key": "settings-key",
        "vl_confirm_model": "settings-model",
        "vl_confirm_timeout": "7",
        "smoke_vl_confirm_max_tokens": "128",
    }
    client = build_vl_client(settings, "smoke", overrides={"vl_confirm_base_url": "http://override-host/v1"})
    assert client._base_url == "http://override-host/v1"
    assert client._api_key == "settings-key"
    assert client._model == "settings-model"
    assert client._timeout == 7.0
    assert client._max_tokens == 128


def test_build_vl_client_scene_specific_sampling():
    from core.vl_confirm import build_vl_client

    settings = {
        "smoke_vl_confirm_temperature": "0.1",
        "fire_door_vl_confirm_temperature": "0.9",
    }
    assert build_vl_client(settings, "smoke")._temperature == 0.1
    assert build_vl_client(settings, "fire_door")._temperature == 0.9


def test_build_vl_client_defaults_when_settings_empty():
    from core.vl_confirm import build_vl_client

    client = build_vl_client({}, "smoke")
    assert client._base_url == "http://localhost:30000/v1"
    assert client._api_key == "EMPTY"
    assert client._model == "/models/Mage-VL"
    assert client._timeout == 60.0


def _model_ok(request, state):
    state["n"] += 1
    return (
        "HTTP/1.1 200 OK",
        {"Content-Type": "application/json"},
        json.dumps(VALID_COMPLETION).encode(),
    )


async def test_vl_none_mode_reaches_model_not_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    model_state: dict = {"n": 0}
    base_url, model_state = await _run_local_vl_server(
        lambda request: _model_ok(request, model_state)
    )
    proxy_state: dict = {"n": 0}
    proxy_task = await _start_recording_proxy(
        lambda path: proxy_state.update(n=proxy_state["n"] + 1), proxy_state
    )
    monkeypatch.setenv("HTTP_PROXY", proxy_state["url"])
    monkeypatch.setenv("http_proxy", proxy_state["url"])
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        client = build_vl_client(
            {"vl_confirm_base_url": base_url, "vl_confirm_timeout": "5"}, "smoke"
        )
        result = await client.complete("hi", "text", None)
    finally:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        proxy_state["shutdown"]()
        await proxy_task
        model_state["shutdown"]()
    assert result["choices"][0]["message"]["content"] == "yes"
    assert model_state["n"] == 1
    assert proxy_state["n"] == 0


async def test_vl_manual_mode_routes_through_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    model_state: dict = {"n": 0}
    base_url, model_state = await _run_local_vl_server(
        lambda request: _model_ok(request, model_state)
    )
    proxy_state: dict = {"n": 0}
    proxy_task = await _start_recording_proxy(
        lambda path: proxy_state.update(n=proxy_state["n"] + 1), proxy_state
    )
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    try:
        client = build_vl_client(
            {
                "vl_confirm_base_url": base_url,
                "vl_confirm_timeout": "5",
                "vl_confirm_proxy_mode": "manual",
                "vl_confirm_proxy_url": proxy_state["url"],
            },
            "smoke",
        )
        result = await client.complete("hi", "text", None)
    finally:
        proxy_state["shutdown"]()
        await proxy_task
        model_state["shutdown"]()
    assert result["choices"][0]["message"]["content"] == "yes"
    assert proxy_state["n"] == 1
    assert model_state["n"] == 0


async def test_vl_system_mode_uses_env_proxy(monkeypatch):
    from core.vl_confirm import build_vl_client

    model_state: dict = {"n": 0}
    base_url, model_state = await _run_local_vl_server(
        lambda request: _model_ok(request, model_state)
    )
    proxy_state: dict = {"n": 0}
    proxy_task = await _start_recording_proxy(
        lambda path: proxy_state.update(n=proxy_state["n"] + 1), proxy_state
    )
    monkeypatch.setenv("HTTP_PROXY", proxy_state["url"])
    monkeypatch.setenv("http_proxy", proxy_state["url"])
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        client = build_vl_client(
            {
                "vl_confirm_base_url": base_url,
                "vl_confirm_timeout": "5",
                "vl_confirm_proxy_mode": "system",
            },
            "smoke",
        )
        result = await client.complete("hi", "text", None)
    finally:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        proxy_state["shutdown"]()
        await proxy_task
        model_state["shutdown"]()
    assert proxy_state["n"] == 1
    assert model_state["n"] == 0
```

注意：`_run_local_vl_server` 现有实现返回 `(base_url, state)`，state 含 `n` 与 `shutdown`；`_model_ok` 递增 `state["n"]`。`_start_recording_proxy` 的 `state["shutdown"]` 置 `Server.should_exit`（uvicorn 优雅退出）。若 uvicorn 对 `http.server` WSGI app 的 `should_exit` 行为不符，实现者改用 `task.cancel()` + `await asyncio.wait(...)` 收尾，并断言前确认 `proxy_state["n"]` 已定值。

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_vl_confirm.py -k "http_client or proxy or merge_order or defaults" -q
```

预期：FAIL（`ImportError: cannot import name 'build_vl_http_client'` 等）。

- [ ] **Step 3: 实现 `core/vl_confirm.py`**

`DEFAULT_VL_CONFIRM_PROMPT` 常量之后加默认值常量：

```python
DEFAULT_VL_BASE_URL = "http://localhost:30000/v1"
DEFAULT_VL_API_KEY = "EMPTY"
DEFAULT_VL_MODEL = "/models/Mage-VL"
DEFAULT_VL_TIMEOUT = 60
```

import 区：`from typing import Any` 保留；补

```python
from typing import TYPE_CHECKING, Any
import httpx2
try:
    from openai import DefaultAsyncHttpxClient
except ImportError:  # pragma: no cover - 极老版本 openai
    DefaultAsyncHttpxClient = None  # type: ignore[assignment]

if TYPE_CHECKING:
    pass
```

（`DefaultAsyncHttpxClient` 在 openai 3.1.0 中可正常导入；try/except 仅为防未来移除。）

`VLConfirmClient.__init__` 签名改为（末尾追加可选参数，既有调用零影响）：

```python
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        disable_thinking: bool | None = None,
        http_client: "httpx2.AsyncClient | None" = None,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, http_client=http_client)
        self._model = model
        self._timeout = float(timeout)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._disable_thinking = disable_thinking
        self._api_key = api_key
```

文件末尾（`VLConfirmClient` 类之后）加工厂：

```python
def build_vl_http_client(mode: str, url: str) -> "httpx2.AsyncClient | None":
    """Build the httpx2 transport for a VL client per proxy mode.
    按代理模式构造 VL 客户端的 httpx2 传输。

    Returns ``None`` for ``system`` mode so the openai SDK builds its own
    default client (which reads environment proxies).
    """
    normalized = str(mode or "none").strip().lower()
    if normalized == "system":
        return None
    if normalized == "manual":
        text = str(url or "").strip()
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("VL manual proxy URL must start with http:// or https://")
        return DefaultAsyncHttpxClient(proxy=text, trust_env=False)
    # none / 未知值 → 确定性直连（忽略环境变量）
    return DefaultAsyncHttpxClient(trust_env=False)


def build_vl_client(
    settings: dict,
    scene_id: str,
    overrides: dict | None = None,
) -> VLConfirmClient:
    """Build a VLConfirmClient from global settings (+ per-request overrides).
    用全局设置（+ 请求级 overrides）统一构造 VLConfirmClient。

    Merge order matches the historical call sites:
    ``overrides → settings → defaults``.
    """
    ov = dict(overrides or {})
    mode = str(ov.get("vl_confirm_proxy_mode") or settings.get("vl_confirm_proxy_mode") or "none")
    url = str(ov.get("vl_confirm_proxy_url") or settings.get("vl_confirm_proxy_url") or "")
    try:
        timeout = int(float(ov.get("vl_confirm_timeout") or settings.get("vl_confirm_timeout") or DEFAULT_VL_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_VL_TIMEOUT
    return VLConfirmClient(
        base_url=str(ov.get("vl_confirm_base_url") or settings.get("vl_confirm_base_url") or DEFAULT_VL_BASE_URL),
        api_key=str(ov.get("vl_confirm_api_key") or settings.get("vl_confirm_api_key") or DEFAULT_VL_API_KEY),
        model=str(ov.get("vl_confirm_model") or settings.get("vl_confirm_model") or DEFAULT_VL_MODEL),
        timeout=timeout,
        **vl_sampling_kwargs(settings, scene_id, ov),
        http_client=build_vl_http_client(mode, url),
    )
```

`build_vl_client` 尾部加一行 INFO（工厂每次调用都记录，不记 URL）：

```python
    logger.info("VL client: proxy_mode={}", mode)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/test_vl_confirm.py -q
```

预期：全部 PASS（含既有 `_run_local_vl_server` 用例与新用例）。

- [ ] **Step 5: 静态检查 + 提交**

```bash
uv run ruff check core/vl_confirm.py tests/test_vl_confirm.py
git add core/vl_confirm.py tests/test_vl_confirm.py
git commit -m "feat(vl): add proxy mode support to VLConfirmClient (none/manual/system)"
```

---

### Task 2: 后端接线 —— 设置持久化 + 两个端点走工厂

**Files:**
- Modify: `backend/models/schemas.py`（`AppSettingsUpdate` ~581、`VlTestRequest` ~635）
- Modify: `backend/api/settings.py`（`PLUGIN_SETTING_KEYS`、vl/test 端点 ~253-304、import）
- Modify: `backend/api/messages.py`（vl-review 端点 ~176、import）
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1 的 `build_vl_client`、`VLConfirmClient`。
- Produces: 设置键 `vl_confirm_proxy_mode` / `vl_confirm_proxy_url` 可持久化、operator 可更新；vl/test 与 vl-review 的 manual 非法 URL 返回 422。

- [ ] **Step 1: 写失败测试**

`tests/test_settings.py` 末尾追加：

```python
async def test_update_persists_vl_proxy_settings(async_client):
    response = await async_client.put(
        "/api/settings",
        json={
            "vl_confirm_proxy_mode": "manual",
            "vl_confirm_proxy_url": "http://10.0.0.1:3128",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["vl_confirm_proxy_mode"] == "manual"
    assert response.json()["vl_confirm_proxy_url"] == "http://10.0.0.1:3128"

    fetched = await async_client.get("/api/settings")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["vl_confirm_proxy_mode"] == "manual"
    assert fetched.json()["vl_confirm_proxy_url"] == "http://10.0.0.1:3128"


async def test_plugin_role_can_update_vl_proxy_settings(async_client, init_db):
    from backend.auth.security import create_access_token

    token = create_access_token(
        subject="00000000-0000-0000-0000-000000000002",
        role="plugin",
        permissions=["settings:plugins", "settings:mediamtx", "settings:notifications"],
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.put(
        "/api/settings",
        json={"vl_confirm_proxy_mode": "system"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["vl_confirm_proxy_mode"] == "system"


async def test_vl_test_rejects_invalid_manual_proxy(async_client):
    response = await async_client.post(
        "/api/settings/vl/test",
        json={
            "scene_id": "smoke",
            "vl_confirm_base_url": "http://localhost:9/v1",
            "vl_confirm_proxy_mode": "manual",
            "vl_confirm_proxy_url": "",
        },
    )
    assert response.status_code == 422, response.text


async def test_vl_test_uses_request_proxy_overrides(async_client):
    with patch("core.vl_confirm.DefaultAsyncHttpxClient") as mock_http:
        response = await async_client.post(
            "/api/settings/vl/test",
            json={
                "scene_id": "smoke",
                "vl_confirm_base_url": "http://localhost:9/v1",
                "vl_confirm_proxy_mode": "manual",
                "vl_confirm_proxy_url": "http://10.9.9.9:3128",
            },
        )
    assert response.status_code in (200, 502), response.text
    kwargs = mock_http.call_args.kwargs
    assert kwargs.get("proxy") == "http://10.9.9.9:3128"


async def test_vl_review_rejects_invalid_manual_proxy(async_client, init_db):
    from backend.db.database import get_source

    source = await get_source("src-0001")
    assert source is not None
    response = await async_client.post(
        "/api/messages/vl-review",
        json={
            "source_id": "src-0001",
            "original_image_base64": "aGVsbG8=",
            "detected_image_base64": "d29ybGQ=",
            "vl_confirm_proxy_mode": "manual",
            "vl_confirm_proxy_url": "not-a-url",
        },
    )
    assert response.status_code == 422, response.text
```

（`tests/test_settings.py` 已 import `patch`；若无则补 `from unittest.mock import patch`。`async_client`/`init_db` 为 conftest 既有 fixture。）

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_settings.py -k "vl_proxy or proxy_settings or invalid_manual or proxy_overrides" -q
```

预期：FAIL（422 用例收到 200/502；持久化用例字段缺失；operator 用例 403）。

- [ ] **Step 3: `AppSettingsUpdate` 加两键**

`backend/models/schemas.py`，`vl_confirm_timeout: str | None = None` 之后：

```python
    vl_confirm_proxy_mode: str | None = None
    vl_confirm_proxy_url: str | None = None
```

- [ ] **Step 4: `VlTestRequest` 加两键**

`backend/models/schemas.py`，`VlTestRequest.vl_confirm_model` 之后：

```python
    vl_confirm_proxy_mode: str | None = None
    vl_confirm_proxy_url: str | None = None
```

- [ ] **Step 5: `PLUGIN_SETTING_KEYS` 加两键**

`backend/api/settings.py`，`"vl_confirm_timeout",` 之后：

```python
    "vl_confirm_proxy_mode",
    "vl_confirm_proxy_url",
```

- [ ] **Step 6: vl/test 端点改走工厂**

`backend/api/settings.py`：

import 行 12 改为：

```python
from core.vl_confirm import VLConfirmClient, build_vl_client
```

端点内（`prompt`/`response_key` 计算之后、`client = VLConfirmClient(...)` 之前）插入 manual 校验，并把 client 构造替换为工厂：

```python
    proxy_mode = str(data.vl_confirm_proxy_mode or "").strip().lower() or "none"
    proxy_url = str(data.vl_confirm_proxy_url or "").strip()
    if proxy_mode == "manual" and not proxy_url.lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422,
            detail="vl_confirm_proxy_url must start with http:// or https:// in manual mode",
        )
    overrides = {
        k: v
        for k, v in {
            "vl_confirm_base_url": data.vl_confirm_base_url,
            "vl_confirm_api_key": data.vl_confirm_api_key,
            "vl_confirm_model": data.vl_confirm_model,
            "vl_confirm_timeout": data.vl_confirm_timeout,
            "vl_confirm_max_tokens": data.vl_confirm_max_tokens,
            "vl_confirm_temperature": data.vl_confirm_temperature,
            "vl_confirm_top_p": data.vl_confirm_top_p,
            "vl_confirm_disable_thinking": data.vl_confirm_disable_thinking,
            "vl_confirm_proxy_mode": proxy_mode,
            "vl_confirm_proxy_url": proxy_url,
        }.items()
        if v is not None
    }
    try:
        client = build_vl_client(app_settings, data.scene_id, overrides=overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

（删除原 `client = VLConfirmClient(...)` 构造块；`vl/test` 的 overrides 键名与 `VlTestRequest` 字段一一对应。`VLConfirmClient` import 若不再被引用则移除——该文件其余处不再直接构造，移除。）

- [ ] **Step 7: vl-review 端点改走工厂**

`backend/api/messages.py`：

import 行 31 改为：

```python
from core.vl_confirm import VLConfirmClient, build_vl_client
```

（若该文件不再直接构造 `VLConfirmClient`，移除该符号，仅留 `build_vl_client`。）

原 176-182 行的 client 构造替换为：

```python
        settings_map = dict(app_settings)
        if data.vl_confirm_base_url is not None:
            settings_map["vl_confirm_base_url"] = data.vl_confirm_base_url
        if data.vl_confirm_api_key is not None:
            settings_map["vl_confirm_api_key"] = data.vl_confirm_api_key
        if data.vl_confirm_model is not None:
            settings_map["vl_confirm_model"] = data.vl_confirm_model
        if data.vl_confirm_proxy_mode is not None:
            settings_map["vl_confirm_proxy_mode"] = data.vl_confirm_proxy_mode
        if data.vl_confirm_proxy_url is not None:
            settings_map["vl_confirm_proxy_url"] = data.vl_confirm_proxy_url
        try:
            client = build_vl_client(settings_map, data.scene_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
```

并在构造前（现有 base_url/model 422 校验之后）补 manual 校验：

```python
    proxy_mode = str(data.vl_confirm_proxy_mode or "").strip().lower()
    if proxy_mode == "manual":
        proxy_url = str(data.vl_confirm_proxy_url or "").strip()
        if not proxy_url.lower().startswith(("http://", "https://")):
            raise HTTPException(
                status_code=422,
                detail="vl_confirm_proxy_url must start with http:// or https:// in manual mode",
            )
```

（`VlReviewRequest` 需同样加 `vl_confirm_proxy_mode` / `vl_confirm_proxy_url` 两个 `str | None = None` 字段——`backend/models/schemas.py`，紧邻 `VlTestRequest` 改动的下方。）

- [ ] **Step 8: 跑测试确认通过**

```bash
uv run pytest tests/test_settings.py -q
```

预期：全部 PASS。

- [ ] **Step 9: 静态检查 + 提交**

```bash
uv run ruff check backend/models/schemas.py backend/api/settings.py backend/api/messages.py tests/test_settings.py
git add backend/models/schemas.py backend/api/settings.py backend/api/messages.py tests/test_settings.py
git commit -m "feat(settings): persist VL proxy mode/url and route vl/test + vl-review through factory"
```

---

### Task 3: 流水线解耦 —— 推流不再等待 VL 复判

**Files:**
- Modify: `core/base_processor.py`（`finalize_result` no-op 钩子，`_should_display_result` 之后）
- Modify: `backend/processing/base.py`（`_dispatch_tasks`、`stop()`、`_handle_result`、`_dispatch_result`）
- Modify: `core/smoke/processor.py`（`import asyncio`、`_pending_vl_tasks`、`stop()`、`process_frame` 改造、`finalize_result`）
- Modify: `core/fire_door/processor.py`（同型改造）
- Test: `tests/test_smoke.py`、`tests/test_fire_door.py`、`tests/test_processing.py`

**Interfaces:**
- Produces:
  - `BaseVideoProcessor.finalize_result(result)` 钩子（core no-op；场景覆写）
  - `result.extra["pending_alert"]` = `{"frame", "annotated", 场景字段..., "vl_task": asyncio.Task | None}`（无告警时为 None）
  - backend `_dispatch_tasks: set[asyncio.Task]`（stop 时 cancel）
- Consumes: 无新依赖。

**行为契约（测试依据）：**
- `process_frame` 返回时：`annotated_frame` 已就绪；有告警且复判开启时 `pending_alert["vl_task"]` 未完成、`messages == []`。
- backend `_process_frame_item` 返回时：推流队列已有帧；消息广播未发生。
- `finalize_result` 完成后：消息构建完毕（`false_positive` 正确、确认/失败开放时附 `email_event`），随后广播 + 通知。
- `stop()` 取消挂起的 dispatch 与 VL 任务。

- [ ] **Step 1: 写失败测试**

`tests/test_smoke.py`：顶部 import 区补 `import asyncio`。文件末尾追加：

```python
async def test_process_frame_returns_before_vl_verdict():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    gate = asyncio.Event()

    async def gated_verdict():
        await gate.wait()
        return True

    processor._vl_confirm_alert = lambda *args: gated_verdict()

    result = await asyncio.wait_for(
        processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, []),
        timeout=5.0,
    )

    vl_task = result.extra["pending_alert"]["vl_task"]
    assert vl_task is not None and not vl_task.done()
    assert result.annotated_frame is not None
    assert result.messages == []

    gate.set()
    await processor.finalize_result(result)
    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert result.extra["email_event"]["event_type"] == "smoke"
```

`tests/test_fire_door.py`：顶部 import 区补 `import asyncio`。文件末尾追加：

```python
async def test_process_frame_returns_before_vl_verdict():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]]

    gate = asyncio.Event()

    async def gated_verdict():
        await gate.wait()
        return True

    processor._vl_confirm_alert = lambda *args: gated_verdict()

    result = await asyncio.wait_for(
        processor.process_frame(frame, b"frame", frame.shape, roi_points),
        timeout=5.0,
    )

    vl_task = result.extra["pending_alert"]["vl_task"]
    assert vl_task is not None and not vl_task.done()
    assert result.annotated_frame is not None
    assert result.messages == []

    gate.set()
    await processor.finalize_result(result)
    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert result.messages[0]["scene_id"] == "fire_door"
    assert "email_event" in result.extra
```

`tests/test_processing.py`：文件末尾追加（`asyncio`/`AsyncMock`/`MagicMock`/`np`/`BaseVideoProcessor`/`AnalysisResult` 均已 import）：

```python
class TestPushVsVlDecoupling:
    def _make_slow_processor(self, gate, ws):
        class SlowProcessor(BaseVideoProcessor):
            async def process_frame(self, frame, encoded, shape, roi_pixel_points):
                result = AnalysisResult(annotated_frame=frame)

                async def verdict():
                    await gate.wait()
                    return True

                result.extra["pending_alert"] = {"vl_task": asyncio.create_task(verdict())}
                return result

            async def finalize_result(self, result):
                task = result.extra.pop("pending_alert")["vl_task"]
                await task
                result.messages.append(
                    {
                        "timestamp": "2026-09-02T00:00:00+00:00",
                        "source_name": "cam",
                        "source_id": "s1",
                        "scene_id": "smoke",
                        "level": "alert",
                        "message": "alert",
                    }
                )

        return SlowProcessor(
            source_id="s1",
            source_name="cam",
            rtsp_url="rtsp://localhost:8554/cam1",
            rois=[],
            vengine_client=MagicMock(),
            ws_manager=ws,
            app_settings={},
        )

    async def test_push_enqueued_before_verdict_broadcast_after(self):
        gate = asyncio.Event()
        ws = AsyncMock()
        proc = self._make_slow_processor(gate, ws)
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        await proc._process_frame_item(frame, b"x")

        assert proc._output_queue.qsize() == 1
        assert ws.broadcast.await_count == 0

        gate.set()
        if proc._dispatch_tasks:
            await asyncio.wait_for(asyncio.gather(*proc._dispatch_tasks), 5.0)
        assert ws.broadcast.await_count == 1

    async def test_stop_cancels_pending_dispatch(self):
        gate = asyncio.Event()
        ws = AsyncMock()
        proc = self._make_slow_processor(gate, ws)
        proc._run_loop = AsyncMock()
        await proc.start()
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        await proc._process_frame_item(frame, b"x")
        assert proc._output_queue.qsize() == 1
        assert ws.broadcast.await_count == 0

        await proc.stop()

        assert ws.broadcast.await_count == 0
        assert proc._dispatch_tasks == set()
        gate.set()
        await asyncio.sleep(0)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_smoke.py::test_process_frame_returns_before_vl_verdict tests/test_fire_door.py::test_process_frame_returns_before_vl_verdict tests/test_processing.py::TestPushVsVlDecoupling -q
```

预期：FAIL（smoke/fire_door 超时/`KeyError: 'pending_alert'`；test_processing 因 `_dispatch_tasks` 不存在 AttributeError，或 broadcast 时机不符）。

- [ ] **Step 3: `core/base_processor.py` 加 no-op 钩子**

`_should_display_result` 方法之后：

```python
    async def finalize_result(self, result: AnalysisResult) -> None:
        """Scene hook for slow post-processing before message dispatch.
        Runs on a detached dispatch task after the display hand-off, so it
        never blocks the real-time push.
        场景钩子：消息分发前的慢速后处理（如等待 VL 复判结论）。
        在推流交接之后、脱离帧处理槽位的后台任务中运行，不阻塞实时画面。"""
        del result
```

- [ ] **Step 4: `backend/processing/base.py` 重排 `_handle_result`**

`__init__` 末尾（`self.started_at: str | None = None` 之后）加：

```python
        self._dispatch_tasks: set[asyncio.Task] = set()
```

现有 `# ── Result dispatch / 结果分发` 注释块（含 `_handle_result`）整体替换为：

```python
    async def stop(self) -> None:
        """Cancel pending dispatch tasks, then stop the core pipeline.
        先取消挂起的分发任务，再停止核心流水线。"""
        if self._dispatch_tasks:
            for task in list(self._dispatch_tasks):
                task.cancel()
            try:
                await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
            except Exception:
                pass
            self._dispatch_tasks.clear()
        await super().stop()

    # ── Result dispatch / 结果分发 ────────────────────────────────────────────

    async def _handle_result(self, frame, result: AnalysisResult) -> None:
        """Enqueue display first so the real-time push never waits for slow
        steps (e.g. VL confirm), then dispatch messages on a detached task.
        先入队推流，保证实时画面不等待慢速步骤（如 VL 复判）；
        消息分发在脱离帧槽位的后台任务中完成。"""
        await super()._handle_result(frame, result)
        task = asyncio.create_task(
            self._dispatch_result(result), name=f"dispatch-{self.source_id}"
        )
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)

    async def _dispatch_result(self, result: AnalysisResult) -> None:
        """Finalize the result (await slow verdicts), then dispatch messages.
        完成场景钩子（等待慢速结论），然后分发消息。"""
        try:
            await self.finalize_result(result)
            if self.agent is not None:
                await self.agent.submit(
                    self.source_id, self.source_name, result
                )
            else:
                for msg in result.messages:
                    if not isinstance(msg, AnalysisMessage):
                        msg = AnalysisMessage(
                            id=msg.get("id"),
                            timestamp=msg.get(
                                "timestamp", datetime.now(timezone.utc).isoformat()
                            ),
                            source_name=msg.get("source_name", self.source_name),
                            source_id=msg.get("source_id", self.source_id),
                            scene_id=msg.get("scene_id", "smoke"),
                            level=msg.get("level", "info"),
                            message=msg.get("message", ""),
                            image_url=msg.get("image_url"),
                            image_base64=msg.get("image_base64"),
                            original_image_url=msg.get("original_image_url"),
                            original_image_base64=msg.get("original_image_base64"),
                            detected_image_url=msg.get("detected_image_url"),
                            detected_image_base64=msg.get("detected_image_base64"),
                            false_positive=bool(msg.get("false_positive", False)),
                        )
                    await self.ws_manager.broadcast(msg)
        except Exception:
            logger.opt(exception=True).error(
                "Failed to dispatch frame result: source={}", self.source_id
            )
```

- [ ] **Step 5: `core/smoke/processor.py` 改造**

import 区补 `import asyncio`（放在 `from datetime import ...` 之前）。

`__init__` 末尾（`self._post_processor = ...` 之后）加：

```python
        self._pending_vl_tasks: set[asyncio.Task] = set()
```

`__init__` 之后加 `stop()` 覆写：

```python
    async def stop(self) -> None:
        if self._pending_vl_tasks:
            for task in list(self._pending_vl_tasks):
                task.cancel()
            try:
                await asyncio.gather(*self._pending_vl_tasks, return_exceptions=True)
            except Exception:
                pass
            self._pending_vl_tasks.clear()
        await super().stop()
```

`process_frame` 中，从 `vl_rejected = False` 开始到方法末尾 `return result` 的整段（VL await 块 + 消息构建块）替换为：

```python
        pending_alert = None
        if post_result.has_alarm and confirmed:
            vl_task = None
            if self._vl_confirm_enabled():
                vl_task = asyncio.create_task(
                    self._vl_confirm_alert(frame, annotated, primary_roi)
                )
                self._pending_vl_tasks.add(vl_task)
                vl_task.add_done_callback(self._pending_vl_tasks.discard)
            pending_alert = {
                "frame": frame,
                "annotated": annotated,
                "confirmed": confirmed,
                "post_result": post_result,
                "timestamp": timestamp,
                "vl_task": vl_task,
            }
        result.extra["pending_alert"] = pending_alert
        return result

    async def finalize_result(self, result: AnalysisResult) -> None:
        """Build the alarm message once the VL verdict (if any) resolves.
        在 VL 复判结论（如有）落地后构建告警消息。"""
        pending = result.extra.pop("pending_alert", None)
        if pending is None:
            return
        vl_task = pending["vl_task"]
        vl_result = await vl_task if vl_task is not None else None
        vl_rejected = vl_result is False
        if vl_result is False:
            logger.warning(
                "Alarm rejected by VL confirm, marked false positive: source={}",
                self.source_name,
            )
        elif vl_result is True:
            logger.info(
                "Alarm confirmed by VL confirm: source={}", self.source_name
            )
        frame = pending["frame"]
        annotated = pending["annotated"]
        confirmed = pending["confirmed"]
        post_result = pending["post_result"]
        timestamp = pending["timestamp"]
        labels = sorted({str(det.get("label", "")).lower() for det in confirmed})
        confidence = max(float(det.get("confidence", 0.0)) for det in confirmed)
        original_image_base64 = self._encode_thumbnail(frame)
        detected_image_base64 = self._encode_thumbnail(annotated)
        event = build_smoke_email_event(
            timestamp=timestamp,
            source_id=self.source_id,
            source_name=self.source_name,
            labels=labels,
            confidence=confidence,
            detection_count=len(confirmed),
            frame_id=post_result.frame_id,
            active_tracks=post_result.active_tracks,
            image_base64=detected_image_base64,
        )
        message = f"Detected {event['event_label']} on {self.source_name} ({len(confirmed)} confirmed detection(s))"
        result.messages.append({
            "timestamp": timestamp,
            "source_name": self.source_name,
            "source_id": self.source_id,
            "scene_id": "smoke",
            "level": "alert",
            "message": message,
            "image_base64": detected_image_base64,
            "original_image_base64": original_image_base64,
            "detected_image_base64": detected_image_base64,
            "false_positive": vl_rejected,
        })
        if not vl_rejected:
            result.extra["email_event"] = event
            result.extra["smoke_event"] = event
```

- [ ] **Step 6: `core/fire_door/processor.py` 同型改造**

import 区补 `import asyncio`。`__init__` 末尾（`self._roi_last_alarm_at = ...` 之后）加 `self._pending_vl_tasks: set[asyncio.Task] = set()`；`__init__` 之后加与 smoke 相同的 `stop()` 覆写。

`process_frame` 中，从 `alert_items = [item for item in classifications if item.get("alarm")]` 开始到方法末尾 `return result` 的整段（VL await 块 + 消息构建块）替换为：

```python
        alert_items = [item for item in classifications if item.get("alarm")]
        pending_alert = None
        if alert_items:
            vl_task = None
            if self._vl_confirm_enabled():
                vl_task = asyncio.create_task(
                    self._vl_confirm_alert(frame, annotated, alert_items, roi_pixel_points)
                )
                self._pending_vl_tasks.add(vl_task)
                vl_task.add_done_callback(self._pending_vl_tasks.discard)
            pending_alert = {
                "frame": frame,
                "annotated": annotated,
                "alert_items": alert_items,
                "classifications": classifications,
                "fire_rois": fire_rois,
                "timestamp": timestamp,
                "vl_task": vl_task,
            }
        result.extra["pending_alert"] = pending_alert
        return result

    async def finalize_result(self, result: AnalysisResult) -> None:
        """Build the alarm message once the VL verdict (if any) resolves.
        在 VL 复判结论（如有）落地后构建告警消息。"""
        pending = result.extra.pop("pending_alert", None)
        if pending is None:
            return
        vl_task = pending["vl_task"]
        vl_result = await vl_task if vl_task is not None else None
        vl_rejected = vl_result is False
        if vl_result is False:
            logger.warning(
                "Alarm rejected by VL confirm, marked false positive: source={}",
                self.source_name,
            )
        elif vl_result is True:
            logger.info(
                "Alarm confirmed by VL confirm: source={}", self.source_name
            )
        frame = pending["frame"]
        annotated = pending["annotated"]
        alert_items = pending["alert_items"]
        classifications = pending["classifications"]
        fire_rois = pending["fire_rois"]
        timestamp = pending["timestamp"]
        best = max(alert_items, key=lambda item: float(item.get("confidence") or 0.0))
        open_count = sum(1 for item in classifications if item.get("door_state") == "open")
        closed_count = sum(1 for item in classifications if item.get("door_state") == "closed")
        original_image_base64 = self._encode_thumbnail(frame)
        detected_image_base64 = self._encode_thumbnail(annotated)
        confidence = float(best.get("confidence") or 0.0)
        event = build_fire_door_email_event(
            timestamp=timestamp,
            source_id=self.source_id,
            source_name=self.source_name,
            source_rtsp_url=self.rtsp_url,
            source_route_path=self._stream_path(),
            source_remark=str(getattr(self, "source_remark", "") or ""),
            roi_id=str(best.get("roi_id") or ""),
            roi_tag=str(best.get("roi_tag") or ""),
            roi_index=int(best.get("roi_index") or 0),
            roi_count=len(fire_rois),
            door_state=str(best.get("door_state") or ""),
            door_state_label=str(best.get("stable_label") or ""),
            confidence=confidence,
            alarm_label=str(best.get("door_state") or best.get("raw_label") or ""),
            open_count=open_count,
            closed_count=closed_count,
            original_image_base64=original_image_base64,
            detected_image_base64=detected_image_base64,
        )
        result.messages.append(
            {
                "timestamp": timestamp,
                "source_name": self.source_name,
                "source_id": self.source_id,
                "scene_id": "fire_door",
                "level": "alert",
                "message": (
                    f"Fire door open on {self.source_name} "
                    f"ROI {event['roi_index']}/{event['roi_count']} "
                    f"({confidence:.2f})"
                ),
                "image_base64": detected_image_base64,
                "original_image_base64": original_image_base64,
                "detected_image_base64": detected_image_base64,
                "false_positive": vl_rejected,
            }
        )
        if not vl_rejected:
            result.extra["email_event"] = event
            result.extra["fire_door_event"] = event
```

- [ ] **Step 7: 更新既有测试（机械改动）**

消息构建移入 `finalize_result` 后，凡 `await processor.process_frame(...)` 之后断言 `result.messages`（非空）或 `result.extra["email_event"]` 的测试，都需在 `process_frame` 调用之后、断言之前补一行 `await processor.finalize_result(result)`（位于 `with patch(...)` / `try` 块内）。清单：

`tests/test_smoke.py`（8 处）：
1. `test_process_frame_generates_alert_message`（~56）
2. `test_vl_confirm_reject_keeps_message_marked_false_positive`（~167）
3. `test_vl_confirm_allows_alarm_when_model_returns_true`（~186）
4. `test_vl_confirm_fail_open_when_model_returns_none`（~205）
5. `test_vl_confirm_skipped_when_disabled`（~232）
6. `test_vl_annotated_full_image_sent_to_model`（~263：原为 `await processor.process_frame(...)` 无赋值 → 改为 `result = await ...` 再补 finalize）
7. `test_vl_sampling_params_from_smoke_settings_only`（~299）
8. `test_vl_reject_logs_warning_with_source`（~324：同 6，补赋值 + finalize，位于 try 内）

`tests/test_fire_door.py`（10 处）：
1. `test_open_label_is_case_insensitive_and_generates_alert`（~51）
2. `test_multiple_rois_batch_classification_alerts_when_any_roi_is_open`（~152）
3. `test_temporal_confirmation_requires_configured_frames`（~194：仅 `second` 需要）
4. `test_vl_confirm_reject_keeps_message_marked_false_positive`（~268）
5. `test_vl_confirm_allows_alarm_when_model_returns_true`（~288）
6. `test_vl_confirm_fail_open_when_model_returns_none`（~309）
7. `test_vl_confirm_skipped_when_disabled`（~326）
8. `test_vl_annotated_full_image_sent_to_model`（~354：补赋值 + finalize）
9. `test_vl_sampling_params_from_fire_door_settings_only`（~383）
10. `test_vl_reject_logs_warning_with_source`（~409：补赋值 + finalize，位于 try 内）

断言 `result.messages == []` 的测试（closed/low-confidence 等）不动。

- [ ] **Step 8: 跑三个测试文件确认通过**

```bash
uv run pytest tests/test_smoke.py tests/test_fire_door.py tests/test_processing.py -q
```

预期：全部 PASS。若出现 pytest-asyncio "pending task" 噪音（`_handle_result` 直调类测试留下的 dispatch 任务），在对应测试末尾补 `await asyncio.sleep(0)` 让任务落定。

- [ ] **Step 9: 静态检查 + 提交**

```bash
uv run ruff check core/base_processor.py core/smoke/processor.py core/fire_door/processor.py backend/processing/base.py tests/test_smoke.py tests/test_fire_door.py tests/test_processing.py
git add core/base_processor.py core/smoke/processor.py core/fire_door/processor.py backend/processing/base.py tests/test_smoke.py tests/test_fire_door.py tests/test_processing.py
git commit -m "feat(processing): decouple real-time push from VL confirm verdict"
```

---

### Task 4: Processor 代理接线 —— `_vl_confirm_alert` 走工厂 + 回退直连

**Files:**
- Modify: `core/smoke/processor.py`（`_vl_confirm_alert` 客户端构造 + import）
- Modify: `core/fire_door/processor.py`（同上）
- Test: `tests/test_smoke.py`、`tests/test_fire_door.py`、`tests/test_settings.py`（422 用例已在 Task 2 写好）

**Interfaces:**
- Consumes: Task 1 `build_vl_client`；Task 3 的 `pending_alert`/`finalize_result` 结构。
- Produces: manual 模式 URL 非法时 processor 回退直连 + WARNING；vl/test、vl-review 非法 manual → 422。

- [ ] **Step 1: 写失败测试（processor 回退）**

`tests/test_smoke.py` 末尾追加：

```python
async def test_smoke_vl_manual_proxy_misconfig_falls_back_to_direct():
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
            await processor.finalize_result(result)
    finally:
        logger.remove(sink_id)

    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert mock_cls.call_count == 1
    assert any(
        "VL manual proxy misconfigured" in r["message"] and "Cam1" in r["message"]
        for r in records
    )
```

`tests/test_fire_door.py` 末尾追加（对应版）：

```python
async def test_fire_door_vl_manual_proxy_misconfig_falls_back_to_direct():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    processor.app_settings["vl_confirm_proxy_mode"] = "manual"
    processor.app_settings["vl_confirm_proxy_url"] = ""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]]

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)
    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        with patch("core.vl_confirm.VLConfirmClient", return_value=mock_client) as mock_cls:
            result = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
            await processor.finalize_result(result)
    finally:
        logger.remove(sink_id)

    assert len(result.messages) == 1
    assert mock_cls.call_count == 1
    assert any(
        "VL manual proxy misconfigured" in r["message"] and "DoorCam" in r["message"]
        for r in records
    )
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_smoke.py::test_smoke_vl_manual_proxy_misconfig_falls_back_to_direct tests/test_fire_door.py::test_fire_door_vl_manual_proxy_misconfig_falls_back_to_direct tests/test_settings.py -k "misconfig or invalid_manual or proxy_overrides" -q
```

预期：processor 用例 FAIL（现在直接构造 `VLConfirmClient`，不会 ValueError → 无 WARNING、无回退）；`test_settings.py` 中 422/overrides 用例若 Task 2 已完成则 PASS（本步骤只需确认 processor 两条红）。

- [ ] **Step 3: smoke `_vl_confirm_alert` 改走工厂**

`core/smoke/processor.py`：import 行改为

```python
from core.vl_confirm import build_vl_client, build_vl_image_data_url
```

（移除 `VLConfirmClient`、`vl_sampling_kwargs`——本文件不再直接使用。）

`_vl_confirm_alert` 方法中，客户端构造部分（原 `client = VLConfirmClient(...)` 直到 `return await client.confirm(...)` 之前）替换为：

```python
        try:
            client = build_vl_client(self.app_settings, "smoke")
        except ValueError as exc:
            logger.warning(
                "VL manual proxy misconfigured ({}), falling back to direct: source={}",
                exc,
                self.source_name,
            )
            client = build_vl_client(
                self.app_settings,
                "smoke",
                overrides={"vl_confirm_proxy_mode": "none"},
            )
        return await client.confirm(image_data_url, prompt, response_key)
```

（`image_data_url`/`prompt`/`response_key` 的既有构建代码不动。）

- [ ] **Step 4: fire_door `_vl_confirm_alert` 同型改造**

`core/fire_door/processor.py`：import 行改为

```python
from core.vl_confirm import build_vl_client, build_vl_image_data_url
```

客户端构造替换为（scene_id 用 `"fire_door"`，其余同 Step 3）。

- [ ] **Step 5: 批量更新既有测试 patch 目标（14 处）**

`from core.vl_confirm import VLConfirmClient` 绑定在各 processor 模块命名空间；改走工厂后，`patch("core.smoke.processor.VLConfirmClient")` 不再拦截工厂内部的构造，必须 patch 工厂所在模块：

- `tests/test_smoke.py`：`core.smoke.processor.VLConfirmClient` → `core.vl_confirm.VLConfirmClient`（7 处）
- `tests/test_fire_door.py`：`core.fire_door.processor.VLConfirmClient` → `core.vl_confirm.VLConfirmClient`（7 处）

`tests/test_settings.py` 中 2 个 sampling 端点测试（`test_vl_test_returns_200...`/`test_vl_test_propagates_backend_error...` 附近，~300/~322）的 `backend.api.settings.VLConfirmClient` → `core.vl_confirm.VLConfirmClient`。

用 `sed` 批量替换后 `git diff` 复核：

```bash
sed -i 's/core\.smoke\.processor\.VLConfirmClient/core.vl_confirm.VLConfirmClient/g' tests/test_smoke.py
sed -i 's/core\.fire_door\.processor\.VLConfirmClient/core.vl_confirm.VLConfirmClient/g' tests/test_fire_door.py
sed -i 's/backend\.api\.settings\.VLConfirmClient/core.vl_confirm.VLConfirmClient/g' tests/test_settings.py
```

- [ ] **Step 6: 跑测试确认通过**

```bash
uv run pytest tests/test_smoke.py tests/test_fire_door.py tests/test_settings.py -q
```

预期：全部 PASS。

- [ ] **Step 7: 静态检查 + 提交**

```bash
uv run ruff check core/smoke/processor.py core/fire_door/processor.py tests/test_smoke.py tests/test_fire_door.py tests/test_settings.py
git add core/smoke/processor.py core/fire_door/processor.py tests/test_smoke.py tests/test_fire_door.py tests/test_settings.py
git commit -m "feat(vl): route processor auto-confirm through factory with direct fallback on bad proxy config"
```

---

### Task 5: 即时告警横幅 —— 不等 VL 复盘的顶部提示

**Files:**
- Modify: `backend/api/ws.py`（`import json`、`WSManager.send_notification`）
- Modify: `backend/processing/base.py`（`_dispatch_result` 增加 `_send_immediate_alert` 步骤）
- Modify: `core/smoke/processor.py`（`_was_alarmed`、`build_event_label` import、`pending_alert` 块加 `scene_id`/`alert_text` 边沿逻辑）
- Modify: `core/fire_door/processor.py`（同型）
- Modify: `frontend/src/stores/message.js`（`activeAlert`/`showActiveAlert`、`onmessage` 分支）
- Modify: `frontend/src/App.vue`（横幅 + 全局 WS 连接 + 样式）
- Test: `tests/test_ws.py`、`tests/test_processing.py`、`tests/test_smoke.py`、`tests/test_fire_door.py`、`frontend/src/stores/__tests__/message.test.js`

**Interfaces:**
- Consumes: Task 3 的 `pending_alert` / `_dispatch_result` / `finalize_result` 结构。
- Produces:
  - `WSManager.send_notification(payload: dict) -> None`（不持久化）
  - WS 事件 `{"type": "alert_notify", "timestamp", "source_id", "source_name", "scene_id", "message"}`
  - store 状态 `activeAlert: {seq, message, sourceName} | null` + `showActiveAlert(payload)`
  - `pending_alert["alert_text"]`（仅上升沿）+ `pending_alert["scene_id"]`

**行为契约（测试依据）：**
- 告警上升沿（无告警→有告警）才产生 `alert_text`；同一告警事件后续帧不重复。
- `alert_text` 与最终消息文本逐字一致（无图像、不依赖 VL）。
- `_dispatch_result` 中 `send_notification` 先于 `finalize_result`（不等 VL）、先于 `broadcast`（消息广播）。
- 横幅：新替换旧；5s（`ALERT_BANNER_DURATION_MS`）无新告警自动隐藏；新告警重置计时器。

- [ ] **Step 1: 写失败测试**

`tests/test_ws.py` 末尾追加：

```python
class TestSendNotification:
    async def test_send_notification_reaches_all_clients_without_persist(self):
        import json

        persist = AsyncMock(return_value="msg-id")
        mgr = WSManager(persist_message=persist)
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.send_notification(
            {"type": "alert_notify", "message": "Detected smoke on Cam1"}
        )

        assert ws1.send_text.await_count == 1
        assert ws2.send_text.await_count == 1
        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["type"] == "alert_notify"
        assert payload["message"] == "Detected smoke on Cam1"
        persist.assert_not_awaited()
```

`tests/test_processing.py` 的 `TestPushVsVlDecoupling` 类内追加：

```python
    async def test_immediate_alert_sent_before_vl_verdict(self):
        gate = asyncio.Event()
        ws = AsyncMock()

        class AlertingProcessor(BaseVideoProcessor):
            async def process_frame(self, frame, encoded, shape, roi_pixel_points):
                result = AnalysisResult(annotated_frame=frame)

                async def verdict():
                    await gate.wait()
                    return True

                result.extra["pending_alert"] = {
                    "vl_task": asyncio.create_task(verdict()),
                    "alert_text": "Detected smoke on cam (1 confirmed detection(s))",
                    "scene_id": "smoke",
                    "timestamp": "2026-09-02T00:00:00+00:00",
                }
                return result

            async def finalize_result(self, result):
                task = result.extra.pop("pending_alert")["vl_task"]
                await task

        proc = AlertingProcessor(
            source_id="s1",
            source_name="cam",
            rtsp_url="rtsp://localhost:8554/cam1",
            rois=[],
            vengine_client=MagicMock(),
            ws_manager=ws,
            app_settings={},
        )
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        await proc._process_frame_item(frame, b"x")

        ws.send_notification.assert_awaited_once()
        payload = ws.send_notification.call_args[0][0]
        assert payload["type"] == "alert_notify"
        assert payload["source_name"] == "cam"
        assert payload["scene_id"] == "smoke"
        assert payload["message"] == "Detected smoke on cam (1 confirmed detection(s))"
        assert ws.broadcast.await_count == 0  # 消息广播仍等 VL 结论

        gate.set()
        if proc._dispatch_tasks:
            await asyncio.wait_for(asyncio.gather(*proc._dispatch_tasks), 5.0)
```

`tests/test_smoke.py` 末尾追加：

```python
async def test_alert_text_only_on_rising_edge():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
        first = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
        second = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
        await processor.finalize_result(first)
        await processor.finalize_result(second)

    first_pending = first.extra["pending_alert"]
    second_pending = second.extra["pending_alert"]
    assert first_pending["alert_text"] == "Detected 烟雾 on Cam1 (1 confirmed detection(s))"
    assert first_pending["scene_id"] == "smoke"
    assert second_pending is not None and "alert_text" not in second_pending
    assert first.messages[0]["message"] == first_pending["alert_text"]
```

`tests/test_fire_door.py` 末尾追加：

```python
async def test_alert_text_only_on_rising_edge():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi_points = [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]]

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.fire_door.processor.VLConfirmClient", return_value=mock_client):
        first = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
        second = await processor.process_frame(frame, b"frame", frame.shape, roi_points)
        await processor.finalize_result(first)
        await processor.finalize_result(second)

    first_pending = first.extra["pending_alert"]
    second_pending = second.extra["pending_alert"]
    assert first_pending["alert_text"] == "Fire door open on DoorCam ROI 1/1 (0.91)"
    assert first_pending["scene_id"] == "fire_door"
    assert second_pending is not None and "alert_text" not in second_pending
    assert first.messages[0]["message"] == first_pending["alert_text"]
```

`frontend/src/stores/__tests__/message.test.js` 末尾追加：

```js
describe('message store — immediate alert banner', () => {
  it('shows the alert and auto hides after the duration', () => {
    vi.useFakeTimers()
    const store = useMessageStore()
    store.showActiveAlert({ message: 'Detected smoke on Cam1 (1 confirmed detection(s))', source_name: 'Cam1' })
    expect(store.activeAlert.message).toBe('Detected smoke on Cam1 (1 confirmed detection(s))')
    vi.advanceTimersByTime(5000)
    expect(store.activeAlert).toBeNull()
    vi.useRealTimers()
  })

  it('a new alert replaces the previous one and resets the hide timer', () => {
    vi.useFakeTimers()
    const store = useMessageStore()
    store.showActiveAlert({ message: 'first', source_name: 'A' })
    vi.advanceTimersByTime(3000)
    store.showActiveAlert({ message: 'second', source_name: 'B' })
    expect(store.activeAlert.message).toBe('second')
    vi.advanceTimersByTime(4000)
    expect(store.activeAlert.message).toBe('second')
    vi.advanceTimersByTime(1000)
    expect(store.activeAlert).toBeNull()
    vi.useRealTimers()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_ws.py::TestSendNotification tests/test_processing.py::TestPushVsVlDecoupling::test_immediate_alert_sent_before_vl_verdict tests/test_smoke.py::test_alert_text_only_on_rising_edge tests/test_fire_door.py::test_alert_text_only_on_rising_edge -q
cd frontend && npm run test -- --run message.test.js && cd ..
```

预期：后端 4 条 FAIL（`send_notification` 不存在 / `alert_text` 缺失）；前端 2 条 FAIL（`showActiveAlert` 未定义）。

- [ ] **Step 3: `backend/api/ws.py` 加 `send_notification`**

顶部 import 区补 `import json`。`WSManager` 类内 `broadcast` 方法之后加：

```python
    async def send_notification(self, payload: dict[str, Any]) -> None:
        """Send a raw notification to all clients without persisting it.
        向所有客户端发送轻量通知（不持久化，不进消息页）。"""
        text = json.dumps(payload, ensure_ascii=False)
        dead: list[WebSocket] = []
        async with self._lock:
            connections = set(self._connections)
        for ws in connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
```

- [ ] **Step 4: `backend/processing/base.py` 在 `_dispatch_result` 前置即时告警**

`_dispatch_result` 的 try 块首行（`await self.finalize_result(result)` 之前）插入：

```python
            await self._send_immediate_alert(result)
```

并在 `_dispatch_result` 之后新增方法：

```python
    async def _send_immediate_alert(self, result: AnalysisResult) -> None:
        """Send the immediate top-banner alert (no VL wait, no DB persist).
        发送即时顶部告警横幅（不等 VL 结论、不入库）。"""
        pending = result.extra.get("pending_alert")
        if not isinstance(pending, dict):
            return
        text = str(pending.get("alert_text") or "").strip()
        if not text or self.ws_manager is None:
            return
        await self.ws_manager.send_notification(
            {
                "type": "alert_notify",
                "timestamp": pending.get("timestamp"),
                "source_id": self.source_id,
                "source_name": self.source_name,
                "scene_id": str(pending.get("scene_id") or ""),
                "message": text,
            }
        )
```

- [ ] **Step 5: `core/smoke/processor.py` 边沿告警文本**

import 行改为：

```python
from core.smoke.email import build_event_label, build_smoke_email_event
```

`__init__` 中 `self._pending_vl_tasks` 之后加：

```python
        self._was_alarmed = False
```

`process_frame` 中 Task 3 建立的 `pending_alert` 块（`pending_alert = None` / `if post_result.has_alarm and confirmed:` …）替换为：

```python
        pending_alert = None
        is_alarmed = bool(post_result.has_alarm and confirmed)
        rising_edge = is_alarmed and not self._was_alarmed
        self._was_alarmed = is_alarmed
        if is_alarmed:
            vl_task = None
            if self._vl_confirm_enabled():
                vl_task = asyncio.create_task(
                    self._vl_confirm_alert(frame, annotated, primary_roi)
                )
                self._pending_vl_tasks.add(vl_task)
                vl_task.add_done_callback(self._pending_vl_tasks.discard)
            labels = sorted({str(det.get("label", "")).lower() for det in confirmed})
            pending_alert = {
                "frame": frame,
                "annotated": annotated,
                "confirmed": confirmed,
                "post_result": post_result,
                "timestamp": timestamp,
                "vl_task": vl_task,
                "scene_id": "smoke",
            }
            if rising_edge:
                pending_alert["alert_text"] = (
                    f"Detected {build_event_label(labels)} on {self.source_name} "
                    f"({len(confirmed)} confirmed detection(s))"
                )
        result.extra["pending_alert"] = pending_alert
        return result
```

- [ ] **Step 6: `core/fire_door/processor.py` 同型改造**

`__init__` 中 `self._pending_vl_tasks` 之后加 `self._was_alarmed = False`。

`process_frame` 中 Task 3 建立的 `pending_alert` 块替换为：

```python
        alert_items = [item for item in classifications if item.get("alarm")]
        is_alarmed = bool(alert_items)
        rising_edge = is_alarmed and not self._was_alarmed
        self._was_alarmed = is_alarmed
        pending_alert = None
        if is_alarmed:
            vl_task = None
            if self._vl_confirm_enabled():
                vl_task = asyncio.create_task(
                    self._vl_confirm_alert(frame, annotated, alert_items, roi_pixel_points)
                )
                self._pending_vl_tasks.add(vl_task)
                vl_task.add_done_callback(self._pending_vl_tasks.discard)
            best = max(alert_items, key=lambda item: float(item.get("confidence") or 0.0))
            pending_alert = {
                "frame": frame,
                "annotated": annotated,
                "alert_items": alert_items,
                "classifications": classifications,
                "fire_rois": fire_rois,
                "timestamp": timestamp,
                "vl_task": vl_task,
                "scene_id": "fire_door",
            }
            if rising_edge:
                pending_alert["alert_text"] = (
                    f"Fire door open on {self.source_name} "
                    f"ROI {int(best.get('roi_index') or 0)}/{len(fire_rois)} "
                    f"({float(best.get('confidence') or 0.0):.2f})"
                )
        result.extra["pending_alert"] = pending_alert
        return result
```

- [ ] **Step 7: 前端 store —— `activeAlert` + `onmessage` 分支**

`frontend/src/stores/message.js`：

`pendingCount`/`selectedIds` 声明附近加状态：

```js
  const activeAlert = ref(null)
  const ALERT_BANNER_DURATION_MS = 5000
  let _alertHideTimer = null
  let _alertSeq = 0

  function showActiveAlert(payload) {
    const seq = ++_alertSeq
    activeAlert.value = {
      seq,
      message: String((payload && payload.message) || ''),
      sourceName: String((payload && payload.source_name) || ''),
    }
    if (_alertHideTimer) clearTimeout(_alertHideTimer)
    _alertHideTimer = setTimeout(() => {
      if (_alertSeq === seq) activeAlert.value = null
    }, ALERT_BANNER_DURATION_MS)
  }
```

`onmessage` 的 `if (msg === 'pong') return` 之后加：

```js
        if (msg.type === 'alert_notify') {
          showActiveAlert(msg)
          return
        }
```

return 对象中 `wsConnected,` 之后加 `activeAlert,` 与 `showActiveAlert,`。

- [ ] **Step 8: 前端 App.vue —— 横幅 + 全局 WS**

`frontend/src/App.vue`：

`<el-main class="app-main">` 内、`<router-view />` 之前插入：

```html
        <div v-if="messageStore.activeAlert" class="alert-banner" role="alert">
          <el-icon class="alert-banner__icon"><Bell /></el-icon>
          <span class="alert-banner__text">{{ messageStore.activeAlert.message }}</span>
        </div>
```

script 区：补 import（若未引入）`import { useMessageStore } from './stores/message.js'` 与 vue 的 `watch`；实例化 `const messageStore = useMessageStore()`；在既有 store/计算属性初始化之后加：

```js
watch(
  () => authStore.token,
  (token) => {
    if (token) messageStore.connectWS()
    else messageStore.disconnectWS()
  },
  { immediate: true },
)
```

（`Bell` 图标 App.vue 已 import；`authStore` 已存在。若 `watch` 尚未从 vue import，补进既有 import。）

样式（并入 App.vue 既有 `<style>` 块，scoped 与否随该块现状）：

```css
.alert-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 12px 0;
  padding: 8px 12px;
  background: rgba(245, 108, 0, 0.12);
  border: 1px solid rgba(245, 108, 0, 0.55);
  border-left: 3px solid #f56c00;
  border-radius: 4px;
  color: #ffb26b;
  font-size: 13px;
}
```

- [ ] **Step 9: 跑测试确认通过**

```bash
uv run pytest tests/test_ws.py tests/test_processing.py tests/test_smoke.py tests/test_fire_door.py -q
cd frontend && npm run test && npm run build && cd ..
```

预期：全部 PASS。

- [ ] **Step 10: 静态检查 + 提交**

```bash
uv run ruff check backend/api/ws.py backend/processing/base.py core/smoke/processor.py core/fire_door/processor.py tests/test_ws.py tests/test_processing.py tests/test_smoke.py tests/test_fire_door.py
git add backend/api/ws.py backend/processing/base.py core/smoke/processor.py core/fire_door/processor.py frontend/src/stores/message.js frontend/src/App.vue frontend/src/stores/__tests__/message.test.js tests/test_ws.py tests/test_processing.py tests/test_smoke.py tests/test_fire_door.py
git commit -m "feat(alerts): immediate top alert banner without waiting for VL verdict"
```

---

### Task 6: 前端 —— 代理模式 UI + i18n

**Files:**
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.js`、`frontend/src/i18n/locales/en-US.js`

**Interfaces:**
- Consumes: 设置键 `vl_confirm_proxy_mode` / `vl_confirm_proxy_url`（Task 2 已可持久化）。

- [ ] **Step 1: `VL_CONFIRM_GLOBAL_KEYS` 加两键**

`frontend/src/views/Settings.vue`（~1367-1372）：

```js
const VL_CONFIRM_GLOBAL_KEYS = [
  'vl_confirm_base_url',
  'vl_confirm_api_key',
  'vl_confirm_model',
  'vl_confirm_timeout',
  'vl_confirm_proxy_mode',
  'vl_confirm_proxy_url'
]
```

- [ ] **Step 2: 模板加两个控件**

`vl_confirm_timeout` 的 `el-form-item`（~850-852）之后插入：

```html
<el-form-item :label="t('settings.vlConfirmProxyMode')">
  <el-select v-model="form.vl_confirm_proxy_mode">
    <el-option value="none" :label="t('settings.vlConfirmProxyModeNone')" />
    <el-option value="manual" :label="t('settings.vlConfirmProxyModeManual')" />
    <el-option value="system" :label="t('settings.vlConfirmProxyModeSystem')" />
  </el-select>
</el-form-item>
<el-form-item v-if="form.vl_confirm_proxy_mode === 'manual'" :label="t('settings.vlConfirmProxyUrl')">
  <el-input v-model="form.vl_confirm_proxy_url" :placeholder="t('settings.vlConfirmProxyUrlPlaceholder')" />
</el-form-item>
```

- [ ] **Step 3: 表单默认值**

`form` 初始值（~1685，`vl_confirm_timeout: '60'` 附近）加：

```js
vl_confirm_proxy_mode: 'none',
vl_confirm_proxy_url: '',
```

- [ ] **Step 4: `testVlConfig` 载荷加两键**

`testVlConfig` 的 payload（~2280-2290，`vl_confirm_disable_thinking` 之后）加：

```js
vl_confirm_proxy_mode: form.vl_confirm_proxy_mode || 'none',
vl_confirm_proxy_url: form.vl_confirm_proxy_url || undefined,
```

- [ ] **Step 5: i18n**

`zh-CN.js`（`vlConfirmTimeout` 行 640 之后）：

```js
vlConfirmProxyMode: 'VL 代理模式',
vlConfirmProxyModeNone: '不走代理',
vlConfirmProxyModeManual: '手动设置',
vlConfirmProxyModeSystem: '走系统代理',
vlConfirmProxyUrl: '代理地址',
vlConfirmProxyUrlPlaceholder: '例如 http://10.0.0.1:3128',
```

`en-US.js`（同行位）：

```js
vlConfirmProxyMode: 'VL proxy mode',
vlConfirmProxyModeNone: 'No proxy',
vlConfirmProxyModeManual: 'Manual',
vlConfirmProxyModeSystem: 'System proxy',
vlConfirmProxyUrl: 'Proxy URL',
vlConfirmProxyUrlPlaceholder: 'e.g. http://10.0.0.1:3128',
```

- [ ] **Step 6: 前端测试 + 构建 + 提交**

```bash
cd frontend && npm run test && npm run build && cd ..
git add frontend/src/views/Settings.vue frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat(settings-ui): add VL proxy mode/url fields"
```

---

### Task 7: 全量验证 + 推送

- [ ] **Step 1: 后端全量测试**

```bash
uv run pytest -q
```

预期：除已知环境性失败（`test_main.py::...::test_direct_frontend_route_serves_index_html`）外全 PASS。

- [ ] **Step 2: Ruff（对照基线 32）**

```bash
uv run ruff check core/ backend/ tests/ 2>&1 | tail -3
```

预期：总错误数 ≤ 32，且改动文件 0 错误。

- [ ] **Step 3: 前端测试 + 构建**

```bash
cd frontend && npm run test && npm run build && cd ..
```

- [ ] **Step 4: 推送（更新 PR #18）**

```bash
git push origin feat/logging-coverage
```

（若遇代理 502，等待数秒重试。）

- [ ] **Step 5: 汇报**

向用户报告：全量结果、PR #18 链接（https://github.com/doubletry/V-Sentinel-Smoke/pull/18）、升级行为变化说明（默认代理模式 = 不走代理；依赖环境变量代理的部署需手动切"走系统代理"）。
