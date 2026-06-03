export const defaultSubjectTemplate = '[{site_title}] {event_label} alert from {source_name}'
export const defaultBodyTemplate = 'Event: {event_label}\nTime: {local_time} ({timezone})\nVideo source: {source_name} ({source_id})\nMessage: {message}'
export const defaultSocketMessageTemplate = '{event_label} alert from {source_name}'
export const ALL_NOTIFICATION_SOURCES_VALUE = '__ALL_NOTIFICATION_SOURCES__'

// Keep in sync with core.notification_client.WebhookNotificationProvider.DEFAULT_PAYLOAD_TEMPLATE.
export const defaultWebhookPayloadTemplate = {
  site_title: '{site_title}',
  event_type: '{event_type}',
  event_label: '{event_label}',
  message: '{message}',
  timestamp: '{timestamp}',
  local_time: '{local_time}',
  timezone: '{timezone}',
  source: {
    id: '{source_id}',
    name: '{source_name}',
    route_path: '{source_route_path}',
    remark: '{source_remark}',
  },
  detection: {
    labels: '{labels}',
    confidence: '{confidence}',
    confidence_percent: '{confidence_percent}',
  },
  images: {
    original_url: '{original_image_url}',
    detected_url: '{detected_image_url}',
  },
}

export function normalizeAddressField(value) {
  return Array.isArray(value) ? value.join(',') : String(value || '')
}

export function formatSocketHexBytes(value) {
  const normalized = String(value || '').replace(/[\s-]+/g, '').toUpperCase()
  return normalized.match(/.{1,2}/g)?.join('-') || ''
}

export function formatSocketHexInput(value, cursorIndex = null) {
  const rawValue = String(value || '')
  const rawCursorIndex = cursorIndex === null || cursorIndex === undefined ? rawValue.length : Number(cursorIndex) || 0
  const normalizedCursorIndex = Math.max(0, Math.min(rawCursorIndex, rawValue.length))
  const hexCharsBeforeCursor = (rawValue.slice(0, normalizedCursorIndex).match(/[\da-fA-F]/g) || []).length
  const text = formatSocketHexBytes(rawValue)
  let cursor = 0
  let hexCharsSeen = 0

  while (cursor < text.length && hexCharsSeen < hexCharsBeforeCursor) {
    if (/[\da-fA-F]/.test(text[cursor])) {
      hexCharsSeen += 1
    }
    cursor += 1
  }

  return { text, cursor }
}

export function normalizeSourceIds(value) {
  return [...new Set((Array.isArray(value) ? value : []).map((item) => String(item || '').trim()).filter(Boolean))]
}

export function serializeNotificationSourceSelection(form) {
  return Boolean(form?.apply_to_all_sources) ? [ALL_NOTIFICATION_SOURCES_VALUE] : normalizeSourceIds(form?.source_ids || [])
}

export function applyNotificationSourceSelection(form, selectedValues) {
  const normalized = normalizeSourceIds(selectedValues)
  const includesAllSources = normalized.includes(ALL_NOTIFICATION_SOURCES_VALUE)
  if (!includesAllSources) {
    return {
      apply_to_all_sources: false,
      source_ids: normalized,
    }
  }

  const selectedSpecificSources = normalized.filter((item) => item !== ALL_NOTIFICATION_SOURCES_VALUE)
  if (Boolean(form?.apply_to_all_sources) && selectedSpecificSources.length) {
    return {
      apply_to_all_sources: false,
      source_ids: selectedSpecificSources,
    }
  }

  return {
    apply_to_all_sources: true,
    source_ids: [],
  }
}

export function createDefaultNotificationInstanceForm(type = 'email') {
  return {
    name: '',
    type,
    enabled: true,
    apply_to_all_sources: true,
    source_ids: [],
    smtp_host: '',
    smtp_port: '587',
    use_tls: true,
    from_address: '',
    smtp_password: '',
    to_addresses: '',
    cc_addresses: '',
    url: '',
    method: 'POST',
    headers_text: '{}',
    webhook_payload_text: JSON.stringify(defaultWebhookPayloadTemplate, null, 2),
    cooldown_seconds: '300',
    subject_template: defaultSubjectTemplate,
    body_template: defaultBodyTemplate,
    socket_protocol: 'tcp',
    socket_host: '',
    socket_port: '',
    socket_message_mode: 'string',
    socket_message_text: defaultSocketMessageTemplate,
    socket_message_hex: '',
    socket_encoding: 'utf-8',
    socket_wait_for_response: false,
    socket_response_timeout_seconds: '3',
  }
}

function parseJsonObject(rawValue, errorMessage) {
  let parsed = {}
  try {
    parsed = JSON.parse(rawValue || '{}')
  } catch {
    throw new Error(errorMessage)
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error(errorMessage)
  }
  return parsed
}

