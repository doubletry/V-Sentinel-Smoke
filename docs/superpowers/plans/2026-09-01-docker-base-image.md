# Docker 预构建基础镜像 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `ffmpeg` / `libturbojpeg0` 预装进独立基础镜像 `v-sentinel-base:py311`，使日常 `./scripts/build_docker.sh` 构建中彻底不再执行 apt。

**Architecture:** 新增 `Dockerfile.base` 定义基础镜像（Python 3.11 + 系统依赖）；`build_docker.sh` 在构建主镜像前检查基础镜像，缺失或 `REBUILD_BASE=1` 时自动先构建；主 `Dockerfile` 第二阶段改为 `FROM ${BASE_IMAGE}` 并删除 apt 步骤。脚本逻辑用 `DOCKER_BIN` 桩（stub）做快速确定性测试，最后做真实构建 E2E 验证。

**Tech Stack:** Docker BuildKit、Bash（`set -euo pipefail`）、Debian apt（python:3.11-slim 内）。

## Global Constraints

- 基础镜像 tag 固定为 `v-sentinel-base:py311`（可通过环境变量 `BASE_IMAGE` 覆盖），tag 含 Python 大版本。
- 不把 pip 三方依赖烤进基础镜像；不改 npm/pip 安装步骤、不改前端 `node:20-alpine` 阶段。
- 保持单一构建入口 `scripts/build_docker.sh`，不新增构建脚本；基础镜像构建复用脚本里**已计算好的**代理 / `--add-host` 参数，不重复实现代理逻辑。
- 基础镜像的 apt 代理处理方式与主镜像现状一致：通过 `--build-arg` 传入 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`（含小写变体）+ `--add-host=host.docker.internal:host-gateway`；不需要 CA secret（现状 apt 也不走 CA 挂载）。
- 主 `Dockerfile` 保留 `# syntax=docker/dockerfile:1.7`（secret 挂载需要）；`Dockerfile.base` 不加 syntax 指令。
- 本机 docker.io 代理不稳定，`docker pull` 报 `Parent proxy unreacheable` 时**重试即可**（通常 2-4 次内成功）；`node:20-alpine` 与 `docker/dockerfile:1.7` 当前已在本机预拉取。
- 提交信息风格：小写 `type(scope): description`（英文），与 `git log` 现有风格一致。

## 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `Dockerfile.base` | 新建 | 基础镜像：python:3.11-slim + ffmpeg + libturbojpeg0 + Python 运行时 ENV |
| `Dockerfile` | 修改 | 第二阶段 `FROM ${BASE_IMAGE}`，删除 apt RUN，ENV 只留 `DB_PATH` |
| `scripts/build_docker.sh` | 修改 | 新增 `BASE_IMAGE`/`REBUILD_BASE`；主构建前自动补建基础镜像；主构建传 `--build-arg BASE_IMAGE` |
| `docs/docker-deployment.md` | 修改 | Build 章节新增 Base image 小节 |
| `README.md` / `README_zh.md` | 修改 | Docker 章节各加一条基础镜像说明 |

---

### Task 1: 创建 `Dockerfile.base` 并手动构建验证

**Files:**
- Create: `Dockerfile.base`

**Interfaces:**
- Produces: 本地镜像 `v-sentinel-base:py311`（含 `ffmpeg`、`libturbojpeg0`、`python`，ENV `PYTHONDONTWRITEBYTECODE=1`/`PYTHONUNBUFFERED=1`）。Task 3 的主 `Dockerfile` 将 `FROM` 此镜像。

- [ ] **Step 1: 创建 `Dockerfile.base`**

写入文件 `/home/hsli/workspace/V-Sentinel-Smoke/Dockerfile.base`：

```dockerfile
ARG PYTHON_BASE=python:3.11-slim
FROM ${PYTHON_BASE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG no_proxy=""

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 \
    && rm -rf /var/lib/apt/lists/*
```

