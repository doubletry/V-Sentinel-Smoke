export function canViewAuditLogs(hasAuditReadPermission) {
  return Boolean(hasAuditReadPermission)
}

function normalizeManagementAccess(accessOrCanManageSettings, canManageUsers, canViewLogs = false) {
  if (typeof accessOrCanManageSettings === 'object' && accessOrCanManageSettings !== null) {
    return {
      canManageSiteSettings: Boolean(accessOrCanManageSettings.canManageSiteSettings),
      canManageUsers: Boolean(accessOrCanManageSettings.canManageUsers),
      canViewLogs: Boolean(accessOrCanManageSettings.canViewLogs),
      canManageVengineSettings: Boolean(accessOrCanManageSettings.canManageVengineSettings),
      canManageNotificationSettings: Boolean(accessOrCanManageSettings.canManageNotificationSettings),
      canManagePluginSettings: Boolean(accessOrCanManageSettings.canManagePluginSettings),
    }
  }
  const canManageSettings = Boolean(accessOrCanManageSettings)
  return {
    canManageSiteSettings: canManageSettings,
    canManageUsers: Boolean(canManageUsers),
    canViewLogs: Boolean(canViewLogs),
    canManageVengineSettings: canManageSettings,
    canManageNotificationSettings: canManageSettings,
    canManagePluginSettings: canManageSettings,
  }
}

export function getDefaultManagementSection(accessOrCanManageSettings, canManageUsers, canViewLogs = false) {
  const access = normalizeManagementAccess(accessOrCanManageSettings, canManageUsers, canViewLogs)
  if (access.canManageSiteSettings) return 'site'
  if (access.canManageUsers) return 'users'
  if (access.canViewLogs) return 'logs'
  if (access.canManageNotificationSettings) return 'notifications'
  if (access.canManagePluginSettings) return 'plugins'
  if (access.canManageVengineSettings) return 'vengine'
  return null
}

export function getDefaultManagementPath(accessOrCanManageSettings, canManageUsers, canViewLogs = false) {
  const section = getDefaultManagementSection(accessOrCanManageSettings, canManageUsers, canViewLogs)
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

export function getManagementSectionFromPath(toPath) {
  const normalizedPath = String(toPath || '').split('?')[0].split('#')[0]
  const match = normalizedPath.match(/^\/management(?:\/([^/]+))?/)
  // Returns null for non-management paths, empty string for management root.
  return match ? (match[1] || '') : null
}

export function canOpenManagementSection(section, accessOrCanManageSettings, canManageUsers, canViewLogs = false) {
  const access = normalizeManagementAccess(accessOrCanManageSettings, canManageUsers, canViewLogs)
  if (section === 'site') return access.canManageSiteSettings
  if (section === 'users') return access.canManageUsers
  if (section === 'logs') return access.canViewLogs
  if (section === 'vengine') return access.canManageVengineSettings
  if (section === 'notifications') return access.canManageNotificationSettings
  if (section === 'plugins') return access.canManagePluginSettings
  return false
}

export function managementRouteRedirect(toPath, accessOrCanManageSettings, canManageUsers, canViewLogs = false) {
  const section = getManagementSectionFromPath(toPath)
  if (section === null) return null
  const fallback = getDefaultManagementPath(accessOrCanManageSettings, canManageUsers, canViewLogs)
  if (!section) return fallback
  if (canOpenManagementSection(section, accessOrCanManageSettings, canManageUsers, canViewLogs)) return null
  return fallback
}

export function legacySettingsSectionToManagement(section) {
  if (section === 'platform') return 'site'
  if (section === 'plugin') return 'plugins'
  if (['notifications', 'users'].includes(section)) return section
  return 'site'
}
