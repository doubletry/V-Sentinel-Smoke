# VL 二次确认功能增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VL 二次确认支持「原图/检测图 × 整图/ROI裁剪」图像选项（按插件）、VL 否决的告警留痕为误报消息（仅抑制通知）、VL 开关按插件启用（全局开关一次性迁移后废弃）。

**Architecture:** 复用现有消息链路（processor messages → agent → WSManager 持久化+广播，`false_positive` 字段已存在）；VL 否决时消息照常生成并标记 `false_positive=True`，仅不设置 `result.extra["email_event"]` 以抑制通知。设置沿用 `dict[str, str]` 扁平结构，新增 6 个插件级 key。消息列表 API 用枚举参数 `false_positive_filter`（all/only/exclude）替换布尔 `false_positive_only`。

**Tech Stack:** Python (FastAPI/aiosqlite/numpy/opencv), Vue 3 + Pinia + Element Plus, pytest + vitest。

**Spec:** `docs/superpowers/specs/2026-09-01-vl-confirm-enhancements-design.md`

## Global Constraints

- 所有设置值为字符串（`dict[str, str]` 约定）；布尔用 `"true"`/`"false"`。
- 新设置 key 命名：`{plugin}_vl_confirm_enabled` / `{plugin}_vl_confirm_image_source`（`original`|`annotated`，默认 `original`）/ `{plugin}_vl_confirm_image_crop`（`roi`|`full`，默认 `roi`）。
- VL 服务端点 key（`vl_confirm_base_url/api_key/model/timeout`）保持全局不变。
- 全局 `vl_confirm_enabled` 废弃：`init_db` 幂等迁移（复制值到两个插件级 key 后删除全局 key），从 `DEFAULT_APP_SETTINGS`、`PLUGIN_SETTING_KEYS`、`AppSettingsUpdate`、前端中全部移除。
- VL 否决消息：`level` 保持 `"alert"`、文本不变、`false_positive: True`；不自动导出图片到 `false_positives/`。
- fail-open 不变：VL 返回 `None` → 正常告警 + 通知 + 无误报标记。
- 提交策略：不主动 commit，全部任务完成后由用户决定提交。
- 测试命令：后端 `uv run pytest tests -q`（工作目录仓库根）；前端 `npm test` 与 `npm run build`（工作目录 `frontend/`）。

---

### Task 1: `build_vl_image_data_url` helper（core/vl_confirm.py）

**Files:**
- Modify: `core/vl_confirm.py`（在 `crop_roi_image` 之后、`VLConfirmClient` 之前插入）
- Test: `tests/test_vl_confirm.py`（文件末尾追加；该文件已有 `_decode_data_url` 与 cv2/np/base64 导入可复用）

**Interfaces:**
- Produces: `build_vl_image_data_url(frame: np.ndarray, annotated_frame: np.ndarray | None, image_source: str, image_crop: str, roi_points: list[dict[str, Any]] | None) -> str`（JPEG data URL）。Task 2/3 的处理器将调用它。

- [ ] **Step 1: 写失败测试**

在 `tests/test_vl_confirm.py` 末尾追加：

```python
class TestBuildVlImageDataUrl:
    def test_original_full_returns_full_frame(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(
            frame, None, "original", "full",
            [{"x": 5, "y": 5}, {"x": 55, "y": 35}],
        )
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (40, 60)

    def test_original_roi_crops_to_bbox(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(
            frame, None, "original", "roi",
            [{"x": 5, "y": 5}, {"x": 55, "y": 35}],
        )
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (31, 51)

    def test_annotated_full_uses_annotated_frame(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        annotated = np.zeros((40, 60, 3), dtype=np.uint8)
        annotated[:, :, 0] = 255  # RGB red
        url = build_vl_image_data_url(frame, annotated, "annotated", "full", None)
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (40, 60)
        assert decoded[:, :, 2].mean() > 200  # BGR 解码后 R 通道

    def test_annotated_missing_falls_back_to_original(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(frame, None, "annotated", "full", None)
        decoded = _decode_data_url(url)
        assert decoded[:, :, 2].mean() < 50

    def test_unknown_values_fall_back_to_original_roi(self):
        frame = np.zeros((40, 60, 3), dtype=np.uint8)
        url = build_vl_image_data_url(
            frame, None, "bogus", "bogus",
            [{"x": 5, "y": 5}, {"x": 55, "y": 35}],
        )
        decoded = _decode_data_url(url)
        assert decoded.shape[:2] == (31, 51)
```

同时更新文件顶部 import 行：

```python
from core.vl_confirm import VLConfirmClient, build_vl_image_data_url, crop_roi_image, parse_vl_response
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_vl_confirm.py -q`
Expected: `ImportError: cannot import name 'build_vl_image_data_url'`（5 个新测试收集即失败）

- [ ] **Step 3: 实现 helper**

在 `core/vl_confirm.py` 的 `crop_roi_image` 函数之后插入：

