import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const localStorageMock = (() => {
  let store = {}
  return {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: (k) => { delete store[k] },
    clear: () => { store = {} },
  }
})()

beforeEach(() => {
  global.window = global.window || {}
  global.window.localStorage = localStorageMock
  global.window.__handlers = {}
  global.window.addEventListener = vi.fn((event, handler) => {
    global.window.__handlers[event] = handler
  })
  global.window.dispatchEvent = vi.fn((event) => {
    const handler = (global.window.__handlers || {})[event.type]
    if (handler) handler(event)
    return true
  })
  global.window.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type
      this.detail = init?.detail
    }
  }
  localStorageMock.clear()
})

afterEach(() => {
  vi.resetModules()
  vi.restoreAllMocks()
  delete global.window.__handlers
})

describe('api response interceptor', () => {
  it('clears the auth token and emits auth-expired on 401', async () => {
    localStorageMock.setItem('v_sentinel_token', 'abc')
    const fired = []
    global.window.addEventListener('v-sentinel:auth-expired', (event) => {
      fired.push(event.detail)
    })

    const { default: api } = await import('../index.js')
    const handler = api.interceptors.response.handlers[0]

    const fakeError = {
      response: { status: 401, data: { detail: 'Account expired' } },
      config: { url: '/api/auth/me' },
      message: '401',
    }
    let caught
    try {
      await handler.rejected(fakeError)
    } catch (err) {
      caught = err
    }
    expect(caught).toBeInstanceOf(Error)
    expect(caught.status).toBe(401)
    expect(caught.detail).toBe('Account expired')
    expect(localStorageMock.getItem('v_sentinel_token')).toBeNull()
    expect(fired.length).toBe(1)
  })

  it('does NOT clear the auth token on 401 from /api/auth/login', async () => {
    localStorageMock.setItem('v_sentinel_token', 'abc')

    const { default: api } = await import('../index.js')
    const handler = api.interceptors.response.handlers[0]
    const fakeError = {
      response: { status: 401, data: { detail: 'Invalid credentials' } },
      config: { url: '/api/auth/login' },
      message: '401',
    }
    try {
      await handler.rejected(fakeError)
    } catch (_) { /* expected */ }
    expect(localStorageMock.getItem('v_sentinel_token')).toBe('abc')
  })

  it('attaches structured detail for 403 IP block payloads', async () => {
    const { default: api } = await import('../index.js')
    const handler = api.interceptors.response.handlers[0]
    const fakeError = {
      response: {
        status: 403,
        data: {
          detail: {
            code: 'IP_BLOCKED',
            message: 'blocked',
            blocked_until: '2030-01-01T00:00:00+00:00',
          },
        },
      },
      config: { url: '/api/auth/login' },
      message: '403',
    }
    let caught
    try {
      await handler.rejected(fakeError)
    } catch (err) {
      caught = err
    }
    expect(caught.status).toBe(403)
    expect(caught.detail.code).toBe('IP_BLOCKED')
    expect(caught.detail.blocked_until).toBe('2030-01-01T00:00:00+00:00')
  })
})
