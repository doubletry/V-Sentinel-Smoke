import { describe, expect, it } from 'vitest'
import {
  auditOperationTypeKey,
  buildAuditOperationOptions,
  localizeAuditOperationType,
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