```python
def build_vl_image_data_url(
    frame: np.ndarray,
    annotated_frame: np.ndarray | None,
    image_source: str,
    image_crop: str,
    roi_points: list[dict[str, Any]] | None,
) -> str:
    """Build the JPEG data URL sent to the VL model from configured options.

    - ``image_source``: ``"original"`` (raw frame, default) or ``"annotated"``
      (frame with detection drawings). Unknown values, or a missing
      ``annotated_frame``, fall back to the original frame.
    - ``image_crop``: ``"roi"`` (crop to the ``roi_points`` bounding box,
      default) or ``"full"`` (full frame). Unknown values fall back to
      ``"roi"``.
    """
    selected = frame
    if str(image_source or "").strip().lower() == "annotated" and annotated_frame is not None:
        selected = annotated_frame
    if str(image_crop or "").strip().lower() == "full":
        return crop_roi_image(selected, None)
    return crop_roi_image(selected, roi_points)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_vl_confirm.py -q`
Expected: 全部 PASS

---

### Task 2: smoke 处理器 — 插件级开关 + 图像选项 + 否决留痕

**Files:**
- Modify: `core/smoke/processor.py:117-182`（`process_frame` 的 VL 段落、`_vl_confirm_enabled`、`_vl_confirm_alert`、顶部 import）
- Test: `tests/test_smoke.py`（文件末尾追加测试类；顶部补 import `from core.vl_confirm import VLConfirmClient` 已存在，无需改）