export function serializeNotificationInstanceForEdit(item) {
  let headersText = '{}'
  try {
    headersText = JSON.stringify(item.config?.headers || {}, null, 2)
  } catch {
    headersText = '{}'
  }

  return {
    name: item.name || '',
    type: item.type || 'email',
    enabled: Boolean(item.enabled),
    apply_to_all_sources: Boolean(item.apply_to_all_sources ?? true),
    source_ids: normalizeSourceIds(item.source_ids || []),
    smtp_host: item.config?.smtp_host || '',
    smtp_port: String(item.config?.smtp_port || '587'),
    use_tls: Boolean(item.config?.use_tls ?? true),
    from_address: item.config?.from_address || '',
    smtp_password: item.config?.smtp_password || '',
    to_addresses: normalizeAddressField(item.config?.to_addresses),
    cc_addresses: normalizeAddressField(item.config?.cc_addresses),
    url: item.config?.url || '',
    method: item.config?.method || 'POST',
    headers_text: headersText,
    webhook_payload_text: JSON.stringify(item.config?.payload_template || defaultWebhookPayloadTemplate, null, 2),
    cooldown_seconds: String(item.config?.cooldown_seconds || '300'),
    subject_template: item.config?.subject_template || defaultSubjectTemplate,
    body_template: item.config?.body_template || defaultBodyTemplate,
    socket_protocol: String(item.config?.protocol || 'tcp').toLowerCase(),
    socket_host: item.config?.host || '',
    socket_port: String(item.config?.port || ''),
    socket_message_mode: String(item.config?.message_mode || 'string').toLowerCase(),
    socket_message_text: item.config?.message_text || defaultSocketMessageTemplate,
    socket_message_hex: item.config?.message_hex || '',
    socket_encoding: item.config?.encoding || 'utf-8',
    socket_wait_for_response: Boolean(item.config?.wait_for_response ?? false),
    socket_response_timeout_seconds: String(item.config?.response_timeout_seconds || '3'),
  }
}

export function buildNotificationInstancePayload(form, t = (key) => key) {
  const sourceIds = normalizeSourceIds(form.source_ids)
  const payload = {
    name: String(form.name || '').trim(),
    type: form.type,
    enabled: Boolean(form.enabled),
    apply_to_all_sources: Boolean(form.apply_to_all_sources),
    source_ids: Boolean(form.apply_to_all_sources) ? [] : sourceIds,
    config: {
      cooldown_seconds: String(form.cooldown_seconds || '300').trim(),
    },
  }

  if (!payload.name) {
    throw new Error(t('settings.notificationInstanceNameRequired'))
  }
  if (!payload.apply_to_all_sources && !payload.source_ids.length) {
    throw new Error(t('settings.notificationSourceSelectionRequired'))
  }

  if (payload.type === 'email') {
    payload.config = {
      ...payload.config,
      subject_template: form.subject_template || defaultSubjectTemplate,
      body_template: form.body_template || defaultBodyTemplate,
      smtp_host: String(form.smtp_host || '').trim(),
      smtp_port: String(form.smtp_port || '587').trim(),
      use_tls: Boolean(form.use_tls),
      from_address: String(form.from_address || '').trim(),
      smtp_username: String(form.from_address || '').trim(),
      smtp_password: form.smtp_password || '',
      to_addresses: String(form.to_addresses || '').trim(),
      cc_addresses: String(form.cc_addresses || '').trim(),
    }
    return payload
  }

  if (payload.type === 'webhook') {
    const headers = parseJsonObject(form.headers_text, t('settings.notificationWebhookHeadersInvalid'))
    const payloadTemplate = parseJsonObject(form.webhook_payload_text, t('settings.notificationWebhookPayloadInvalid'))
    payload.config = {
      ...payload.config,
      url: String(form.url || '').trim(),
      method: String(form.method || 'POST').toUpperCase(),
      headers,
      payload_template: payloadTemplate,
    }
    return payload
  }

  const protocol = String(form.socket_protocol || 'tcp').trim().toLowerCase()
  const messageMode = String(form.socket_message_mode || 'string').trim().toLowerCase()
  payload.config = {
    ...payload.config,
    protocol,
    host: String(form.socket_host || '').trim(),
    port: String(form.socket_port || '').trim(),
    message_mode: messageMode,
  }
  if (!payload.config.host || !payload.config.port) {
    throw new Error(t('settings.notificationSocketAddressRequired'))
  }
  if (messageMode === 'hex') {
    const normalizedHex = String(form.socket_message_hex || '').replace(/[\s-]+/g, '')
    if (!normalizedHex || normalizedHex.length % 2 !== 0 || !/^[\da-fA-F]+$/.test(normalizedHex)) {
      throw new Error(t('settings.notificationSocketHexInvalid'))
    }
    payload.config.message_hex = normalizedHex
  } else {
    payload.config.message_text = String(form.socket_message_text || defaultSocketMessageTemplate)
    payload.config.encoding = String(form.socket_encoding || 'utf-8').trim() || 'utf-8'
  }
  if (protocol === 'tcp') {
    payload.config.wait_for_response = Boolean(form.socket_wait_for_response)
    if (payload.config.wait_for_response) {
      const timeoutText = String(form.socket_response_timeout_seconds || '3').trim()
      const timeoutValue = Number(timeoutText)
      if (!Number.isFinite(timeoutValue) || timeoutValue <= 0) {
        throw new Error(t('settings.notificationSocketTimeoutInvalid'))
      }
      payload.config.response_timeout_seconds = timeoutText
    }
  }
  return payload
}