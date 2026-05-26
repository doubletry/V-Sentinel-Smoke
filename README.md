[中文文档](README_zh.md)

# V-Sentinel

**AI Video Surveillance Analysis Platform**

V-Sentinel is a full-stack video surveillance AI analysis platform that integrates with the [V-Engine](https://github.com/doubletry/V-Engine) gRPC AI inference microservice. It provides a Vue 3 frontend for live video monitoring and a high-concurrency FastAPI backend for real-time multi-camera AI analysis.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        V-Sentinel Platform                           │
│                                                                      │
│  ┌─────────────────┐         ┌──────────────────────────────────┐   │
│  │  Vue 3 Frontend │◄──WS────│         FastAPI Backend          │   │
│  │  (Element Plus) │◄──REST──│    (uvicorn, asyncio, grpc.aio)  │   │
│  └────────┬────────┘         └──────────────┬───────────────────┘   │
│           │                                 │                       │
│           │ WebRTC (WHEP)                   │ gRPC (async)          │
│           ▼                                 ▼                       │
│  ┌─────────────────┐         ┌──────────────────────────────────┐   │
│  │ External RTSP / │         │          V-Engine                │   │
│  │ WebRTC Gateway  │         │  Detection / Classification /   │   │
│  │ (e.g. MediaMTX) │         │  Action / OCR / Upload           │   │
│  └─────────────────┘         │                                  │   │
│                               └──────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  core/  — Standalone Processor SDK                           │   │
│  │  Develop & test processors independently, then plug into     │   │
│  │  the full backend with zero code changes.                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘

Backend Async Processing Architecture:
┌─────────────────────────────────────────────────────────────────┐
│  Thread Pool: RTSP Frame Pulling (1 thread per camera)          │
│  ┌─────────────────────────────────────────────────┐            │
│  │ av.open(rtsp) → decode → TurboJPEG.encode → Q  │            │
│  └─────────────────────┬───────────────────────────┘            │
│                        │ frames via asyncio.Queue               │
│                        ▼                                        │
│  AsyncIO Event Loop (single thread, all coroutines)             │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Camera-1: await process_frame()                 │            │
│  │   ├─ await vengine.detect()   (gRPC I/O)        │            │
│  │   ├─ await vengine.ocr()      (gRPC I/O)        │            │
│  │   ├─ asyncio.gather(detect, ocr) — concurrent  │            │
│  │   └─ ws_manager.broadcast()                     │            │
│  │ Camera-2: (interleaved)                         │            │
│  │ Camera-N: ...                                   │            │
│  └─────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3 + Element Plus + Vite |
| Backend | FastAPI (Python, fully async) |
| Video Streaming | External RTSP/WebRTC gateway (MediaMTX-compatible) |
| AI Inference | V-Engine gRPC microservices |
| JPEG Encoding | TurboJPEG (via PyTurboJPEG) |
| RTSP Push | Persistent av container per camera |
| gRPC Client | grpc.aio (async gRPC) |
| Real-time | WebSocket |
| ROI Config | YAML import/export (pyyaml) |
| Python Env | uv + pyproject.toml |
| Database | SQLite via aiosqlite |
| Processor SDK | `core/` standalone package |

---

## Prerequisites

- **Node.js** >= 18
- **Python** >= 3.11
- **uv** — [install](https://docs.astral.sh/uv/getting-started/installation/)
- **libturbojpeg** — required by PyTurboJPEG (`apt install libturbojpeg0-dev` on Debian/Ubuntu)
- **Optional video gateway** — a MediaMTX-compatible RTSP/WebRTC gateway is only required for the Video Wall page
- **V-Engine** — running gRPC microservices (see [V-Engine repo](https://github.com/doubletry/V-Engine))

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/doubletry/V-Sentinel.git
cd V-Sentinel

# Install Python dependencies (includes PyTurboJPEG, pyyaml, and all others)
uv sync
```

### 2. Start the backend

```bash
# Default port 8000 — use any port you like
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation: `http://localhost:<port>/docs`

### 3. Start the frontend (dev mode)

```bash
cd frontend
npm install

# The Vite dev proxy defaults to backend port 8000.
# Override with VITE_BACKEND_PORT if your backend runs on a different port:
#   VITE_BACKEND_PORT=9000 npm run dev
npm run dev
```

The frontend will be available at http://localhost:5173

> **Note:** The frontend uses relative URLs for all API and WebSocket calls, so it
> works with any backend port — no hardcoded addresses.

### 4. Build frontend for production

```bash
cd frontend
npm run build
```

FastAPI automatically serves the built frontend from `/` when `frontend/dist/` exists.

---

## Configuration

Only a small set of runtime options are environment-based. Create a `.env` file
in the project root if you need to override them:

```dotenv
# HTTP service port
BACKEND_PORT=8000

# Database
DB_PATH=./v_sentinel.db
```

Most operational settings are stored in the database and edited in the **Settings**
page after the app starts, including:

- V-Engine host/ports and service toggles
- MediaMTX RTSP / WebRTC base addresses
- MediaMTX RTSP / WebRTC usernames and passwords
- smoke/fire detection thresholds
- email notification templates and recipients

Runtime message thumbnails are persisted beside the database in `message_thumbnails/`. Exported false-positive original/detected images are persisted in `false_positives/`.

### MediaMTX gateway settings

The Video Wall uses an external MediaMTX-compatible gateway.

- **RTSP Address** is the base address used when creating online sources.
- **RTSP Username / Password** are injected into saved RTSP URLs so protected
  streams can be opened without manual URL editing.
- **WebRTC Address** is the base WHEP address used by the frontend player.
- **WebRTC Username / Password** are sent when the browser negotiates playback.

When the MediaMTX RTSP address or RTSP credentials change, V-Sentinel
automatically rewrites all saved online-source RTSP URLs to keep the same route
path under the new base address. When the WebRTC address or WebRTC credentials
change, existing frontend players reconnect with the new playback settings.

### Smoke / fire advanced settings

The smoke/fire scene uses a multi-stage post-processor:

- **Detection Confidence / NMS** tune the raw detector output.
- **Temporal Confirm Frames / Window / Max Miss Frames** control how many
  consistent detections are required before an alarm is considered real.
- **Alarm Hold Time** keeps the alarm active briefly after short detection gaps.
- **Advanced thresholds** filter glare, white objects, motion blur, hard edges,
  and static clutter that can look like smoke.

If your scene is already stable, keep the advanced thresholds at their defaults
and only adjust them when you see a clear false-positive pattern.

### Email template placeholders

Event email templates support placeholders returned by
`/api/settings/email/template-placeholders`, including:

`{site_title}`, `{local_time}`, `{timezone}`, `{source_name}`, `{source_id}`,
`{event_type}`, `{event_label}`, `{labels}`, `{confidence_percent}`,
`{detection_count}`, `{frame_id}`, and `{active_tracks}`.

### Frontend proxy port

During development, the Vite dev server proxies `/api` and `/ws` requests to the
backend. The target port is read from the `VITE_BACKEND_PORT` environment variable
(defaults to `8000`):

```bash
VITE_BACKEND_PORT=9000 npm run dev
```

---

## Core Package — Standalone Processor SDK

The `core/` directory is a self-contained Python package (`v-sentinel-core`) that
lets you develop and test video processors **independently** of the full backend.

### Install

```bash
pip install ./core            # minimal install
pip install ./core[grpc]      # with V-Engine gRPC support
```

### Usage

```python
from core.base_processor import BaseVideoProcessor, AnalysisResult

class MyProcessor(BaseVideoProcessor):
    async def process_frame(self, frame, encoded, shape, roi_pixel_points):
        # Your AI logic here
        annotated = self.draw_on_frame(frame, AnalysisResult())
        return AnalysisResult(annotated_frame=annotated)
```

Run standalone:

```python
from core.runner import run_processor
from my_processor import MyProcessor

run_processor(
    MyProcessor,
    rtsp_input="rtsp://localhost:8554/cam1",
    mediamtx_rtsp_addr="rtsp://localhost:8554",
)
```

Once ready, add a thin backend adapter in `backend/processing/`, register it in
`backend/processing/registry.py`, add a scene definition, and bind each video
source to that scene with `scene_id`.

See [`core/README.md`](core/README.md) for full details.
See [`docs/processor-plugin-usage.md`](docs/processor-plugin-usage.md) for the
core-template + backend-adapter workflow.

---

## Proto Generation

The `.proto` sources and the generated Python stubs (`*_pb2.py`,
`*_pb2_grpc.py`) both live in the canonical `core/proto/` package.
To regenerate from the latest proto files:

```bash
bash core/proto/generate.sh
```

---

## Creating a Custom Processor

Subclass `BaseVideoProcessor` in `backend/processing/`:

```python
from backend.processing.base import BaseVideoProcessor, AnalysisResult
from backend.models.schemas import AnalysisMessage
import asyncio
from datetime import datetime, timezone

class MyProcessor(BaseVideoProcessor):
    async def process_frame(self, frame, encoded, shape, roi_pixel_points):
        detections, ocr = await asyncio.gather(
            self.vengine.detect(
                shape=shape,
                model_name="yolov8n",
                image_bytes=encoded,
            ),
            self.vengine.ocr(
                shape=shape,
                model_name="paddleocr",
                image_bytes=encoded,
            ),
        )
        messages = []
        if detections:
            messages.append(AnalysisMessage(
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_name=self.source_name,
                source_id=self.source_id,
                level="info",
                message=f"Detected: {', '.join(d['label'] for d in detections)}",
            ))
        result = AnalysisResult(detections=detections, ocr_texts=ocr, messages=messages)
        result.annotated_frame = await asyncio.to_thread(self.draw_on_frame, frame, result)
        return result
```

Register it in `backend/processing/registry.py`, then bind a video source to
the scene:

```json
{
    "name": "Factory Camera 1",
    "route_path": "factory/cam-1",
    "scene_id": "my_scene"
}
```

See [`docs/processor-plugin-usage.md`](docs/processor-plugin-usage.md).

---

## API Reference

### Sources

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sources` | Create video source |
| `GET` | `/api/sources` | List all sources |
| `GET` | `/api/sources/{id}` | Get source with ROIs |
| `PUT` | `/api/sources/{id}` | Update source and ROIs |
| `DELETE` | `/api/sources/{id}` | Delete source |
| `GET` | `/api/sources/by-rtsp?rtsp_url=` | Get source by RTSP URL |

### ROI Import / Export

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sources/{id}/rois/export` | Export ROIs as YAML |
| `POST` | `/api/sources/{id}/rois/import` | Import ROIs from YAML (with tag validation) |

### Processor

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/processor/start` | Start AI analysis |
| `POST` | `/api/processor/stop` | Stop AI analysis |
| `GET` | `/api/processor/status` | Get all processor statuses |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws/messages` | Real-time analysis message stream |

### Accounts & Access Control

The `user` role is restricted to the `/messages` view only. The frontend
router redirects `user`-role logins to `/messages`, and the backend trims
the `user` role's permission set accordingly. Operators and administrators
keep the full live-video and settings access they had previously.

Account management lives under `Settings → User Management` (admin-only):

- `POST /api/users`, `PATCH /api/users/{username}`, `DELETE /api/users/{username}`,
  `POST /api/users/{username}/password` cover create / update / delete / admin
  password reset. The API refuses to delete the signed-in user or the last
  admin, and refuses to ban the signed-in user or the last unbanned admin.
- Banned (`401 Account banned`) or expired (`401 Account expired`) accounts
  are rejected immediately on the next request; the existing token does
  not have to expire first.
- Three settings keys control per-role default expiration (in days, `0` or
  empty = never): `account_expiration_days_user`,
  `account_expiration_days_operator`, `account_expiration_days_admin`.
  An explicit `expires_at` on `POST /api/users` overrides the role default.

Brute-force login protection (admin-only):

- Settings keys `login_lockout_max_attempts`,
  `login_lockout_window_seconds`, `login_lockout_duration_seconds` control
  IP-level lockout. `duration_seconds = 0` means the IP stays blocked until
  an administrator unblocks it.
- `GET /api/access/blocked-ips`, `DELETE /api/access/blocked-ips/{ip}`, and
  `POST /api/access/blocked-ips` (optional manual block) live under the
  `users:*` permission.
- A blocked IP receives HTTP `403` with `detail.code = IP_BLOCKED` and a
  `blocked_until` ISO timestamp; the frontend renders a friendly message.

---

## Docker

This repository now ships a **single-container** deployment flow.

```bash
./scripts/build_docker.sh
docker run -d \
  --name v-sentinel \
  --add-host=host.docker.internal:host-gateway \
  --add-host=docker.internal:host-gateway \
  -p 8000:8000 \
  -e DB_PATH=/app/data/v_sentinel.db \
  -v "$(pwd)/data:/app/data" \
  v-sentinel:latest
```

- Frontend, REST API, WebSocket, and persisted message thumbnails are all served from port `8000`
- `docker-compose` is no longer required
- MediaMTX is not bundled into the image; configure any external RTSP/WebRTC gateway in the Settings page if you need live video playback
- The container runtime now merges `NO_PROXY` / `no_proxy` defaults for localhost, Docker host aliases, and private LAN ranges so local service traffic bypasses proxies by default

See [`docs/docker-deployment.md`](docs/docker-deployment.md) for details.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