**Interfaces:**
- Consumes: Task 1 的 `build_vl_image_data_url`；设置 key `smoke_vl_confirm_enabled` / `smoke_vl_confirm_image_source` / `smoke_vl_confirm_image_crop`。
- Produces: `result.messages[i]` 新增键 `"false_positive": bool`；VL 否决时 `result.extra` 不含 `email_event`/`smoke_event`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_smoke.py` 末尾追加（`AsyncMock`/`patch`/`np`/`SmokeFireProcessor`/`VLConfirmClient` 均已 import）：

```python
def _decode_data_url(data_url: str) -> np.ndarray:
    import base64
    import cv2

    buf = np.frombuffer(base64.b64decode(data_url.split(",", 1)[1]), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _vl_smoke_processor(vengine, extra_settings=None):
    settings = {
        "smoke_temporal_confirm_frames": "1",
        "smoke_enable_appearance_filter": "false",
        "smoke_vl_confirm_enabled": "true",
        "smoke_vl_confirm_prompt": "Verify",
        "smoke_vl_confirm_response_key": "smoke",
    }
    settings.update(extra_settings or {})
    return SmokeFireProcessor(
        source_id="s1",
        source_name="Cam1",
        rtsp_url="",
        rois=[],
        vengine_client=vengine,
        app_settings=settings,
    )


class TestSmokeVlConfirm:
    DET = [{"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "confidence": 0.95, "label": "smoke", "class_id": 0}]

    async def _run(self, processor, vl_result, frame):
        mock_client = AsyncMock(spec=VLConfirmClient)
        mock_client.confirm = AsyncMock(return_value=vl_result)
        with patch("core.smoke.processor.VLConfirmClient", return_value=mock_client):
            result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])
        return result, mock_client

    async def test_vl_reject_keeps_message_marked_false_positive(self):
        vengine = AsyncMock()
        vengine.detect.return_value = self.DET
        processor = _vl_smoke_processor(vengine)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result, _ = await self._run(processor, False, frame)

        assert len(result.messages) == 1
        assert result.messages[0]["false_positive"] is True
        assert "email_event" not in result.extra

    async def test_vl_confirm_keeps_message_and_event(self):
        vengine = AsyncMock()
        vengine.detect.return_value = self.DET
        processor = _vl_smoke_processor(vengine)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result, _ = await self._run(processor, True, frame)

        assert len(result.messages) == 1
        assert result.messages[0]["false_positive"] is False
        assert result.extra["email_event"]["event_type"] == "smoke"

    async def test_vl_fail_open_keeps_message_and_event(self):
        vengine = AsyncMock()
        vengine.detect.return_value = self.DET
        processor = _vl_smoke_processor(vengine)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result, _ = await self._run(processor, None, frame)

        assert len(result.messages) == 1
        assert result.messages[0]["false_positive"] is False
        assert "email_event" in result.extra

    async def test_vl_disabled_skips_client(self):
        vengine = AsyncMock()
        vengine.detect.return_value = self.DET
        processor = _vl_smoke_processor(vengine, {"smoke_vl_confirm_enabled": "false"})
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        with patch("core.smoke.processor.VLConfirmClient") as mock_cls:
            result = await processor.process_frame(frame, b"not-a-real-jpeg", frame.shape, [])

        mock_cls.assert_not_called()
        assert len(result.messages) == 1
        assert result.messages[0]["false_positive"] is False

    async def test_vl_annotated_full_image_sent_to_model(self):
        vengine = AsyncMock()
        vengine.detect.return_value = self.DET
        processor = _vl_smoke_processor(
            vengine,
            {"smoke_vl_confirm_image_source": "annotated", "smoke_vl_confirm_image_crop": "full"},
        )
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result, mock_client = await self._run(processor, True, frame)

        data_url = mock_client.confirm.await_args.args[0]
        decoded = _decode_data_url(data_url)
        assert decoded.shape[:2] == (100, 100)
        assert decoded.std() > 5  # 检测图上画了检测框，非纯黑（纯黑帧 std≈0）
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_smoke.py -q`
Expected: `TestSmokeVlConfirm` 中 reject/annotated/disabled 相关 FAIL（当前实现否决后 `result.messages == []`、开关仍读全局 key）

- [ ] **Step 3: 修改处理器**

`core/smoke/processor.py` 三处改动：

1. 顶部 import（line 23）：

```python
from core.vl_confirm import VLConfirmClient, build_vl_image_data_url
```

2. `process_frame` 中 VL 段落（lines 117-151）改为：

```python
        vl_rejected = False
        if post_result.has_alarm and confirmed:
            if self._vl_confirm_enabled():
                vl_result = await self._vl_confirm_alert(frame, annotated, primary_roi)
                if vl_result is False:
                    vl_rejected = True
                # True or None (fail-open) → keep alerts
        if post_result.has_alarm and confirmed:
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
        return result
```

3. `_vl_confirm_enabled`（lines 154-155）与 `_vl_confirm_alert`（lines 157-182）改为：

```python
    def _vl_confirm_enabled(self) -> bool:
        return str(self.app_settings.get("smoke_vl_confirm_enabled") or "false").lower() == "true"

    async def _vl_confirm_alert(
        self,
        frame: np.ndarray,
        annotated: np.ndarray,
        primary_roi: list[dict] | None,
    ) -> bool | None:
        """Ask the VL model to verify a smoke/fire alarm. Returns True/False/None."""
        image_data_url = build_vl_image_data_url(
            frame,
            annotated,
            str(self.app_settings.get("smoke_vl_confirm_image_source") or "original"),
            str(self.app_settings.get("smoke_vl_confirm_image_crop") or "roi"),
            primary_roi,
        )
        prompt = str(
            self.app_settings.get("smoke_vl_confirm_prompt")
            or DEFAULT_VL_CONFIRM_PROMPT
        )
        response_key = str(
            self.app_settings.get("smoke_vl_confirm_response_key")
            or DEFAULT_VL_CONFIRM_RESPONSE_KEY
        )

        client = VLConfirmClient(
            base_url=str(
                self.app_settings.get("vl_confirm_base_url")
                or "http://localhost:30000/v1"
            ),
            api_key=str(self.app_settings.get("vl_confirm_api_key") or "EMPTY"),
            model=str(self.app_settings.get("vl_confirm_model") or "/models/Mage-VL"),
            timeout=self._setting_int("vl_confirm_timeout", 60),
        )
        return await client.confirm(image_data_url, prompt, response_key)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_smoke.py tests/test_vl_confirm.py -q`
Expected: 全部 PASS

---

### Task 3: fire_door 处理器 — 插件级开关 + 图像选项 + 否决留痕

**Files:**
- Modify: `core/fire_door/processor.py:24,171-261`（import、`process_frame` VL 段落、`_vl_confirm_enabled`、`_vl_confirm_alert`）
- Test: `tests/test_fire_door.py:234-315`（改 `_vl_processor` 与 4 个现有 VL 测试，追加 1 个图像选项测试）

**Interfaces:**
- Consumes: Task 1 的 `build_vl_image_data_url`；设置 key `fire_door_vl_confirm_enabled` / `fire_door_vl_confirm_image_source` / `fire_door_vl_confirm_image_crop`。
- Produces: 与 Task 2 相同的消息契约（`false_positive` 键、否决时 extra 无 `email_event`/`fire_door_event`）。

- [ ] **Step 1: 更新/新增测试**

`tests/test_fire_door.py` 改动：

1. `_vl_processor`（lines 234-245）中 `"vl_confirm_enabled": "true"` 改为 `"fire_door_vl_confirm_enabled": "true"`。
2. 文件顶部追加解码 helper（`AsyncMock`/`patch`/`np` 已 import）：

```python
def _decode_data_url(data_url: str) -> np.ndarray:
    import base64
    import cv2

    buf = np.frombuffer(base64.b64decode(data_url.split(",", 1)[1]), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)
```

3. `test_vl_confirm_suppresses_alarm_when_model_returns_false`（lines 248-263）改名为 `test_vl_confirm_reject_keeps_message_marked_false_positive`，断言改为：

```python
    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is True
    assert "email_event" not in result.extra
```

4. `test_vl_confirm_allows_alarm_when_model_returns_true`（lines 266-281）末尾断言改为：

```python
    assert len(result.messages) == 1
    assert result.messages[0]["false_positive"] is False
    assert "email_event" in result.extra
```

5. `test_vl_confirm_fail_open_when_model_returns_none`（lines 284-299）末尾断言同上（`false_positive` False + `email_event` in extra）。
6. `test_vl_confirm_skipped_when_disabled`（line 305）settings 改为 `{"fire_door_vl_confirm_enabled": "false"}`。
7. 文件末尾追加：

```python
async def test_vl_annotated_full_image_sent_to_model():
    vengine = AsyncMock()
    vengine.classify.return_value = [{"label": "open", "confidence": 0.91, "class_id": 1}]
    processor = _processor(
        vengine,
        settings={
            "fire_door_vl_confirm_enabled": "true",
            "fire_door_vl_confirm_prompt": "Verify",
            "fire_door_vl_confirm_response_key": "open",
            "fire_door_vl_confirm_image_source": "annotated",
            "fire_door_vl_confirm_image_crop": "full",
        },
    )
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    mock_client = AsyncMock(spec=VLConfirmClient)
    mock_client.confirm = AsyncMock(return_value=True)

    with patch("core.fire_door.processor.VLConfirmClient", return_value=mock_client):
        await processor.process_frame(
            frame, b"frame", frame.shape,
            [[{"x": 10, "y": 10}, {"x": 90, "y": 10}, {"x": 90, "y": 90}, {"x": 10, "y": 90}]],
        )

    data_url = mock_client.confirm.await_args.args[0]
    decoded = _decode_data_url(data_url)
    assert decoded.shape[:2] == (100, 100)
    assert decoded.std() > 5  # 检测图上画了 ROI 标注，非纯黑（纯黑帧 std≈0）
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_fire_door.py -q`
Expected: 改名的 reject 测试 FAIL（当前否决后 `result.messages == []`）、图像选项测试 FAIL（当前开关读全局 key 不触发 VL）

- [ ] **Step 3: 修改处理器**

`core/fire_door/processor.py` 三处改动：

1. import（line 24）：

```python
from core.vl_confirm import VLConfirmClient, build_vl_image_data_url
```

2. `process_frame` VL 段落（lines 171-222）：

```python
        vl_rejected = False
        if alert_items and self._vl_confirm_enabled():
            vl_result = await self._vl_confirm_alert(frame, annotated, alert_items, roi_pixel_points)
            if vl_result is False:
                vl_rejected = True
            # True or None (fail-open) → keep alerts
        if alert_items:
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
        return result
```

3. `_vl_confirm_enabled`（lines 224-225）与 `_vl_confirm_alert`（lines 227-261）改为：

```python
    def _vl_confirm_enabled(self) -> bool:
        return str(self.app_settings.get("fire_door_vl_confirm_enabled") or "false").lower() == "true"

    async def _vl_confirm_alert(
        self,
        frame: np.ndarray,
        annotated: np.ndarray,
        alert_items: list[dict[str, Any]],
        roi_pixel_points: list[list[dict]],
    ) -> bool | None:
        """Ask the VL model to verify an alarm. Returns True/False/None."""
        best = max(alert_items, key=lambda item: float(item.get("confidence") or 0.0))
        roi_index = int(best.get("roi_index", 1)) - 1
        roi_points = (
            roi_pixel_points[roi_index]
            if 0 <= roi_index < len(roi_pixel_points)
            else None
        )

        image_data_url = build_vl_image_data_url(
            frame,
            annotated,
            str(self.app_settings.get("fire_door_vl_confirm_image_source") or "original"),
            str(self.app_settings.get("fire_door_vl_confirm_image_crop") or "roi"),
            roi_points,
        )
        prompt = str(
            self.app_settings.get("fire_door_vl_confirm_prompt")
            or DEFAULT_VL_CONFIRM_PROMPT
        )
        response_key = str(
            self.app_settings.get("fire_door_vl_confirm_response_key")
            or DEFAULT_VL_CONFIRM_RESPONSE_KEY
        )

        client = VLConfirmClient(
            base_url=str(
                self.app_settings.get("vl_confirm_base_url")
                or "http://localhost:30000/v1"
            ),
            api_key=str(self.app_settings.get("vl_confirm_api_key") or "EMPTY"),
            model=str(self.app_settings.get("vl_confirm_model") or "/models/Mage-VL"),
            timeout=self._setting_int("vl_confirm_timeout", 60),
        )
        return await client.confirm(image_data_url, prompt, response_key)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_fire_door.py -q`
Expected: 全部 PASS

---

### Task 4: 后端设置项 + 一次性迁移

**Files:**
- Modify: `backend/config.py:145-166`（DEFAULT_APP_SETTINGS）
- Modify: `backend/models/schemas.py:576-586`（AppSettingsUpdate）
- Modify: `backend/api/settings.py:30-77`（PLUGIN_SETTING_KEYS）
- Modify: `backend/db/database.py:330-393`（init_db 内调用迁移）+ 新增 `_migrate_vl_confirm_enabled` 函数（放在 `_now_iso` 附近）
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: 设置 key `smoke_vl_confirm_enabled`/`smoke_vl_confirm_image_source`/`smoke_vl_confirm_image_crop`/`fire_door_vl_confirm_enabled`/`fire_door_vl_confirm_image_source`/`fire_door_vl_confirm_image_crop`（默认 `"false"`/`"original"`/`"roi"`）；`vl_confirm_enabled` 不再出现。

- [ ] **Step 1: 写失败测试**

`tests/test_settings.py`：

1. `test_defaults_seeded`（lines 24-46）末尾追加：

```python
        assert all_settings["smoke_vl_confirm_enabled"] == "false"
        assert all_settings["smoke_vl_confirm_image_source"] == "original"
        assert all_settings["smoke_vl_confirm_image_crop"] == "roi"
        assert all_settings["fire_door_vl_confirm_enabled"] == "false"
        assert all_settings["fire_door_vl_confirm_image_source"] == "original"
        assert all_settings["fire_door_vl_confirm_image_crop"] == "roi"
        assert "vl_confirm_enabled" not in all_settings
```

2. 文件末尾（或 `TestSettingsDB` 内）追加迁移测试：

```python
    async def test_legacy_vl_confirm_enabled_is_migrated(self, init_db):
        """Legacy global vl_confirm_enabled=true migrates into per-scene keys, then disappears."""
        await update_settings({"vl_confirm_enabled": "true"})

        from backend.db.database import init_db as re_init
        await re_init()

        all_settings = await get_all_settings()
        assert all_settings["smoke_vl_confirm_enabled"] == "true"
        assert all_settings["fire_door_vl_confirm_enabled"] == "true"
        assert "vl_confirm_enabled" not in all_settings
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_settings.py -q`
Expected: 新断言 FAIL（key 不存在 / `vl_confirm_enabled` 仍在）

- [ ] **Step 3: 实现**

1. `backend/config.py`（lines 145-166）改为：

```python
    # VL secondary confirmation (shared endpoint) / VL 二次确认（共享端点）
    "vl_confirm_base_url": "http://localhost:30000/v1",
    "vl_confirm_api_key": "EMPTY",
    "vl_confirm_model": "/models/Mage-VL",
    "vl_confirm_timeout": "60",
    # VL secondary confirmation (per-scene) / VL 二次确认（场景级）
    "smoke_vl_confirm_enabled": "false",
    "smoke_vl_confirm_image_source": "original",
    "smoke_vl_confirm_image_crop": "roi",
    "smoke_vl_confirm_prompt": (
        "This image was flagged as containing smoke or fire. Verify the detection. "
        "Only confirm if you can clearly see smoke or fire in the image. "
        'Reply with ONLY: {"smoke": true} or {"smoke": false}.'
    ),
    "smoke_vl_confirm_response_key": "smoke",
    "fire_door_vl_confirm_enabled": "false",
    "fire_door_vl_confirm_image_source": "original",
    "fire_door_vl_confirm_image_crop": "roi",
    "fire_door_vl_confirm_prompt": (
        "This image was flagged as a potential OPEN door. Verify the detection. "
        "A door is OPEN if the door panel is visibly separated from the frame, "
        "showing a clear gap or opening (you can see a darker space behind/beside the panel). "
        "A door is CLOSED if the panel is flush within the frame with no visible opening. "
        "Only confirm OPEN if you can clearly see the gap. "
        'Reply with ONLY: {"open": true} or {"open": false}.'
    ),
    "fire_door_vl_confirm_response_key": "open",
```

（注意：prompt 文本保持与现有一字不差，只调整键的分组顺序；删除 `"vl_confirm_enabled": "false",`。）

2. `backend/models/schemas.py`（lines 576-586）改为：

```python
    # VL secondary confirmation (shared endpoint) / VL 二次确认（共享端点）
    vl_confirm_base_url: str | None = None
    vl_confirm_api_key: str | None = None
    vl_confirm_model: str | None = None
    vl_confirm_timeout: str | None = None
    # VL secondary confirmation (per-scene) / VL 二次确认（场景级）
    smoke_vl_confirm_enabled: str | None = None
    smoke_vl_confirm_image_source: str | None = None
    smoke_vl_confirm_image_crop: str | None = None
    smoke_vl_confirm_prompt: str | None = None
    smoke_vl_confirm_response_key: str | None = None
    fire_door_vl_confirm_enabled: str | None = None
    fire_door_vl_confirm_image_source: str | None = None
    fire_door_vl_confirm_image_crop: str | None = None
    fire_door_vl_confirm_prompt: str | None = None
    fire_door_vl_confirm_response_key: str | None = None
```

3. `backend/api/settings.py` `PLUGIN_SETTING_KEYS`（lines 30-77）：删除 `"vl_confirm_enabled",`，并在 `"smoke_vl_confirm_response_key",` 之前/之后补齐 6 个新 key：

```python
    "vl_confirm_base_url",
    "vl_confirm_api_key",
    "vl_confirm_model",
    "vl_confirm_timeout",
    "smoke_vl_confirm_enabled",
    "smoke_vl_confirm_image_source",
    "smoke_vl_confirm_image_crop",
    "smoke_vl_confirm_prompt",
    "smoke_vl_confirm_response_key",
    "fire_door_vl_confirm_enabled",
    "fire_door_vl_confirm_image_source",
    "fire_door_vl_confirm_image_crop",
    "fire_door_vl_confirm_prompt",
    "fire_door_vl_confirm_response_key",
```

4. `backend/db/database.py`：在 `_now_iso()` 函数（line 396）之前新增：

```python
async def _migrate_vl_confirm_enabled(db: aiosqlite.Connection) -> None:
    """One-time migration: copy legacy global ``vl_confirm_enabled`` into the
    per-scene ``{scene}_vl_confirm_enabled`` keys, then drop the global key.
    一次性迁移：将旧全局 VL 开关复制进各场景开关后删除全局 key。"""
    async with db.execute(
        "SELECT value FROM app_settings WHERE key = 'vl_confirm_enabled'"
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return
    for scene_key in ("smoke_vl_confirm_enabled", "fire_door_vl_confirm_enabled"):
        await db.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (scene_key, str(row[0])),
        )
    await db.execute("DELETE FROM app_settings WHERE key = 'vl_confirm_enabled'")
```

并在 `init_db` 内、`for key, value in DEFAULT_APP_SETTINGS.items()` 播种循环（line 384）之前加一行：

```python
        await _migrate_vl_confirm_enabled(db)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_settings.py tests/test_database.py -q`
Expected: 全部 PASS

---

### Task 5: 消息列表三态筛选（后端 API/DB）

**Files:**
- Modify: `backend/db/database.py:2526-2553`（`list_analysis_messages` 签名与 where 条件）
- Modify: `backend/api/messages.py:35,47-54`（query 参数）
- Test: `tests/test_messages.py`（lines 241/265 参数改名 + 新增 exclude 测试）

**Interfaces:**
- Produces: `GET /api/messages?false_positive_filter=all|only|exclude`（默认 `all`）；`list_analysis_messages(..., false_positive_filter: str = "all")`。前端 Task 6 依赖该参数。

- [ ] **Step 1: 写失败测试**

1. `tests/test_messages.py` line 241 与 line 265：`params={"false_positive_only": "true"}` 改为 `params={"false_positive_filter": "only"}`。
2. 在 `test_unmark_false_positive_clears_filter_match` 之后追加：

```python
    async def test_list_messages_false_positive_filter_exclude(self, async_client: AsyncClient):
        normal_id = await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "normal",
            }
        )
        await save_analysis_message(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_name": "Cam1",
                "source_id": "s1",
                "level": "alert",
                "message": "fp",
                "false_positive": True,
            }
        )

        excluded = await async_client.get("/api/messages", params={"false_positive_filter": "exclude"})
        assert excluded.status_code == 200
        excluded_data = excluded.json()
        assert len(excluded_data["items"]) == 1
        assert excluded_data["items"][0]["id"] == normal_id
        assert excluded_data["items"][0]["false_positive"] is False

        all_msgs = await async_client.get("/api/messages", params={"false_positive_filter": "all"})
        assert all_msgs.status_code == 200
        assert all_msgs.json()["total"] == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_messages.py -q`
Expected: 新测试 FAIL（`false_positive_filter` 参数被忽略 → exclude 返回 2 条）

- [ ] **Step 3: 实现**

1. `backend/db/database.py` `list_analysis_messages`：签名参数 `false_positive_only: bool = False` 改为 `false_positive_filter: str = "all"`；where 构造处：

```python
    if false_positive_filter == "only":
        where_clauses.append("false_positive = 1")
    elif false_positive_filter == "exclude":
        where_clauses.append("false_positive = 0")
