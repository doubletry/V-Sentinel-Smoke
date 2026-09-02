import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const listMock = vi.fn()
const vlReviewMock = vi.fn()
const deleteMock = vi.fn()
const batchDeleteMock = vi.fn()

vi.mock('../../api/index.js', () => ({
  messagesApi: {
    list: (...args) => listMock(...args),
    markFalsePositive: vi.fn(),
    unmarkFalsePositive: vi.fn(),
    resendNotification: vi.fn(),
    vlReview: (...args) => vlReviewMock(...args),
    delete: (...args) => deleteMock(...args),
    batchDelete: (...args) => batchDeleteMock(...args),
  },
}))

vi.mock('../../config.js', () => ({ default: { wsBaseUrl: '' } }))

import { useMessageStore } from '../message.js'

beforeEach(() => {
  setActivePinia(createPinia())
  listMock.mockReset()
  vlReviewMock.mockReset()
  deleteMock.mockReset()
  batchDeleteMock.mockReset()
})

describe('message store — date range filter', () => {
  it('passes start_date / end_date to the API when set', async () => {
    listMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 })
    const store = useMessageStore()
    store.setDateRange('2026-05-01', '2026-05-02')
    await store.fetchMessages()
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ start_date: '2026-05-01', end_date: '2026-05-02' })
    )
  })

  it('omits date params when range is cleared', async () => {
    listMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 })
    const store = useMessageStore()
    store.setDateRange('', '')
    await store.fetchMessages()
    const call = listMock.mock.calls[0][0]
    expect(call.start_date).toBeUndefined()
    expect(call.end_date).toBeUndefined()
  })

  it('clears selection when date range changes', () => {
    const store = useMessageStore()
    store.toggleSelection('a', true)
    expect(store.selectedIds).toEqual({ a: true })
    store.setDateRange('2026-05-01', '2026-05-02')
    expect(store.selectedIds).toEqual({})
  })
})

describe('message store — selection helpers', () => {
  it('toggleSelection adds and removes ids', () => {
    const store = useMessageStore()
    store.toggleSelection('id-1', true)
    store.toggleSelection('id-2', true)
    expect(store.selectedIds).toEqual({ 'id-1': true, 'id-2': true })
    store.toggleSelection('id-1', false)
    expect(store.selectedIds).toEqual({ 'id-2': true })
  })

  it('setSelection applies to many ids at once', () => {
    const store = useMessageStore()
    store.setSelection(['a', 'b', 'c'], true)
    expect(store.selectedIds).toEqual({ a: true, b: true, c: true })
    store.setSelection(['b'], false)
    expect(store.selectedIds).toEqual({ a: true, c: true })
  })
})

describe('message store — deletion', () => {
  it('removes a deleted message locally and decrements total', async () => {
    deleteMock.mockResolvedValue({ id: 'id-1', deleted: true, false_positive_was: false })
    const store = useMessageStore()
    store.messages = [{ id: 'id-1' }, { id: 'id-2' }]
    store.total = 2
    store.toggleSelection('id-1', true)
    await store.deleteMessage('id-1')
    expect(store.messages.map((m) => m.id)).toEqual(['id-2'])
    expect(store.total).toBe(1)
    expect(store.selectedIds).toEqual({})
  })

  it('batchDelete only removes ids reported as deleted', async () => {
    batchDeleteMock.mockResolvedValue({ deleted_ids: ['id-1'], missing_ids: ['id-3'] })
    const store = useMessageStore()
    store.messages = [{ id: 'id-1' }, { id: 'id-2' }]
    store.total = 2
    store.setSelection(['id-1', 'id-3'], true)
    const result = await store.batchDelete(['id-1', 'id-3'])
    expect(result.missing_ids).toEqual(['id-3'])
    expect(store.messages.map((m) => m.id)).toEqual(['id-2'])
    expect(store.total).toBe(1)
    expect(store.selectedIds).toEqual({ 'id-3': true })
  })
})

describe('message store — false positive filter modes', () => {
  it('defaults to exclude and sends false_positive_filter to the API', async () => {
    listMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 })
    const store = useMessageStore()
    await store.fetchMessages()
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ false_positive_filter: 'exclude' })
    )
  })

  it('setFalsePositiveFilter switches modes and sanitises unknown values', async () => {
    listMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 })
    const store = useMessageStore()
    store.setFalsePositiveFilter('only')
    await store.fetchMessages()
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ false_positive_filter: 'only' })
    )
    store.setFalsePositiveFilter('bogus')
    expect(store.falsePositiveFilter).toBe('exclude')
  })

  it('exclude mode hides a message just marked as false positive locally', async () => {
    const store = useMessageStore()
    store.setFalsePositiveFilter('exclude')
    store.messages = [
      { id: 'a', false_positive: false },
      { id: 'b', false_positive: false },
    ]
    await store.markFalsePositive('b')
    expect(store.messages.map((m) => m.id)).toEqual(['a'])
  })

  it('only mode keeps only false positives after unmarking', async () => {
    const store = useMessageStore()
    store.setFalsePositiveFilter('only')
    store.messages = [
      { id: 'a', false_positive: true },
      { id: 'b', false_positive: true },
    ]
    await store.unmarkFalsePositive('a')
    expect(store.messages.map((m) => m.id)).toEqual(['b'])
  })
})

describe('message store — vl review', () => {
  it('vlReviewMessage calls the API and returns the result', async () => {
    const store = useMessageStore()
    vlReviewMock.mockResolvedValue({ result: 'confirmed', raw_response: '{"smoke": true}', latency_ms: 120, model: '/models/Mage-VL' })
    const result = await store.vlReviewMessage('id-9')
    expect(vlReviewMock).toHaveBeenCalledWith('id-9')
    expect(result.result).toBe('confirmed')
  })
})

describe('message store — immediate alert banner', () => {
  it('shows the alert and auto hides after the duration', () => {
    vi.useFakeTimers()
    const store = useMessageStore()
    store.showActiveAlert({ message: 'Detected smoke on Cam1 (1 confirmed detection(s))', source_name: 'Cam1' })
    expect(store.activeAlert.message).toBe('Detected smoke on Cam1 (1 confirmed detection(s))')
    vi.advanceTimersByTime(5000)
    expect(store.activeAlert).toBeNull()
    vi.useRealTimers()
  })

  it('a new alert replaces the previous one and resets the hide timer', () => {
    vi.useFakeTimers()
    const store = useMessageStore()
    store.showActiveAlert({ message: 'first', source_name: 'A' })
    vi.advanceTimersByTime(3000)
    store.showActiveAlert({ message: 'second', source_name: 'B' })
    expect(store.activeAlert.message).toBe('second')
    vi.advanceTimersByTime(4000)
    expect(store.activeAlert.message).toBe('second')
    vi.advanceTimersByTime(1000)
    expect(store.activeAlert).toBeNull()
    vi.useRealTimers()
  })
})
