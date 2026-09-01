<template>
  <div class="message-list">
    <div v-for="group in groupedMessages" :key="group.date" class="message-group">
      <div class="msg-date-separator">
        <el-checkbox
          v-if="canDeleteMessages && group.selectableIds.length"
          :model-value="group.allSelected"
          :indeterminate="group.someSelected && !group.allSelected"
          :aria-label="t('messageList.selectThisDate')"
          @change="onToggleGroup(group, $event)"
        />
        <span class="msg-date-separator__label">{{ group.label }}</span>
        <span class="msg-date-separator__count">{{ group.messages.length }}</span>
      </div>
      <div
        v-for="(msg, idx) in group.messages"
        :key="messageKey(msg, idx)"
        class="message-card"
        :class="[`level-${msg.level}`, { 'agent-summary': msg.source_id === '__agent__' }]"
      >
        <div class="msg-header">
          <el-checkbox
            v-if="canDeleteMessages && msg.id && msg.source_id !== '__agent__'"
            :model-value="Boolean(selectedIds[msg.id])"
            :aria-label="t('messageList.delete')"
            @change="(value) => emit('toggle-select', msg.id, value)"
          />
          <el-tag :type="levelType(msg.level)" size="small" effect="dark">
            {{ msg.source_id === '__agent__' ? t('messageList.summary') : msg.level.toUpperCase() }}
          </el-tag>
          <el-tag v-if="msg.false_positive" type="warning" size="small" effect="plain">
            {{ t('messageList.falsePositive') }}
          </el-tag>
          <span class="msg-source">{{ msg.source_name }}</span>
          <span class="msg-time">{{ formatDateTimeWithTimezone(msg.timestamp, appSettingsStore.timeZone) }}</span>
        </div>
        <div class="msg-body">{{ msg.message }}</div>
        <div v-if="hasAnyImage(msg)" class="msg-image-grid">
          <div v-if="originalImageSrc(msg)" class="msg-image-card">
            <div class="msg-image-title">{{ t('messageList.originalImage') }}</div>
            <img
              :src="originalImageSrc(msg)"
              alt="original snapshot"
              @dblclick="openPreview(originalImageSrc(msg))"
            />
          </div>
          <div v-if="detectedImageSrc(msg)" class="msg-image-card">
            <div class="msg-image-title">{{ t('messageList.detectedImage') }}</div>
            <img
              :src="detectedImageSrc(msg)"
              alt="detected snapshot"
              @dblclick="openPreview(detectedImageSrc(msg))"
            />
          </div>
        </div>
        <div class="msg-actions">
          <el-button
            v-if="canAnnotateMessages && msg.id"
            size="small"
            type="primary"
            plain
            :loading="Boolean(resendingMessageIds[msg.id])"
            @click="emit('resend-notification', msg)"
          >
            {{ t('messageList.resendNotification') }}
          </el-button>
          <el-button
            v-if="vlReviewVisible(msg)"
            size="small"
            type="primary"
            plain
            :loading="Boolean(reviewingMessageIds[msg.id])"
            @click="emit('vl-review', msg)"
          >
            {{ t('messageList.vlReview') }}
          </el-button>
          <el-button
            v-if="canAnnotateMessages && msg.id && !msg.false_positive"
            size="small"
            type="warning"
            plain
            @click="emit('mark-false-positive', msg)"
          >
            {{ t('messageList.markFalsePositive') }}
          </el-button>
          <el-button
            v-if="canAnnotateMessages && msg.id && msg.false_positive"
            size="small"
            type="info"
            plain
            @click="emit('unmark-false-positive', msg)"
          >
            {{ t('messageList.unmarkFalsePositive') }}
          </el-button>
          <el-button
            v-if="canDeleteMessages && msg.id"
            size="small"
            type="danger"
            plain
            @click="emit('delete-message', msg)"
          >
            {{ t('messageList.delete') }}
          </el-button>
        </div>
      </div>
    </div>

    <el-empty
      v-if="!messages.length"
      :description="t('messageList.noMessages')"
      :image-size="80"
      class="empty-msgs"
    />

    <el-dialog v-model="previewVisible" width="70%" top="5vh" append-to-body>
      <img v-if="previewImage" :src="previewImage" alt="preview" class="preview-image" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import config from '../config.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useAuthStore } from '../stores/auth.js'
import { formatDateTimeWithTimezone, formatWithTimezone } from '../utils/time.js'
import { resolveAppUrl } from '../utils/appPath.js'

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  resendingMessageIds: {
    type: Object,
    default: () => ({}),
  },
  reviewingMessageIds: {
    type: Object,
    default: () => ({}),
  },
  selectedIds: {
    type: Object,
    default: () => ({}),
  },
})
const emit = defineEmits([
  'mark-false-positive',
  'unmark-false-positive',
  'resend-notification',
  'vl-review',
  'delete-message',
  'toggle-select',
  'toggle-select-group',
])

const { t } = useI18n()
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const previewVisible = ref(false)
const previewImage = ref('')
const canAnnotateMessages = computed(() => authStore.hasPermission('messages:annotate'))
const canDeleteMessages = computed(() => authStore.hasPermission('messages:delete'))

function vlReviewVisible(message) {
  if (!canAnnotateMessages.value || !message?.id) return false
  if (!message.source_id || message.source_id === '__agent__') return false
  const scene = message.scene_id || 'smoke'
  const enabled = appSettingsStore.settings?.[`${scene}_vl_confirm_enabled`]
  return String(enabled || 'false').toLowerCase() === 'true'
}

function levelType(level) {
  const map = { info: '', warning: 'warning', alert: 'danger' }
  return map[level] ?? ''
}

