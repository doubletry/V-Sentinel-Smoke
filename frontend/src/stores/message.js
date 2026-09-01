import { defineStore } from 'pinia'
import { ref } from 'vue'
import config from '../config.js'
import { messagesApi } from '../api/index.js'
import { AUTH_TOKEN_STORAGE_KEY } from '../utils/authStorage.js'
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '../constants/pagination.js'

function timestampDay(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ''
  return date.toISOString().slice(0, 10)
}

export const useMessageStore = defineStore('message', () => {
  const messages = ref([])
  const wsConnected = ref(false)
  const filterSource = ref('')
  const falsePositiveFilter = ref('exclude')
  const startDate = ref('')
  const endDate = ref('')
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)
  const total = ref(0)
  const totalPages = ref(0)
  const lastUpdatedAt = ref('')
  const pendingCount = ref(0)
  const selectedIds = ref({})
  let _ws = null
  let _reconnectTimer = null

  const pageSizeOptions = PAGE_SIZE_OPTIONS

  async function fetchMessages(nextPage = page.value, nextPageSize = pageSize.value) {
    loading.value = true
    try {
      const data = await messagesApi.list({
        page: nextPage,
        page_size: nextPageSize,
        source_id: filterSource.value || undefined,
        false_positive_filter: falsePositiveFilter.value,
        start_date: startDate.value || undefined,
        end_date: endDate.value || undefined,
      })
      page.value = Number(data.page || nextPage)
      pageSize.value = Number(data.page_size || nextPageSize)
      total.value = Number(data.total || 0)
      totalPages.value = Number(data.total_pages || 0)
      messages.value = Array.isArray(data.items) ? data.items : []
      lastUpdatedAt.value = new Date().toISOString()
      pendingCount.value = 0
      pruneSelection()
      return messages.value
    } finally {
      loading.value = false
    }
  }

  function falsePositiveFilterMatches(isFalsePositive) {
    if (falsePositiveFilter.value === 'all') return true
    if (falsePositiveFilter.value === 'only') return Boolean(isFalsePositive)
    return !isFalsePositive
  }

  function matchesActiveDateRange(timestamp) {
    if (!startDate.value && !endDate.value) return true
    const day = timestampDay(timestamp)
    if (!day) return true
    if (startDate.value && day < startDate.value) return false
    if (endDate.value && day > endDate.value) return false
    return true
  }

  function connectWS() {
    if (_ws && _ws.readyState === WebSocket.OPEN) return

    // Build WebSocket URL: if wsBaseUrl is empty (relative), derive from current page
    let wsBase = config.wsBaseUrl
    if (!wsBase) {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      wsBase = `${proto}//${window.location.host}`
    }
    const url = `${wsBase}/ws/messages`
    const token = window.localStorage?.getItem(AUTH_TOKEN_STORAGE_KEY)
    const wsUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url
    _ws = new WebSocket(wsUrl)

    _ws.onopen = () => {
      wsConnected.value = true
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer)
        _reconnectTimer = null
      }
    }

    _ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg === 'pong') return
        const matchesFilter = !filterSource.value || msg.source_id === filterSource.value
        const matchesFalsePositive = falsePositiveFilterMatches(msg.false_positive)
        const matchesDate = matchesActiveDateRange(msg.timestamp)
        if (!matchesFilter || !matchesFalsePositive || !matchesDate) return
        if (page.value === 1) {
          messages.value.unshift(msg)
          if (messages.value.length > pageSize.value) {
            messages.value = messages.value.slice(0, pageSize.value)
          }
        } else {
          pendingCount.value += 1
        }
      } catch (_) {
        // Ignore parse errors
      }
    }

    _ws.onclose = () => {
      wsConnected.value = false
      _ws = null
      // Auto reconnect after 3s
      _reconnectTimer = setTimeout(connectWS, 3000)
    }

    _ws.onerror = () => {
      _ws?.close()
    }
  }

  function disconnectWS() {
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
      _reconnectTimer = null
    }
    _ws?.close()
    _ws = null
    wsConnected.value = false
  }

  function clearMessages() {
    messages.value = []
    total.value = 0
    pendingCount.value = 0
    clearSelection()
  }

  function setFilterSource(sourceId) {
    filterSource.value = sourceId
    clearSelection()
  }

  function setFalsePositiveFilter(value) {
    falsePositiveFilter.value = ['exclude', 'all', 'only'].includes(value) ? value : 'exclude'
    clearSelection()
  }

  function setDateRange(start, end) {
    startDate.value = String(start || '')
    endDate.value = String(end || '')
    clearSelection()
  }

  function applyFalsePositiveFilterToLocalMessages() {
    if (falsePositiveFilter.value === 'all') return
    messages.value = messages.value.filter((item) => falsePositiveFilterMatches(item.false_positive))
  }

  async function markFalsePositive(messageId) {
    const result = await messagesApi.markFalsePositive(messageId)
    const target = messages.value.find((item) => item.id === messageId)
    if (target) {
      target.false_positive = true
    }
    applyFalsePositiveFilterToLocalMessages()
    return result
  }

  async function unmarkFalsePositive(messageId) {
    const result = await messagesApi.unmarkFalsePositive(messageId)
    const target = messages.value.find((item) => item.id === messageId)
    if (target) {
      target.false_positive = false
    }
    applyFalsePositiveFilterToLocalMessages()
    return result
  }

  async function resendNotification(messageId) {
    return messagesApi.resendNotification(messageId)
  }

  async function vlReviewMessage(messageId) {
    return messagesApi.vlReview(messageId)
  }

  function toggleSelection(messageId, value) {
    if (!messageId) return
    const next = { ...selectedIds.value }
    const shouldSelect = value === undefined ? !next[messageId] : Boolean(value)
    if (shouldSelect) {
      next[messageId] = true
    } else {
      delete next[messageId]
    }
    selectedIds.value = next
  }

  function setSelection(ids, value) {
    const next = { ...selectedIds.value }
    const shouldSelect = Boolean(value)
    for (const id of ids || []) {
      if (!id) continue
      if (shouldSelect) {
        next[id] = true
      } else {
        delete next[id]
      }
    }
    selectedIds.value = next
  }

  function clearSelection() {
    selectedIds.value = {}
  }

  function pruneSelection() {
    const visible = new Set(messages.value.map((item) => item.id).filter(Boolean))
    const next = {}
    for (const id of Object.keys(selectedIds.value)) {
      if (visible.has(id)) next[id] = true
    }
    selectedIds.value = next
  }

  async function deleteMessage(messageId) {
    const result = await messagesApi.delete(messageId)
    messages.value = messages.value.filter((item) => item.id !== messageId)
    if (total.value > 0) total.value -= 1
    const next = { ...selectedIds.value }
    delete next[messageId]
    selectedIds.value = next
    return result
  }

  async function batchDelete(ids) {
    const result = await messagesApi.batchDelete(ids)
    const deleted = new Set(result.deleted_ids || [])
    if (deleted.size) {
      messages.value = messages.value.filter((item) => !deleted.has(item.id))
      total.value = Math.max(0, total.value - deleted.size)
      const next = { ...selectedIds.value }
      for (const id of deleted) delete next[id]
      selectedIds.value = next
    }
    return result
  }

  return {
    messages,
    loading,
    page,
    pageSize,
    total,
    totalPages,
    lastUpdatedAt,
    pendingCount,
    pageSizeOptions,
    wsConnected,
    filterSource,
    falsePositiveFilter,
    startDate,
    endDate,
    selectedIds,
    fetchMessages,
    connectWS,
    disconnectWS,
    clearMessages,
    setFilterSource,
    setFalsePositiveFilter,
    setDateRange,
    markFalsePositive,
    unmarkFalsePositive,
    resendNotification,
    vlReviewMessage,
    toggleSelection,
    setSelection,
    clearSelection,
    deleteMessage,
    batchDelete,
  }
})