```

2. `backend/api/messages.py`：

```python
    false_positive_filter: str = Query(default="all", description="all | only | exclude"),
```

调用处同步改为 `false_positive_filter=false_positive_filter,`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_messages.py -q`
Expected: 全部 PASS

---

### Task 6: 前端 message store 三态筛选

**Files:**
- Modify: `frontend/src/stores/message.js`
- Test: `frontend/src/stores/__tests__/message.test.js`

**Interfaces:**
- Consumes: Task 5 的 `false_positive_filter` API 参数。
- Produces: store 状态 `falsePositiveFilter`（`'exclude'` 默认 | `'all'` | `'only'`）与 action `setFalsePositiveFilter(value)`。Task 7 的 Messages.vue 依赖。

- [ ] **Step 1: 写失败测试**

`frontend/src/stores/__tests__/message.test.js` 末尾追加：

```js
describe('message store — false positive filter modes', () => {
  it('defaults to exclude and sends false_positive_filter to the API', async () => {
    listMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 })
    const store = useMessageStore()
    await store.fetchMessages()
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ false_positive_filter: 'exclude' })
    )
  })

  it('setFalsePositiveFilter switches modes and sanitises unknown values', async () => {
    listMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 })
    const store = useMessageStore()
    store.setFalsePositiveFilter('only')
    await store.fetchMessages()
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ false_positive_filter: 'only' })
    )
    store.setFalsePositiveFilter('bogus')
    expect(store.falsePositiveFilter).toBe('exclude')
  })

  it('exclude mode hides a message just marked as false positive locally', async () => {
    const store = useMessageStore()
    store.setFalsePositiveFilter('exclude')
    store.messages = [
      { id: 'a', false_positive: false },
      { id: 'b', false_positive: false },
    ]
    await store.markFalsePositive('b')
    expect(store.messages.map((m) => m.id)).toEqual(['a'])
  })

  it('only mode keeps only false positives after unmarking', async () => {
    const store = useMessageStore()
    store.setFalsePositiveFilter('only')
    store.messages = [
      { id: 'a', false_positive: true },
      { id: 'b', false_positive: true },
    ]
    await store.unmarkFalsePositive('a')
    expect(store.messages.map((m) => m.id)).toEqual(['b'])
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`
Expected: 新 describe 块 FAIL（`setFalsePositiveFilter` 不存在 / 参数名不匹配）

