import { describe, it, expect, vi, beforeEach } from 'vitest'

const { postMock, apiInstance } = vi.hoisted(() => {
  const postMock = vi.fn()
  return {
    postMock,
    apiInstance: {
      post: postMock,
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    },
  }
})

vi.mock('axios', () => ({
  default: { create: vi.fn(() => apiInstance) },
}))

import { settingsApi, messagesApi } from '../index.js'

describe('VL long-running API calls override the global 10s timeout', () => {
  beforeEach(() => {
    postMock.mockReset()
  })

  it('settingsApi.testVl disables the axios request timeout', async () => {
    postMock.mockResolvedValue({ status: 'ok' })

    await settingsApi.testVl({})

    const [url, _data, cfg] = postMock.mock.calls[0]
    expect(url).toBe('/api/settings/vl/test')
    expect(cfg).toMatchObject({ timeout: 0 })
  })

  it('messagesApi.vlReview disables the axios request timeout', async () => {
    postMock.mockResolvedValue({ result: 'unknown' })

    await messagesApi.vlReview('id-1')

    const [url, _data, cfg] = postMock.mock.calls[0]
    expect(url).toBe('/api/messages/id-1/vl-review')
    expect(cfg).toMatchObject({ timeout: 0 })
  })
})
