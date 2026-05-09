import axios from 'axios'
import config from '../config.js'

const api = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 10000,
})

// Request interceptor
api.interceptors.request.use(
  (cfg) => cfg,
  (error) => Promise.reject(error)
)

// Response interceptor
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || error.message || 'Request failed'
    return Promise.reject(new Error(msg))
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
  startAll: () => api.post('/api/processor/start-all'),
  stopAll: () => api.post('/api/processor/stop-all'),
  plugins: () => api.get('/api/processor/plugins'),
  logs: (page = 1, pageSize = 20) => api.get('/api/processor/logs', {
    params: { page, page_size: pageSize },
  }),
  status: () => api.get('/api/processor/status'),
}

export const messagesApi = {
  list: (params = {}) => api.get('/api/messages', { params }),
  markFalsePositive: (id) => api.post(`/api/messages/${id}/false-positive`),
  unmarkFalsePositive: (id) => api.delete(`/api/messages/${id}/false-positive`),
}


// Settings API
export const settingsApi = {
  get: () => api.get('/api/settings'),
  update: (data) => api.put('/api/settings', data),
  testEmail: (data) => api.post('/api/settings/email/test', data),
  emailTemplatePlaceholders: () => api.get('/api/settings/email/template-placeholders'),
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
  templates: () => api.get('/api/notifications/templates'),
  createTemplate: (data) => api.post('/api/notifications/templates', data),
  updateTemplate: (id, data) => api.put(`/api/notifications/templates/${id}`, data),
  policies: () => api.get('/api/notifications/policies'),
  createPolicy: (data) => api.post('/api/notifications/policies', data),
  updatePolicy: (id, data) => api.put(`/api/notifications/policies/${id}`, data),
}

export default api
