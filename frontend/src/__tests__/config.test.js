import { afterEach, describe, expect, it, vi } from 'vitest'

describe('frontend config base path detection', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('reads the app base path from document.baseURI', async () => {
    vi.stubGlobal('document', { baseURI: 'http://example.com/sentinel/' })

    const config = (await import('../config.js')).default

    expect(config.appBasePath).toBe('/sentinel')
  })

  it('falls back to the root path for direct deployments', async () => {
    vi.stubGlobal('document', { baseURI: 'http://example.com/' })

    const config = (await import('../config.js')).default

    expect(config.appBasePath).toBe('')
  })
})
