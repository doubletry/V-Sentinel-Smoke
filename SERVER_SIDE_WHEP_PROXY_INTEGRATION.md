# 第三方 Web 通过后端代理 WHEP 接入 W2W

本文档说明第三方 Web 系统如何在不把 W2W API 密钥暴露给浏览器的情况下，播放 W2W/MediaMTX 的 WebRTC 实时视频。

## 适用场景

- 第三方 Web 系统有自己的可信后端服务。
- 第三方用户在该系统内登录，观看权限也由该系统判断。
- 第三方后端可以安全保存 W2W API 密钥。
- 第三方前端需要播放 W2W 管理的视频源，但不能拿到 W2W API 密钥。
- W2W 不新增接口，继续使用现有 MediaMTX 外部鉴权链路。

不适用于纯前端项目。纯前端项目无法安全保存长期密钥，必须改为用户登录 W2W、由 W2W 签发媒体令牌，或增加可信后端。

## 架构

推荐链路：

```text
第三方前端
  1. 创建 RTCPeerConnection 和 SDP offer
  2. 把 offer 发给第三方后端
        |
        v
第三方后端
  3. 校验当前业务用户是否有权观看 stream_path
  4. 使用 W2W API 密钥请求 MediaMTX WHEP
        |
        v
MediaMTX
  5. 回调 W2W /api/media-auth 校验 API 密钥、read scope、path_prefix、allowed_cidrs
  6. 返回 SDP answer
        |
        v
第三方后端
  7. 把 SDP answer 返回给第三方前端
        |
        v
第三方前端
  8. setRemoteDescription(answer)，开始播放
```

关键点：

- W2W API 密钥只存在第三方后端。
- 浏览器不直接请求 MediaMTX WHEP 端点。
- 浏览器网络面板中不应出现 W2W API 密钥。
- W2W 不需要为该方案新增接口。

## W2W 侧配置

为第三方系统创建一个专用 API 密钥，并尽量使用最小权限：

- `scopes`: 只选择 `read`。
- `path_prefix`: 限制到第三方系统允许读取的流路径前缀，例如 `alice/site-a`。
- `allowed_cidrs`: 限制为第三方后端的出口 IP 或网段。
- `expires_hours`: 根据运维策略设置过期时间，并建立轮换流程。

如果第三方后端和 MediaMTX/W2W 部署在不同网络中，确保：

- 第三方后端可以访问 MediaMTX 的 WHEP 地址，例如 `https://media.example.com:8889`。
- MediaMTX 调用 W2W `/api/media-auth` 的配置保持可用。
- W2W 的读流 IP 策略允许最终被 MediaMTX 传给认证钩子的来源 IP。

该方案下，WHEP HTTP 请求由第三方后端发起，通常不需要把第三方前端 Origin 加入 MediaMTX `webrtcAllowOrigins`。如果第三方前端仍直接访问 MediaMTX 的其他 HLS/WebRTC 端点，则需要按实际 Origin 配置 CORS。

## 第三方后端需要新增的接口

建议新增一个只属于第三方系统的信令接口。接口路径可按业务系统风格调整，核心是“前端提交 SDP offer，后端返回 SDP answer”：

```http
POST /api/videos/{stream_path}/whep-offer
Content-Type: application/sdp
```

请求体为浏览器生成的 SDP offer。响应体为 MediaMTX 返回的 SDP answer：

```http
200 OK
Content-Type: application/sdp

v=0
...
```

后端处理步骤：

1. 从第三方系统登录态中识别当前用户。
2. 校验该用户是否有权观看 `{stream_path}`。
3. 规范化并校验 `{stream_path}`，只允许 W2W 的三级路径格式，例如 `username/machine/channel`。路径段由字母、数字、点、下划线、连字符组成（点用于 IP 地址等段，如 `10.37.192.5`）。
4. 读取请求体中的 SDP offer。
5. 请求 MediaMTX WHEP 端点。
6. 将 MediaMTX 的 SDP answer 原样返回给前端。

后端请求 MediaMTX 时优先使用 Bearer 头：

```http
POST https://media.example.com:8889/{stream_path}/whep
Content-Type: application/sdp
Authorization: Bearer <W2W_API_KEY>
```

如果实际 MediaMTX/W2W 部署未从 Bearer 头传递到认证钩子的 `token` 字段，可使用现有兼容写法：