- [ ] **Step 3: 实现**

`frontend/src/stores/message.js`：

1. state（line 19）：`const falsePositiveOnly = ref(false)` → `const falsePositiveFilter = ref('exclude')`
2. `fetchMessages` 参数（line 42）：`false_positive_only: falsePositiveOnly.value || undefined,` → `false_positive_filter: falsePositiveFilter.value,`
3. 新增 helper（放在 `matchesActiveDateRange` 附近）：

```js
  function falsePositiveFilterMatches(isFalsePositive) {
    if (falsePositiveFilter.value === 'all') return true
    if (falsePositiveFilter.value === 'only') return Boolean(isFalsePositive)
    return !isFalsePositive
  }
```

4. WS `onmessage`（line 96）：`const matchesFalsePositive = !falsePositiveOnly.value || Boolean(msg.false_positive)` → `const matchesFalsePositive = falsePositiveFilterMatches(msg.false_positive)`
5. `setFalsePositiveOnly`（lines 146-149）改为：

```js
  function setFalsePositiveFilter(value) {
    falsePositiveFilter.value = ['exclude', 'all', 'only'].includes(value) ? value : 'exclude'
    clearSelection()
  }
```

6. `applyFalsePositiveFilterToLocalMessages`（lines 157-160）改为：

```js
  function applyFalsePositiveFilterToLocalMessages() {
    if (falsePositiveFilter.value === 'all') return
    messages.value = messages.value.filter((item) => falsePositiveFilterMatches(item.false_positive))
  }
```

