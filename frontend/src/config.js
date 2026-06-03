import { normalizeAppBasePath } from './utils/appPath.js'

/**
 * Application configuration.
 *
 * In production the frontend is served from the same reverse-proxy path as the
 * backend API, so API / WS base URLs include the app base path. During Vite
 * development requests are proxied to the backend automatically.
 *
 * Override via environment variables when needed:
 *   VITE_APP_BASE_PATH, VITE_API_BASE_URL, VITE_WS_BASE_URL,
 *   VITE_MEDIAMTX_WEBRTC_URL
 */
export const appBasePath = normalizeAppBasePath(
  typeof document !== 'undefined' && document.baseURI
    ? new URL(document.baseURI).pathname
    : '/',
)

function detectApiBase() {
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL
  if (import.meta.env.DEV && !appBasePath) return ''
  if (typeof window === 'undefined') return appBasePath
  return `${window.location.origin}${appBasePath}`
}

function detectWsBase() {
  if (import.meta.env.VITE_WS_BASE_URL) return import.meta.env.VITE_WS_BASE_URL
  if (import.meta.env.DEV && !appBasePath) return ''
  if (typeof window === 'undefined') return appBasePath
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${appBasePath}`
}

export default {
  siteName: 'V-Sentinel',
  siteDescription: 'AI Video Surveillance Analysis Platform',
  appBasePath,
  apiBaseUrl: detectApiBase(),
  wsBaseUrl: detectWsBase(),
  mediamtxWebrtcUrl: import.meta.env.VITE_MEDIAMTX_WEBRTC_URL || 'http://localhost:8889',
}
