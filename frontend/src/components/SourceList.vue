<template>
  <div class="source-list">
    <!-- Top section: Video Sources -->
    <div class="section sources-section">
      <div class="list-header">
        <span class="list-title">{{ t('sourceList.title') }}</span>
        <el-button v-if="canOperateSources" type="primary" size="small" @click="showAddDialog = true">
          <el-icon><Plus /></el-icon>
          {{ t('common.add') }}
        </el-button>
      </div>

      <el-scrollbar class="sources-scroll">
        <div
          v-for="(source, sourceIndex) in store.sources"
          :key="source.id"
          class="source-item"
          draggable="true"
          v-memo="[
            source.id,
            source.name,
            source.rtsp_url,
            source.route_path,
            source.source_remark,
            source.push_result_stream,
            source.alarm_confidence_threshold,
            store.isRunning(source.id),
            store.isPushActive(source.id),
            actionLoading[source.id],
            activePluginLabel,
            activePluginAlarmConfidenceThreshold,
          ]"
          @dragstart="onDragStart($event, source)"
        >
          <div class="source-info">
            <div class="source-name">
              <el-badge
                :type="store.isRunning(source.id) ? 'success' : 'info'"
                is-dot
                class="status-dot"
              />
              <span class="source-index">#{{ sourceIndex + 1 }}</span>
              {{ source.name }}
            </div>
            <div class="source-scene">{{ t('sourceList.activePlugin') }}: {{ activePluginLabel }}</div>
            <div class="source-settings-line">
              {{ t('sourceList.pushResultStream') }}:
              <el-switch
                :model-value="source.push_result_stream !== false"
                size="small"
                :loading="pushToggleLoading[source.id]"
                :disabled="!store.isRunning(source.id) || !canOperateSources"
                style="--el-switch-on-color: #67c23a; margin-left: 4px;"
                @change="onTogglePush(source)"
              />
              <span class="settings-separator">·</span>
              {{ t('sourceList.alarmConfidenceThresholdShort') }}:
              {{ formatAlarmThreshold(source.alarm_confidence_threshold) }}
            </div>
            <div class="source-url">{{ getSourceRoute(source) }}</div>
          </div>
          <div class="source-actions">
            <el-space :size="6" wrap>
              <el-button
                v-if="canOperateSources"
                size="small"
                :type="store.isRunning(source.id) ? 'warning' : 'success'"
                :loading="actionLoading[source.id]"
                @click="toggleAnalysis(source)"
              >
                {{ store.isRunning(source.id) ? t('sourceList.stop') : t('sourceList.analyze') }}
              </el-button>
              <el-button
                v-if="canOperateSources"
                size="small"
                :title="t('common.edit')"
                @click="openEditDialog(source)"
              >
                <el-icon><EditPen /></el-icon>
              </el-button>
              <el-button
                v-if="canOperateSources"
                size="small"
                type="danger"
                :title="t('common.delete')"
                @click="confirmDelete(source)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-space>
          </div>
        </div>

        <el-empty
          v-if="!store.sources.length"
          :description="t('sourceList.noSources')"
          :image-size="64"
          class="empty-hint"
        />
      </el-scrollbar>
    </div>

    <!-- Bottom section: Result Streams (auto-detected) -->
    <div class="section results-section">
      <div class="list-header results-header">
        <span class="list-title">{{ t('sourceList.resultStreams') }}</span>
      </div>

      <el-scrollbar class="sources-scroll">
        <div
          v-for="rs in resultStreams"
          :key="rs.id"
          class="source-item result-item"
          draggable="true"
           v-memo="[rs.id, rs.name, rs.streamPath, rs.sourceIndex]"
          @dragstart="onResultDragStart($event, rs)"
        >
          <div class="source-info">
            <div class="source-name result-name">
              <el-badge type="success" is-dot class="status-dot" />
              <span class="source-index">#{{ rs.sourceIndex }}</span>
              {{ rs.name }}
            </div>
            <div class="source-url">{{ rs.streamPath }}</div>
          </div>
        </div>

        <el-empty
          v-if="!resultStreams.length"
          :description="t('sourceList.noResultStreams')"
          :image-size="56"
          class="empty-hint"
        />
      </el-scrollbar>
    </div>

    <!-- Add Source Dialog -->
    <el-dialog
      v-model="showAddDialog"
      :title="t('sourceList.addSource')"
      width="460px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="132px" class="source-dialog-form" @submit.prevent="addSource">
        <el-form-item :label="t('sourceList.name')" required>
          <el-input v-model="form.name" :placeholder="t('sourceList.name')" />
        </el-form-item>
        <el-form-item :label="t('sourceList.routePath')" required>
          <el-input
            v-model="form.route_path"
            :placeholder="t('sourceList.routePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('sourceList.sourceRemark')">
          <el-input
            v-model="form.source_remark"
            type="textarea"
            :rows="2"
            :placeholder="t('sourceList.sourceRemarkPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('sourceList.pushResultStream')">
          <div class="field-stack">
            <el-switch v-model="form.push_result_stream" />
            <div class="route-hint">{{ t('sourceList.pushResultStreamHint') }}</div>
          </div>
        </el-form-item>
        <el-form-item :label="t('sourceList.alarmConfidenceThreshold')">
          <div class="field-stack">
            <el-input
              v-model="form.alarm_confidence_threshold"
              :placeholder="alarmConfidenceThresholdPlaceholder"
            />
            <div class="route-hint">{{ t('sourceList.alarmConfidenceThresholdHint') }}</div>
          </div>
        </el-form-item>
        <el-form-item :label="t('sourceList.activePlugin')">
          <el-input :model-value="activePluginLabel" disabled />
          <div class="route-hint">{{ t('sourceList.activePluginHint') }}</div>
        </el-form-item>
        <div class="route-hint">{{ t('sourceList.routeHint', { base: appSettingsStore.mediamtxRtspAddr }) }}</div>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="addLoading" @click="addSource">
          {{ t('common.add') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Edit Source Dialog -->
    <el-dialog
      v-model="showEditDialog"
      :title="t('sourceList.editSource')"
      width="460px"
      :close-on-click-modal="false"
    >
      <el-form :model="editForm" label-width="132px" class="source-dialog-form" @submit.prevent="saveEdit">
        <el-form-item :label="t('sourceList.name')" required>
          <el-input v-model="editForm.name" :placeholder="t('sourceList.name')" />
        </el-form-item>
        <el-form-item :label="t('sourceList.routePath')" required>
          <el-input
            v-model="editForm.route_path"
            :placeholder="t('sourceList.routePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('sourceList.sourceRemark')">
          <el-input
            v-model="editForm.source_remark"
            type="textarea"
            :rows="2"
            :placeholder="t('sourceList.sourceRemarkPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('sourceList.pushResultStream')">
          <div class="field-stack">
            <el-switch v-model="editForm.push_result_stream" />
            <div class="route-hint">{{ t('sourceList.pushResultStreamHint') }}</div>
          </div>
        </el-form-item>
        <el-form-item :label="t('sourceList.alarmConfidenceThreshold')">
          <div class="field-stack">
            <el-input
              v-model="editForm.alarm_confidence_threshold"
              :placeholder="alarmConfidenceThresholdPlaceholder"
            />
            <div class="route-hint">{{ t('sourceList.alarmConfidenceThresholdHint') }}</div>
          </div>
        </el-form-item>
        <el-form-item :label="t('sourceList.activePlugin')">
          <el-input :model-value="activePluginLabel" disabled />
          <div class="route-hint">{{ t('sourceList.activePluginHint') }}</div>
        </el-form-item>
        <div class="route-hint">{{ t('sourceList.routeHint', { base: appSettingsStore.mediamtxRtspAddr }) }}</div>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="editLoading" @click="saveEdit">
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import ElMessageBox from 'element-plus/es/components/message-box/index'
import { useSourceStore } from '../stores/source.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useAuthStore } from '../stores/auth.js'
import { extractRoutePath, normalizeRoutePath } from '../utils/sourceAddress.js'
import { scenesApi } from '../api/index.js'

const store = useSourceStore()
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const { t, locale } = useI18n()
const showAddDialog = ref(false)
const showEditDialog = ref(false)
const addLoading = ref(false)
const editLoading = ref(false)
const actionLoading = reactive({})
const pushToggleLoading = reactive({})
const editingSourceId = ref('')
const scenes = ref([])
const DEFAULT_SCENE_ID = 'smoke'

const form = reactive({
  name: '',
  route_path: '',
  source_remark: '',
  push_result_stream: true,
  alarm_confidence_threshold: '',
})
const editForm = reactive({
  name: '',
  route_path: '',
  source_remark: '',
  push_result_stream: true,
  alarm_confidence_threshold: '',
})

const sceneById = computed(() => new Map(scenes.value.map((scene) => [scene.id, scene])))
const canOperateSources = computed(() => authStore.hasPermission('sources:operate'))
const activePluginId = computed(() => appSettingsStore.activePluginId || DEFAULT_SCENE_ID)
const activePluginLabel = computed(() => sceneLabel(activePluginId.value))
const activePluginAlarmConfidenceThreshold = computed(() => {
  const settings = appSettingsStore.settings || {}
  const raw = activePluginId.value === 'fire_door'
    ? settings.fire_door_classification_confidence
    : settings.smoke_detection_confidence
  const fallback = activePluginId.value === 'fire_door' ? '0.50' : '0.35'
  const value = Number(String(raw ?? fallback).trim())
  return Number.isFinite(value) ? value.toFixed(2) : fallback
})
const alarmConfidenceThresholdPlaceholder = computed(() => (
  t('sourceList.alarmConfidenceThresholdPlaceholder', {
    value: activePluginAlarmConfidenceThreshold.value,
  })
))

function sceneLabel(sceneId) {
  const resolvedSceneId = sceneId ?? DEFAULT_SCENE_ID
  const scene = sceneById.value.get(resolvedSceneId)
  if (!scene) return resolvedSceneId
  return locale.value === 'en-US' ? scene.label_en : scene.label_zh
}

/**
 * Computed result streams from running analysis sources.
 * Each running source automatically gets a corresponding result stream
 * with the path `{route}_processed`.
 */
const resultStreams = computed(() => {
  return store.sources
    .map((source, index) => ({ source, sourceIndex: index + 1 }))
    .filter(({ source }) => store.isRunning(source.id) && store.isPushActive(source.id))
    .map(({ source: s, sourceIndex }) => {
      const route = getSourceRoute(s)
      return {
        id: `result_${s.id}`,
        name: `${s.name} (${t('sourceList.resultSuffix')})`,
        streamPath: `${route}_processed`,
        isResult: true,
        originalSourceId: s.id,
        sourceIndex,
      }
    })
})

function onDragStart(event, source) {
  event.dataTransfer.setData('source-id', source.id)
  event.dataTransfer.effectAllowed = 'copy'
}

function onResultDragStart(event, resultStream) {
  // Pass virtual result stream data for drag-and-drop into the grid
  event.dataTransfer.setData('result-stream', JSON.stringify(resultStream))
  event.dataTransfer.effectAllowed = 'copy'
}

async function addSource() {
  const routePath = normalizeRoutePath(form.route_path)
  const alarmThreshold = normalizeAlarmThreshold(form.alarm_confidence_threshold)

  if (!form.name || !routePath) {
    ElMessage.warning(t('sourceList.fillAllFields'))
    return
  }
  if (!appSettingsStore.mediamtxRtspAddr) {
    ElMessage.warning(t('sourceList.missingRtspBase'))
    return
  }
  if (alarmThreshold === false) {
    ElMessage.warning(t('sourceList.invalidAlarmConfidenceThreshold'))
    return
  }

  addLoading.value = true
  try {
    await store.createSource({
      name: form.name,
      route_path: routePath,
      source_remark: form.source_remark,
      push_result_stream: form.push_result_stream,
      alarm_confidence_threshold: alarmThreshold,
    })
    showAddDialog.value = false
    form.name = ''
    form.route_path = ''
    form.source_remark = ''
    form.push_result_stream = true
    form.alarm_confidence_threshold = ''
    ElMessage.success(t('sourceList.sourceAdded'))
  } catch (err) {
    ElMessage.error(err.message || t('sourceList.failedToAdd'))
  } finally {
    addLoading.value = false
  }
}

async function toggleAnalysis(source) {
  actionLoading[source.id] = true
  try {
    if (store.isRunning(source.id)) {
      await store.stopProcessing(source.id)
    } else {
      await store.startProcessing(source.id)
    }
  } finally {
    delete actionLoading[source.id]
  }
}

async function onTogglePush(source) {
  const newValue = source.push_result_stream === false
  pushToggleLoading[source.id] = true
  try {
    await store.togglePushResultStream(source.id, newValue)
  } finally {
    delete pushToggleLoading[source.id]
  }
}

function openEditDialog(source) {
  editingSourceId.value = source.id
  editForm.name = source.name
  editForm.route_path = extractRoutePath(source.rtsp_url, appSettingsStore.mediamtxRtspAddr)
  editForm.source_remark = source.source_remark || ''
  editForm.push_result_stream = source.push_result_stream !== false
  editForm.alarm_confidence_threshold = source.alarm_confidence_threshold ?? ''
  showEditDialog.value = true
}

async function saveEdit() {
  if (!editingSourceId.value) return

  const routePath = normalizeRoutePath(editForm.route_path)
  const alarmThreshold = normalizeAlarmThreshold(editForm.alarm_confidence_threshold)

  if (!editForm.name || !routePath) {
    ElMessage.warning(t('sourceList.fillAllFields'))
    return
  }
  if (!appSettingsStore.mediamtxRtspAddr) {
    ElMessage.warning(t('sourceList.missingRtspBase'))
    return
  }
  if (alarmThreshold === false) {
    ElMessage.warning(t('sourceList.invalidAlarmConfidenceThreshold'))
    return
  }

  editLoading.value = true
  try {
    await store.updateSource(editingSourceId.value, {
      name: editForm.name,
      route_path: routePath,
      source_remark: editForm.source_remark,
      push_result_stream: editForm.push_result_stream,
      alarm_confidence_threshold: alarmThreshold,
    })
    showEditDialog.value = false
    ElMessage.success(t('sourceList.sourceUpdated'))
  } catch (err) {
    ElMessage.error(err.message || t('sourceList.failedToUpdate'))
  } finally {
    editLoading.value = false
  }
}

async function confirmDelete(source) {
  try {
    await ElMessageBox.confirm(
      t('sourceList.deleteConfirmMessage', { name: source.name }),
      t('sourceList.deleteConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('common.delete'),
        cancelButtonText: t('common.cancel'),
      }
    )
    await store.deleteSource(source.id)
    ElMessage.success(t('sourceList.deleted'))
  } catch (_) {
    // User cancelled
  }
}

function getSourceRoute(source) {
  return extractRoutePath(source.rtsp_url, appSettingsStore.mediamtxRtspAddr) || source.rtsp_url
}

function normalizeAlarmThreshold(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  const threshold = Number(text)
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    return false
  }
  return threshold
}

function formatAlarmThreshold(value) {
  if (value === null || value === undefined || value === '') {
    return t('sourceList.globalDefaultWithValue', {
      value: activePluginAlarmConfidenceThreshold.value,
    })
  }
  return Number(value).toFixed(2)
}

onMounted(async () => {
  if (!appSettingsStore.loaded) {
    await appSettingsStore.fetchSettings().catch(() => {
      // Keep fallback defaults when settings API is unavailable.
    })
  }
  scenes.value = await scenesApi.list().catch(() => [])
  await store.syncProcessorStatus()
})
</script>

<style scoped>
.source-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1a1a2e;
  border-right: 1px solid #333;
}