```text
https://media.example.com:8889/{stream_path}/whep?token=<W2W_API_KEY>
```

不要把带 `token=<W2W_API_KEY>` 的 URL 返回给浏览器。

### 后端伪代码

该逻辑可以用任意后端语言实现，例如 Python、Java、Go、Node.js、PHP、C#。不要依赖具体框架，保持下面这些步骤即可：

```text
handle POST /api/videos/{owner}/{machine}/{channel}/whep-offer:
  current_user = authenticate_current_business_user(request)
  stream_path = join(owner, machine, channel)

  if any path segment is not /^[A-Za-z0-9._-]+$/ or segment is "." or "..":
    return 400

  if current_user cannot watch stream_path:
    return 403

  offer_sdp = request.body
  mediamtx_url = MEDIAMTX_WHEP_BASE + "/" + url_escape_path(stream_path) + "/whep"

  upstream_response = http.post(
    mediamtx_url,
    headers = {
      "Content-Type": "application/sdp",
      "Authorization": "Bearer " + W2W_API_KEY
    },
    body = offer_sdp
  )

  return upstream_response.status, upstream_response.content_type, upstream_response.body
```

实现时注意：

- `W2W_API_KEY` 从服务端环境变量或密钥管理系统读取。
- `stream_path` 不要直接拼接未经校验的用户输入。
- 后端访问 MediaMTX 的超时时间应设置得比前端播放超时略短，例如 10-15 秒。
- 日志里不要输出完整 API 密钥或带密钥的完整 URL。

## 第三方前端播放流程

第三方前端只调用自己的后端，不直接访问 MediaMTX WHEP：

```ts
async function playW2wStream(video: HTMLVideoElement, streamPath: string) {
  const pc = new RTCPeerConnection({ iceServers: [] })

  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })

  pc.ontrack = (event) => {
    if (event.streams[0]) {
      video.srcObject = event.streams[0]
    }
  }

  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  await waitForIceGathering(pc, 5000)

  const response = await fetch(`/api/videos/${streamPath}/whep-offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/sdp' },
    body: pc.localDescription?.sdp || '',
  })

  if (!response.ok) {
    throw new Error(`WHEP request failed: ${response.status}`)
  }

  const answer = await response.text()
  await pc.setRemoteDescription({ type: 'answer', sdp: answer })
  return pc
}

function waitForIceGathering(pc: RTCPeerConnection, timeoutMs: number): Promise<void> {
  if (pc.iceGatheringState === 'complete') {
    return Promise.resolve()
  }

  return new Promise((resolve) => {
    const timer = window.setTimeout(done, timeoutMs)

    function done() {
      window.clearTimeout(timer)
      pc.removeEventListener('icegatheringstatechange', onChange)
      resolve()
    }

    function onChange() {
      if (pc.iceGatheringState === 'complete') {
        done()
      }
    }

    pc.addEventListener('icegatheringstatechange', onChange)
  })
}
```

关闭播放器时，第三方前端应调用：

```ts
pc.close()
video.srcObject = null
```

## 错误处理建议

第三方后端可以按下列规则处理 MediaMTX 返回值：

- `200`: 返回 SDP answer。
- `401`/`403`: 转换为第三方系统的无权限或播放凭据错误。
- `404`: 流不存在或路径错误。
- `408`/`502`/`504`: MediaMTX 或上游不可用，可提示稍后重试。
- 其他状态：记录第三方后端日志，并返回统一播放失败错误。

日志中可以记录：

- 第三方系统用户 ID。
- `stream_path`。
- W2W API 密钥前缀或密钥名称。
- MediaMTX 返回状态码。

不要记录完整 W2W API 密钥，也不要记录带密钥的完整 URL。

## 验收清单

- 第三方前端浏览器网络面板中看不到 W2W API 密钥。
- 第三方前端只请求自己的 `whep-offer` 接口。
- 第三方后端未授权用户不会向 MediaMTX 发起 WHEP 请求。
- 使用 read-only API 密钥可以播放授权路径。
- API 密钥缺少 `read` scope 时播放失败。
- API 密钥 `path_prefix` 不匹配时播放失败。
- API 密钥 `allowed_cidrs` 不包含第三方后端出口 IP 时播放失败。
- 关闭播放器后 `RTCPeerConnection` 被关闭。