说明：代理 ARG 与主 `Dockerfile` 现状一致（RUN 需要代理环境）；`PYTHON_BASE` 参数化便于将来锁 digest 或升 Python。

- [ ] **Step 2: 构建基础镜像（真实构建，约 1-3 分钟）**

```bash
cd /home/hsli/workspace/V-Sentinel-Smoke
docker build \
  --add-host=host.docker.internal:host-gateway \
  --build-arg HTTP_PROXY=http://host.docker.internal:3139 \
  --build-arg http_proxy=http://host.docker.internal:3139 \
  --build-arg HTTPS_PROXY=http://host.docker.internal:3139 \
  --build-arg https_proxy=http://host.docker.internal:3139 \
  -f Dockerfile.base -t v-sentinel-base:py311 .
```

预期：`apt-get install` 执行一次，构建成功。若中途 `Parent proxy unreacheable`，整个命令重跑（apt 层会重算）。
注意：代理端口 `3139` 取自本机当前 `HTTP_PROXY` 环境变量；若执行时端口不同，用实际端口替换（4 处）。

- [ ] **Step 3: 验证镜像内容**

```bash
docker run --rm v-sentinel-base:py311 sh -c \
  'ffmpeg -version | head -1 && ldconfig -p | grep turbojpeg && python --version && env | grep -E "PYTHONDONTWRITEBYTECODE|PYTHONUNBUFFERED"'
```

预期输出（版本数字可能不同）：
- `ffmpeg version 5.1.x-...`
- `libturbojpeg.so.0 (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/libturbojpeg.so.0`
- `Python 3.11.x`
- `PYTHONDONTWRITEBYTECODE=1` 和 `PYTHONUNBUFFERED=1`

- [ ] **Step 4: Commit**

```bash
git add Dockerfile.base
git commit -m "chore(docker): add base image Dockerfile with system deps"
```

---

### Task 2: `build_docker.sh` 自动补建基础镜像（桩测试）

**Files:**
- Modify: `scripts/build_docker.sh`（顶部变量区 + 主构建前插入基础镜像逻辑）

**Interfaces:**
- Consumes: Task 1 的 `Dockerfile.base` 与 tag `v-sentinel-base:py311`；脚本已有的 `HTTP_PROXY_VALUE`/`HTTPS_PROXY_VALUE`/`NO_PROXY_VALUE`/`extra_args`/`DOCKER_BIN` 变量。
- Produces: 环境变量 `BASE_IMAGE`（默认 `v-sentinel-base:py311`）、`REBUILD_BASE`（默认 `0`）；主构建命令中追加 `--build-arg BASE_IMAGE=<值>`。Task 3 依赖该 ARG。

- [ ] **Step 1: 写桩测试脚本（先写测试）**

```bash
mkdir -p /tmp/opencode/dockerstub
cat > /tmp/opencode/dockerstub/docker <<'EOF'
#!/usr/bin/env bash
echo "CALL: $*" >> "${STUB_LOG:-/tmp/opencode/dockerstub/calls.log}"
if [[ "${1:-}" == "image" && "${2:-}" == "inspect" ]]; then
  exit "${STUB_INSPECT_EXIT:-1}"
fi
exit 0
EOF
chmod +x /tmp/opencode/dockerstub/docker
```

- [ ] **Step 2: 运行桩测试，确认当前行为（应失败：脚本还不会构建基础镜像）**

```bash
cd /home/hsli/workspace/V-Sentinel-Smoke
rm -f /tmp/opencode/dockerstub/calls.log
STUB_INSPECT_EXIT=1 DOCKER_BIN=/tmp/opencode/dockerstub/docker ./scripts/build_docker.sh
echo "--- calls ---"; cat /tmp/opencode/dockerstub/calls.log
```

预期（当前代码）：只有 1 行 `CALL: build ... -t v-sentinel:latest .`，**没有** `-f Dockerfile.base`。这就是「失败」基线。

- [ ] **Step 3: 修改 `scripts/build_docker.sh`**

