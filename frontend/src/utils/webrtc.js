import config from '../config.js'
import { AUTH_TOKEN_STORAGE_KEY } from './authStorage.js'
import {
  buildWhepPatchHeaders,
  generateSdpFragment,
  parseOfferData,
} from './webrtcHelpers.js'

function _encodePath(streamPath) {
  return String(streamPath || '')
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/')
}

function _whepOfferUrl(streamPath) {
  return `${config.apiBaseUrl}/api/video/${_encodePath(streamPath)}/whep-offer`
}

function _whepSessionUrl(streamPath, sessionId) {
  return `${config.apiBaseUrl}/api/video/${_encodePath(streamPath)}/whep-session/${encodeURIComponent(sessionId)}`
}

function _authHeaders() {
  const token = window.localStorage?.getItem(AUTH_TOKEN_STORAGE_KEY)
  const headers = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

async function sendOffer(whepUrl, offerSdp) {
  const response = await fetch(whepUrl, {
    method: 'POST',
    headers: {
      ..._authHeaders(),
      'Content-Type': 'application/sdp',
    },
    body: offerSdp,
  })

  switch (response.status) {
    case 200: {
      const sessionLocation = response.headers.get('X-Whep-Session-Location') || ''
      const sessionId = _extractSessionId(sessionLocation)
      return {
        answerSdp: await response.text(),
        sessionId,
      }
    }
    case 404: {
      const error = new Error('stream not found')
      error.name = 'WHEPError'
      error.status = 404
      throw error
    }
    default: {
      const error = new Error(`WHEP error: ${response.status}`)
      error.name = 'WHEPError'
      error.status = response.status
      throw error
    }
  }
}

function _extractSessionId(location) {
  if (!location) return ''
  try {
    const url = new URL(location, 'http://localhost')
    const segments = url.pathname.split('/').filter(Boolean)
    return segments[segments.length - 1] || ''
  } catch (_) {
    const segments = location.split('/').filter(Boolean)
    return segments[segments.length - 1] || ''
  }
}

async function patchLocalCandidates(streamPath, sessionId, offerData, candidates) {
  if (!streamPath || !sessionId || !candidates.length) return

  const sessionUrl = _whepSessionUrl(streamPath, sessionId)
  await fetch(sessionUrl, {
    method: 'PATCH',
    headers: {
      ..._authHeaders(),
      ...buildWhepPatchHeaders(),
    },
    body: generateSdpFragment(offerData, candidates),
  })
}

function deleteSession(streamPath, sessionId) {
  if (!streamPath || !sessionId) return

  const sessionUrl = _whepSessionUrl(streamPath, sessionId)
  fetch(sessionUrl, {
    method: 'DELETE',
    headers: _authHeaders(),
  }).catch(() => {
    // Ignore cleanup failures.
  })
}

/**
 * Connect to a MediaMTX stream via the backend WHEP proxy.
 * @param {string} streamPath
 * @param {HTMLVideoElement} videoEl
 * @returns {object} - { pc, stop }
 */
export async function connectWebRTC(streamPath, videoEl) {
  const whepUrl = _whepOfferUrl(streamPath)

  const pc = new RTCPeerConnection({
    iceServers: [],
  })

  let sessionId = null
  let stopped = false
  const queuedCandidates = []
  const pendingPatchCandidates = []
  let patchInFlight = false
  let offerData = null
  const transceiverDirection = 'recvonly'

  pc.addTransceiver('video', { direction: transceiverDirection })
  pc.addTransceiver('audio', { direction: transceiverDirection })
  pc.createDataChannel('')

  pc.ontrack = (event) => {
    if (videoEl && !videoEl.srcObject) {
      videoEl.srcObject = event.streams[0]
    }
  }

  async function patchPendingCandidates() {
    if (patchInFlight || stopped || !streamPath || !sessionId || !offerData || !pendingPatchCandidates.length) return

    patchInFlight = true
    const candidatesToPatch = pendingPatchCandidates.splice(0)
    try {
      await patchLocalCandidates(streamPath, sessionId, offerData, candidatesToPatch)
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

    if (!sessionId) {
      queuedCandidates.push(event.candidate)
      return
    }

    pendingPatchCandidates.push(event.candidate)
    patchPendingCandidates()
  }

  let answerSdp
  try {
    const result = await sendOffer(whepUrl, offer.sdp)
    sessionId = result.sessionId
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
      deleteSession(streamPath, sessionId)
      pc.close()
    },
  }
}
