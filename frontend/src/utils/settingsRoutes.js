export function canViewProcessingLogs(hasSourceOperatePermission, canManageSettings) {
  return Boolean(hasSourceOperatePermission || canManageSettings)
}

export function getDefaultManagementSection(canManageSettings, canManageUsers, canViewLogs = false) {
  if (canManageSettings) return 'site'
  if (canManageUsers) return 'users'
  if (canViewLogs) return 'logs'
  return null
}

export function getDefaultManagementPath(canManageSettings, canManageUsers, canViewLogs = false) {
  const section = getDefaultManagementSection(canManageSettings, canManageUsers, canViewLogs)
  return section ? `/management/${section}` : null
}

export function getDefaultSettingsSection(canManageSettings, canManageUsers) {
  if (canManageSettings) return 'site'
  if (canManageUsers) return 'users'
  return null
}

export function getDefaultSettingsPath(canManageSettings, canManageUsers) {
  return getDefaultManagementPath(canManageSettings, canManageUsers)
}

export function legacySettingsSectionToManagement(section) {
  if (section === 'platform') return 'site'
  if (section === 'plugin') return 'plugins'
  if (['notifications', 'users'].includes(section)) return section
  return 'site'
}