3a. 在 `DOCKER_BIN="${DOCKER_BIN:-docker}"`（第 6 行）之后加两行：

```bash
BASE_IMAGE="${BASE_IMAGE:-v-sentinel-base:py311}"
REBUILD_BASE="${REBUILD_BASE:-0}"
```

3b. 在 `if [[ -n "$BUILD_CA_CERT_PATH" ]]; then ... fi` 块（secret_args 填充，约第 133-135 行）之后、`docker_cmd=("${DOCKER_BIN}" build)`（第 137 行）之前，插入：

```bash
base_build_args=()
for key in HTTP_PROXY http_proxy; do
  if [[ -n "$HTTP_PROXY_VALUE" ]]; then
    base_build_args+=(--build-arg "${key}=${HTTP_PROXY_VALUE}")
  fi
done

for key in HTTPS_PROXY https_proxy; do
  if [[ -n "$HTTPS_PROXY_VALUE" ]]; then
    base_build_args+=(--build-arg "${key}=${HTTPS_PROXY_VALUE}")
  fi
done

for key in NO_PROXY no_proxy; do
  if [[ -n "$NO_PROXY_VALUE" ]]; then
    base_build_args+=(--build-arg "${key}=${NO_PROXY_VALUE}")
  fi
done

if [[ "$REBUILD_BASE" == "1" ]] || ! "${DOCKER_BIN}" image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
  echo "[build_docker] base image ${BASE_IMAGE} missing or REBUILD_BASE=1, building it first..."
  base_cmd=("${DOCKER_BIN}" build)
  if [[ ${#extra_args[@]} -gt 0 ]]; then
    base_cmd+=("${extra_args[@]}")
  fi
  if [[ ${#base_build_args[@]} -gt 0 ]]; then
    base_cmd+=("${base_build_args[@]}")
  fi
  base_cmd+=(-f Dockerfile.base -t "${BASE_IMAGE}" .)
  "${base_cmd[@]}"
fi

build_args+=(--build-arg "BASE_IMAGE=${BASE_IMAGE}")
```

- [ ] **Step 4: 语法检查**

```bash
bash -n scripts/build_docker.sh && echo SYNTAX_OK
```

预期：`SYNTAX_OK`，无输出错误。

- [ ] **Step 5: 桩测试三个场景**

场景 A — 基础镜像缺失（inspect 失败），应「先建基础 + 再建主」：

```bash
rm -f /tmp/opencode/dockerstub/calls.log
STUB_INSPECT_EXIT=1 DOCKER_BIN=/tmp/opencode/dockerstub/docker ./scripts/build_docker.sh
echo "--- calls ---"; cat /tmp/opencode/dockerstub/calls.log
```

预期：`[build_docker] base image ... building it first...`；calls.log 共 2 行：
- 第 1 行含 `-f Dockerfile.base -t v-sentinel-base:py311 .`
- 第 2 行含 `BASE_IMAGE=v-sentinel-base:py311` 且含 `-t v-sentinel:latest .`

场景 B — 基础镜像已存在（inspect 成功）且未设 REBUILD_BASE，应只建主镜像：

```bash
rm -f /tmp/opencode/dockerstub/calls.log
STUB_INSPECT_EXIT=0 DOCKER_BIN=/tmp/opencode/dockerstub/docker ./scripts/build_docker.sh
echo "--- calls ---"; cat /tmp/opencode/dockerstub/calls.log
```

预期：无 `building it first` 输出；calls.log 仅 1 行，含 `-t v-sentinel:latest .`，不含 `Dockerfile.base`。

场景 C — 基础镜像已存在但 `REBUILD_BASE=1`，应强制重建基础：

```bash
rm -f /tmp/opencode/dockerstub/calls.log
STUB_INSPECT_EXIT=0 REBUILD_BASE=1 DOCKER_BIN=/tmp/opencode/dockerstub/docker ./scripts/build_docker.sh
echo "--- calls ---"; cat /tmp/opencode/dockerstub/calls.log
```

