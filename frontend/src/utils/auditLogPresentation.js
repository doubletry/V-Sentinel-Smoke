function normalizeOperationType(value) {
  return String(value || '').trim()
}

function normalizeText(value) {
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

export function localizeAuditRole(t, role, operationType = '') {
  const normalizedRole = normalizeText(role).toLowerCase()
  if (normalizedRole) {
    const roleKey = `auth.roles.${normalizedRole}`
    const localizedRole = t(roleKey)
    return localizedRole === roleKey ? normalizedRole : localizedRole
  }

  if (normalizeText(operationType) === 'auth.register') {
    return t('auth.roles.admin')
  }

  return '-'
}

export function localizeAuditResource(t, row) {
  const resourceType = normalizeText(row?.resource_type)
  const resourceId = normalizeText(row?.resource_id)

  if (!resourceType && !resourceId) {
    return '-'
  }

  const typeKey = auditOperationTypeKey(resourceType)
  const messageKey = `auditLogs.resourceTypes.${typeKey}`
  const localizedType = typeKey ? t(messageKey) : ''
  const typeLabel = localizedType && localizedType !== messageKey ? localizedType : resourceType

  if (typeLabel && resourceId) {
    return t('auditLogs.resourceValueFormat', { type: typeLabel, value: resourceId })
  }

  return typeLabel || resourceId || '-'
}