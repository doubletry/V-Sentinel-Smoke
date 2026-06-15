# Docker Deployment

## Configuration

The application reads environment variables from a `.env` file at startup (via `pydantic-settings`). Copy `.env.example` to `.env` and adjust values for your deployment:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Default | Description |
|---|---|---|
| `BACKEND_PORT` | `8000` | Backend HTTP server port |
| `DB_PATH` | `./v_sentinel.db` | SQLite database path |
| `V_SENTINEL_AUTH_SECRET` | (random) | HMAC secret for API token signing. **Must be set in production**, otherwise tokens are invalidated on restart. |
| `V_SENTINEL_ADMIN_PASSWORD` | `admin` | Default admin password (first bootstrap) |
| `V_SENTINEL_CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |
| `VITE_APP_BASE_PATH` | `/` | Frontend SPA base path for sub-path reverse proxy |
| `VITE_API_BASE_URL` | (auto) | Explicit API base URL |
| `VITE_WS_BASE_URL` | (auto) | Explicit WebSocket base URL |
| `VITE_MEDIAMTX_WEBRTC_URL` | `http://localhost:8889` | MediaMTX WebRTC URL for frontend player |

When running with Docker, you can either:

1. **Mount a `.env` file** into the container (recommended for production):
   ```bash
   docker run -d \
     --name v-sentinel \
     -v "$(pwd)/.env:/app/.env:ro" \
     ...
   ```

2. **Pass variables directly** via `-e` flags:
   ```bash
   docker run -d \
     --name v-sentinel \
     -e V_SENTINEL_AUTH_SECRET=your-secret-here \
     -e V_SENTINEL_CORS_ORIGINS=https://your-domain.com \
     ...
   ```

> **Note**: `V_SENTINEL_AUTH_SECRET` is critical for production. Without it, all API tokens become invalid on every container restart, forcing users to re-login.

## Build

```bash
./scripts/build_docker.sh
```

The build script automatically reads the current shell proxy settings (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, and their lowercase variants) and passes them to `docker build` only for the image build. If the detected proxy host is `127.0.0.1` / `localhost`, it is rewritten to `host.docker.internal` for Docker build networking.

When an HTTPS proxy is present:

- run `RELAX_HTTPS_VERIFICATION=true ./scripts/build_docker.sh` if you need npm / pip to relax HTTPS verification behind a self-signed interception proxy
- leave `RELAX_HTTPS_VERIFICATION` unset to keep normal HTTPS verification
- the relaxed mode is a build-time-only compatibility fallback for trusted internal networks, because it reduces HTTPS verification for npm / pip dependency downloads
- pip relaxation only covers the default PyPI hosts added in the Dockerfile (`pypi.org`, `pypi.python.org`, and `files.pythonhosted.org`)

If the shell also exposes a readable PEM CA file path (`BUILD_CA_CERT`, `NODE_EXTRA_CA_CERTS`, `NPM_CONFIG_CAFILE`, `PIP_CERT`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, or `SSL_CERT_FILE`), that certificate is mounted into the build as an additional fallback.

You can override the image name or tag:

```bash
IMAGE_NAME=my-registry/v-sentinel IMAGE_TAG=2026.04.03 ./scripts/build_docker.sh
```

## Run

The application is packaged as a **single container**. It serves the built frontend, the REST API, the WebSocket endpoint, and the persisted message thumbnails from the same process.

**Recommended: mount `.env` file (production)**

```bash
docker run -d \
  --name v-sentinel \
  --add-host=host.docker.internal:host-gateway \
  --add-host=docker.internal:host-gateway \
  -p 8000:8000 \
  -v "$(pwd)/.env:/app/.env:ro" \
  -v "$(pwd)/data:/app/data" \
  v-sentinel:latest
```

**Alternative: pass variables via `-e` flags**

```bash
docker run -d \
  --name v-sentinel \
  --add-host=host.docker.internal:host-gateway \
  --add-host=docker.internal:host-gateway \
  -p 8000:8000 \
  -e BACKEND_PORT=8000 \
  -e DB_PATH=/app/data/v_sentinel.db \
  -e V_SENTINEL_AUTH_SECRET=your-secret-here \
  -v "$(pwd)/data:/app/data" \
  v-sentinel:latest
```

## Exposed interface

- `8000/tcp`: frontend + REST API + WebSocket + persisted message thumbnails

## Persistent data

Mount `/app/data` so the following are retained:

- `v_sentinel.db`
- `message_thumbnails/`
- `false_positives/`

Message thumbnails are written to the filesystem and are no longer stored inside SQLite.

Mount `.env` (read-only) for production configuration:

- `.env` — environment variables for auth secrets, CORS, ports, etc. (see `.env.example`)

## External services

This container does **not** start MediaMTX or any other sidecar service.

- If you need the 视频墙 page to play live video, configure an external RTSP/WebRTC gateway in the Settings page.
- Configure one shared **MediaMTX username / password** when the gateway is protected by authentication; the same credentials are used for RTSP and WebRTC.
- When the MediaMTX RTSP address or shared credentials change, V-Sentinel rewrites saved source RTSP URLs automatically so existing online sources keep the same route path under the new gateway.
- When the MediaMTX WebRTC address or shared credentials change, frontend playback reconnects by using the new WHEP settings.
- If you need AI inference, configure the V-Engine service addresses in the Settings page. For host-side V-Engine services, prefer `docker.internal`, `host.docker.internal`, or a LAN IP instead of `localhost`.
- The container startup script now exports merged `NO_PROXY` / `no_proxy` defaults for `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `docker.internal`, and private LAN ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `100.64.0.0/10`) so local gRPC / RTSP / WebRTC traffic bypasses HTTP proxies by default.
- When deploying behind nginx under `/sentinel`, also enable `login_lockout_trust_proxy` in Settings so audit logs and IP lockout use the forwarded client IP from nginx.
- For subpath deployments, `docker run -e VITE_APP_BASE_PATH=/sentinel ...` also works; the trailing slash is optional. The backend will inject the matching base path at runtime, so the image does not need to be rebuilt when the prefix changes.
- If you need daily-summary email delivery, configure the email service in the Settings page.

## Smoke / fire scene operations

The smoke/fire plugin includes advanced post-processing thresholds in the Settings page.

- Start by tuning the basic detector parameters (`Detection Confidence`, `NMS`).
- Use temporal settings (`Confirm Frames`, `Confirm Window`, `Max Miss Frames`) to balance stability vs. responsiveness.
- Keep advanced appearance thresholds at their defaults unless you are targeting a specific false-positive pattern such as glare, white hard-edged objects, or motion blur.

The settings page now includes inline descriptions for each smoke/fire advanced parameter so operators can tune them without reading the processor source code.

## Upgrade

```bash
docker pull <your-image>
docker stop v-sentinel
docker rm v-sentinel
docker run -d \
  --name v-sentinel \
  --add-host=host.docker.internal:host-gateway \
  --add-host=docker.internal:host-gateway \
  -p 8000:8000 \
  -v "$(pwd)/.env:/app/.env:ro" \
  -v "$(pwd)/data:/app/data" \
  <your-image>
```
