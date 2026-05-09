import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sourcesApi, processorApi } from '../api/index.js'
import ElMessage from 'element-plus/es/components/message/index'
import { i18n } from '../i18n/index.js'
import { extractRoutePath, normalizeRoutePath } from '../utils/sourceAddress.js'

const GRID_ASSIGNMENTS_STORAGE_KEY = 'v-sentinel.grid.assignments'
const LEGACY_RTSP_BASE_ADDRESS = ''

let gridAssignmentStorageWarningShown = false

function stripResultStreamSuffix(value) {
  return String(value || '').replace(/_processed$/, '')
}

function extractRoutePathFromLegacyStreamPath(value) {
  return normalizeRoutePath(value.routePath || stripResultStreamSuffix(value.streamPath))
}

function normalizePersistedAssignment(value) {
  if (!value || typeof value !== 'object') return null

  if (value.type === 'result' && value.originalSourceId) {
    return {
      type: 'result',
      originalSourceId: String(value.originalSourceId),
      routePath: normalizeRoutePath(value.routePath || ''),
    }
  }

  if (value.type === 'source' && value.sourceId) {
    return {
      type: 'source',
      sourceId: String(value.sourceId),
    }
  }

  if (value.isResult && value.originalSourceId) {
    return {
      type: 'result',
      originalSourceId: String(value.originalSourceId),
      routePath: extractRoutePathFromLegacyStreamPath(value),
    }
  }

  if (value.sourceId || value.id) {
    return {
      type: 'source',
      sourceId: String(value.sourceId || value.id),
    }
  }

  return null
}

function loadStoredGridAssignments() {
  if (typeof window === 'undefined') return {}

  try {
    const parsed = JSON.parse(window.localStorage.getItem(GRID_ASSIGNMENTS_STORAGE_KEY) || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {}
    }
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([cell, value]) => {
          const normalized = normalizePersistedAssignment(value)
          return normalized ? [cell, normalized] : null
        })
        .filter(Boolean)
    )
  } catch (_) {
    return {}
  }
}

function buildPersistedAssignment(source) {
  if (!source) return null

  if (source.isResult) {
    return source.originalSourceId
      ? {
          type: 'result',
          originalSourceId: String(source.originalSourceId),
          routePath: normalizeRoutePath(stripResultStreamSuffix(source.streamPath)),
        }
      : null
  }

  return source.id
    ? {
        type: 'source',
        sourceId: String(source.id),
      }
    : null
}

function warnGridAssignmentStorage(error) {
  if (gridAssignmentStorageWarningShown) return
  gridAssignmentStorageWarningShown = true
  console.warn('Failed to persist video wall assignments:', error)
}

