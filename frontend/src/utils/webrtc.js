import config from '../config.js'

function normalizeBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function normalizeRoutePath(value) {
  return String(value || '').trim().replace(/^\/+/, '').replace(/\/+$/, '')
}

const ICE_SERVER_LINK_PATTERN =
  /^<(.+?)>; rel="ice-server"(?:; username="(.*?)"; credential="(.*?)"; credential-type="password")?$/i

async function supportsNonAdvertisedCodec(codec, fmtp) {
  // MediaMTX's compatibility workaround probes audio codecs only, since those
  // are the codecs that need extra advertisement in browser SDP offers.
  const pc = new RTCPeerConnection({ iceServers: [] })
  const mediaType = 'audio'
  let payloadType = ''

  try {
    pc.addTransceiver(mediaType, { direction: 'recvonly' })

    const offer = await pc.createOffer()
    if (!offer.sdp) {
      throw new Error('SDP not present')
    }
    if (offer.sdp.toLowerCase().includes(codec.toLowerCase())) {
      throw new Error('already present')
    }

    const sections = offer.sdp.split(`m=${mediaType}`)
    const payloadTypes = sections.slice(1)
      .map((section) => section.split('\r\n')[0].split(' ').slice(3))
      .reduce((prev, current) => [...prev, ...current], [])

    payloadType = reservePayloadType(payloadTypes)

    const lines = sections[1].split('\r\n')
    lines[0] += ` ${payloadType}`
    lines.splice(lines.length - 1, 0, `a=rtpmap:${payloadType} ${codec}`)
    if (fmtp !== undefined) {
      lines.splice(lines.length - 1, 0, `a=fmtp:${payloadType} ${fmtp}`)
    }
    sections[1] = lines.join('\r\n')
    offer.sdp = sections.join(`m=${mediaType}`)

    await pc.setLocalDescription(offer)
    await pc.setRemoteDescription(new RTCSessionDescription({
      type: 'answer',
      sdp: 'v=0\r\n'
        + 'o=- 6539324223450680508 0 IN IP4 0.0.0.0\r\n'
        + 's=-\r\n'
        + 't=0 0\r\n'
        + 'a=fingerprint:sha-256 0D:9F:78:15:42:B5:4B:E6:E2:94:3E:5B:37:78:E1:4B:54:59:A3:36:3A:E5:05:EB:27:EE:8F:D2:2D:41:29:25\r\n'
        + `m=${mediaType} 9 UDP/TLS/RTP/SAVPF ${payloadType}\r\n`
        + 'c=IN IP4 0.0.0.0\r\n'
        + 'a=ice-pwd:7c3bf4770007e7432ee4ea4d697db675\r\n'
        + 'a=ice-ufrag:29e036dc\r\n'
        + 'a=sendonly\r\n'
        + 'a=rtcp-mux\r\n'
        + `a=rtpmap:${payloadType} ${codec}\r\n`
        + (fmtp !== undefined ? `a=fmtp:${payloadType} ${fmtp}\r\n` : ''),
    }))
    return true
  } catch (err) {
    return false
  } finally {
    pc.close()
  }
}

function reservePayloadType(payloadTypes) {
  // Dynamic RTP payload types are available in the 30-63 and 96-127 ranges.
  // Reserve a free one that is valid for browser SDP offers.
  for (let i = 30; i <= 127; i += 1) {
    if ((i <= 63 || i >= 96) && !payloadTypes.includes(i.toString())) {
      const value = i.toString()
      payloadTypes.push(value)
      return value
    }
  }

  throw new Error('Unable to find a free payload type')
}

function enableStereoPcmuPcma(payloadTypes, section) {
  const lines = section.split('\r\n')

  let payloadType = reservePayloadType(payloadTypes)
  lines[0] += ` ${payloadType}`
  lines.splice(lines.length - 1, 0, `a=rtpmap:${payloadType} PCMU/8000/2`)
  lines.splice(lines.length - 1, 0, `a=rtcp-fb:${payloadType} transport-cc`)

  payloadType = reservePayloadType(payloadTypes)
  lines[0] += ` ${payloadType}`
  lines.splice(lines.length - 1, 0, `a=rtpmap:${payloadType} PCMA/8000/2`)
  lines.splice(lines.length - 1, 0, `a=rtcp-fb:${payloadType} transport-cc`)

  return lines.join('\r\n')
}

