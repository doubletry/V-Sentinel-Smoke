import { describe, it, expect } from 'vitest'
import { canViewAuditLogs, defaultLandingFor, userRoleRedirect } from '../settingsRoutes.js'

describe('canViewAuditLogs', () => {
  it('only allows explicit audit read permission', () => {
    expect(canViewAuditLogs(true)).toBe(true)
    expect(canViewAuditLogs(false)).toBe(false)
    expect(canViewAuditLogs(null)).toBe(false)
  })
})

describe('defaultLandingFor', () => {
  it('returns /messages for the user role', () => {
    expect(defaultLandingFor('user')).toBe('/messages')
    expect(defaultLandingFor('USER')).toBe('/messages')
  })

  it('returns / for operator and admin', () => {
    expect(defaultLandingFor('operator')).toBe('/')
    expect(defaultLandingFor('admin')).toBe('/')
  })

  it('returns / for empty or unknown roles', () => {
    expect(defaultLandingFor('')).toBe('/')
    expect(defaultLandingFor(null)).toBe('/')
    expect(defaultLandingFor(undefined)).toBe('/')
    expect(defaultLandingFor('guest')).toBe('/')
  })
})

describe('userRoleRedirect', () => {
  it('redirects user-role away from / and management routes', () => {
    expect(userRoleRedirect('user', '/')).toBe('/messages')
    expect(userRoleRedirect('user', '/management/users')).toBe('/messages')
    expect(userRoleRedirect('user', '/management')).toBe('/messages')
    expect(userRoleRedirect('user', '/processing-logs')).toBe('/messages')
    expect(userRoleRedirect('user', '/settings/users')).toBe('/messages')
  })

  it('returns null for /messages and /auth even for user role', () => {
    expect(userRoleRedirect('user', '/messages')).toBeNull()
    expect(userRoleRedirect('user', '/auth')).toBeNull()
  })

  it('never redirects operator or admin roles', () => {
    expect(userRoleRedirect('operator', '/')).toBeNull()
    expect(userRoleRedirect('admin', '/management/users')).toBeNull()
    expect(userRoleRedirect('', '/management/users')).toBeNull()
  })
})
