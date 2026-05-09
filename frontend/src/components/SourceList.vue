<template>
  <div class="source-list">
    <SourcePanelSummary
      :total-sources="store.sources.length"
      :running-count="store.runningCount"
      :rtsp-base="appSettingsStore.mediamtxRtspAddr"
      :bulk-action="bulkAction"
      @add="showAddDialog = true"
      @start-all="handleStartAll"
      @stop-all="handleStopAll"
    />

    <div class="section sources-section">
      <div class="list-header">
        <div>
          <span class="list-title">{{ t('sourceList.title') }}</span>
          <p class="list-subtitle">{{ t('sourceList.manageHint') }}</p>
        </div>
      </div>

      <el-scrollbar class="sources-scroll">
        <div
          v-for="source in store.sources"
          :key="source.id"
          class="source-item"
          draggable="true"
          @dragstart="onDragStart($event, source)"
        >
          <div class="source-info">
            <div class="source-name">
              <el-badge
                :type="store.isRunning(source.id) ? 'success' : 'info'"
                is-dot
                class="status-dot"
              />
              {{ source.name }}
            </div>
            <div class="source-url">{{ getSourceRoute(source) }}</div>
          </div>
          <div class="source-actions">
            <el-button
              size="small"
              :type="store.isRunning(source.id) ? 'warning' : 'success'"
              :loading="actionLoading[source.id]"
              @click="toggleAnalysis(source)"
            >
              {{ store.isRunning(source.id) ? t('sourceList.stop') : t('sourceList.analyze') }}
            </el-button>
            <el-button size="small" :title="t('common.edit')" @click="openEditDialog(source)">
              <el-icon><EditPen /></el-icon>
            </el-button>
            <el-button size="small" type="danger" :title="t('common.delete')" @click="confirmDelete(source)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>

        <div v-if="!store.sources.length" class="empty-hint">
          <el-icon :size="32" color="#555"><VideoCamera /></el-icon>
          <span>{{ t('sourceList.noSources') }}</span>
        </div>
      </el-scrollbar>
    </div>

    <div class="section results-section">
      <div class="list-header results-header">
        <div>
          <span class="list-title">{{ t('sourceList.resultStreams') }}</span>
          <p class="list-subtitle">{{ t('sourceList.resultsHint') }}</p>
        </div>
      </div>

      <el-scrollbar class="sources-scroll">
        <div
          v-for="rs in resultStreams"
          :key="rs.id"
          class="source-item result-item"
          draggable="true"
          @dragstart="onResultDragStart($event, rs)"
        >
          <div class="source-info">
            <div class="source-name result-name">
              <el-badge type="success" is-dot class="status-dot" />
              {{ rs.name }}
            </div>
            <div class="source-url">{{ rs.streamPath }}</div>
          </div>
        </div>

        <div v-if="!resultStreams.length" class="empty-hint">
          <el-icon :size="24" color="#555"><Monitor /></el-icon>
          <span>{{ t('sourceList.noResultStreams') }}</span>
        </div>
      </el-scrollbar>
    </div>

    <SourceEditorDialog
      v-model="showAddDialog"
      :title="t('sourceList.addSource')"
      :submit-label="t('common.add')"
      :form="form"
      :loading="addLoading"
      :rtsp-base="appSettingsStore.mediamtxRtspAddr"
      @submit="addSource"
    />

    <SourceEditorDialog
      v-model="showEditDialog"
      :title="t('sourceList.editSource')"
      :submit-label="t('common.save')"
      :form="editForm"
      :loading="editLoading"
      :rtsp-base="appSettingsStore.mediamtxRtspAddr"
      @submit="saveEdit"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import ElMessageBox from 'element-plus/es/components/message-box/index'
import SourceEditorDialog from './source/SourceEditorDialog.vue'
import SourcePanelSummary from './source/SourcePanelSummary.vue'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useSourceStore } from '../stores/source.js'
import { extractRoutePath, normalizeRoutePath } from '../utils/sourceAddress.js'

