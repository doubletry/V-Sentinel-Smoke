# Processor plugin template

This project is structured as a generic video-AI template plus scene plugins.
The default scene plugin is `smoke`, which detects `smoke` and `fire` labels.

## Layers

- `core/base_processor.py`: shared RTSP, ROI, drawing, inference helper, and result-push lifecycle.
- `core/analysis_agent.py`: generic aggregation/agent template.
- `core/notification_client.py`: direct SMTP and reserved Webhook notification providers.
- `core/smoke/`: smoke/fire constants, post-processing, processor, and event-email helpers.
- `backend/processing/`: backend adapters and plugin registry.
- `backend/api/scenes.py`: scene catalog API. A video source is designed to bind to exactly one scene.
- `backend/api/video_gateways.py`: video gateway API. MediaMTX RTSP and WebRTC use the same stored username/password while applying protocol-specific authentication at the client side.
- `backend/api/notifications.py`: notification provider/template/policy APIs. Email and Webhook are the first two reserved channel types.
- `backend/api/access.py`: built-in user/operator/admin role catalog for the three-level RBAC model.
- `frontend/src/views/Settings.vue`: configurable model, post-processing, email cooldown, and email template settings.

## Template foundation APIs

Blank databases are seeded with:

- `smoke` scene metadata.
- `default-mediamtx` video gateway.
- disabled `default-email` SMTP provider.
- disabled `default-webhook` provider.
- `default-event-email` template.
- `default-alert-policy` policy.

The foundation endpoints are:

```text
GET  /api/scenes
GET  /api/scenes/{scene_id}
GET  /api/video-gateways
POST /api/video-gateways
PUT  /api/video-gateways/{gateway_id}
GET  /api/notifications/providers
POST /api/notifications/providers
PUT  /api/notifications/providers/{provider_id}
GET  /api/notifications/templates
POST /api/notifications/templates
PUT  /api/notifications/templates/{template_id}
GET  /api/notifications/policies
POST /api/notifications/policies
PUT  /api/notifications/policies/{policy_id}
GET  /api/access/roles
```

RBAC roles are intentionally simple at this stage:

- `user`: view video, sources, and messages.
- `operator`: user permissions plus source operation and message annotation.
- `admin`: full platform configuration and user-management permissions.

The next implementation phases should wire these definitions into request-time
authorization and frontend route/action guards.

## Frontend expert mode

The Settings page exposes a user-friendly mode switch. Advanced smoke/fire
thresholds and thread-pool controls are hidden until expert mode is enabled, so
regular operators can configure common fields without navigating low-frequency
tuning options.

## Smoke plugin

Set the DB-backed setting below to enable the smoke/fire scene:

```json
{
  "processor_plugin": "smoke"
}
```

The smoke plugin only requires the detection service. It forwards `model_name`, optional `model_version`, confidence, NMS, and ROI to V-Engine detection, then applies the temporal smoke/fire post-processor.

## Notifications and SMTP email

Runtime event notifications are now routed through
`backend.notifications.dispatcher.NotificationDispatcher`.

- Email uses direct SMTP through `core.notification_client.SmtpNotificationProvider`.
- Webhook is reserved through `core.notification_client.WebhookNotificationProvider`.
- Sources can bind notification policies through `notification_policy_ids`.
- If a source has no policy binding, the dispatcher falls back to `default-alert-policy`.
- Cooldown is enforced per policy/source/event type.

The legacy email gRPC client remains in `core/email_client.py` for template helper
compatibility and tests, but event delivery should use notification providers.

## Event template placeholders

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