function enableMultichannelOpus(payloadTypes, section) {
  const lines = section.split('\r\n')
  const variants = [
    ['multiopus/48000/3', 'channel_mapping=0,2,1;num_streams=2;coupled_streams=1'],
    ['multiopus/48000/4', 'channel_mapping=0,1,2,3;num_streams=2;coupled_streams=2'],
    ['multiopus/48000/5', 'channel_mapping=0,4,1,2,3;num_streams=3;coupled_streams=2'],
    ['multiopus/48000/6', 'channel_mapping=0,4,1,2,3,5;num_streams=4;coupled_streams=2'],
    ['multiopus/48000/7', 'channel_mapping=0,4,1,2,3,5,6;num_streams=4;coupled_streams=4'],
    ['multiopus/48000/8', 'channel_mapping=0,6,1,4,5,2,3,7;num_streams=5;coupled_streams=4'],
  ]

  variants.forEach(([codec, fmtp]) => {
    const payloadType = reservePayloadType(payloadTypes)
    lines[0] += ` ${payloadType}`
    lines.splice(lines.length - 1, 0, `a=rtpmap:${payloadType} ${codec}`)
    lines.splice(lines.length - 1, 0, `a=fmtp:${payloadType} ${fmtp}`)
    lines.splice(lines.length - 1, 0, `a=rtcp-fb:${payloadType} transport-cc`)
  })

  return lines.join('\r\n')
}

function enableL16(payloadTypes, section) {
  const lines = section.split('\r\n')
  const codecs = ['L16/8000/2', 'L16/16000/2', 'L16/48000/2']
  codecs.forEach((codec) => {
    const payloadType = reservePayloadType(payloadTypes)
    lines[0] += ` ${payloadType}`
    lines.splice(lines.length - 1, 0, `a=rtpmap:${payloadType} ${codec}`)
    lines.splice(lines.length - 1, 0, `a=rtcp-fb:${payloadType} transport-cc`)
  })
  return lines.join('\r\n')
}

function enableStereoOpus(section) {
  const lines = section.split('\r\n')
  let opusPayloadFormat = ''

  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].startsWith('a=rtpmap:') && lines[i].toLowerCase().includes('opus/')) {
      opusPayloadFormat = lines[i].slice('a=rtpmap:'.length).split(' ')[0]
      break
    }
  }

  if (!opusPayloadFormat) return section

  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].startsWith(`a=fmtp:${opusPayloadFormat} `)) {
      if (!lines[i].includes('stereo')) lines[i] += ';stereo=1'
      if (!lines[i].includes('sprop-stereo')) lines[i] += ';sprop-stereo=1'
    }
  }

  return lines.join('\r\n')
}

function editOffer(sdp, nonAdvertisedCodecs) {
  const sections = sdp.split('m=')
  const payloadTypes = sections.slice(1)
    .map((section) => section.split('\r\n')[0].split(' ').slice(3))
    .reduce((prev, current) => [...prev, ...current], [])

  for (let i = 1; i < sections.length; i += 1) {
    if (!sections[i].startsWith('audio')) continue

    sections[i] = enableStereoOpus(sections[i])

    if (nonAdvertisedCodecs.includes('pcma/8000/2')) {
      sections[i] = enableStereoPcmuPcma(payloadTypes, sections[i])
    }
    if (nonAdvertisedCodecs.includes('multiopus/48000/6')) {
      sections[i] = enableMultichannelOpus(payloadTypes, sections[i])
    }
    if (nonAdvertisedCodecs.includes('L16/48000/2')) {
      sections[i] = enableL16(payloadTypes, sections[i])
    }

    break
  }

  return sections.join('m=')
}

async function getNonAdvertisedCodecs() {
  const checks = await Promise.all([
    supportsNonAdvertisedCodec('pcma/8000/2'),
    supportsNonAdvertisedCodec('multiopus/48000/6', 'channel_mapping=0,4,1,2,3,5;num_streams=4;coupled_streams=2'),
    supportsNonAdvertisedCodec('L16/48000/2'),
  ])

  return [
    checks[0] ? 'pcma/8000/2' : false,
    checks[1] ? 'multiopus/48000/6' : false,
    checks[2] ? 'L16/48000/2' : false,
  ].filter(Boolean)
}

