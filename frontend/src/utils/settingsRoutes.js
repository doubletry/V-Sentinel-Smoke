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

export function defaultLandingFor(role) {
  // The `user` role is restricted to viewing alarm messages only.
  // `user` 角色仅允许查看告警消息。
  if (String(role || '').toLowerCase() === 'user') return '/messages'
  return '/'
}

export function userRoleRedirect(role, toPath) {
  // Returns the path the router should redirect to when a `user`-role
  // account navigates to a restricted route, or null if no redirect is needed.
  // 当 `user` 角色访问受限路由时返回重定向目标，无需重定向则返回 null。
  if (String(role || '').toLowerCase() !== 'user') return null
  if (toPath === '/messages' || toPath === '/auth') return null
  return '/messages'
}

export function legacySettingsSectionToManagement(section) {
  if (section === 'platform') return 'site'
  if (section === 'plugin') return 'plugins'
  if (['notifications', 'users'].includes(section)) return section
  return 'site'
}