.section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sources-section {
  flex: 1;
  overflow: hidden;
}

.results-section {
  flex: 0 0 auto;
  max-height: 40%;
  border-top: 2px solid #333;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.results-header {
  background: rgba(103, 194, 58, 0.06);
}

.list-title {
  font-size: 14px;
  font-weight: 600;
  color: #ccc;
}

.sources-scroll {
  flex: 1;
}

.source-item {
  padding: 10px 12px;
  border-bottom: 1px solid #222;
  cursor: grab;
  transition: background 0.15s;
  content-visibility: auto;
  contain-intrinsic-size: 88px;
}

.source-item:hover {
  background: rgba(64, 158, 255, 0.08);
}

.result-item {
  background: rgba(103, 194, 58, 0.03);
}

.result-item:hover {
  background: rgba(103, 194, 58, 0.08);
}

.source-name {
  font-size: 13px;
  font-weight: 600;
  color: #ddd;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.source-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 18px;
  border-radius: 999px;
  background: rgba(64, 158, 255, 0.16);
  color: #8cc5ff;
  font-size: 12px;
  font-weight: 700;
}

.result-name {
  color: #a3d977;
}

.source-url {
  font-size: 11px;
  color: #666;
  word-break: break-all;
}

.source-scene {
  font-size: 11px;
  color: #8aa6d9;
  margin-bottom: 2px;
}

.source-settings-line {
  font-size: 11px;
  color: #6f86aa;
  margin-bottom: 2px;
}

.settings-separator {
  color: #444;
  margin: 0 4px;
}

.field-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.source-dialog-form :deep(.el-form-item__label) {
  white-space: nowrap;
}

.route-hint {
  margin-top: 2px;
  color: #7587af;
  font-size: 12px;
}

.source-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: nowrap;
}

.source-actions :deep(.el-button span) {
  white-space: nowrap;
}

.empty-hint {
  padding: 20px;
}

.empty-hint :deep(.el-empty__description) {
  color: #8aa6d9;
  font-size: 13px;
}
</style>