7. 返回对象（lines 248-279）：`falsePositiveOnly,` → `falsePositiveFilter,`；`setFalsePositiveOnly,` → `setFalsePositiveFilter,`

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npm test`
Expected: 全部 PASS

---

### Task 7: Messages.vue 三态筛选 UI

**Files:**
- Modify: `frontend/src/views/Messages.vue:42-49`（模板）、`170-173`（handler）、`.false-positive-filter` 相关 CSS（删除不再使用的 `__label` 规则，保留容器规则）

**Interfaces:**
- Consumes: Task 6 的 `store.falsePositiveFilter` / `store.setFalsePositiveFilter`。

- [ ] **Step 1: 改模板**

lines 42-49 的误报开关块改为：

```vue
          <el-radio-group
            v-model="store.falsePositiveFilter"
            size="small"
            :aria-label="t('messages.falsePositiveFilterHint')"
            @change="handleFalsePositiveFilterChange"
          >
            <el-radio-button value="exclude">{{ t('messages.filterValidAlerts') }}</el-radio-button>
            <el-radio-button value="all">{{ t('messages.filterAll') }}</el-radio-button>
            <el-radio-button value="only">{{ t('messages.filterFalsePositives') }}</el-radio-button>
          </el-radio-group>
```

- [ ] **Step 2: 改 handler（lines 170-173）**

```js
async function handleFalsePositiveFilterChange(value) {
  store.setFalsePositiveFilter(value)
  await refresh(1, store.pageSize)
}
```

- [ ] **Step 3: i18n 文案（zh-CN.js / en-US.js `messages` 段）**

zh-CN：删除 `falsePositiveOnly` / `falsePositiveOnlyHint` 两行，追加：

```js
    filterValidAlerts: '有效告警',
    filterAll: '全部',
    filterFalsePositives: '只看误报',
    falsePositiveFilterHint: '按误报状态筛选消息',
