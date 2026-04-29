import {
  buildWhepEndpointHeaders,
  buildWhepPatchHeaders,
  buildWhepUrl,
  generateSdpFragment,
  parseOfferData,
} from './webrtcHelpers.js'

async function sendOffer(whepUrl, offerSdp, authHeaders) {
  const response = await fetch(whepUrl, {
    method: 'POST',
    headers: authHeaders,
    body: offerSdp,
  })

  switch (response.status) {
    case 201:
      return {
        answerSdp: await response.text(),
        sessionUrl: new URL(response.headers.get('location'), whepUrl).toString(),
      }
    case 404: {
      const error = new Error('stream not found')
      error.name = 'WHEPError'
      error.status = 404
      throw error
    }
    default: {
      const error = new Error(`WHEP error: ${response.status} ${response.statusText}`)
      error.name = 'WHEPError'
      error.status = response.status
      throw error
    }
  }
}

async function patchLocalCandidates(sessionUrl, offerData, candidates) {
  if (!sessionUrl || !candidates.length) return

  await fetch(sessionUrl, {
    method: 'PATCH',
    headers: buildWhepPatchHeaders(),
    body: generateSdpFragment(offerData, candidates),
  })
}

function deleteSession(sessionUrl) {
  if (!sessionUrl) return

  fetch(sessionUrl, {
    method: 'DELETE',
  }).catch(() => {
    // Ignore cleanup failures.
  })
}

/**
 * Connect to a MediaMTX stream via its documented WHEP browser flow.
 * @param {string} streamPath
 * @param {HTMLVideoElement} videoEl
 * @param {string} webrtcBaseUrl
 * @param {string} webrtcUsername
 * @param {string} webrtcPassword
 * @returns {object} - { pc, stop }
 */
export async function connectWebRTC(
  streamPath,
  videoEl,
  webrtcBaseUrl,
  webrtcUsername = '',
  webrtcPassword = ''
) {
  const whepUrl = buildWhepUrl(webrtcBaseUrl, streamPath)
  if (!whepUrl) {
    throw new Error('Missing WebRTC gateway address')
  }

  const offerHeaders = buildWhepEndpointHeaders(webrtcUsername, webrtcPassword, {
    'Content-Type': 'application/sdp',
  })
  const pc = new RTCPeerConnection({
    // MediaMTX can return server-side ICE candidates inside the WHEP answer and
    // this flow incrementally PATCHes the browser's local candidates afterward.
    iceServers: [],
  })

  let sessionUrl = null
  let stopped = false
  const queuedCandidates = []
  const pendingPatchCandidates = []
  let patchInFlight = false
  let offerData = null
  const transceiverDirection = 'recvonly'

  pc.addTransceiver('video', { direction: transceiverDirection })
  pc.addTransceiver('audio', { direction: transceiverDirection })
  // MediaMTX's documented browser WHEP flow creates a local data channel so
  // the peer connection can receive server-side data channels when available.
  pc.createDataChannel('')

  pc.ontrack = (event) => {
    if (videoEl && !videoEl.srcObject) {
      videoEl.srcObject = event.streams[0]
    }
  }

  async function patchPendingCandidates() {
    if (patchInFlight || stopped || !sessionUrl || !offerData || !pendingPatchCandidates.length) return

    patchInFlight = true
    const candidatesToPatch = pendingPatchCandidates.splice(0)
    try {
      await patchLocalCandidates(sessionUrl, offerData, candidatesToPatch)
    } catch (error) {
      console.warn(
        'Failed to send ICE candidates to WHEP session (connection quality may be affected):',
        error
      )
    } finally {
      patchInFlight = false
      if (pendingPatchCandidates.length) {
        patchPendingCandidates()
      }
    }
  }

  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  offerData = parseOfferData(offer.sdp)

  pc.onicecandidate = (event) => {
    if (stopped || !event.candidate) return

    if (!sessionUrl) {
      queuedCandidates.push(event.candidate)
      return
    }

    pendingPatchCandidates.push(event.candidate)
    patchPendingCandidates()
  }

  let answerSdp
  try {
    const result = await sendOffer(whepUrl, offer.sdp, offerHeaders)
    sessionUrl = result.sessionUrl
    answerSdp = result.answerSdp
  } catch (error) {
    pc.close()
    throw error
  }

  await pc.setRemoteDescription({
    type: 'answer',
    sdp: answerSdp,
  })

  if (queuedCandidates.length) {
    pendingPatchCandidates.push(...queuedCandidates)
    queuedCandidates.splice(0, queuedCandidates.length)
    patchPendingCandidates()
  }

  return {
    pc,
    stop: () => {
      if (stopped) return
      stopped = true
      deleteSession(sessionUrl)
      pc.close()
    },
  }
}