function parseIceServers(linkHeader) {
  if (!linkHeader) return []

  // MediaMTX returns WHEP ICE servers through RFC 8288 Link headers and adds
  // MediaMTX-specific username / credential parameters when TURN auth is needed:
  // <stun:host:port>; rel="ice-server"; username="..."; credential="..."
  return linkHeader
    .split(/,\s*(?=<)/)
    .map((entry) => {
      const match = entry.match(ICE_SERVER_LINK_PATTERN)
      if (!match) return null

      const [, url, username, credential] = match
      const server = { urls: [url] }

      if (username !== undefined) {
        // MediaMTX returns quoted-string header values; unescape the subset
        // used by Link parameters without evaluating arbitrary JSON input.
        server.username = unescapeQuotedHeaderValue(username)
        server.credential = unescapeQuotedHeaderValue(credential || '')
        server.credentialType = 'password'
      }

      return server
    })
    .filter(Boolean)
}

function unescapeQuotedHeaderValue(value) {
  return String(value || '').replace(/\\(["\\])/g, '$1')
}

/**
 * Connect to a MediaMTX stream via WebRTC (WHEP protocol).
 * @param {string} streamPath - The stream path on MediaMTX (e.g. "camera1")
 * @param {HTMLVideoElement} videoEl - The video element to attach to
 * @param {string} webrtcBaseUrl - MediaMTX WebRTC base address from settings
 * @returns {object} - { pc: RTCPeerConnection, stop: Function }
 */
function buildBasicAuthHeader(username, password) {
  const normalizedUsername = String(username || '').trim()
  if (!normalizedUsername) return {}

  const encoded = window.btoa(unescape(encodeURIComponent(`${normalizedUsername}:${String(password || '')}`)))
  return {
    Authorization: `Basic ${encoded}`,
  }
}

async function requestIceServers(whepUrl, authHeaders) {
  let response
  try {
    response = await fetch(whepUrl, {
      method: 'OPTIONS',
      headers: authHeaders,
    })
  } catch (err) {
    throw new Error(`WHEP ICE server request failed: ${err.message}`)
  }

  if (!response.ok) {
    const error = new Error(`WHEP error: ${response.status} ${response.statusText}`)
    error.name = 'WHEPError'
    error.status = response.status
    throw error
  }

  return parseIceServers(response.headers.get('Link'))
}

export async function connectWebRTC(
  streamPath,
  videoEl,
  webrtcBaseUrl,
  webrtcUsername = '',
  webrtcPassword = ''
) {
  const base = normalizeBaseUrl(webrtcBaseUrl || config.mediamtxWebrtcUrl)
  const route = normalizeRoutePath(streamPath)
  const whepUrl = `${base}/${route}/whep`
  const authHeaders = buildBasicAuthHeader(webrtcUsername, webrtcPassword)
  const iceServers = await requestIceServers(whepUrl, authHeaders)

  const pc = new RTCPeerConnection({
    iceServers,
  })

  // Add transceivers to receive audio and video
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })
  // The empty label is intentional and matches MediaMTX's browser reader.js.
  // Creating a local data channel keeps the generated offer compatible with
  // servers that expose data channels alongside media tracks.
  pc.createDataChannel('')

  // Attach stream to video element when tracks arrive
  pc.ontrack = (event) => {
    if (videoEl) {
      if (!videoEl.srcObject) {
        videoEl.srcObject = event.streams[0]
      }
    }
  }

  // Create SDP offer
  const offer = await pc.createOffer()
  offer.sdp = editOffer(offer.sdp, await getNonAdvertisedCodecs())
  await pc.setLocalDescription(offer)

  // Wait for ICE gathering to complete (or timeout)
  await waitForIceGathering(pc)

  // Send offer to MediaMTX WHEP endpoint
  let response
  try {
    response = await fetch(whepUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/sdp',
        ...authHeaders,
      },
      body: pc.localDescription.sdp,
    })
  } catch (err) {
    pc.close()
    throw new Error(`WHEP request failed: ${err.message}`)
  }

  if (!response.ok) {
    pc.close()
    const error = new Error(`WHEP error: ${response.status} ${response.statusText}`)
    error.name = 'WHEPError'
    error.status = response.status
    throw error
  }

  const answerSdp = await response.text()
  await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp })

  return {
    pc,
    stop: () => pc.close(),
  }
}

/**
 * Wait for ICE gathering to complete (or timeout after 3s).
 */
function waitForIceGathering(pc) {
  return new Promise((resolve) => {
    if (pc.iceGatheringState === 'complete') {
      resolve()
      return
    }
    const timeout = setTimeout(resolve, 3000)
    pc.addEventListener('icegatheringstatechange', () => {
      if (pc.iceGatheringState === 'complete') {
        clearTimeout(timeout)
        resolve()
      }
    })
  })
}
