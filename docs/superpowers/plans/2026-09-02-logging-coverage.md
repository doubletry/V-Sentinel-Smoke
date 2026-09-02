# Logging Coverage (VL 复判全链路 + 关键缺日志) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 VL 大模型复判三条路径（告警自动确认、手动复判、连接测试）在成功与失败时都在默认日志级别记录 VL 响应/错误详情，并补齐审计发现的关键缺日志点（静默吞异常、gRPC 非 OK、API 5xx 零日志、安全事件、WHEP 失败、审计中间件无保护、RTSP URL 泄密）。

**Architecture:** 纯增量日志改造。核心逻辑集中在 `core/vl_confirm.py` 的 `VLConfirmClient.complete()`（成功记原始响应、失败记完整异常），各调用方（2 个 processor、2 个 API 端点）记录业务结论；其余任务按子系统逐一补齐 WARNING/ERROR/INFO 日志，不改变业务行为（唯一例外：Task 4 的三处异常保护，让失败可见且不杀流水线）。

**Tech Stack:** Python 3.12 / FastAPI / loguru（唯一日志库，stderr sink，级别 INFO，见 `backend/main.py:41-42`）/ pytest + pytest-asyncio（`asyncio_mode = auto`）/ ruff。

## Global Constraints

- 日志库只用 loguru：`from loguru import logger`。**严禁使用 `exc_info=True`**（标准库 logging 参数，loguru 静默忽略，是本 bug 的根源）；需要异常栈时用 `logger.opt(exception=True).warning(...)`（必须在 `except` 块内调用）。
- 默认 sink 级别是 INFO：所有"必须可见"的新日志必须是 INFO 及以上；DEBUG 不会被看到。
- 日志消息用英文，惰性格式化：`logger.info("... {}", x)`；沿用现有 `Component: action` / `key=value` 风格。
- 严禁记录密钥值（api_key、password、token）；记录 settings 变更时只记**键名**；含凭据的 RTSP URL 必须经 `redact_url()` 脱敏后再记录（Task 8 提供）。
- 除 Task 4 的三处异常保护外，不得改变任何业务行为（返回值、HTTP 状态码、状态机均不变）。
- 验证命令：`uv run pytest <file> -q`（基线：441 个测试，1 个**既有失败** `tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`，与本计划无关）；`uv run ruff check <改动文件>`（仓库有 35 个**既有** ruff 错误，改动文件不得**新增**错误；注意 `backend/api/whep_proxy.py:178` 既有 F841 会被 Task 7 的改动顺带消除，属预期）。
- 分支：`feat/logging-coverage`（已创建，spec 提交已在分支上）。提交信息用 Conventional Commits（`feat(logging): ...`）。

---

### Task 1: VLConfirmClient 全链路日志（核心修复）

**Files:**
- Modify: `core/vl_confirm.py`（imports、`__init__` 214-236、`complete` 238-260、`confirm` 262-279）
- Test: `tests/test_vl_confirm.py`

**Interfaces:**
- Consumes: 无（最底层）
- Produces: `VLConfirmClient._base_url: str` 实例属性；`complete()` 成功时记两条 INFO（`VL request ok: model={} latency_ms={}`、`VL raw response: {}`），失败时记 WARNING（`VL request failed: model={} base_url={} latency_ms={} error={}`，含异常栈）后照旧 raise；`confirm()` 成功记 INFO（`VL confirm verdict={}`），失败记 WARNING（`VL confirm failed, failing open: model={}`）后返回 None。

- [ ] **Step 1: 写失败测试**

在 `tests/test_vl_confirm.py` 顶部 import 区（第 8 行 `import pytest` 后）加：

```python
from loguru import logger
```

在文件末尾追加 3 个测试：

```python
async def test_complete_success_logs_raw_response():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"smoke": true}'
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(return_value=mock_response)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        raw = await client.complete("data:image/jpeg;base64,abc", "Ping")
    finally:
        logger.remove(sink_id)

    assert raw == '{"smoke": true}'
    messages = [r["message"] for r in records]
    assert any("VL request ok" in m and "/models/Mage-VL" in m for m in messages)
    assert any("VL raw response" in m and '{"smoke": true}' in m for m in messages)


async def test_complete_failure_logs_exception_details():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("conn-refused-detail")
    )

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        with pytest.raises(RuntimeError, match="conn-refused-detail"):
            await client.complete("data:image/jpeg;base64,abc", "Ping")
    finally:
        logger.remove(sink_id)

    failures = [r for r in records if "VL request failed" in r["message"]]
    assert failures, "expected a 'VL request failed' warning"
    assert "conn-refused-detail" in failures[0]["message"]
    # 回归：loguru 忽略 stdlib 风格 exc_info=True；record 必须携带异常（完整栈），
    # 否则 VL 服务端返回的错误体在日志中不可见。
    assert failures[0]["exception"] is not None


async def test_confirm_failure_logs_failing_open():
    client = VLConfirmClient("http://localhost:30000/v1", "EMPTY", "/models/Mage-VL")
    client._client = AsyncMock()
    client._client.chat.completions.create = AsyncMock(side_effect=Exception("boom-vl"))

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        result = await client.confirm("data:image/jpeg;base64,abc", "Verify", "open")
    finally:
        logger.remove(sink_id)

    assert result is None
    assert any(
        "failing open" in r["message"] and "/models/Mage-VL" in r["message"]
        for r in records
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_vl_confirm.py -q -k "logs_raw_response or exception_details or failing_open"`
Expected: 3 FAILED（`VL request failed` / `VL raw response` / `failing open` 均未出现，或 `AttributeError`/断言失败）

- [ ] **Step 3: 实现**

`core/vl_confirm.py` 改动：

(a) imports 区（第 10-14 行）在 `import re` 后加一行：

```python
import time
```

(b) `__init__`（214-236 行）在 `self._model = model` 前加一行：

```python
        self._base_url = base_url
```

(c) `complete()` 的 `response = await self._client.chat.completions.create(**create_kwargs)` 及之后两行（259-260 行）替换为：

```python
        started = time.monotonic()
        try:
            response = await self._client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.opt(exception=True).warning(
                "VL request failed: model={} base_url={} latency_ms={} error={}",
                self._model,
                self._base_url,
                latency_ms,
                exc,
            )
            raise
        raw = response.choices[0].message.content or ""
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info("VL request ok: model={} latency_ms={}", self._model, latency_ms)
        logger.info("VL raw response: {}", raw)
        return raw
```

(d) `confirm()` 的 try/except 体（273-279 行）替换为：

```python
        try:
            raw = await self.complete(image_data_url, prompt)
            verdict = parse_vl_response(raw, response_key)
            logger.info("VL confirm verdict={}", verdict)
            return verdict
        except Exception:
            logger.warning("VL confirm failed, failing open: model={}", self._model)
            return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_vl_confirm.py -q`
