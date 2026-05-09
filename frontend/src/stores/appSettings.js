import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import config from '../config.js'
import { settingsApi } from '../api/index.js'
import { setI18nLocale } from '../i18n/index.js'

const DEFAULT_EVENT_EMAIL_BODY_TEMPLATE = [
  'Event: {event_label}',
  'Time: {local_time} ({timezone})',
  'Video source: {source_name} ({source_id})',
  'Labels: {labels}',
  'Highest confidence: {confidence_percent}',
  'Detection count: {detection_count}',
  'Frame ID: {frame_id}',
  'Active tracks: {active_tracks}',
].join('\n')

const DEFAULT_UI_SETTINGS = {
  ui_language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  processor_plugin: 'smoke',
  site_title: config.siteName,
  site_description: config.siteDescription,
  favicon_url: '/favicon.ico',
  roi_tag_options: '["person","vehicle","intrusion"]',
  mediamtx_rtsp_addr: 'rtsp://localhost:8554',
  mediamtx_rtsp_username: '',
  mediamtx_rtsp_password: '',
  mediamtx_webrtc_addr: config.mediamtxWebrtcUrl || 'http://localhost:8889',
  mediamtx_webrtc_username: '',
  mediamtx_webrtc_password: '',
  email_from_address: '',
  email_from_auth_code: '',
  email_to_addresses: '',
  email_cc_addresses: '',
  email_port: '50055',
  email_event_enabled: 'true',
  email_timed_enabled: 'false',
  email_event_subject_template: '[{site_title}] {event_label} alert from {source_name}',
  email_event_body_template: DEFAULT_EVENT_EMAIL_BODY_TEMPLATE,
  smoke_detection_model_name: 'smoke-fire-detection',
  smoke_detection_model_version: '',
  smoke_temporal_confirm_frames: '3',
  smoke_email_cooldown_seconds: '300',
  message_retention_days: '7',
}

export function parseRoiTagOptions(raw) {
  if (Array.isArray(raw)) {
    return Array.from(
      new Set(raw.map((item) => String(item || '').trim()).filter(Boolean))
    )
  }

  const text = String(raw || '').trim()
  if (!text) return []

  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) {
      return Array.from(
        new Set(parsed.map((item) => String(item || '').trim()).filter(Boolean))
      )
    }
  } catch (_) {
    // Fallback to comma-separated parsing for backward compatibility.
  }

  return Array.from(
    new Set(text.split(',').map((item) => item.trim()).filter(Boolean))
  )
}

export const useAppSettingsStore = defineStore('appSettings', () => {
  const settingsSchema = ref({
    defaults: { ...DEFAULT_UI_SETTINGS },
    sections: [],
  })
  const schemaLoaded = ref(false)
  const loading = ref(false)
  const loaded = ref(false)
  const settingsDefaults = computed(() => ({
    ...DEFAULT_UI_SETTINGS,
    ...(settingsSchema.value?.defaults || {}),
  }))
  const settingsSections = computed(() => settingsSchema.value?.sections || [])
  const settings = ref({ ...settingsDefaults.value })

  function withDefaults(data = {}) {
    return {
      ...settingsDefaults.value,
      ...data,
    }
  }

  const siteTitle = computed(() => settings.value.site_title || DEFAULT_UI_SETTINGS.site_title)
  const siteDescription = computed(() => settings.value.site_description || DEFAULT_UI_SETTINGS.site_description)
  const uiLanguage = computed(() => settings.value.ui_language || DEFAULT_UI_SETTINGS.ui_language)
  const timeZone = computed(() => settings.value.timezone || DEFAULT_UI_SETTINGS.timezone)
  const faviconUrl = computed(() => settings.value.favicon_url || DEFAULT_UI_SETTINGS.favicon_url)
  const siteIconUrl = computed(() => faviconUrl.value)
  const roiTagOptions = computed(
    () => parseRoiTagOptions(settings.value.roi_tag_options || DEFAULT_UI_SETTINGS.roi_tag_options)
  )
  const mediamtxRtspAddr = computed(
    () => settings.value.mediamtx_rtsp_addr || DEFAULT_UI_SETTINGS.mediamtx_rtsp_addr
  )
  const mediamtxWebrtcAddr = computed(
    () => settings.value.mediamtx_webrtc_addr || DEFAULT_UI_SETTINGS.mediamtx_webrtc_addr
  )
  const mediamtxRtspUsername = computed(
    () => settings.value.mediamtx_rtsp_username || DEFAULT_UI_SETTINGS.mediamtx_rtsp_username
  )
  const mediamtxRtspPassword = computed(
    () => settings.value.mediamtx_rtsp_password || DEFAULT_UI_SETTINGS.mediamtx_rtsp_password
  )
  const mediamtxWebrtcUsername = computed(
    () => settings.value.mediamtx_webrtc_username || DEFAULT_UI_SETTINGS.mediamtx_webrtc_username
  )
  const mediamtxWebrtcPassword = computed(
    () => settings.value.mediamtx_webrtc_password || DEFAULT_UI_SETTINGS.mediamtx_webrtc_password
  )

  async function fetchSettingsSchema(force = false) {
    if (schemaLoaded.value && !force) {
      return settingsSchema.value
    }

    const data = await settingsApi.schema()
    settingsSchema.value = {
      defaults: {
        ...DEFAULT_UI_SETTINGS,
        ...(data?.defaults || {}),
      },
      sections: Array.isArray(data?.sections) ? data.sections : [],
    }
    schemaLoaded.value = true
    settings.value = withDefaults(settings.value)
    return settingsSchema.value
  }

  async function fetchSettings(force = false) {
    if (loaded.value && !force) {
      return settings.value
    }

    loading.value = true
    try {
      await fetchSettingsSchema(force)
      const data = await settingsApi.get()
      settings.value = withDefaults(data)
      loaded.value = true
      return settings.value
    } finally {
      loading.value = false
    }
  }

  async function updateSettings(payload) {
    if (!schemaLoaded.value) {
      await fetchSettingsSchema()
    }
    const data = await settingsApi.update(payload)
    settings.value = withDefaults(data)
    loaded.value = true
    return settings.value
  }

  async function testEmail(payload) {
    return settingsApi.testEmail(payload)
  }

  function patchSettings(partial) {
    settings.value = withDefaults({
      ...settings.value,
      ...partial,
    })
  }

  function applyLanguage(language) {
    const locale = language || uiLanguage.value
    setI18nLocale(locale)
  }

  return {
    settings,
    settingsSchema,
    settingsDefaults,
    settingsSections,
    loading,
    loaded,
    siteTitle,
    siteDescription,
    uiLanguage,
    timeZone,
    faviconUrl,
    siteIconUrl,
    roiTagOptions,
    mediamtxRtspAddr,
    mediamtxWebrtcAddr,
    mediamtxRtspUsername,
    mediamtxRtspPassword,
    mediamtxWebrtcUsername,
    mediamtxWebrtcPassword,
    fetchSettingsSchema,
    fetchSettings,
    updateSettings,
    testEmail,
    patchSettings,
    applyLanguage,
  }
})