```

en-US（lines 201-202 同样删除两行）追加：

```js
    filterValidAlerts: 'Valid alerts only',
    filterAll: 'All',
    filterFalsePositives: 'False positives only',
    falsePositiveFilterHint: 'Filter messages by false-positive state',
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（无未定义引用报错）

---

### Task 8: Settings.vue 按插件 VL 配置 UI

**Files:**
- Modify: `frontend/src/views/Settings.vue`（模板 lines 822-855 smoke VL 段、933-966 fire_door VL 段；脚本 lines 1297-1303、1304-1328、1404-1431、1578）
- Modify: `frontend/src/i18n/locales/zh-CN.js` / `en-US.js`（`settings` 段新增 8 个 key）

**Interfaces:**
- Consumes: Task 4 的后端新 key（经 `PUT /api/settings` 白名单）。

- [ ] **Step 1: i18n settings 段**

zh-CN `settings` 段，`vlConfirmResponseKey`（line 631）之后追加：

```js
    vlConfirmImageSource: '确认图像来源',
    vlConfirmImageSourceHint: '发送给 VL 模型的图像：原图（无标注）或检测图（含检测框标注）。',
    vlConfirmImageSourceOriginal: '原图',
    vlConfirmImageSourceAnnotated: '检测图',
    vlConfirmImageCrop: '图像裁剪方式',
    vlConfirmImageCropHint: 'ROI 裁剪仅发送告警 ROI 区域；整图发送完整画面。',
    vlConfirmImageCropRoi: 'ROI 裁剪',
    vlConfirmImageCropFull: '整图',
```

en-US 对应段追加：

```js
    vlConfirmImageSource: 'Image source',
    vlConfirmImageSourceHint: 'Image sent to the VL model: original (no annotations) or detected (with detection boxes).',
    vlConfirmImageSourceOriginal: 'Original',
    vlConfirmImageSourceAnnotated: 'Detected',
    vlConfirmImageCrop: 'Crop mode',
    vlConfirmImageCropHint: 'ROI crop sends only the alert ROI area; full sends the complete frame.',
    vlConfirmImageCropRoi: 'ROI crop',
    vlConfirmImageCropFull: 'Full frame',
```