Expected: 全部 PASS（37 既有 + 3 新增 = 40 passed）

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check core/vl_confirm.py tests/test_vl_confirm.py
git add core/vl_confirm.py tests/test_vl_confirm.py
git commit -m "feat(logging): log VL raw response and full failure details in VLConfirmClient"
```

---

### Task 2: 两个 processor 的 VL 结论日志

**Files:**
- Modify: `core/smoke/processor.py`（imports；117-123 行 VL 分支）
- Modify: `core/fire_door/processor.py`（imports；172-176 行 VL 分支）
- Test: `tests/test_smoke.py`、`tests/test_fire_door.py`

**Interfaces:**
- Consumes: Task 1 的 `VLConfirmClient.confirm()` 返回值语义（True/False/None）不变
- Produces: 拒绝时 WARNING `Alarm rejected by VL confirm, marked false positive: source={}`；确认时 INFO `Alarm confirmed by VL confirm: source={}`（source 为 `self.source_name`）

- [ ] **Step 1: 写失败测试**

`tests/test_smoke.py` 顶部加 `from loguru import logger`，文件末尾追加：

```python
async def test_vl_reject_logs_warning_with_source():
    vengine = AsyncMock()
    vengine.detect.return_value = [
        {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}
    ]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
            await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
    finally:
        logger.remove(sink_id)

    assert any(
        "Alarm rejected by VL confirm" in r["message"]
        and "Cam1" in r["message"]
        and r["level"].name == "WARNING"
        for r in records
    )