const store = useSourceStore()
const appSettingsStore = useAppSettingsStore()
const { t } = useI18n()
const showAddDialog = ref(false)
const showEditDialog = ref(false)
const addLoading = ref(false)
const editLoading = ref(false)
const bulkAction = ref('')
const actionLoading = reactive({})
const editingSourceId = ref('')

const form = reactive({ name: '', route_path: '' })
const editForm = reactive({ name: '', route_path: '' })

const resultStreams = computed(() => {
  return store.sources
    .filter((s) => store.isRunning(s.id))
    .map((s) => {
      const route = getSourceRoute(s)
      return {
        id: `result_${s.id}`,
        name: `${s.name} (${t('sourceList.resultSuffix')})`,
        streamPath: `${route}_processed`,
        isResult: true,
        originalSourceId: s.id,
      }
    })
})

function onDragStart(event, source) {
  event.dataTransfer.setData('source-id', source.id)
  event.dataTransfer.effectAllowed = 'copy'
}

function onResultDragStart(event, resultStream) {
  event.dataTransfer.setData('result-stream', JSON.stringify(resultStream))
  event.dataTransfer.effectAllowed = 'copy'
}

async function addSource() {
  const routePath = normalizeRoutePath(form.route_path)

  if (!form.name || !routePath) {
    ElMessage.warning(t('sourceList.fillAllFields'))
    return
  }
  if (!appSettingsStore.mediamtxRtspAddr) {
    ElMessage.warning(t('sourceList.missingRtspBase'))
    return
  }

  addLoading.value = true
  try {
    await store.createSource({ name: form.name, route_path: routePath })
    showAddDialog.value = false
    form.name = ''
    form.route_path = ''
    ElMessage.success(t('sourceList.sourceAdded'))
  } catch (err) {
    ElMessage.error(err.message || t('sourceList.failedToAdd'))
  } finally {
    addLoading.value = false
  }
}

async function handleStartAll() {
  bulkAction.value = 'start'
  try {
    await store.startAllProcessing()
  } finally {
    bulkAction.value = ''
  }
}

async function handleStopAll() {
  bulkAction.value = 'stop'
  try {
    await store.stopAllProcessing()
  } finally {
    bulkAction.value = ''
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

function openEditDialog(source) {
  editingSourceId.value = source.id
  editForm.name = source.name
  editForm.route_path = extractRoutePath(source.rtsp_url, appSettingsStore.mediamtxRtspAddr)
  showEditDialog.value = true
}

async function saveEdit() {
  if (!editingSourceId.value) return

  const routePath = normalizeRoutePath(editForm.route_path)

  if (!editForm.name || !routePath) {
    ElMessage.warning(t('sourceList.fillAllFields'))
    return
  }
  if (!appSettingsStore.mediamtxRtspAddr) {
    ElMessage.warning(t('sourceList.missingRtspBase'))
    return
  }

  editLoading.value = true
  try {
    await store.updateSource(editingSourceId.value, {
      name: editForm.name,
      route_path: routePath,
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

onMounted(async () => {
  if (!appSettingsStore.loaded) {
    await appSettingsStore.fetchSettings().catch(() => {
      // Keep fallback defaults when settings API is unavailable.
    })
  }
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

.list-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #7f8bad;
}

.sources-scroll {
  flex: 1;
}

.source-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #2a2a3e;
  cursor: grab;
  transition: background 0.2s;
}

.source-item:hover {
  background: #24243e;
}

.source-info {
  flex: 1;
  min-width: 0;
}

.source-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  margin-bottom: 4px;
}

.result-name {
  color: #67c23a;
}

.source-url {
  font-size: 12px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-actions {
  display: flex;
  gap: 4px;
  margin-left: 12px;
  flex-shrink: 0;
}

.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: #666;
  font-size: 13px;
}

@media (max-width: 920px) {
  .source-item {
    align-items: flex-start;
    gap: 10px;
    flex-direction: column;
  }

  .source-actions {
    margin-left: 0;
  }
}
</style>