预期：出现 `building it first`；calls.log 共 2 行（同场景 A 的顺序与内容）。

- [ ] **Step 6: Commit**

```bash
git add scripts/build_docker.sh
git commit -m "chore(docker): auto-build base image in build_docker.sh with REBUILD_BASE override"
```

---

### Task 3: 主 `Dockerfile` 切换到基础镜像（真实 E2E）

**Files:**
- Modify: `Dockerfile:29-47`（第二阶段 FROM / ENV / apt RUN）

**Interfaces:**
- Consumes: Task 1 的 `v-sentinel-base:py311`；Task 2 的 `--build-arg BASE_IMAGE`。
- Produces: 主镜像 `v-sentinel:latest`，第二阶段无 apt 步骤。

- [ ] **Step 1: 修改主 `Dockerfile` 第二阶段**

把现有第 29-47 行：

```dockerfile
FROM python:3.11-slim
WORKDIR /app

ARG RELAX_HTTPS_VERIFICATION=false

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG no_proxy=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/v_sentinel.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 \
    && rm -rf /var/lib/apt/lists/*
```

替换为：

```dockerfile
ARG BASE_IMAGE=v-sentinel-base:py311
FROM ${BASE_IMAGE}
WORKDIR /app

ARG RELAX_HTTPS_VERIFICATION=false

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG no_proxy=""

ENV DB_PATH=/app/data/v_sentinel.db
```

（前端阶段、`COPY`、pip 步骤、ENTRYPOINT/CMD 全部不动。）

- [ ] **Step 2: 真实全量构建（REBUILD_BASE=1，约 10-20 分钟）**

```bash
cd /home/hsli/workspace/V-Sentinel-Smoke
REBUILD_BASE=1 ./scripts/build_docker.sh 2>&1 | tee /tmp/opencode/build_e2e.log | tail -20
```

预期：先输出 `building it first` 并构建基础镜像（其中 apt 执行一次），随后主镜像构建成功。
若 `docker pull` 报 `Parent proxy unreacheable`：重试整条命令（`node:20-alpine`、`docker/dockerfile:1.7` 已预拉取，通常只有偶发失败）。

- [ ] **Step 3: 验证 apt 只出现在基础镜像构建中**

```bash
grep -c "RUN apt-get" /tmp/opencode/build_e2e.log
grep -n "RUN apt-get" /tmp/opencode/build_e2e.log
```

预期：计数为 `1`；该唯一一行属于 `Dockerfile.base` 的构建段（其上方可见 `building with` 基础镜像构建的开始，且**不**在 `#N [stage-1 ...]` 主构建段内）。

- [ ] **Step 4: 验证最终镜像能力**

```bash
docker run --rm v-sentinel:latest sh -c \
  'ffmpeg -version | head -1 && ldconfig -p | grep turbojpeg && python -c "import av; print(\"av\", av.__version__)" && python -c "import turbojpeg; print(\"turbojpeg ok\")"'
```

预期：ffmpeg 版本行、`libturbojpeg.so.0 ...`、`av 12.x`（或更高）、`turbojpeg ok`。

- [ ] **Step 5: 容器启动冒烟测试**

```bash
docker rm -f vs-base-smoke 2>/dev/null
docker run -d --name vs-base-smoke -p 18000:8000 v-sentinel:latest
for i in $(seq 1 30); do curl -sf http://127.0.0.1:18000/api/health >/dev/null 2>&1 && break; sleep 2; done
curl -s -o /dev/null -w "root=%{http_code}\n" http://127.0.0.1:18000/
curl -s http://127.0.0.1:18000/api/health
docker rm -f vs-base-smoke
```

预期：`root=200`；`/api/health` 返回 JSON（含 status 字段）。

- [ ] **Step 6: Commit**

```bash
git add Dockerfile
git commit -m "feat(docker): build runtime stage on pre-baked base image, drop apt from main build"
```

---

### Task 4: 二次构建幂等验证（无 apt、不重建基础）

