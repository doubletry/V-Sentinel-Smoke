import { describe, expect, it } from 'vitest'
import { normalizeAppBasePath, resolveAppUrl } from '../appPath.js'

describe('normalizeAppBasePath', () => {
  it('normalizes empty and root paths to an empty prefix', () => {
    expect(normalizeAppBasePath('')).toBe('')
    expect(normalizeAppBasePath('/')).toBe('')
  })

  it('trims and strips trailing slashes', () => {
    expect(normalizeAppBasePath('sentinel/')).toBe('/sentinel')
    expect(normalizeAppBasePath('/sentinel//')).toBe('/sentinel')
  })
})

describe('resolveAppUrl', () => {
  it('keeps absolute external URLs untouched', () => {
    expect(resolveAppUrl('https://example.com/icon.ico', '/sentinel')).toBe('https://example.com/icon.ico')
  })

  it('prefixes app-relative URLs with the reverse-proxy base', () => {
    expect(resolveAppUrl('/api/messages/1', '/sentinel/')).toBe('/sentinel/api/messages/1')
    expect(resolveAppUrl('/favicon.ico', '/sentinel')).toBe('/sentinel/favicon.ico')
  })

  it('does not double-prefix URLs that already include the app base', () => {
    expect(resolveAppUrl('/sentinel/api/messages/1', '/sentinel')).toBe('/sentinel/api/messages/1')
  })

  it('supports relative URLs and empty base paths', () => {
    expect(resolveAppUrl('message_thumbnails/abc.jpg', '')).toBe('/message_thumbnails/abc.jpg')
  })
})
