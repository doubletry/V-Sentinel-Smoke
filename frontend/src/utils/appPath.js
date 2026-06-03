const ABSOLUTE_URL_PATTERN = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i

export function normalizeAppBasePath(value) {
  const text = String(value || '').trim()
  if (!text || text === '/') return ''
  const prefixed = text.startsWith('/') ? text : `/${text}`
  return prefixed.replace(/\/+$/, '')
}

export function resolveAppUrl(value, basePath = '') {
  const text = String(value || '').trim()
  if (!text) return ''
  if (ABSOLUTE_URL_PATTERN.test(text)) return text

  const base = normalizeAppBasePath(basePath)
  if (base && (text === base || text.startsWith(`${base}/`))) {
    return text
  }
  if (text.startsWith('/')) {
    return `${base}${text}`
  }
  return `${base}/${text}`
}
