# Docker 预构建基础镜像设计

## 背景与问题

`./scripts/build_docker.sh` 每次构建时，主镜像里的 `apt-get install ffmpeg libturbojpeg0`（`Dockerfile:45-47`）都会重跑，导致构建慢、且每次都要从 apt 源下载一堆包。

根因：apt 层位于主镜像构建路径中，Docker 层缓存一旦被「弄脏」该层就会重跑。已确认的诱因包括：

- 基础镜像 `python:3.11-slim` 未锁定 digest，重新 pull 到新版本会使其后所有层（含 apt）失效；
- 构建脚本每次把代理 `HTTP_PROXY` / `HTTPS_PROXY` 作为 build-arg 传入，代理值变化会使 apt 层缓存 key 改变；
- 磁盘接近写满，缓存易被挤掉。

目标：**日常构建中彻底不再执行 apt**，把系统依赖的安装从「每次构建」中挪走。

## 范围

- **做**：把 `ffmpeg` / `libturbojpeg0` 等系统依赖预装进一个独立基础镜像；主镜像改为基于该基础镜像构建。
- **不做**（后续可单独提）：
  - 不把 pip 三方依赖烤进基础镜像（本次只针对 apt）；
  - 不做基础镜像的仓库分发 / 多机 / CI 支持（用户只在本机构建）。

## 约束

- 用户只在本机跑 `build_docker.sh`，无 CI。
- 构建走公司代理（`build_docker.sh` 已处理代理 / CA 证书 / `host.docker.internal` 改写），基础镜像构建必须复用同一套逻辑。
- 保持单一构建入口，尽量不新增脚本、不重复造轮子。

## 方案：预构建基础镜像

把 apt 的活固化进一个独立、长期复用的基础镜像；主镜像只做「COPY 代码 + pip install」。该方案不依赖 BuildKit 层缓存是否留存，最稳健。

### 1. 基础镜像 `v-sentinel-base:py311`

新增 `Dockerfile.base`（仓库根目录，与 `Dockerfile` 并列）：

```dockerfile
ARG PYTHON_BASE=python:3.11-slim
FROM ${PYTHON_BASE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 \
    && rm -rf /var/lib/apt/lists/*
```

- 用 `ARG PYTHON_BASE` 参数化基础 Python 镜像，默认 `python:3.11-slim`，便于将来锁 digest 或升级 Python 大版本。
- 不加 `# syntax` 指令：纯 apt 安装用不到 BuildKit 特性，少一次 `docker.io` 拉取。
- tag 为 `v-sentinel-base:py311`；tag 内带 Python 大版本，将来升 3.12 时换 `py312` 重建即可。
- 代理 / CA 证书处理与主构建一致（见第 3 节，复用 `build_docker.sh` 现有参数）。

### 2. 主 `Dockerfile` 改动

- 第二阶段 `FROM python:3.11-slim` → `FROM v-sentinel-base:py311`。
- **删除** apt 步骤（现 `Dockerfile:45-47`）。
- `ENV PYTHONDONTWRITEBYTECODE=1` / `ENV PYTHONUNBUFFERED=1` 移入基础镜像（主镜像自动继承）；主镜像 `ENV` 仅保留 `DB_PATH=/app/data/v_sentinel.db`。
- 前端 `node:20-alpine` 阶段、`pip install` 步骤、代理相关 `ARG` 全部保持不变。
- 效果：日常构建日志中不再出现 `apt-get`，第二阶段从「装系统包」变为「COPY + pip」。

### 3. `build_docker.sh` 改动（单入口，不新增脚本）

- 顶部新增：`BASE_IMAGE="${BASE_IMAGE:-v-sentinel-base:py311}"`（可用环境变量覆盖）。
- 构建主镜像前，用 `docker image inspect "$BASE_IMAGE"` 检查基础镜像是否存在：
  - 不存在 → 先用**已计算好的同一套**代理 / CA / `--add-host` 参数 `docker build -f Dockerfile.base -t "$BASE_IMAGE" .`，再构建主镜像；
  - 存在 → 直接构建主镜像。
- 新增 `REBUILD_BASE=1` 环境变量：强制重建基础镜像（升级 ffmpeg / 系统依赖 / Python 时使用）。
- 代理 / CA / `host.docker.internal` 改写逻辑复用脚本中现有的函数与变量，不重复实现。

### 4. 使用方式

- 日常：`./scripts/build_docker.sh`（首次会自动构建基础镜像，之后直接复用）。
- 升级系统依赖 / Python：`REBUILD_BASE=1 ./scripts/build_docker.sh`。

## 验证

1. `REBUILD_BASE=1 ./scripts/build_docker.sh`：确认 apt 只在 `Dockerfile.base` 里执行一次，主镜像构建不含 apt。
2. 再次 `./scripts/build_docker.sh`：确认日志无 `apt-get`，且复用既有基础镜像。
3. `docker run` 启动容器：确认 `ffmpeg` / `libturbojpeg` 可用（如 `ffmpeg -version`、Python 导入 `turbojpeg` / `PyAV`），服务正常监听 8000 端口。

## 风险与缓解

- 基础镜像丢失（误删 / 清磁盘）：`build_docker.sh` 检测到缺失会自动重建，构建不会失败。
- 基础镜像与主镜像漂移：升级系统依赖时用 `REBUILD_BASE=1` 重建；tag 带 Python 版本，降低误用不同大版本的概率。
- 代理不可达导致基础镜像构建失败：与主构建同一代理逻辑，失败时给出与现状一致的报错，不引入新失败面。
