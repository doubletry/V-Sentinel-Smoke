function normalizeOperationType(value) {
  return String(value || '').trim()
}

export function auditOperationTypeKey(value) {
  const normalized = normalizeOperationType(value)
  if (!normalized) {
    return ''
  }

  return normalized
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

export function localizeAuditOperationType(t, value) {
  const normalized = normalizeOperationType(value)
  if (!normalized) {
    return '-'
  }

  const translationKey = auditOperationTypeKey(normalized)
  if (!translationKey) {
    return normalized
  }

  const messageKey = `auditLogs.operationTypes.${translationKey}`
  const localized = t(messageKey)
  return localized === messageKey ? normalized : localized
}

export function buildAuditOperationOptions(t, values) {
  return (Array.isArray(values) ? values : []).map((value) => ({
    value,
    label: localizeAuditOperationType(t, value),
  }))
}