- [ ] **Step 2: Settings.vue 脚本**

1. `VL_CONFIRM_GLOBAL_KEYS`（lines 1297-1303）删除 `'vl_confirm_enabled',`，保留其余 4 个。
2. `PROCESSOR_RESTART_SETTING_KEYS`（lines 1304-1328）：在 `...VL_CONFIRM_GLOBAL_KEYS,` 之后追加 6 行：

```js
  'smoke_vl_confirm_enabled',
  'smoke_vl_confirm_image_source',
  'smoke_vl_confirm_image_crop',
  'fire_door_vl_confirm_enabled',
  'fire_door_vl_confirm_image_source',
  'fire_door_vl_confirm_image_crop',
```

3. `SMOKE_PLUGIN_SETTING_KEYS`（lines 1404-1418）：在 `...VL_CONFIRM_GLOBAL_KEYS,` 之后追加：

```js
  'smoke_vl_confirm_enabled',
  'smoke_vl_confirm_image_source',
  'smoke_vl_confirm_image_crop',
```

4. `FIRE_DOOR_PLUGIN_SETTING_KEYS`（lines 1419-1431）：在 `...VL_CONFIRM_GLOBAL_KEYS,` 之后追加：

```js
  'fire_door_vl_confirm_enabled',
  'fire_door_vl_confirm_image_source',
  'fire_door_vl_confirm_image_crop',
```

5. 表单默认值（line 1578）`vl_confirm_enabled: 'false',` 替换为：

```js
  smoke_vl_confirm_enabled: 'false',
  smoke_vl_confirm_image_source: 'original',
  smoke_vl_confirm_image_crop: 'roi',
  fire_door_vl_confirm_enabled: 'false',
  fire_door_vl_confirm_image_source: 'original',
  fire_door_vl_confirm_image_crop: 'roi',
```

- [ ] **Step 3: Settings.vue 模板**

1. smoke VL 段（lines 830-853）：开关绑定改为 `form.smoke_vl_confirm_enabled`（其余不变）；在「超时时间」项（lines 845-847）之后、「确认提示词」项之前插入两个下拉：

```vue
                      <el-form-item :label="t('settings.vlConfirmImageSource')">
                        <el-select v-model="form.smoke_vl_confirm_image_source">
                          <el-option :label="t('settings.vlConfirmImageSourceOriginal')" value="original" />
                          <el-option :label="t('settings.vlConfirmImageSourceAnnotated')" value="annotated" />
                        </el-select>
                        <p class="form-hint">{{ t('settings.vlConfirmImageSourceHint') }}</p>
                      </el-form-item>
                      <el-form-item :label="t('settings.vlConfirmImageCrop')">
                        <el-select v-model="form.smoke_vl_confirm_image_crop">
                          <el-option :label="t('settings.vlConfirmImageCropRoi')" value="roi" />
                          <el-option :label="t('settings.vlConfirmImageCropFull')" value="full" />
                        </el-select>
                        <p class="form-hint">{{ t('settings.vlConfirmImageCropHint') }}</p>
                      </el-form-item>
```

2. fire_door VL 段（lines 941-965）：开关绑定改为 `form.fire_door_vl_confirm_enabled`（其余不变）；「超时时间」项（lines 956-958）之后、「确认提示词」项之前插入：

```vue
                      <el-form-item :label="t('settings.vlConfirmImageSource')">
                        <el-select v-model="form.fire_door_vl_confirm_image_source">
                          <el-option :label="t('settings.vlConfirmImageSourceOriginal')" value="original" />
                          <el-option :label="t('settings.vlConfirmImageSourceAnnotated')" value="annotated" />
                        </el-select>
                        <p class="form-hint">{{ t('settings.vlConfirmImageSourceHint') }}</p>
                      </el-form-item>
                      <el-form-item :label="t('settings.vlConfirmImageCrop')">
                        <el-select v-model="form.fire_door_vl_confirm_image_crop">
                          <el-option :label="t('settings.vlConfirmImageCropRoi')" value="roi" />
                          <el-option :label="t('settings.vlConfirmImageCropFull')" value="full" />
                        </el-select>
                        <p class="form-hint">{{ t('settings.vlConfirmImageCropHint') }}</p>
                      </el-form-item>
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build && npm test`
Expected: 构建成功、单测通过

---

### Task 9: 全量回归 + 收尾检查

- [ ] **Step 1: 后端全量测试**

Run: `uv run pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 2: 前端全量测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: 全部 PASS / 构建成功

- [ ] **Step 3: 残留引用检查**

Run: `rg "vl_confirm_enabled" --glob '!docs/**' --glob '!*.tar.gz' .`（仓库根）
Expected: 仅剩 `smoke_vl_confirm_enabled` / `fire_door_vl_confirm_enabled`（及迁移函数内的旧 key 字面量）；`rg "false_positive_only" .` 无残留（docs 除外）。

- [ ] **Step 4: 汇报**

向用户汇报改动清单与测试结果；不 commit（由用户决定）。
