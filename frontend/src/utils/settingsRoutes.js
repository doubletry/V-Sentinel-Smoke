export function getDefaultSettingsSection(canManageSettings, canManageUsers) {
  if (canManageSettings) return 'platform'
  if (canManageUsers) return 'users'
  return 'platform'
}

export function getDefaultSettingsPath(canManageSettings, canManageUsers) {
  return `/settings/${getDefaultSettingsSection(canManageSettings, canManageUsers)}`
}
