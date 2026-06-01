import { describe, expect, it } from 'vitest'
import {
  auditOperationTypeKey,
  buildAuditOperationOptions,
  localizeAuditOperationType,
  localizeAuditResource,
  localizeAuditRole,
} from '../auditLogPresentation.js'

describe('auditOperationTypeKey', () => {
  it('normalizes dotted operation codes into translation keys', () => {
    expect(auditOperationTypeKey('auth.login')).toBe('auth_login')
    expect(auditOperationTypeKey('notifications.instances.test')).toBe('notifications_instances_test')
  })

  it('returns an empty string for blank values', () => {
    expect(auditOperationTypeKey('')).toBe('')
    expect(auditOperationTypeKey(null)).toBe('')
  })
})

describe('localizeAuditOperationType', () => {
  const t = (key) => ({
    'auditLogs.operationTypes.auth_login': '账号登录',
    'auditLogs.operationTypes.processor_stop': '停止处理流程',
  }[key] ?? key)

  it('returns the localized label when the translation exists', () => {
    expect(localizeAuditOperationType(t, 'auth.login')).toBe('账号登录')
    expect(localizeAuditOperationType(t, 'processor.stop')).toBe('停止处理流程')
  })

  it('falls back to the raw operation code when the translation is missing', () => {
    expect(localizeAuditOperationType(t, 'video_gateways.create')).toBe('video_gateways.create')
  })

  it('returns a placeholder for blank values', () => {
    expect(localizeAuditOperationType(t, '')).toBe('-')
  })
})

describe('buildAuditOperationOptions', () => {
  const t = (key) => ({
    'auditLogs.operationTypes.auth_login': '账号登录',
  }[key] ?? key)

  it('keeps raw values for filtering while exposing localized labels', () => {
    expect(buildAuditOperationOptions(t, ['auth.login', 'sources.update'])).toEqual([
      { value: 'auth.login', label: '账号登录' },
      { value: 'sources.update', label: 'sources.update' },
    ])
  })
})

describe('localizeAuditRole', () => {
  const t = (key) => ({
    'auth.roles.admin': '管理员',
    'auth.roles.operator': '操作员',
  }[key] ?? key)

  it('localizes stored role codes', () => {
    expect(localizeAuditRole(t, 'admin', 'users.create')).toBe('管理员')
    expect(localizeAuditRole(t, 'operator', 'processor.stop')).toBe('操作员')
  })

  it('infers admin for bootstrap registration rows that lack a stored role', () => {
    expect(localizeAuditRole(t, '', 'auth.register')).toBe('管理员')
  })

  it('returns a placeholder for unknown empty roles', () => {
    expect(localizeAuditRole(t, '', 'settings.update')).toBe('-')
  })
})

describe('localizeAuditResource', () => {
  const t = (key, params) => ({
    'auditLogs.resourceTypes.auth': '账号',
    'auditLogs.resourceTypes.notifications_instances': '通知实例',
    'auditLogs.resourceValueFormat': `${params?.type}：${params?.value}`,
  }[key] ?? key)

  it('formats localized resource labels with ids', () => {
    expect(localizeAuditResource(t, { resource_type: 'auth', resource_id: 'smoketest-admin' })).toBe('账号：smoketest-admin')
    expect(localizeAuditResource(t, { resource_type: 'notifications.instances', resource_id: 'email-primary' })).toBe('通知实例：email-primary')
  })

  it('falls back to the raw resource type when no translation exists', () => {
    expect(localizeAuditResource(t, { resource_type: 'custom.scope', resource_id: 'abc' })).toBe('custom.scope：abc')
  })

  it('returns a placeholder when the resource is empty', () => {
    expect(localizeAuditResource(t, { resource_type: '', resource_id: '' })).toBe('-')
  })
})