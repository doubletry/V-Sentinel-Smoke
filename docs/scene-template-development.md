# 后端场景模板开发指南

本文档说明如何基于 `backend.processing.template.TemplateSceneProcessor`
开发一个新的后端场景插件。模板是可运行代码，不依赖外部 AI 服务，方便先完成
数据流验证，再替换为真实模型推理。

## 运行链路

1. 视频源绑定一个 `scene_id`。
2. `ProcessorManager` 根据 `source.scene_id` 选择处理器类。
3. `BaseVideoProcessor` 读取 RTSP 帧并把 ROI 转换为像素坐标。
4. 子类实现 `process_frame(frame, encoded, shape, roi_pixel_points)`。
5. 返回 `AnalysisResult`：
   - `detections/classifications/ocr_texts/actions` 用于标注和后续分析。
   - `messages` 会广播到前端并持久化到数据库。
   - `annotated_frame` 会推送到 MediaMTX 输出流。
   - `extra["event"]` 会交给通知调度器，按视频源绑定策略发送 SMTP 或
     Webhook。

## 新建场景步骤

复制模板目录：

```bash
cp -R backend/processing/template backend/processing/my_scene
```

然后修改：

1. `backend/processing/my_scene/processor.py`
   - 改类名，例如 `MySceneProcessor`。
   - 在 `process_frame()` 中替换自定义处理逻辑。
2. `backend/processing/my_scene/metadata.py`
   - 修改 `label_zh` 和 `label_en`。
3. `backend/processing/my_scene/__init__.py`
   - 导出新处理器类。
4. `backend/processing/registry.py`
   - 把 `"my_scene": MySceneProcessor` 加入 `PROCESSOR_PLUGINS`。
5. 在数据库初始化中 seed 场景元数据，或通过未来的场景管理接口写入。

## `process_frame()` 输入说明

```python
async def process_frame(
    self,
    frame: np.ndarray,
    encoded: bytes,
    shape: tuple[int, int, int],
    roi_pixel_points: list[list[dict]],
) -> AnalysisResult:
    ...
```

- `frame`：OpenCV BGR 图像，可直接用于裁剪、画框和模型前处理。
- `encoded`：当前帧 JPEG 字节，可上传给外部推理服务。
- `shape`：`(height, width, channels)`。
- `roi_pixel_points`：当前视频源 ROI 的像素坐标列表。

## 返回结果与持久化

`messages` 中的每条消息应包含：

```python
{
    "timestamp": now,
    "source_name": self.source_name,
    "source_id": self.source_id,
    "level": "info",
    "message": "业务描述",
}
```

这些消息会被 `AnalysisAgent` 统一广播和持久化，不需要场景插件直接写数据库。

## 通知事件

当需要触发通知时，返回：

```python
AnalysisResult(
    messages=[message],
    extra={
        "event": {
            "timestamp": now,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "event_type": "my_event",
            "event_label": "我的事件",
            "labels": ["my_event"],
            "confidence": 0.92,
            "detection_count": 1,
            "frame_id": frame_id,
            "active_tracks": 0,
        }
    },
)
```

通知调度器会根据视频源的 `notification_policy_ids` 选择策略；未绑定策略时使用
`default-alert-policy`。邮件通过 SMTP 直连发送，Webhook 已预留。

## 真实运行验证建议

1. 使用空白数据库启动后端。
2. 创建视频源并设置 `scene_id="template"`。
3. 启动处理器，确认：
   - `/api/processor/status` 显示运行中。
   - 前端消息页收到模板消息。
   - 数据库 `analysis_messages` 中有记录。
   - 若通知 provider 已启用，SMTP/Webhook 收到事件。
