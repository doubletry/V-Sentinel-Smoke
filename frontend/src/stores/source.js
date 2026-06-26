import { defineStore } from 'pinia'
import { ref, computed, onUnmounted } from 'vue'
import { sourcesApi, processorApi } from '../api/index.js'
import ElMessage from 'element-plus/es/components/message/index'
import { i18n } from '../i18n/index.js'

function friendlyOperationError(message) {
  if (String(message || '').toLowerCase().includes('missing bearer token')) {
    return i18n.global.t('auth.loginRequired')
  }
  return message
}

export const useSourceStore = defineStore('source', () => {
  const sources = ref([])
  const loading = ref(false)

  // Map: sourceId → { status, push_result_stream, push_active }
  const processorStatusMap = ref(new Map())

  // Polling interval handle
  let _pollTimer = null
  const POLL_INTERVAL_MS = 5000

  // Grid cell assignments: cellIndex -> source
  const gridAssignments = ref({})

  function _startPolling() {
    if (_pollTimer) return
    _pollTimer = setInterval(syncProcessorStatus, POLL_INTERVAL_MS)
  }

  function _stopPolling() {
    if (_pollTimer) {
      clearInterval(_pollTimer)
      _pollTimer = null
    }
  }

  // Clean up polling on store disposal
  if (typeof onUnmounted === 'function') {
    try { onUnmounted(_stopPolling) } catch (_) { /* ignore */ }
  }

  const isRunning = computed(() => (sourceId) => {
    const status = processorStatusMap.value.get(sourceId)
    return status?.status === 'running'
  })

  const isPushActive = computed(() => (sourceId) => {
    const status = processorStatusMap.value.get(sourceId)
    return status?.push_active === true
  })

  function syncAssignedSourceReferences() {
    const latestById = new Map(sources.value.map((source) => [source.id, source]))
    gridAssignments.value = Object.fromEntries(
      Object.entries(gridAssignments.value)
        .map(([cell, source]) => {
          if (source?.isResult) return [cell, source]
          const latest = latestById.get(source?.id)
          return latest ? [cell, latest] : null
        })
        .filter(Boolean)
    )
  }

  async function fetchSources() {
    loading.value = true
    try {
      sources.value = await sourcesApi.list()
      syncAssignedSourceReferences()
    } catch (err) {
      ElMessage.error(i18n.global.t('sourceList.failedToLoadSources', { message: err.message }))
    } finally {
      loading.value = false
    }
  }

  async function createSource(data) {
    const source = await sourcesApi.create(data)
    sources.value.push(source)
    syncAssignedSourceReferences()
    return source
  }

  async function updateSource(id, data) {
    const updated = await sourcesApi.update(id, data)
    const idx = sources.value.findIndex((s) => s.id === id)
    if (idx !== -1) sources.value[idx] = updated
    syncAssignedSourceReferences()
    return updated
  }

  async function deleteSource(id) {
    await sourcesApi.delete(id)
    sources.value = sources.value.filter((s) => s.id !== id)
    // Remove from grid
    for (const [cell, src] of Object.entries(gridAssignments.value)) {
      if (src.id === id) delete gridAssignments.value[cell]
    }
    processorStatusMap.value.delete(id)
  }

  async function startProcessing(sourceId) {
    try {
      await processorApi.start(sourceId)
      _startPolling()
      await syncProcessorStatus()
      ElMessage.success(i18n.global.t('sourceList.analysisStarted'))
    } catch (err) {
      ElMessage.error(i18n.global.t('sourceList.failedToStart', { message: friendlyOperationError(err.message) }))
    }
  }

  async function stopProcessing(sourceId) {
    try {
      await processorApi.stop(sourceId)
      processorStatusMap.value.delete(sourceId)
      ElMessage.success(i18n.global.t('sourceList.analysisStopped'))
    } catch (err) {
      ElMessage.error(i18n.global.t('sourceList.failedToStop', { message: friendlyOperationError(err.message) }))
    }
  }

  async function syncProcessorStatus() {
    try {
      const statuses = await processorApi.status()
      const map = new Map()
      for (const s of statuses) {
        map.set(s.source_id, {
          status: s.status,
          push_result_stream: s.push_result_stream,
          push_active: s.push_active,
        })
      }
      processorStatusMap.value = map
    } catch (_) {
      // Ignore poll failures
    }
  }

  function getRunningSourceIdsSnapshot() {
    return Array.from(processorStatusMap.value.entries())
      .filter(([_, p]) => p.status === 'running')
      .map(([id]) => id)
  }

  async function restartProcessing(sourceIds) {
    const targets = Array.from(
      new Set((sourceIds || []).map((item) => String(item || '').trim()).filter(Boolean))
    )

    if (!targets.length) {
      return {
        status: 'not_running',
        restarted: 0,
        stopped: 0,
        failed: [],
      }
    }

    const failed = []
    const stoppedIds = []
    let restarted = 0

    for (const sourceId of targets) {
      try {
        await processorApi.stop(sourceId)
        stoppedIds.push(sourceId)
        processorStatusMap.value.delete(sourceId)
      } catch (err) {
        failed.push({
          source_id: sourceId,
          phase: 'stop',
          reason: err.message,
        })
      }
    }

    for (const sourceId of stoppedIds) {
      try {
        const result = await processorApi.start(sourceId)
        if (result.status === 'started' || result.status === 'already_running') {
          restarted += 1
        } else {
          failed.push({
            source_id: sourceId,
            phase: 'start',
            reason: result.status || 'unknown',
          })
        }
      } catch (err) {
        failed.push({
          source_id: sourceId,
          phase: 'start',
          reason: err.message,
        })
      }
    }

    _startPolling()
    await syncProcessorStatus()

    return {
      status: failed.length ? 'partial' : 'restarted',
      restarted,
      stopped: stoppedIds.length,
      failed,
    }
  }

  async function togglePushResultStream(sourceId, enabled) {
    try {
      const result = await processorApi.togglePushResultStream(sourceId, enabled)
      // Update local map immediately
      const entry = processorStatusMap.value.get(sourceId)
      if (entry) {
        processorStatusMap.value = new Map(processorStatusMap.value).set(sourceId, {
          ...entry,
          push_result_stream: result.push_result_stream,
        })
      }
      // Update the source's local push_result_stream so the switch reflects it
      const source = sources.value.find((s) => s.id === sourceId)
      if (source) {
        source.push_result_stream = result.push_result_stream
      }
    } catch (err) {
      ElMessage.error(i18n.global.t('sourceList.failedToTogglePush', { message: friendlyOperationError(err.message) }))
    }
  }

  function assignToCell(cellIndex, source) {
    gridAssignments.value[cellIndex] = source
  }

  function removeFromCell(cellIndex) {
    delete gridAssignments.value[cellIndex]
  }

  return {
    sources,
    loading,
    processorStatusMap,
    gridAssignments,
    isRunning,
    isPushActive,
    fetchSources,
    createSource,
    updateSource,
    deleteSource,
    syncAssignedSourceReferences,
    startProcessing,
    stopProcessing,
    syncProcessorStatus,
    getRunningSourceIdsSnapshot,
    restartProcessing,
    togglePushResultStream,
    assignToCell,
    removeFromCell,
  }
})