**Files:**
- 无新改动（纯验证）。若发现行为不符，回到 Task 2/3 修复后再过本任务。

**Interfaces:**
- Consumes: Task 1-3 的全部产物。

- [ ] **Step 1: 再次完整构建**

```bash
cd /home/hsli/workspace/V-Sentinel-Smoke
./scripts/build_docker.sh 2>&1 | tee /tmp/opencode/build_second.log | tail -20
```

预期：构建成功，且由于代码无变化，大部分层 `CACHED`，速度快。

- [ ] **Step 2: 断言无 apt、无基础镜像重建**

```bash
echo "apt-runs: $(grep -c 'RUN apt-get' /tmp/opencode/build_second.log)"
echo "base-rebuilds: $(grep -c 'building it first' /tmp/opencode/build_second.log)"
```

预期：`apt-runs: 0` 且 `base-rebuilds: 0`。

- [ ] **Step 3: 提交（若无代码改动则跳过 commit）**

本任务无文件改动，不产生 commit。

---

### Task 5: 文档更新

**Files:**
- Modify: `docs/docker-deployment.md`（Build 章节）
- Modify: `README.md:421-448`（Docker 章节）
- Modify: `README_zh.md:392-418`（Docker 章节）

**Interfaces:**
- Consumes: Task 2 的 `REBUILD_BASE` / `BASE_IMAGE` 语义。

- [ ] **Step 1: `docs/docker-deployment.md` 新增 Base image 小节**

在 Build 章节的「The build script automatically reads the current shell proxy settings ...」段落之后、「When an HTTPS proxy is present:」之前插入：

```markdown
### Base image

The runtime stage of the main image is built on a pre-baked base image
`v-sentinel-base:py311` (defined in `Dockerfile.base`), which contains the
Python 3.11 runtime and the system packages `ffmpeg` and `libturbojpeg0`.
This keeps `apt-get` out of the normal build path.

- `./scripts/build_docker.sh` checks for the base image before building the
  main image and builds it automatically on first use, reusing the same proxy
  and `host.docker.internal` handling as the main build.
- Rebuild the base image when system dependencies or the Python version
  change:

  ```bash
  REBUILD_BASE=1 ./scripts/build_docker.sh
  ```

- Override the base image reference if needed:

  ```bash
  BASE_IMAGE=my-registry/v-sentinel-base:py311 ./scripts/build_docker.sh
  ```

```

- [ ] **Step 2: `README.md` Docker 章节加一条**

在 `README.md` 的 `- Frontend, REST API, WebSocket, and persisted message thumbnails are all served from port `8000`` 列表项之前（即 Docker 代码块之后的第一个列表项前）插入：

```markdown
- The runtime stage builds on a pre-baked base image `v-sentinel-base:py311` (ffmpeg / libturbojpeg0 preinstalled); `build_docker.sh` creates it automatically on first use — rebuild it with `REBUILD_BASE=1 ./scripts/build_docker.sh` when system dependencies change

```

- [ ] **Step 3: `README_zh.md` Docker 章节加一条**

在 `README_zh.md` 的 `- 前端、REST API、WebSocket 和消息缩略图统一由 `8000` 端口提供` 列表项之前插入：

```markdown
- 运行时镜像基于预构建基础镜像 `v-sentinel-base:py311`（已预装 ffmpeg / libturbojpeg0）；`build_docker.sh` 首次使用时自动构建，系统依赖变更时用 `REBUILD_BASE=1 ./scripts/build_docker.sh` 重建

```

- [ ] **Step 4: Commit**

```bash
git add docs/docker-deployment.md README.md README_zh.md
git commit -m "docs: document docker base image and REBUILD_BASE usage"
```

---

## 收尾

全部任务完成后：
1. `git log --oneline -8` 确认 4 个实现 commit（Task 1/2/3/5）+ 已有的 spec commit + 计划文档 commit。
2. 向用户汇报验证结果（Task 3/4 的关键输出），由用户决定是否 `git push`。
