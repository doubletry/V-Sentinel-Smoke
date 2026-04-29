export function normalizeRoutePath(value) {
  return String(value || '').trim().replace(/^\/+/, '').replace(/\/+$/, '')
}

export function normalizeBaseAddress(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function normalizeCredential(value) {
  return String(value || '').trim()
}

function tryParseUrl(value) {
  try {
    return new URL(value)
  } catch (_) {
    return null
  }
}

function applyCredentials(url, username, password) {
  const normalizedUsername = normalizeCredential(username)
  const normalizedPassword = String(password || '')
  url.username = normalizedUsername
  url.password = normalizedUsername ? normalizedPassword : ''
}

export function buildRtspUrl(rtspBaseAddress, routePath) {
  const base = normalizeBaseAddress(rtspBaseAddress)
  const route = normalizeRoutePath(routePath)
  if (!base || !route) return ''
  return `${base}/${route}`
}

export function buildRtspUrlWithAuth(rtspBaseAddress, routePath, username, password) {
  const base = normalizeBaseAddress(rtspBaseAddress)
  const route = normalizeRoutePath(routePath)
  if (!base || !route) return ''

  const parsed = tryParseUrl(base)
  if (!parsed) return `${base}/${route}`

  applyCredentials(parsed, username, password)
  parsed.pathname = `${parsed.pathname.replace(/\/+$/, '')}/${route}`
  return parsed.toString()
}

export function buildWebRtcUrlWithAuth(webrtcBaseAddress, username, password) {
  const base = normalizeBaseAddress(webrtcBaseAddress)
  if (!base) return ''

  const parsed = tryParseUrl(base)
  if (!parsed) return base

  applyCredentials(parsed, username, password)
  return parsed.toString()
}

export function extractRoutePath(rtspUrl, rtspBaseAddress) {
  const full = String(rtspUrl || '').trim()
  if (!full) return ''

  const base = normalizeBaseAddress(rtspBaseAddress)
  const parsedFull = tryParseUrl(full)
  const parsedBase = tryParseUrl(base)
  if (
    parsedFull &&
    parsedBase &&
    parsedFull.protocol === parsedBase.protocol &&
    parsedFull.hostname === parsedBase.hostname &&
    parsedFull.port === parsedBase.port
  ) {
    const fullPath = normalizeRoutePath(parsedFull.pathname)
    const basePath = normalizeRoutePath(parsedBase.pathname)
    if (basePath && fullPath.startsWith(`${basePath}/`)) {
      return normalizeRoutePath(fullPath.slice(basePath.length + 1))
    }
    if (!basePath) {
      return fullPath
    }
  }

  if (base && full.startsWith(`${base}/`)) {
    return normalizeRoutePath(full.slice(base.length + 1))
  }

  try {
    const parsed = new URL(full)
    return normalizeRoutePath(parsed.pathname)
  } catch (_) {
    const marker = full.indexOf('://')
    if (marker >= 0) {
      const firstSlash = full.indexOf('/', marker + 3)
      if (firstSlash >= 0) {
        return normalizeRoutePath(full.slice(firstSlash + 1))
      }
    }
  }

  return normalizeRoutePath(full)
}
