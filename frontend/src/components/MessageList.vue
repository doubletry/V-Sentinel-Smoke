<template>
  <div class="message-list">
    <div
      v-for="(msg, idx) in messages"
      :key="messageKey(msg, idx)"
      class="message-card"
      :class="[`level-${msg.level}`, { 'agent-summary': msg.source_id === '__agent__' }]"
    >
      <div class="msg-header">
        <el-tag :type="levelType(msg.level)" size="small" effect="dark">
          {{ msg.source_id === '__agent__' ? t('messageList.summary') : msg.level.toUpperCase() }}
        </el-tag>
        <el-tag v-if="msg.false_positive" type="warning" size="small" effect="plain">
          {{ t('messageList.falsePositive') }}
        </el-tag>
        <span class="msg-source">{{ msg.source_name }}</span>
        <span class="msg-time">{{ formatTimeWithTimezone(msg.timestamp, appSettingsStore.timeZone) }}</span>
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
      </div>
    </div>

    <div v-if="!messages.length" class="empty-msgs">
      <el-icon :size="32" color="#555"><ChatRound /></el-icon>
      <span>{{ t('messageList.noMessages') }}</span>
    </div>

    <el-dialog v-model="previewVisible" width="70%" top="5vh" append-to-body>
      <img v-if="previewImage" :src="previewImage" alt="preview" class="preview-image" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useAuthStore } from '../stores/auth.js'
import { formatTimeWithTimezone } from '../utils/time.js'

defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  resendingMessageIds: {
    type: Object,
    default: () => ({}),
  },
})
const emit = defineEmits(['mark-false-positive', 'unmark-false-positive', 'resend-notification'])

const { t } = useI18n()
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const previewVisible = ref(false)
const previewImage = ref('')
const canAnnotateMessages = computed(() => authStore.hasPermission('messages:annotate'))

function levelType(level) {
  const map = { info: '', warning: 'warning', alert: 'danger' }
  return map[level] ?? ''
}

function originalImageSrc(message) {
  if (message?.original_image_url) return message.original_image_url
  if (message?.original_image_base64) return `data:image/jpeg;base64,${message.original_image_base64}`
  return ''
}

function detectedImageSrc(message) {
  if (message?.detected_image_url) return message.detected_image_url
  if (message?.image_url) return message.image_url
  if (message?.detected_image_base64) return `data:image/jpeg;base64,${message.detected_image_base64}`
  if (message?.image_base64) return `data:image/jpeg;base64,${message.image_base64}`
  return ''
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
    || `${message?.timestamp || 'no-timestamp'}-${message?.source_id || message?.source_name || 'no-source'}-${message?.level || 'no-level'}-${idx}`
  )
}
</script>

<style scoped>
.message-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
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
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 10px;
  color: #555;
  font-size: 13px;
}
</style>