function originalImageSrc(message) {
  if (message?.original_image_url) return appendAuthToken(resolveAppUrl(message.original_image_url, config.appBasePath))
  if (message?.original_image_base64) return `data:image/jpeg;base64,${message.original_image_base64}`
  return ''
}

function detectedImageSrc(message) {
  if (message?.detected_image_url) return appendAuthToken(resolveAppUrl(message.detected_image_url, config.appBasePath))
  if (message?.image_url) return appendAuthToken(resolveAppUrl(message.image_url, config.appBasePath))
  if (message?.detected_image_base64) return `data:image/jpeg;base64,${message.detected_image_base64}`
  if (message?.image_base64) return `data:image/jpeg;base64,${message.image_base64}`
  return ''
}

function appendAuthToken(url) {
  if (!url || !authStore.token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(authStore.token)}`
}

function hasAnyImage(message) {
  return Boolean(originalImageSrc(message) || detectedImageSrc(message))
}

function openPreview(imageSrc) {
  previewImage.value = imageSrc
  previewVisible.value = true
}

function messageKey(message, idx) {
  return (
    message?.id
    || `${message?.timestamp || 'no-timestamp'}-${message?.source_id || message?.source_name || 'no-source'}-${message?.level || 'no-level'}-${message?.message || 'no-message'}-${idx}`
  )
}

function timezoneDayKey(timestamp) {
  if (!timestamp) return ''
  const tz = appSettingsStore.timeZone || 'Asia/Shanghai'
  const parts = formatWithTimezone(timestamp, tz, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  // Normalise to YYYY-MM-DD regardless of locale separators.
  const digits = String(parts).match(/(\d{4})\D(\d{1,2})\D(\d{1,2})/)
  if (!digits) return String(parts)
  const [, y, m, d] = digits
  return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
}

function dayLabel(dayKey) {
  if (!dayKey) return ''
  const tz = appSettingsStore.timeZone || 'Asia/Shanghai'
  const todayKey = timezoneDayKey(new Date().toISOString())
  // Compute yesterday in the active timezone via subtracting 24h from now and re-keying.
  const yesterdayDate = new Date(Date.now() - 24 * 60 * 60 * 1000)
  const yesterdayKey = timezoneDayKey(yesterdayDate.toISOString())
  if (dayKey === todayKey) return t('messageList.today')
  if (dayKey === yesterdayKey) return t('messageList.yesterday')
  // Compose a noon timestamp on that day for nice locale-formatted output.
  const display = formatWithTimezone(`${dayKey}T12:00:00Z`, tz, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
  })
  return display
}

const groupedMessages = computed(() => {
  const groups = new Map()
  const order = []
  for (const msg of props.messages) {
    const key = timezoneDayKey(msg?.timestamp) || 'unknown'
    if (!groups.has(key)) {
      order.push(key)
      groups.set(key, [])
    }
    groups.get(key).push(msg)
  }
  return order.map((key) => {
    const items = groups.get(key)
    const selectableIds = items
      .filter((m) => m?.id && m?.source_id !== '__agent__')
      .map((m) => m.id)
    const selectedCount = selectableIds.filter((id) => props.selectedIds[id]).length
    return {
      date: key,
      label: dayLabel(key),
      messages: items,
      selectableIds,
      allSelected: selectableIds.length > 0 && selectedCount === selectableIds.length,
      someSelected: selectedCount > 0,
    }
  })
})

function onToggleGroup(group, value) {
  emit('toggle-select-group', group.selectableIds, Boolean(value))
}
</script>

<style scoped>
.message-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}

.message-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.msg-date-separator {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  background: linear-gradient(90deg, rgba(64, 158, 255, 0.18), rgba(26, 26, 46, 0.85));
  border-left: 3px solid #409EFF;
  border-radius: 4px;
  color: #c8d5f0;
  font-size: 13px;
  font-weight: 600;
}

.msg-date-separator__label {
  flex: 1 1 auto;
}

.msg-date-separator__count {
  background: rgba(64, 158, 255, 0.25);
  color: #c8d5f0;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.message-card {
  background: #1e1e2e;
  border-radius: 6px;
  padding: 10px 14px;
  border-left: 4px solid #555;
  border-top: 1px solid rgba(69, 83, 117, 0.55);
  border-right: 1px solid rgba(69, 83, 117, 0.55);
  border-bottom: 1px solid rgba(69, 83, 117, 0.55);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}

.message-card.level-info {
  border-left-color: #409EFF;
}

.message-card.level-warning {
  border-left-color: #e6a23c;
}

.message-card.level-alert {
  border-left-color: #f56c6c;
}

.message-card.agent-summary {
  background: #1a2a3e;
  border-left-color: #67c23a;
  border: 1px solid #2a3a4e;
}

.msg-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  min-width: 0;
}

.msg-source {
  font-size: 13px;
  font-weight: 600;
  color: #aaa;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-time {
  margin-left: auto;
  font-size: 13px;
  color: #9aa6c0;
  font-weight: 600;
  white-space: nowrap;
}

.msg-body {
  font-size: 13px;
  color: #ccc;
  line-height: 1.5;
}

.msg-image-grid {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.msg-image-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg-image-title {
  color: #9aa6c0;
  font-size: 12px;
}

.msg-image-card img {
  width: auto;
  max-width: min(100%, 360px);
  max-height: 220px;
  border-radius: 4px;
  object-fit: contain;
  cursor: zoom-in;
  image-rendering: auto;
  border: 1px solid rgba(69, 83, 117, 0.55);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.22);
}

.msg-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.preview-image {
  width: 100%;
  max-height: 75vh;
  object-fit: contain;
}

.empty-msgs {
  padding: 40px 20px;
}

.empty-msgs :deep(.el-empty__description) {
  color: #8aa6d9;
}
</style>
