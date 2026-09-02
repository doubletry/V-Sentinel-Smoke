import axios from 'axios'
import config from '../config.js'
import { AUTH_TOKEN_STORAGE_KEY } from '../utils/authStorage.js'

const api = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 10000,
})

function requestPathname(url) {
  const value = typeof url === 'string' ? url : ''
  if (!value) return ''
  try {
    return new URL(value, 'http://localhost').pathname
  } catch (_) {
    return value.split('?')[0]
  }
}

// Request interceptor
api.interceptors.request.use(
  (cfg) => {
    const token = window.localStorage?.getItem(AUTH_TOKEN_STORAGE_KEY)
    cfg.headers = cfg.headers || {}
    if (token) {
      cfg.headers.Authorization = `Bearer ${token}`
    }
    return cfg
  },
  (error) => Promise.reject(error)
)

// Response interceptor
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    const detailText =
      typeof detail === 'string'
        ? detail
        : detail?.message || error.message || 'Request failed'
    const path = requestPathname(error.config?.url)
    const isAuthEndpoint = path === '/api/auth/login' || path === '/api/auth/bootstrap'
    const shouldExpireSession =
      typeof detail !== 'string' ||
      detail === 'Account banned' ||
      detail === 'Account expired' ||
      detail === 'Invalid token' ||
      detail === 'Invalid token payload' ||
      detail === 'Invalid token role' ||
      detail === 'Invalid token signature' ||
      detail === 'Missing bearer token' ||
      detail === 'Token expired'
    if (status === 401 && !isAuthEndpoint && shouldExpireSession && typeof window !== 'undefined') {
      try {
        window.localStorage?.removeItem(AUTH_TOKEN_STORAGE_KEY)
      } catch (_) { /* ignore */ }
      // Notify listeners (router/auth store) so they can redirect.
      try {
        window.dispatchEvent(new CustomEvent('v-sentinel:auth-expired', {
          detail: { reason: typeof detail === 'string' ? detail : detail?.code || 'unauthorized' },
        }))
      } catch (_) { /* ignore */ }
    }
    const err = new Error(detailText)
    err.status = status
    err.detail = detail
    return Promise.reject(err)
  }
)

// Sources API
export const sourcesApi = {
  list: () => api.get('/api/sources'),
  get: (id) => api.get(`/api/sources/${id}`),
  getByRtsp: (rtspUrl) => api.get('/api/sources/by-rtsp', { params: { rtsp_url: rtspUrl } }),
  create: (data) => api.post('/api/sources', data),
  update: (id, data) => api.put(`/api/sources/${id}`, data),
  delete: (id) => api.delete(`/api/sources/${id}`),
  exportRois: (id) =>
    api.get(`/api/sources/${id}/rois/export`, { responseType: 'blob' }),
  importRois: (id, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/api/sources/${id}/rois/import`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// Processor API
export const processorApi = {
  start: (sourceId) => api.post('/api/processor/start', { source_id: sourceId }),
  stop: (sourceId) => api.post('/api/processor/stop', { source_id: sourceId }),
  status: () => api.get('/api/processor/status'),
  togglePushResultStream: (sourceId, enabled) =>
    api.post(`/api/processor/${encodeURIComponent(sourceId)}/push-result-stream`, { enabled }),
}

export const messagesApi = {
  list: (params = {}) => api.get('/api/messages', { params }),
  markFalsePositive: (id) => api.post(`/api/messages/${id}/false-positive`),
  unmarkFalsePositive: (id) => api.delete(`/api/messages/${id}/false-positive`),
  resendNotification: (id) => api.post(`/api/messages/${id}/resend-notification`),
  vlReview: (id) => api.post(`/api/messages/${id}/vl-review`, null, { timeout: 0 }),
  delete: (id) => api.delete(`/api/messages/${id}`),
  batchDelete: (ids) => api.post('/api/messages/batch-delete', { ids }),
}


// Settings API
export const settingsApi = {
  get: () => api.get('/api/settings'),
  update: (data) => api.put('/api/settings', data),
  testEmail: (data) => api.post('/api/settings/email/test', data),
  testVl: (data) => api.post('/api/settings/vl/test', data, { timeout: 0 }),
  emailTemplatePlaceholders: () => api.get('/api/settings/email/template-placeholders'),
}

export const authApi = {
  bootstrap: () => api.get('/api/auth/bootstrap'),
  login: (data) => api.post('/api/auth/login', data),
  register: (data) => api.post('/api/auth/register', data),
  me: () => api.get('/api/auth/me'),
  changePassword: (data) => api.post('/api/auth/password', data),
}

export const usersApi = {
  list: () => api.get('/api/users'),
  create: (data) => api.post('/api/users', data),
  update: (username, data) => api.patch(`/api/users/${encodeURIComponent(username)}`, data),
  remove: (username) => api.delete(`/api/users/${encodeURIComponent(username)}`),
  resetPassword: (username, newPassword) => api.post(
    `/api/users/${encodeURIComponent(username)}/password`,
    { new_password: newPassword },
  ),
}

export const accessApi = {
  auditLogs: (params = {}) => api.get('/api/access/audit-logs', { params }),
  roles: () => api.get('/api/access/roles'),
  listBlockedIps: () => api.get('/api/access/blocked-ips'),
  unblockIp: (ip) => api.delete(`/api/access/blocked-ips/${encodeURIComponent(ip)}`),
  blockIp: (data) => api.post('/api/access/blocked-ips', data),
}

export const scenesApi = {
  list: () => api.get('/api/scenes'),
  get: (id) => api.get(`/api/scenes/${id}`),
}

export const videoGatewaysApi = {
  list: () => api.get('/api/video-gateways'),
  create: (data) => api.post('/api/video-gateways', data),
  update: (id, data) => api.put(`/api/video-gateways/${id}`, data),
}

export const notificationsApi = {
  providers: () => api.get('/api/notifications/providers'),
  createProvider: (data) => api.post('/api/notifications/providers', data),
  updateProvider: (id, data) => api.put(`/api/notifications/providers/${id}`, data),
  instances: () => api.get('/api/notifications/instances'),
  createInstance: (data) => api.post('/api/notifications/instances', data),
  updateInstance: (id, data) => api.put(`/api/notifications/instances/${id}`, data),
  testInstance: (id) => api.post(`/api/notifications/instances/${id}/test`),
  templates: () => api.get('/api/notifications/templates'),
  createTemplate: (data) => api.post('/api/notifications/templates', data),
  updateTemplate: (id, data) => api.put(`/api/notifications/templates/${id}`, data),
  policies: () => api.get('/api/notifications/policies'),
  createPolicy: (data) => api.post('/api/notifications/policies', data),
  updatePolicy: (id, data) => api.put(`/api/notifications/policies/${id}`, data),
}

export default api
