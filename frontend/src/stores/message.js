import { defineStore } from 'pinia'
import { ref } from 'vue'
import config from '../config.js'
import { messagesApi } from '../api/index.js'
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '../constants/pagination.js'

export const useMessageStore = defineStore('message', () => {
  const messages = ref([])
  const wsConnected = ref(false)
  const filterSource = ref('')
  const falsePositiveOnly = ref(false)
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)
  const total = ref(0)
  const pendingCount = ref(0)
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
          false_positive_only: falsePositiveOnly.value || undefined,
        })
      page.value = Number(data.page || nextPage)
      pageSize.value = Number(data.page_size || nextPageSize)
      total.value = Number(data.total || 0)
      messages.value = Array.isArray(data.items) ? data.items : []
      pendingCount.value = 0
      return messages.value
    } finally {
      loading.value = false
    }
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
    _ws = new WebSocket(url)

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
        const matchesFalsePositive = !falsePositiveOnly.value || Boolean(msg.false_positive)
        if (!matchesFilter || !matchesFalsePositive) return
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
  }

  function setFilterSource(sourceId) {
    filterSource.value = sourceId
  }

  function setFalsePositiveOnly(value) {
    falsePositiveOnly.value = Boolean(value)
  }

  async function markFalsePositive(messageId) {
    const result = await messagesApi.markFalsePositive(messageId)
    const target = messages.value.find((item) => item.id === messageId)
    if (target) {
      target.false_positive = true
    }
    if (falsePositiveOnly.value) {
      messages.value = messages.value.filter((item) => item.false_positive)
    }
    return result
  }

  return {
    messages,
    loading,
    page,
    pageSize,
    total,
    pendingCount,
    pageSizeOptions,
    wsConnected,
    filterSource,
    falsePositiveOnly,
    fetchMessages,
    connectWS,
    disconnectWS,
    clearMessages,
    setFilterSource,
    setFalsePositiveOnly,
    markFalsePositive,
  }
})