export const useSourceStore = defineStore('source', () => {
  const sources = ref([])
  const loading = ref(false)
  const runningSourceIds = ref(new Set())
  const processorStatusLoaded = ref(false)
  const persistedGridAssignments = ref(loadStoredGridAssignments())

  // Grid cell assignments: cellIndex -> hydrated source/result object
  const gridAssignments = ref({})

  const isRunning = computed(() => (sourceId) => runningSourceIds.value.has(sourceId))
  const runningCount = computed(() => runningSourceIds.value.size)

  function persistGridAssignments() {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(
        GRID_ASSIGNMENTS_STORAGE_KEY,
        JSON.stringify(persistedGridAssignments.value)
      )
    } catch (error) {
      warnGridAssignmentStorage(error)
    }
  }

  function isResultStreamActive(sourceId) {
    return runningSourceIds.value.has(sourceId)
  }

  function hydrateResultAssignment(source, assignment) {
    if (!source) return null

    if (processorStatusLoaded.value && !isResultStreamActive(source.id)) {
      return null
    }

    // Persisted result tiles may come from older storage without routePath.
    // In that case, derive the path from the saved RTSP URL without assuming a base address.
    const routePath = normalizeRoutePath(
      assignment.routePath || extractRoutePath(source.rtsp_url, LEGACY_RTSP_BASE_ADDRESS)
    )
    if (!routePath) return null

    return {
      id: `result_${source.id}`,
      name: `${source.name} (${i18n.global.t('sourceList.resultSuffix')})`,
      streamPath: `${routePath}_processed`,
      isResult: true,
      originalSourceId: source.id,
    }
  }

  function syncAssignedSourceReferences() {
    const latestById = new Map(sources.value.map((source) => [source.id, source]))
    const nextAssignments = {}
    const nextPersistedAssignments = {}

    Object.entries(persistedGridAssignments.value).forEach(([cell, assignment]) => {
      const normalized = normalizePersistedAssignment(assignment)
      if (!normalized) return

      if (normalized.type === 'result') {
        const source = latestById.get(normalized.originalSourceId)
        const hydrated = hydrateResultAssignment(source, normalized)
        if (hydrated) {
          nextAssignments[cell] = hydrated
          nextPersistedAssignments[cell] = normalized
        }
        return
      }

      const source = latestById.get(normalized.sourceId)
      if (source) {
        nextAssignments[cell] = source
        nextPersistedAssignments[cell] = normalized
      }
    })

    gridAssignments.value = nextAssignments
    persistedGridAssignments.value = nextPersistedAssignments
    persistGridAssignments()
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
    const cellsToDelete = Object.entries(persistedGridAssignments.value)
      .filter(([, assignment]) => assignment.sourceId === id || assignment.originalSourceId === id)
      .map(([cell]) => cell)
    cellsToDelete.forEach((cell) => {
      delete persistedGridAssignments.value[cell]
    })
    runningSourceIds.value.delete(id)
    syncAssignedSourceReferences()
  }

  async function startProcessing(sourceId) {
    try {
      await processorApi.start(sourceId)
      processorStatusLoaded.value = true
      runningSourceIds.value.add(sourceId)
      syncAssignedSourceReferences()
      ElMessage.success(i18n.global.t('sourceList.analysisStarted'))
    } catch (err) {
      ElMessage.error(i18n.global.t('sourceList.failedToStart', { message: err.message }))
    }
  }

  async function stopProcessing(sourceId) {
    try {
      await processorApi.stop(sourceId)
      processorStatusLoaded.value = true
      runningSourceIds.value.delete(sourceId)
      syncAssignedSourceReferences()
      ElMessage.success(i18n.global.t('sourceList.analysisStopped'))
    } catch (err) {
      ElMessage.error(i18n.global.t('sourceList.failedToStop', { message: err.message }))
    }
  }

  async function startAllProcessing() {
    try {
      const result = await processorApi.startAll()
      await syncProcessorStatus()

      if (result.status === 'no_sources') {
        ElMessage.warning(i18n.global.t('service.noSources'))
      } else if (result.status === 'partial') {
        ElMessage.warning(i18n.global.t('service.partialStarted', { started: result.started }))
      } else {
        ElMessage.success(i18n.global.t('service.startedAll', { started: result.started }))
      }

      return result
    } catch (err) {
      ElMessage.error(i18n.global.t('service.startAllFailed', { message: err.message }))
      throw err
    }
  }

  async function stopAllProcessing() {
    try {
      const result = await processorApi.stopAll()
      await syncProcessorStatus()

      if (result.status === 'not_running') {
        ElMessage.info(i18n.global.t('service.notRunning'))
      } else if (result.status === 'partial') {
        ElMessage.warning(i18n.global.t('service.partialStopped', { stopped: result.stopped }))
      } else {
        ElMessage.success(i18n.global.t('service.stoppedAll', { stopped: result.stopped }))
      }

      return result
    } catch (err) {
      ElMessage.error(i18n.global.t('service.stopAllFailed', { message: err.message }))
      throw err
    }
  }

  async function syncProcessorStatus() {
    try {
      const statuses = await processorApi.status()
      const running = new Set(
        statuses.filter((s) => s.status === 'running').map((s) => s.source_id)
      )
      processorStatusLoaded.value = true
      runningSourceIds.value = running
      syncAssignedSourceReferences()
    } catch (_) {
      // Ignore
    }
  }

  function getRunningSourceIdsSnapshot() {
    return Array.from(runningSourceIds.value)
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
        runningSourceIds.value.delete(sourceId)
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
          runningSourceIds.value.add(sourceId)
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

    processorStatusLoaded.value = true
    await syncProcessorStatus()

    return {
      status: failed.length ? 'partial' : 'restarted',
      restarted,
      stopped: stoppedIds.length,
      failed,
    }
  }

  function assignToCell(cellIndex, source) {
    const persisted = buildPersistedAssignment(source)
    if (!persisted) return
    gridAssignments.value[cellIndex] = source
    persistedGridAssignments.value[cellIndex] = persisted
    persistGridAssignments()
  }

  function removeFromCell(cellIndex) {
    delete gridAssignments.value[cellIndex]
    delete persistedGridAssignments.value[cellIndex]
    persistGridAssignments()
  }

  function clearGridAssignments() {
    gridAssignments.value = {}
    persistedGridAssignments.value = {}
    persistGridAssignments()
  }

  function autoAssignSources(preferredSources = []) {
    const nextAssignments = {}
    const nextPersistedAssignments = {}
    Array.from(
      new Map((preferredSources || []).map((source) => [source.id || source.streamPath, source])).values()
    ).forEach((source, index) => {
      const persisted = buildPersistedAssignment(source)
      if (!persisted) return
      nextAssignments[index] = source
      nextPersistedAssignments[index] = persisted
    })
    gridAssignments.value = nextAssignments
    persistedGridAssignments.value = nextPersistedAssignments
    persistGridAssignments()
  }

  return {
    sources,
    loading,
    runningSourceIds,
    runningCount,
    gridAssignments,
    isRunning,
    fetchSources,
    createSource,
    updateSource,
    deleteSource,
    syncAssignedSourceReferences,
    startProcessing,
    stopProcessing,
    startAllProcessing,
    stopAllProcessing,
    syncProcessorStatus,
    getRunningSourceIdsSnapshot,
    restartProcessing,
    assignToCell,
    removeFromCell,
    clearGridAssignments,
    autoAssignSources,
  }
})