```

`tests/test_fire_door.py` 顶部加 `from loguru import logger`，文件末尾追加：

```python
async def test_vl_reject_logs_warning_with_source():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _vl_processor(vengine)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=False)

    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
    try:
        with patch("core.fire_door.processor.VLConfirmClient", return_value=mock_client):
            await processor.process_frame(
                frame, b"frame", frame.shape,
                [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
            )
    finally:
        logger.remove(sink_id)

    assert any(
        "Alarm rejected by VL confirm" in r["message"]
        and "DoorCam" in r["message"]
        and r["level"].name == "WARNING"
        for r in records
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_smoke.py::test_vl_reject_logs_warning_with_source tests/test_fire_door.py::test_vl_reject_logs_warning_with_source -q`
Expected: 2 FAILED（断言无匹配日志）

- [ ] **Step 3: 实现**

两个文件顶部 import 区各加一行（`import time` 附近）：`from loguru import logger`

`core/smoke/processor.py` 117-123 行替换为：

```python
        vl_rejected = False
        if post_result.has_alarm and confirmed:
            if self._vl_confirm_enabled():
                vl_result = await self._vl_confirm_alert(frame, annotated, primary_roi)
                if vl_result is False:
                    vl_rejected = True
                    logger.warning(
                        "Alarm rejected by VL confirm, marked false positive: source={}",
                        self.source_name,
                    )
                elif vl_result is True:
                    logger.info("Alarm confirmed by VL confirm: source={}", self.source_name)
                # True or None (fail-open) → keep alerts
```

`core/fire_door/processor.py` 172-176 行替换为：

```python
        alert_items = [item for item in classifications if item.get("alarm")]
        vl_rejected = False
        if alert_items and self._vl_confirm_enabled():
            vl_result = await self._vl_confirm_alert(frame, annotated, alert_items, roi_pixel_points)
            if vl_result is False:
                vl_rejected = True
                logger.warning(
                    "Alarm rejected by VL confirm, marked false positive: source={}",
                    self.source_name,
                )
            elif vl_result is True:
                logger.info("Alarm confirmed by VL confirm: source={}", self.source_name)
            # True or None (fail-open) → keep alerts
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_smoke.py tests/test_fire_door.py -q`
Expected: 全部 PASS

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check core/smoke/processor.py core/fire_door/processor.py tests/test_smoke.py tests/test_fire_door.py
git add core/smoke/processor.py core/fire_door/processor.py tests/test_smoke.py tests/test_fire_door.py
git commit -m "feat(logging): log VL confirm verdict and alarm rejection in processors"
```

---

### Task 3: VL 相关 API 端点日志（手动复判 + 连接测试）

**Files:**
- Modify: `backend/api/messages.py`（imports；`review_message_with_vl` 182-195 行）
- Modify: `backend/api/settings.py`（`test_vl_settings` 271-281 行；该文件已有 loguru import）
- Test: `tests/test_messages.py`、`tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1 的 `complete()`（成功/失败日志已由客户端记录，本任务补端点级业务上下文）
- Produces: INFO `VL re-review ok: message_id={} verdict={} latency_ms={}` / WARNING `VL re-review failed: message_id={} model={}`（带异常栈）；INFO `VL connection test ok: scene={} model={} latency_ms={}` / WARNING `VL connection test failed: scene={} model={} base_url={}`（带异常栈）。HTTP 状态码与响应体不变。

- [ ] **Step 1: 写失败测试**

`tests/test_messages.py` 顶部 import 区加 `from loguru import logger`。在 `TestVLReview` 类内（`test_vl_review_upstream_error_502` 之后）追加：

```python
    async def test_vl_review_failure_logs_warning(self, async_client: AsyncClient, init_db):
        source = await self._create_source()
        message_id = await self._save_message_with_image(source.id)
        await update_settings({"smoke_vl_confirm_enabled": "true"})

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with patch(
                "core.vl_confirm.VLConfirmClient.complete",
                new=AsyncMock(side_effect=Exception("conn refused")),
            ):
                resp = await async_client.post(f"/api/messages/{message_id}/vl-review")
        finally:
            logger.remove(sink_id)

        assert resp.status_code == 502
        failures = [r for r in records if "VL re-review failed" in r["message"]]
        assert failures and message_id in failures[0]["message"]
        # 注意：测试 patch 掉了 complete()，客户端级 "VL request failed" 不会触发；
        # 上游错误 "conn refused" 在 record["exception"]（异常栈）里，不在渲染消息里。
        assert failures[0]["exception"] is not None
```

`tests/test_settings.py` 顶部 import 区加 `from loguru import logger`。在 `test_vl_test_endpoint_upstream_error_502` 之后追加（与该测试同级的 class 内）：

```python
    async def test_vl_test_failure_logs_warning(self, async_client: AsyncClient):
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with patch(
                "core.vl_confirm.VLConfirmClient.complete",
                new=AsyncMock(side_effect=Exception("vl backend down")),
            ):
                resp = await async_client.post(
                    "/api/settings/vl/test",
                    json={
                        "scene_id": "smoke",
                        "vl_confirm_base_url": "http://vl.example.com/v1",
                        "vl_confirm_model": "/models/test-vl",
                    },
                )
        finally:
            logger.remove(sink_id)

        assert resp.status_code == 502
        failures = [r for r in records if "VL connection test failed" in r["message"]]
        assert failures
        assert "smoke" in failures[0]["message"]
        assert "/models/test-vl" in failures[0]["message"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_messages.py -q -k "vl_review_failure_logs_warning" tests/test_settings.py -q -k "vl_test_failure_logs_warning"`
Expected: 2 FAILED（"VL re-review failed" / "VL connection test failed" 未出现）

- [ ] **Step 3: 实现**

`backend/api/messages.py` 顶部 import 区加 `from loguru import logger`。`review_message_with_vl` 的 182-187 行替换为：

```python
    started = time.monotonic()
    try:
        raw = await client.complete(image_data_url, prompt)
    except Exception as exc:
        logger.opt(exception=True).warning(
            "VL re-review failed: message_id={} model={}", message_id, model
        )
        raise HTTPException(status_code=502, detail=f"VL request failed: {exc}")
```

同函数 187-195 行的 return 前插入一行（`result = ...` 之后）：

```python
    logger.info(
        "VL re-review ok: message_id={} verdict={} latency_ms={}",
        message_id, result, latency_ms,
    )
```

`backend/api/settings.py` `test_vl_settings` 的 271-281 行替换为：

```python
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

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_messages.py tests/test_settings.py -q`
Expected: 全部 PASS

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check backend/api/messages.py backend/api/settings.py tests/test_messages.py tests/test_settings.py
git add backend/api/messages.py backend/api/settings.py tests/test_messages.py tests/test_settings.py
git commit -m "feat(logging): log VL re-review and connection test outcomes in API layer"
```

---

### Task 4: 帧流水线静默吞异常保护（base_processor + ws）

**Files:**
- Modify: `core/base_processor.py:810-822`（`_wait_for_processing_slot`）、`824-841`（`_process_frame_item`）
- Modify: `backend/api/ws.py:98-108`（`WSManager.broadcast` 持久化段）
- Test: `tests/test_ws.py`、`tests/test_processing.py`

**Interfaces:**
- Consumes: 无
- Produces: WARNING `Frame task failed: source={}`（帧任务异常，带栈）；ERROR `Failed to handle frame result: source={}`（带栈）；ERROR `Failed to persist analysis message: source={}`（带栈，广播不中断）。行为变化仅限这三处异常不再上抛/静默丢失。

- [ ] **Step 1: 写失败测试**

`tests/test_ws.py` 顶部加 `from loguru import logger`，文件末尾追加：

```python
    async def test_broadcast_persist_failure_is_logged_not_raised(self):
        from backend.models.schemas import AnalysisMessage

        async def failing_persist(message):
            raise RuntimeError("db down")

        mgr = WSManager(persist_message=failing_persist)
        ws = AsyncMock()
        await mgr.connect(ws)

        msg = AnalysisMessage(
            timestamp="t",
            source_name="c",
            source_id="s-1",
            level="info",
            message="m",
        )
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="ERROR")
        try:
            await mgr.broadcast(msg)  # 不得抛出
        finally:
            logger.remove(sink_id)

        ws.send_text.assert_awaited_once()  # 广播不受持久化失败影响
        assert any(
            "Failed to persist analysis message" in r["message"] and "s-1" in r["message"]
            for r in records
        )
```

`tests/test_processing.py` 顶部加 `from loguru import logger`，`TestBaseVideoProcessor` 类内追加：

```python
    async def test_process_frame_item_logs_handle_result_failure(self):
        proc = self._make_processor()
        proc.push_result_stream = False
        proc._handle_result = AsyncMock(side_effect=RuntimeError("ws down"))

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="ERROR")
        try:
            frame = np.zeros((10, 10, 3), dtype=np.uint8)
            await proc._process_frame_item(frame, b"encoded")  # 不得抛出
        finally:
            logger.remove(sink_id)

        assert any(
            "Failed to handle frame result" in r["message"] and "s1" in r["message"]
            for r in records
        )

    async def test_wait_for_processing_slot_logs_failed_task(self):
        proc = self._make_processor()
        proc._max_inflight_frames = 1

        async def boom():
            raise RuntimeError("inference boom")

        task = asyncio.create_task(boom())
        await asyncio.sleep(0)  # 让任务失败
        proc._processing_tasks.add(task)

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            await proc._wait_for_processing_slot()
        finally:
            logger.remove(sink_id)

        assert any("Frame task failed" in r["message"] and "s1" in r["message"] for r in records)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_ws.py -q -k "persist_failure" tests/test_processing.py -q -k "handle_result_failure or logs_failed_task"`
Expected: 3 FAILED

- [ ] **Step 3: 实现**

`core/base_processor.py` `_wait_for_processing_slot` 818-822 行替换为：

```python
        for task in done:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.opt(exception=True).warning(
                    "Frame task failed: source={}", self.source_id
                )
```

`core/base_processor.py` `_process_frame_item` 841 行 `await self._handle_result(frame, result)` 替换为：

```python
        try:
            await self._handle_result(frame, result)
        except Exception:
            logger.opt(exception=True).error(
                "Failed to handle frame result: source={}", self.source_id
            )
```

`backend/api/ws.py` `broadcast` 103-108 行替换为：

```python
        # Persist to DB / 持久化到数据库
        message_id: str | None = None
        if self._persist_message is not None:
            try:
                message_id = await self._persist_message(message)
            except Exception:
                logger.opt(exception=True).error(
                    "Failed to persist analysis message: source={}", message.source_id
                )
        if message_id:
            message.id = message_id
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_ws.py tests/test_processing.py -q`
Expected: 全部 PASS

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check core/base_processor.py backend/api/ws.py tests/test_ws.py tests/test_processing.py
git add core/base_processor.py backend/api/ws.py tests/test_ws.py tests/test_processing.py
git commit -m "feat(logging): stop silent exception swallowing in frame pipeline and ws persistence"
```

---

### Task 5: V-Engine 客户端日志（非 OK 响应 / 未连接服务 / 连接地址）

**Files:**
- Modify: `core/vengine_client.py`（常量区、`__init__` 82-85、`_normalize_service_host` 117-129、`connect` 166-186、`detect` 498-513、`classify` 588-598、`ocr` 670-684、`recognize_action` 758-768、`upload_image` 806-816、`upload_video` 851-861、`load_model` 886-888、`unload_model` 925-927、`list_models` 956-958、`list_models` 非 OK 965-979、`health_check` 991-993）
- Test: `tests/test_vengine_client.py`

**Interfaces:**
- Consumes: 无
- Produces: 模块常量 `NON_OK_LOG_COOLDOWN_SECONDS = 60.0`；实例属性 `_non_ok_last: dict[str, tuple[str, float]]`；方法 `_log_non_ok(self, service: str, status_code: int, error_message: str) -> None`（60s 去重）；WARNING `"{service} gRPC non-OK: status={} error={}"`、WARNING `"V-Engine service '{}' not connected"`；INFO 连接日志含地址映射；WARNING Docker 别名解析失败。

- [ ] **Step 1: 写失败测试**

`tests/test_vengine_client.py` 顶部 import 区加 `from unittest.mock import AsyncMock, MagicMock` 与 `from loguru import logger`。文件末尾追加：

```python
class TestNonOkAndConnectLogging:
    def _client_with_non_ok_detection(self):
        client = AsyncVEngineClient(Settings())
        client._enabled = {"detection": True}
        response = MagicMock()
        response.response_header.status_code = base_pb2.StatusCode.STATUS_MODEL_NOT_FOUND
        response.response_header.error_message = "model not loaded"
        response.results = []
        stub = MagicMock()
        stub.Predict = AsyncMock(return_value=response)
        client._stubs["detection"] = stub
        return client

    async def test_detect_non_ok_status_logs_error_message(self):
        client = self._client_with_non_ok_detection()
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            result = await client.detect(
                shape=(100, 200, 3), model_name="m", image_bytes=b"x"
            )
        finally:
            logger.remove(sink_id)
        assert result == []
        assert any(
            "detection gRPC non-OK" in r["message"] and "model not loaded" in r["message"]
            for r in records
        )

    async def test_detect_repeated_non_ok_is_rate_limited(self):
        client = self._client_with_non_ok_detection()
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            await client.detect(shape=(100, 200, 3), model_name="m", image_bytes=b"x")
            await client.detect(shape=(100, 200, 3), model_name="m", image_bytes=b"x")
        finally:
            logger.remove(sink_id)
        matches = [r for r in records if "detection gRPC non-OK" in r["message"]]
        assert len(matches) == 1  # 60s 内相同错误只记一次

    async def test_unknown_service_health_check_warns(self):
        client = AsyncVEngineClient(Settings())
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            result = await client.health_check("nope")
        finally:
            logger.remove(sink_id)
        assert result == {"error": "Unknown service: nope"}
        assert any("not connected" in r["message"] for r in records)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_vengine_client.py -q -k "NonOkAndConnectLogging"`
Expected: 3 FAILED

- [ ] **Step 3: 实现**

(a) 模块常量：`_DOCKER_HOST_ALIASES = {...}`（第 56 行）后加：

```python
NON_OK_LOG_COOLDOWN_SECONDS = 60.0
```

(b) `__init__`（82-85 行）末尾加：

```python
        self._non_ok_last: dict[str, tuple[str, float]] = {}
```

(c) 在 `is_service_enabled`（159-162 行）之后加方法：

```python
    def _log_non_ok(self, service: str, status_code: int, error_message: str) -> None:
        """Log a non-OK gRPC response, rate-limited per service.
        记录非 OK 的 gRPC 响应；同一服务相同错误 60 秒内只记一次，防止逐帧刷屏。"""
        key = f"{status_code}:{error_message}"
        now = time.monotonic()
        last = self._non_ok_last.get(service)
        if last is not None and last[0] == key and now - last[1] < NON_OK_LOG_COOLDOWN_SECONDS:
            return
        self._non_ok_last[service] = (key, now)
        logger.warning(
            "{} gRPC non-OK: status={} error={}", service, status_code, error_message
        )
```

(d) 7 个推理/管理方法的非 OK 分支补日志。现状结构（7 处相同）是：`if ... STATUS_OK:` 无 else，`return results`（list_models 为 `return models`）在 **if 之外**、try 之内。对每处在 if 与 `return` 之间插入同级的 `else` 分支，以 `detect` 为例（改后完整片段）：

```python
            if response.response_header.status_code == base_pb2.StatusCode.STATUS_OK:
                for det_result in response.results:
                    for box in det_result.boxes:
                        ...  # 原有解析代码不变
            else:
                self._log_non_ok(
                    "detection",
                    response.response_header.status_code,
                    response.response_header.error_message,
                )
            return results
```

7 处位置与 `_log_non_ok` 第一个实参（service 名）的对应关系：`detect`→`"detection"`、`classify`→`"classification"`、`ocr`→`"ocr"`、`recognize_action`→`"action"`、`upload_image`→`"upload"`、`upload_video`→`"upload"`、`list_models`→`service`（该函数有 `service` 形参，直接传它，return 语句是 `return models`）。

(e) 4 处 `stub is None` 分支（`load_model` 887-888、`unload_model` 926-927、`list_models` 957-958、`health_check` 992-993）加 WARNING，以 `load_model` 为例：

```python
            stub = self._stubs.get(service)
            if stub is None:
                logger.warning("V-Engine service '{}' not connected", service)
                return {"error": f"Unknown service: {service}"}
```

`list_models` 同模式但 `return []`。

(f) `_normalize_service_host` 125-129 行替换为：

```python
        gateway_ip = cls._detect_docker_host_gateway()
        if gateway_ip:
            logger.info("Resolved Docker host alias '{}' to '{}'", normalized_host, gateway_ip)
            return gateway_ip
        logger.warning("Could not resolve Docker host alias '{}', using it as-is", normalized_host)
        return normalized_host
```

(g) `connect` 182-186 行替换为：

```python
        logger.info(
            "AsyncVEngineClient connected — enabled: {}, disabled: {}, addresses: {}",
            enabled_list or "(none)",
            disabled_list or "(none)",
            addrs,
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_vengine_client.py tests/test_core.py -q`
Expected: 全部 PASS

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check core/vengine_client.py tests/test_vengine_client.py
git add core/vengine_client.py tests/test_vengine_client.py
git commit -m "feat(logging): log V-Engine non-OK gRPC responses, unconnected services and addresses"
```

---

### Task 6: API 层 5xx 与安全事件日志

**Files:**
- Modify: `backend/api/processor.py`（imports；30-31、73-74 行）
- Modify: `backend/api/sources.py`（imports；32-37 行）
- Modify: `backend/api/notifications.py`（imports；184-187 行）
- Modify: `backend/api/auth.py`（imports；`_register_failure_and_maybe_block` 67-81 行）
- Modify: `backend/api/ws.py`（`ws_messages_endpoint` 150-158 行；该文件已有 loguru import）
- Test: `tests/test_login_lockout.py`、`tests/test_ws.py`

**Interfaces:**
- Consumes: 无
- Produces: WARNING `Failed to start processor: source={}` / `Failed to toggle push result stream: source={}` / `Failed to create source: name={}` / `Notification instance test failed: provider={} type={} error={}` / `IP {} blocked for {} after {} failed login attempts` / `WS client rejected: missing token, client={}` / `WS client rejected: invalid token, client={}`。HTTP 行为不变。

- [ ] **Step 1: 写失败测试**

`tests/test_login_lockout.py` 顶部加 `from loguru import logger`，`TestLoginLockout` 类内追加：

```python
    async def test_ip_block_is_logged(self, async_client: AsyncClient):
        await async_client.put(
            "/api/settings",
            json={
                "login_lockout_max_attempts": "3",
                "login_lockout_window_seconds": "300",
                "login_lockout_duration_seconds": "900",
            },
        )
        await async_client.post(
            "/api/users",
            json={"username": "victim-log", "password": "correct", "role": "operator"},
        )

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            for _ in range(3):
                await async_client.post(
                    "/api/auth/login",
                    json={"username": "victim-log", "password": "wrong"},
                )
        finally:
            logger.remove(sink_id)

        assert any(
            "blocked" in r["message"] and "failed login attempts" in r["message"]
            for r in records
        )
```

`tests/test_ws.py` 顶部 import 区加 `from loguru import logger`，文件末尾追加（新 class）：

```python
class TestWSEndpointAuth:
    def test_ws_invalid_token_close_is_logged(self):
        import pytest
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        from backend.main import app

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as excinfo:
                    client.websocket_connect("/ws/messages?token=bad-token")
                assert excinfo.value.code == 4001
        finally:
            logger.remove(sink_id)

        assert any("invalid token" in r["message"] for r in records)

    def test_ws_missing_token_close_is_logged(self):
        import pytest
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        from backend.main import app

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect):
                    client.websocket_connect("/ws/messages")
        finally:
            logger.remove(sink_id)

        assert any("missing token" in r["message"] for r in records)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_login_lockout.py -q -k "block_is_logged" tests/test_ws.py -q -k "TestWSEndpointAuth"`
Expected: 3 FAILED

- [ ] **Step 3: 实现**

四个文件（`processor.py` / `sources.py` / `notifications.py` / `auth.py`）顶部各加 `from loguru import logger`。

`backend/api/processor.py` 30-31 行替换为：

```python
    except Exception as exc:
        logger.opt(exception=True).warning(
            "Failed to start processor: source={}", request.source_id
        )
        raise HTTPException(status_code=500, detail=str(exc))
```

73-74 行替换为：

```python
    except Exception as exc:
        logger.opt(exception=True).warning(
            "Failed to toggle push result stream: source={}", source_id
        )
        raise HTTPException(status_code=500, detail=str(exc))
```

`backend/api/sources.py` 32-37 行替换为：

```python
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(
                status_code=409, detail="A source with this RTSP URL already exists"
            )
        logger.opt(exception=True).warning("Failed to create source: name={}", source.name)
        raise HTTPException(status_code=500, detail=str(exc))
```

`backend/api/notifications.py` 186-187 行替换为：

```python
    except Exception as exc:  # noqa: BLE001 - surface provider errors to the UI
        logger.warning(
            "Notification instance test failed: provider={} type={} error={}",
            provider.name, provider.type, exc,
        )
        raise HTTPException(status_code=400, detail=str(exc) or exc.__class__.__name__) from exc
```

`backend/api/auth.py` `_register_failure_and_maybe_block` 73-74 行（`blocked, blocked_until = await db.is_ip_blocked(ip)` 之后、`raise HTTPException` 之前）插入：

```python
        logger.warning(
            "IP {} blocked for {} after {} failed login attempts",
            ip,
            f"{duration_seconds}s" if duration_seconds > 0 else "indefinitely",
            failures,
        )
```

`backend/api/ws.py` 150-158 行替换为：

```python
    token = websocket.query_params.get("token")
    client_text = str(websocket.client) if websocket.client else "unknown"
    if not token:
        logger.warning("WS client rejected: missing token, client={}", client_text)
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        verify_access_token(token)
    except Exception:
        logger.warning("WS client rejected: invalid token, client={}", client_text)
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_login_lockout.py tests/test_ws.py tests/test_auth_users.py -q`
Expected: 全部 PASS

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check backend/api/processor.py backend/api/sources.py backend/api/notifications.py backend/api/auth.py backend/api/ws.py tests/test_login_lockout.py tests/test_ws.py
git add backend/api/processor.py backend/api/sources.py backend/api/notifications.py backend/api/auth.py backend/api/ws.py tests/test_login_lockout.py tests/test_ws.py
git commit -m "feat(logging): log API 5xx causes and security events (IP block, WS auth rejects)"
```

---

### Task 7: WHEP 代理上游失败 + 审计中间件保护

**Files:**
- Modify: `backend/api/whep_proxy.py`（`whep_offer` 96-107、`whep_patch` 149-157、`whep_delete` 184-190）
- Modify: `backend/audit.py`（imports；246-262 行两处 `write_audit_log` 调用）
- Test: `tests/test_whep_proxy.py`、`tests/test_audit_logs.py`

**Interfaces:**
- Consumes: 无
- Produces: WARNING `WHEP proxy POST/PATCH/DELETE ... timed out` / `... upstream auth failed: {}` / `... upstream error: {}`（PATCH/DELETE 上游非 2xx；DELETE 恒返 204 的行为不变）；INFO `WHEP proxy POST {} upstream 404`；审计写入失败时 ERROR `Failed to write audit log: {} {}`（请求不被审计故障破坏）。

- [ ] **Step 1: 写失败测试**

`tests/test_whep_proxy.py` 顶部 import 区加 `from loguru import logger`，文件末尾追加：

```python
async def test_delete_upstream_error_is_logged(async_client, monkeypatch):
    from backend.api import whep_proxy
    import httpx as httpx_lib

    async def fake_proxy(method, url, username, password, body=None, content_type=None):
        return httpx_lib.Response(500, content=b"boom")

    monkeypatch.setattr(whep_proxy, "_proxy_to_mediamtx", fake_proxy)
    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        resp = await async_client.delete(
            "/api/video/huotai/zhongkong/10.37.192.5/whep-session/sess-1"
        )
    finally:
        logger.remove(sink_id)

    assert resp.status_code == 204  # 行为不变：仍恒返 204
    assert any("WHEP proxy DELETE" in r["message"] and "500" in r["message"] for r in records)


async def test_offer_timeout_is_logged(async_client, monkeypatch):
    from backend.api import whep_proxy
    import httpx as httpx_lib

    async def fake_proxy(method, url, username, password, body=None, content_type=None):
        raise httpx_lib.TimeoutException(
            "upstream timeout", request=httpx_lib.Request("POST", "http://x/whep")
        )

    monkeypatch.setattr(whep_proxy, "_proxy_to_mediamtx", fake_proxy)
    records: list[dict] = []
    sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
    try:
        resp = await async_client.post(
            "/api/video/cam1/whep-offer",
            content=b"v=0\r\n",
            headers={"Content-Type": "application/sdp"},
        )
    finally:
        logger.remove(sink_id)

    assert resp.status_code == 504
    assert any("WHEP proxy POST" in r["message"] and "timed out" in r["message"] for r in records)
```

`tests/test_audit_logs.py` 顶部 import 区加 `from loguru import logger` 与 `from unittest.mock import patch`（若无），`TestAuditLogs` 类内追加：

```python
    async def test_request_succeeds_when_audit_write_fails(self, async_client: AsyncClient):
        import backend.audit as audit_mod

        async def failing_create(**kwargs):
            raise RuntimeError("audit db down")

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="ERROR")
        try:
            with patch.object(audit_mod.db, "create_audit_log", new=failing_create):
                resp = await async_client.put(
                    "/api/settings", json={"site_title": "AuditFail"}
                )
        finally:
            logger.remove(sink_id)

        assert resp.status_code == 200  # 审计故障不得破坏正常请求
        assert any("Failed to write audit log" in r["message"] for r in records)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_whep_proxy.py -q -k "upstream_error_is_logged or timeout_is_logged" tests/test_audit_logs.py -q -k "audit_write_fails"`
Expected: 3 FAILED

- [ ] **Step 3: 实现**

`backend/api/whep_proxy.py`：

`whep_offer` 96-107 行替换为：

```python
    except httpx.TimeoutException:
        logger.warning("WHEP proxy POST {} timed out", normalized_path)
        raise HTTPException(status_code=504, detail="Upstream WHEP request timed out")
    except httpx.RequestError as exc:
        logger.warning("WHEP proxy POST {} failed: {}", normalized_path, exc)
        raise HTTPException(status_code=502, detail="Upstream WHEP request failed")

    if upstream.status_code == 404:
        logger.info("WHEP proxy POST {} upstream 404 (stream not found)", normalized_path)
        raise HTTPException(status_code=404, detail="Stream not found")
    if upstream.status_code == 401 or upstream.status_code == 403:
        logger.warning(
            "WHEP proxy POST {} upstream auth failed: {}", normalized_path, upstream.status_code
        )
        raise HTTPException(status_code=502, detail="Upstream authentication failed")
    if upstream.status_code != 201:
        logger.warning(
            "WHEP proxy POST {} upstream error: {}", normalized_path, upstream.status_code
        )
        raise HTTPException(status_code=502, detail=f"Upstream WHEP error: {upstream.status_code}")
```

`whep_patch` 149-150 行（Timeout 分支）加日志：

```python
    except httpx.TimeoutException:
        logger.warning("WHEP proxy PATCH {}/{} timed out", normalized_path, session_id)
        raise HTTPException(status_code=504, detail="Upstream WHEP PATCH timed out")
```

155-157 行替换为：

```python
    if upstream.status_code in (204, 304):
        return Response(status_code=upstream.status_code)
    logger.warning(
        "WHEP proxy PATCH {}/{} upstream error: {}", normalized_path, session_id, upstream.status_code
    )
    return Response(content=upstream.content, status_code=upstream.status_code)
```

`whep_delete` 184-185 行（Timeout 分支）加日志：

```python
    except httpx.TimeoutException:
        logger.warning("WHEP proxy DELETE {}/{} timed out", normalized_path, session_id)
        raise HTTPException(status_code=504, detail="Upstream WHEP DELETE timed out")
```

190 行 `return Response(status_code=204)` 前插入：

```python
    if upstream.status_code >= 400:
        logger.warning(
            "WHEP proxy DELETE {}/{} upstream error: {}", normalized_path, session_id, upstream.status_code
        )
```

`backend/audit.py` 顶部 import 区（第 6 行 `from fastapi import Request` 后）加 `from loguru import logger`。`audit_request` 246-263 行替换为：

```python
    try:
        response = await call_next(working_request)
    except Exception as exc:
        try:
            await write_audit_log(
                working_request,
                status_code=500,
                payload=payload,
                detail=_exception_detail(exc),
            )
        except Exception:
            logger.opt(exception=True).error(
                "Failed to write audit log for failed request: {} {}",
                request.method,
                request.url.path,
            )
        raise

    try:
        await write_audit_log(
            working_request,
            response=response,
            status_code=response.status_code,
            payload=payload,
        )
    except Exception:
        logger.opt(exception=True).error(
            "Failed to write audit log: {} {}", request.method, request.url.path
        )
    return response
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_whep_proxy.py tests/test_audit_logs.py -q`
Expected: 全部 PASS（注意：`whep_delete` 的 F841 既有告警应随 `upstream.status_code` 的使用而消失）

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check backend/api/whep_proxy.py backend/audit.py tests/test_whep_proxy.py tests/test_audit_logs.py
git add backend/api/whep_proxy.py backend/audit.py tests/test_whep_proxy.py tests/test_audit_logs.py
git commit -m "feat(logging): log WHEP upstream failures and guard audit middleware against DB errors"
```

---

### Task 8: RTSP URL 日志脱敏

**Files:**
- Modify: `core/base_processor.py`（模块级加 `redact_url`；10 处日志点 + 1 处异常消息）
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: 无
- Produces: 模块函数 `redact_url(url: str) -> str`（`scheme://user:pass@host` → `scheme://user:***@host`；无凭据/非 URL 原样返回）。后续 Task 9 的帧读取器退出日志依赖它。

- [ ] **Step 1: 写失败测试**

`tests/test_core.py` 文件末尾追加：

```python
class TestRedactUrl:
    def test_redacts_password(self):
        from core.base_processor import redact_url

        assert (
            redact_url("rtsp://admin:secret@10.0.0.1:8554/stream")
            == "rtsp://admin:***@10.0.0.1:8554/stream"
        )

    def test_username_only_unchanged(self):
        from core.base_processor import redact_url

        assert redact_url("rtsp://admin@10.0.0.1:8554/stream") == "rtsp://admin@10.0.0.1:8554/stream"

    def test_no_credentials_unchanged(self):
        from core.base_processor import redact_url

        assert redact_url("rtsp://10.0.0.1:8554/stream") == "rtsp://10.0.0.1:8554/stream"

    def test_empty_string(self):
        from core.base_processor import redact_url

        assert redact_url("") == ""

    def test_non_url_unchanged(self):
        from core.base_processor import redact_url

        assert redact_url("not a url") == "not a url"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_core.py -q -k "TestRedactUrl"`
Expected: 5 FAILED（ImportError: cannot import name 'redact_url'）

- [ ] **Step 3: 实现**

`core/base_processor.py` 模块级（`class BaseVideoProcessor` 定义之前）加：

```python
def redact_url(url: str) -> str:
    """Redact ``user:password@`` userinfo from a URL before logging.
    脱敏 URL 中的 ``user:password@`` 凭据，用于日志输出。"""
    text = str(url or "")
    scheme_end = text.find("://")
    if scheme_end == -1:
        return text
    rest = text[scheme_end + 3:]
    at = rest.find("@")
    if at == -1:
        return text
    authority = rest[:at]
    if ":" in authority:
        user, _sep, _password = authority.partition(":")
        if user:
            return f"{text[:scheme_end + 3]}{user}:***@{rest[at + 1:]}"
    return text
```

替换 10 处日志点（`self.rtsp_url` → `redact_url(self.rtsp_url)`；push 处 `rtsp_url` → `redact_url(rtsp_url)`）：

- 266 行 `logger.info("Frame reader started for {}", self.rtsp_url)`
- 297 行 `raise RuntimeError(f"No video track found in stream {self.rtsp_url}")`（异常消息会被 354 行的 `logger.exception` 连带打出，必须脱敏）
- 351 行 `logger.warning("PyAV reader ended before yielding frames for {}", self.rtsp_url)`
- 354 行 `logger.exception("Frame reader error for {}: {}", self.rtsp_url, exc)`
- 370 行（reconnect limit ERROR 的第二参数）
- 376 行（stream lost WARNING 的第一参数）
- 388 行 `logger.info("Frame reader exited for {}", self.rtsp_url)`
- 1185、1200、1217、1224 行（push 相关 4 处，变量为 `rtsp_url`）

每处仅把参数改为 `redact_url(...)` 包裹，消息文本不变。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_core.py tests/test_smoke.py tests/test_fire_door.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 确认无明文凭据残留并提交**

```bash
uv run ruff check core/base_processor.py tests/test_core.py
rg -n 'logger\.(info|warning|error|exception|debug)\(.*rtsp_url' core/base_processor.py
# 期望：输出的每一行日志语句中 rtsp_url 都被 redact_url(...) 包裹
git add core/base_processor.py tests/test_core.py
git commit -m "feat(logging): redact RTSP URL credentials in processor logs"
```

---

### Task 9: 关闭/恢复路径 + 推流生命周期 + 设置变更日志

**Files:**
- Modify: `backend/processing/manager.py`（`restore_desired_processors` 135-154、`_stop_all_processors` 156-179、`stop_all` 181-185、`toggle_push_result_stream` 205-213）
- Modify: `core/base_processor.py`（`_frame_reader` 383-388、`_push_frame` 1174-1180 附近、`set_push_result_stream` 1382-1390）
- Modify: `backend/api/settings.py`（`update_settings` 173-175 行后）
- Test: `tests/test_processing.py`、`tests/test_settings.py`

**Interfaces:**
- Consumes: Task 8 的 `redact_url`
- Produces: WARNING `ProcessorManager: failed to stop processor: source={}`（带栈）；WARNING `ProcessorManager: stopped {} processor(s), {} failed: {}`（有失败时）/ 既有 INFO（无失败时）；ERROR `ProcessorManager: restore desired processors aborted`（带栈）；INFO `ProcessorManager: restored {}/{} desired processors`；INFO `ffmpeg push started for {}: {}x{} @ {} fps, bitrate {}`；INFO `Push result stream {}: source={}`；ERROR `Frame reader exited without stop request: source={}`；INFO `Settings updated, changed keys: {}`（仅键名）。

- [ ] **Step 1: 写失败测试**

`tests/test_processing.py` `TestProcessorManager` 类内追加：

```python
    async def test_stop_all_logs_failed_stops(self, init_db):
        source = await create_source(
            VideoSourceCreate(name="cam-fail", rtsp_url="rtsp://localhost:8554/cam-fail")
        )
        mgr = self._make_manager()
        processor = MagicMock(status="running")
        processor.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
        mgr._processors[source.id] = processor

        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            await mgr.stop_all()
        finally:
            logger.remove(sink_id)

        assert any(
            "failed to stop processor" in r["message"] and source.id in r["message"]
            for r in records
        )
        # 汇总日志如实报告失败：stopped 0 processor(s), 1 failed: [<source_id>]
        assert any(
            "stopped" in r["message"] and "failed" in r["message"] and source.id in r["message"]
            for r in records
        )
```

`tests/test_settings.py` `TestSettingsAPI`（含 `test_update_settings(self, async_client)` 的 class）内追加：

```python
    async def test_update_settings_logs_changed_keys(self, async_client: AsyncClient):
        records: list[dict] = []
        sink_id = logger.add(lambda m: records.append(m.record), level="INFO")
        try:
            resp = await async_client.put("/api/settings", json={"site_title": "LogCheck"})
        finally:
            logger.remove(sink_id)

        assert resp.status_code == 200
        assert any(
            "Settings updated, changed keys" in r["message"] and "site_title" in r["message"]
            for r in records
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_processing.py -q -k "stop_all_logs_failed_stops" tests/test_settings.py -q -k "changed_keys"`
Expected: 2 FAILED

- [ ] **Step 3: 实现**

`backend/processing/manager.py` `restore_desired_processors` 135-154 行整体替换为：

```python
    async def restore_desired_processors(self, *, delay_seconds: float = 1.0) -> dict:
        """Gradually restart sources that were running before process shutdown."""
        try:
            sources = await list_desired_analysis_sources()
            restored = 0
            failed: list[dict[str, str]] = []
            for index, source in enumerate(sources):
                if index > 0 and delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                try:
                    result = await self.start_processor(source.id)
                    if result.get("status") in {"started", "already_running"}:
                        restored += 1
                except Exception as exc:
                    logger.warning(
                        "ProcessorManager: failed to restore processor for {}: {}",
                        source.id,
                        exc,
                    )
                    failed.append({"source_id": source.id, "reason": str(exc)})
            logger.info(
                "ProcessorManager: restored {}/{} desired processors",
                restored,
                len(sources),
            )
            return {"status": "restored", "restored": restored, "failed": failed}
        except Exception:
            logger.opt(exception=True).error(
                "ProcessorManager: restore desired processors aborted"
            )
            return {"status": "failed", "restored": 0, "failed": []}
```

`_stop_all_processors` 167-173 行的 for 循环体替换为：

```python
        for source_id in source_ids:
            try:
                result = await self.stop_processor(source_id, persist_desired=False)
                if result["status"] == "stopped":
                    stopped += 1
            except Exception as exc:
                logger.opt(exception=True).warning(
                    "ProcessorManager: failed to stop processor: source={}", source_id
                )
                failed.append({"source_id": source_id, "reason": str(exc)})
```

`stop_all` 181-185 行替换为：

```python
    async def stop_all(self) -> None:
        """Stop all running processors (called during shutdown).
        停止所有运行中的处理器（关闭时调用）。"""
        summary = await self._stop_all_processors()
        failed = summary.get("failed", [])
        if failed:
            logger.warning(
                "ProcessorManager: stopped {} processor(s), {} failed: {}",
                summary.get("stopped", 0),
                len(failed),
                [item["source_id"] for item in failed],
            )
        else:
            logger.info("ProcessorManager: all processors stopped")
```

`core/base_processor.py` `_frame_reader` 末尾 383-388 行替换为（384-387 的 sentinel 块保持）：

```python
        # Send sentinel when reader fully exits
        try:
            loop.call_soon_threadsafe(self._enqueue_reader_sentinel)
        except Exception:
            pass
        if self._stop_event.is_set():
            logger.info("Frame reader exited for {}", redact_url(self.rtsp_url))
        else:
            logger.error(
                "Frame reader exited without stop request: source={}", self.source_id
            )
```

`core/base_processor.py` `_push_frame` 中 `self._push_bitrate = video_bitrate`（1178 行）之后、`time.sleep(PUSH_STARTUP_CHECK_DELAY)`（1180 行）之前插入：

```python
                    logger.info(
                        "ffmpeg push started for {}: {}x{} @ {} fps, bitrate {}",
                        self.source_id, w, h, target_fps, video_bitrate,
                    )
```

（`w` / `h` / `target_fps` / `video_bitrate` 均为 `_push_frame` 内已有局部变量。）

`set_push_result_stream` 1382-1390 行替换为：

```python
    def set_push_result_stream(self, enabled: bool) -> None:
        """Enable or disable push at runtime without restarting analysis.
        运行时启用或禁用推流，无需重启分析进程。"""
        self.push_result_stream = bool(enabled)
        logger.info(
            "Push result stream {}: source={}", self.push_result_stream, self.source_id
        )
        if self.push_result_stream:
            self._start_output_worker()
        else:
            self._stop_output_worker()
            self._close_push_process()
```

`backend/api/settings.py` `update_settings` 在 `result = await db.update_settings(updates)`（174 行）之后插入：

```python
    changed_keys = sorted(
        key for key in updates
        if str(previous_settings.get(key) or "") != str(result.get(key) or "")
    )
    if changed_keys:
        logger.info("Settings updated, changed keys: {}", changed_keys)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_processing.py tests/test_settings.py -q`
Expected: 全部 PASS

- [ ] **Step 5: lint 并提交**

```bash
uv run ruff check backend/processing/manager.py core/base_processor.py backend/api/settings.py tests/test_processing.py tests/test_settings.py
git add backend/processing/manager.py core/base_processor.py backend/api/settings.py tests/test_processing.py tests/test_settings.py
git commit -m "feat(logging): log shutdown/restore outcomes, push lifecycle and settings key changes"
```

---

### Task 10: 全量验证 + 推送 + 创建 PR

**Files:** 无新改动（仅验证；如有修复则 amend 到最近相关提交或新提交）

- [ ] **Step 1: 全量测试**

Run: `uv run pytest -q`
Expected: `1 failed, 466 passed`（466 = 基线 440 + 新增 26；唯一失败必须是既有的 `tests/test_main.py::TestFrontendFallbackRoutes::test_direct_frontend_route_serves_index_html`，与前端 dist 环境有关，非本计划引入。若出现其他失败，先定位修复再继续。）

- [ ] **Step 2: 全量 lint 对比基线**

Run: `uv run ruff check core/ backend/ tests/ | tail -3`
Expected: 错误数 ≤ 35（基线 35，Task 7 顺带消除 1 个既有 F841，期望 34）。用 `uv run ruff check core/ backend/ tests/ --output-format=concise` 与改动前对比：任何**改动文件**不得出现新错误（既有错误保持原样）。

- [ ] **Step 3: 冒烟验证日志输出（可选但推荐）**

用真实 VL 后端不可达的配置手动跑一次 `uv run pytest tests/test_vl_confirm.py -q -s`，观察 stderr 中出现 `VL request failed: ... error=...` 及完整异常栈。

- [ ] **Step 4: 推送分支并创建 PR**

```bash
git push -u origin feat/logging-coverage
gh pr create \
  --title "feat(logging): VL 复判全链路日志 + 关键缺日志补全" \
  --body-file - <<'EOF'
## 背景
VL 大模型复判（告警自动确认 / 手动复判 / 连接测试）在成功与失败时都没有可见日志：
- `VLConfirmClient.confirm` 成功只写 DEBUG（INFO sink 下不可见）；失败用 `exc_info=True`——loguru 会静默忽略该标准库参数，VL 服务端返回的错误体全部丢失（已实测 loguru 0.7.3 复现）。
- 手动复判 / 连接测试端点失败直接抛 502，服务端零日志。
- VL 拒报（告警被标记误报）无任何日志。

## 变更
- **VL 全链路**：`VLConfirmClient.complete` 成功记原始响应（INFO）+ 延迟，失败记完整异常（含上游错误体）；`confirm` 记录判定结论与 fail-open；两个 processor 记录 VL 确认/拒报；两个 API 端点记录成功/失败。
- **关键缺日志**：帧流水线三处静默吞异常加保护与日志（DB 故障不再无声杀死分析）；V-Engine gRPC 非 OK 响应记录服务端 error_message（60s 去重防刷屏）；API 5xx 零日志补 WARNING；暴力破解封 IP / WS 坏 token 等安全事件补日志；WHEP 代理上游超时/401/403/5xx 补日志；审计中间件加 try/except 防止审计故障吞掉原始异常或把 200 变 500；关闭/恢复路径如实报告；ffmpeg 推流启动与运行时开关补 INFO。
- **日志脱敏**：`redact_url()` 脱敏 RTSP URL 中的 `user:password@`（11 处，含被异常消息带出的 URL）。

## 不做（YAGNI）
DEBUG→INFO 提升、文件日志 sink、DB 迁移日志、analysis_agent 聚合循环健壮性修复（补日志后已可见，行为修复另开任务）。

## 验证
- 新增 26 个测试（回归测试覆盖 `exc_info` 无效、非 OK 去重、脱敏等），全量 467 测试仅 1 个既有环境性失败（test_main.py 前端 dist）。
- `uv run ruff check` 无新增错误。
- spec: docs/superpowers/specs/2026-09-02-logging-coverage-design.md
EOF
```

PR 创建后把 URL 报告给用户。**不要** merge（等用户审阅）。
