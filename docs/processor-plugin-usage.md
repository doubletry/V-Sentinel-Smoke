# Processor plugin template

This project is structured as a generic video-AI template plus scene plugins.
The default scene plugin is `smoke`, which detects `smoke` and `fire` labels.

## Layers

- `core/base_processor.py`: shared RTSP, ROI, drawing, inference helper, and result-push lifecycle.
- `core/analysis_agent.py`: generic aggregation/agent template.
- `core/smoke/`: smoke/fire constants, post-processing, processor, and event-email helpers.
- `backend/processing/`: backend adapters and plugin registry.
- `frontend/src/views/Settings.vue`: configurable model, post-processing, email cooldown, and email template settings.

## Smoke plugin

Set the DB-backed setting below to enable the smoke/fire scene:

```json
{
  "processor_plugin": "smoke"
}
```

The smoke plugin only requires the detection service. It forwards `model_name`, optional `model_version`, confidence, NMS, and ROI to V-Engine detection, then applies the temporal smoke/fire post-processor.

## Event email templates

Event email subject/body templates support `{element}` placeholders. The backend exposes the supported placeholder list through:

```text
GET /api/settings/email/template-placeholders
```

Important placeholders include:

- `{local_time}`
- `{timezone}`
- `{source_name}`
- `{source_id}`
- `{event_type}`
- `{event_label}`
- `{labels}`
- `{confidence_percent}`
- `{detection_count}`
- `{frame_id}`
- `{active_tracks}`
- `{site_title}`

Screenshots are attached by the backend automatically when the smoke/fire processor emits an alert event.
