export function getDefaultSettingsSection(canManageSettings, canManageUsers) {
  if (canManageSettings) return 'platform'
  if (canManageUsers) return 'users'
  return null
}

export function getDefaultSettingsPath(canManageSettings, canManageUsers) {
  const section = getDefaultSettingsSection(canManageSettings, canManageUsers)
  return section ? `/settings/${section}` : null
}
