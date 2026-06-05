import { describe, expect, it } from 'vitest'
import {
  SITE_LOGIN_SECURITY_SETTING_KEYS,
  USER_LOGIN_SECURITY_SETTING_KEYS,
} from '../loginSecuritySettings.js'

describe('loginSecuritySettings', () => {
  it('keeps reverse-proxy trust in site settings only', () => {
    expect(SITE_LOGIN_SECURITY_SETTING_KEYS).toEqual(['login_lockout_trust_proxy'])
    expect(USER_LOGIN_SECURITY_SETTING_KEYS).toEqual([
      'login_lockout_max_attempts',
      'login_lockout_window_seconds',
      'login_lockout_duration_seconds',
    ])
    expect(USER_LOGIN_SECURITY_SETTING_KEYS).not.toContain('login_lockout_trust_proxy')
  })
})
