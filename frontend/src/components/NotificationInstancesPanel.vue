<template>
  <section class="settings-section section-card notification-instances-section">
    <div class="section-card__head notification-instances-section__head">
      <div>
        <h2>{{ t('settings.notificationInstancesSection') }}</h2>
        <p class="info-tip">{{ t('settings.notificationInstancesHint') }}</p>
      </div>
    </div>

    <div class="notification-instances-toolbar">
      <span class="notification-instances-toolbar__meta">
        {{ t('settings.notificationTypeEmail') }} / {{ t('settings.notificationTypeWebhook') }} / {{ t('settings.notificationTypeSocket') }}
      </span>
      <el-button size="small" class="notification-instances-section__add" @click="openCreateDialog">
        {{ t('settings.addNotificationInstance') }}
      </el-button>
    </div>

    <div v-loading="loading" class="notification-instance-grid">
      <article
        v-for="item in instances"
        :key="item.id"
        :class="['notification-instance-card', `notification-instance-card--${item.type}`, { 'is-disabled': !item.enabled }]"
      >
        <header class="notification-instance-card__header">
          <div class="notification-instance-card__title-wrap">
            <span :class="['notification-instance-card__type-badge', `notification-instance-card__type-badge--${item.type}`]">
              {{ notificationTypeLabel(item.type) }}
            </span>
            <h3 class="notification-instance-card__name">{{ item.name }}</h3>
          </div>
          <el-switch
            :model-value="item.enabled"
            @change="toggleEnabled(item, $event)"
          />
        </header>

        <dl class="notification-instance-card__meta-grid">
          <div class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationEndpoint') }}</dt>
            <dd>{{ endpointSummary(item) }}</dd>
          </div>
          <div class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationSources') }}</dt>
            <dd>{{ sourceScopeSummary(item) }}</dd>
          </div>
          <div v-if="item.type === 'email'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationTemplateSubject') }}</dt>
            <dd class="notification-instance-card__code">{{ item.config?.subject_template || defaultSubjectTemplate }}</dd>
          </div>
          <div v-if="item.type === 'email'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationTemplateBody') }}</dt>
            <dd class="notification-instance-card__code notification-instance-card__body">{{ item.config?.body_template || defaultBodyTemplate }}</dd>
          </div>
          <div v-else-if="item.type === 'webhook'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationWebhookPayload') }}</dt>
            <dd class="notification-instance-card__code notification-instance-card__body">
              {{ payloadSummary(item) }}
            </dd>
          </div>
          <div v-else-if="item.type === 'socket'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationSocketMessageMode') }}</dt>
            <dd class="notification-instance-card__code notification-instance-card__body">
              {{ socketSummary(item) }}
            </dd>
          </div>
          <div v-if="item.type === 'socket' && item.config?.protocol === 'tcp'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationSocketWaitForResponse') }}</dt>
            <dd>{{ tcpWaitSummary(item) }}</dd>
          </div>
        </dl>

        <footer class="notification-instance-card__footer">
          <span class="notification-instance-card__timestamp">{{ formatTimestamp(item.created_at) }}</span>
          <div class="notification-instance-card__actions">
            <el-button
              size="small"
              plain
              :loading="testingInstanceId === item.id"
              :disabled="Boolean(testingInstanceId)"
              @click="testInstance(item)"
            >
              {{ t('settings.testNotificationInstance') }}
            </el-button>
            <el-button size="small" plain @click="openEditDialog(item)">
              {{ t('common.edit') }}
            </el-button>
          </div>
        </footer>
      </article>

      <div v-if="!loading && !instances.length" class="notification-instance-empty">
        {{ t('settings.noNotificationInstances') }}
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingInstanceId ? t('settings.editNotificationInstance') : t('settings.addNotificationInstance')"
      width="760px"
      class="notification-instance-dialog"
      destroy-on-close
    >
      <el-form label-position="top">
        <div class="notification-instance-form-grid">
          <el-form-item :label="t('settings.notificationInstanceName')">
            <el-input v-model="form.name" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationType')">
            <el-select v-model="form.type" :disabled="Boolean(editingInstanceId)" style="width: 100%">
              <el-option value="email" :label="t('settings.notificationTypeEmail')" />
              <el-option value="webhook" :label="t('settings.notificationTypeWebhook')" />
              <el-option value="socket" :label="t('settings.notificationTypeSocket')" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.notificationEnabled')">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationCooldownSeconds')">
            <el-input v-model="form.cooldown_seconds" placeholder="300" />
          </el-form-item>
        </div>

        <div class="notification-instance-form-grid notification-instance-form-grid--sources">
          <el-form-item :label="t('settings.notificationSources')" class="notification-instance-form-span-full">
            <div class="source-picker-panel">
              <div class="source-picker-panel__head">
                <div>
                  <div class="source-picker-panel__eyebrow">{{ t('settings.notificationSources') }}</div>
                  <p class="source-picker-panel__summary">{{ sourceSelectionSummary }}</p>
                </div>
                <el-tag
                  size="small"
                  effect="dark"
                  :type="form.apply_to_all_sources ? 'success' : 'info'"
                  class="source-picker-panel__status"
                >
                  {{ sourceSelectionStatus }}
                </el-tag>
              </div>

              <el-select
                v-model="selectedSourceValues"
                multiple
                clearable
                filterable
                collapse-tags
                collapse-tags-tooltip
                class="source-picker-panel__select"
                :placeholder="t('settings.notificationSourceSelectPlaceholder')"
                style="width: 100%"
              >
                <el-option :value="ALL_NOTIFICATION_SOURCES_VALUE" :label="t('settings.notificationAllSources')">
                  <div class="source-picker-panel__option">
                    <span>{{ t('settings.notificationAllSources') }}</span>
                    <span class="source-picker-panel__option-hint">{{ t('settings.notificationAllSourcesAutoHint') }}</span>
                  </div>
                </el-option>
                <el-option
                  v-for="source in availableSources"
                  :key="source.id"
                  :value="source.id"
                  :label="source.name"
                >
                  <div class="source-picker-panel__option">
                    <span>{{ source.name }}</span>
                    <span class="source-picker-panel__option-hint">{{ source.remark || source.route_path || source.id }}</span>
                  </div>
                </el-option>
              </el-select>

              <p class="form-hint">
                {{ form.apply_to_all_sources ? t('settings.notificationAllSourcesAutoHint') : t('settings.notificationSourceSelectionHint') }}
              </p>
              <div v-if="!availableSources.length" class="source-picker-panel__empty">
                {{ t('settings.notificationSourceSelectionEmptyHint') }}
              </div>
            </div>
          </el-form-item>
        </div>

        <div v-if="form.type === 'email'" class="notification-instance-form-grid">
          <el-form-item :label="t('settings.emailFromAddress')">
            <el-input v-model="form.from_address" placeholder="sender@example.com" />
          </el-form-item>
          <el-form-item :label="t('settings.emailSmtpHost')">
            <el-input v-model="form.smtp_host" placeholder="smtp.example.com" />
          </el-form-item>
          <el-form-item :label="t('settings.emailSmtpPort')">
            <el-input v-model="form.smtp_port" placeholder="587" />
          </el-form-item>
          <el-form-item :label="t('settings.emailSmtpUseTls')">
            <el-switch v-model="form.use_tls" />
          </el-form-item>
          <el-form-item :label="t('settings.emailFromAuthCode')">
            <el-input v-model="form.smtp_password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="t('settings.emailToAddresses')" class="notification-instance-form-span-full">
            <el-input v-model="form.to_addresses" type="textarea" :rows="2" placeholder="ops@example.com,team@example.com" />
          </el-form-item>
          <el-form-item :label="t('settings.emailCcAddresses')" class="notification-instance-form-span-full">
            <el-input v-model="form.cc_addresses" type="textarea" :rows="2" placeholder="cc@example.com" />
          </el-form-item>
        </div>

        <div v-else-if="form.type === 'webhook'" class="notification-instance-form-grid">
          <el-form-item :label="t('settings.notificationWebhookUrl')" class="notification-instance-form-span-full">
            <el-input v-model="form.url" placeholder="https://example.com/webhook" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationWebhookMethod')">
            <el-select v-model="form.method" style="width: 100%">
              <el-option value="POST" label="POST" />
              <el-option value="PUT" label="PUT" />
              <el-option value="PATCH" label="PATCH" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.notificationWebhookHeaders')" class="notification-instance-form-span-full">
            <el-input v-model="form.headers_text" type="textarea" :rows="4" placeholder='{"Authorization":"Bearer xxx"}' />
          </el-form-item>
          <el-form-item :label="t('settings.notificationWebhookPayload')" class="notification-instance-form-span-full">
            <div class="field-stack">
              <el-input v-model="form.webhook_payload_text" type="textarea" :rows="10" />
              <p class="form-hint">{{ t('settings.notificationWebhookPayloadHint') }}</p>
              <div class="placeholder-group-list">
                <div
                  v-for="group in placeholderGroups"
                  :key="`webhook-${group.key}`"
                  class="placeholder-group"
                >
                  <div class="placeholder-group__title">{{ group.label }}</div>
                  <div class="placeholder-tags">
                    <el-tooltip
                      v-for="item in group.items"
                      :key="`webhook-${group.key}-${item}`"
                      effect="dark"
                      placement="top"
                      trigger="hover"
                      :show-after="120"
                      :content="placeholderDescription(item)"
                    >
                      <el-tag
                        size="small"
                        effect="dark"
                        :type="placeholderTagType(group.key)"
                        class="placeholder-tag"
                        tabindex="0"
                        :title="placeholderDescription(item)"
                      >
                        {{ '{' + item + '}' }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                </div>
              </div>
            </div>
          </el-form-item>
        </div>

        <div v-if="form.type === 'email'" class="notification-instance-form-grid">
          <el-form-item :label="t('settings.notificationTemplateSubject')" class="notification-instance-form-span-full">
            <el-input v-model="form.subject_template" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationTemplateBody')" class="notification-instance-form-span-full">
            <div class="field-stack">
              <el-input v-model="form.body_template" type="textarea" :rows="8" />
              <p class="form-hint">{{ t('settings.emailTemplateHint') }}</p>
              <div class="placeholder-group-list">
                <div
                  v-for="group in placeholderGroups"
                  :key="group.key"
                  class="placeholder-group"
                >
                  <div class="placeholder-group__title">{{ group.label }}</div>
                  <div class="placeholder-tags">
                    <el-tooltip
                      v-for="item in group.items"
                      :key="`${group.key}-${item}`"
                      effect="dark"
                      placement="top"
                      trigger="hover"
                      :show-after="120"
                      :content="placeholderDescription(item)"
                    >
                      <el-tag
                        size="small"
                        effect="dark"
                        :type="placeholderTagType(group.key)"
                        class="placeholder-tag"
                        tabindex="0"
                        :title="placeholderDescription(item)"
                      >
                        {{ '{' + item + '}' }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                </div>
              </div>
            </div>
          </el-form-item>
        </div>

        <div v-else class="notification-instance-form-grid">
          <el-form-item :label="t('settings.notificationSocketProtocol')">
            <el-select v-model="form.socket_protocol" style="width: 100%">
              <el-option value="tcp" :label="t('settings.notificationSocketProtocolTcp')" />
              <el-option value="udp" :label="t('settings.notificationSocketProtocolUdp')" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.notificationSocketHost')">
            <el-input v-model="form.socket_host" placeholder="127.0.0.1" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationSocketPort')">
            <el-input v-model="form.socket_port" placeholder="9527" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationSocketMessageMode')">
            <el-select v-model="form.socket_message_mode" style="width: 100%">
              <el-option value="string" :label="t('settings.notificationSocketMessageModeString')" />
              <el-option value="hex" :label="t('settings.notificationSocketMessageModeHex')" />
            </el-select>
          </el-form-item>
          <el-form-item
            v-if="form.socket_message_mode === 'string'"
            :label="t('settings.notificationSocketMessageText')"
            class="notification-instance-form-span-full"
          >
            <div class="field-stack">
              <el-input v-model="form.socket_message_text" type="textarea" :rows="5" />
              <p class="form-hint">{{ t('settings.notificationSocketStringHint') }}</p>
              <div class="placeholder-group-list">
                <div
                  v-for="group in placeholderGroups"
                  :key="`socket-${group.key}`"
                  class="placeholder-group"
                >
                  <div class="placeholder-group__title">{{ group.label }}</div>
                  <div class="placeholder-tags">
                    <el-tooltip
                      v-for="item in group.items"
                      :key="`socket-${group.key}-${item}`"
                      effect="dark"
                      placement="top"
                      trigger="hover"
                      :show-after="120"
                      :content="placeholderDescription(item)"
                    >
                      <el-tag
                        size="small"
                        effect="dark"
                        :type="placeholderTagType(group.key)"
                        class="placeholder-tag"
                        tabindex="0"
                        :title="placeholderDescription(item)"
                      >
                        {{ '{' + item + '}' }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                </div>
              </div>
            </div>
          </el-form-item>
          <el-form-item v-if="form.socket_message_mode === 'string'" :label="t('settings.notificationSocketEncoding')">
            <el-input v-model="form.socket_encoding" placeholder="utf-8" />
          </el-form-item>
          <el-form-item v-if="form.socket_protocol === 'tcp'" :label="t('settings.notificationSocketWaitForResponse')">
            <el-switch v-model="form.socket_wait_for_response" />
          </el-form-item>
          <el-form-item
            v-if="form.socket_protocol === 'tcp' && form.socket_wait_for_response"
            :label="t('settings.notificationSocketResponseTimeout')"
          >
            <el-input v-model="form.socket_response_timeout_seconds" placeholder="3" />
          </el-form-item>
          <el-form-item
            v-if="form.socket_message_mode === 'hex'"
            :label="t('settings.notificationSocketMessageHex')"
            class="notification-instance-form-span-full"
          >
            <div class="field-stack">
              <el-input
                ref="socketHexInput"
                :model-value="socketHexText"
                type="textarea"
                :rows="4"
                placeholder="41-42-43-44"
                @input="updateSocketHexText"
              />
              <p class="form-hint">{{ t('settings.notificationSocketHexHint') }}</p>
            </div>
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submit">
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { notificationsApi, settingsApi, sourcesApi } from '../api/index.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import {
  ALL_NOTIFICATION_SOURCES_VALUE,
  applyNotificationSourceSelection,
  buildNotificationInstancePayload,
  createDefaultNotificationInstanceForm,
  defaultBodyTemplate,
  defaultSubjectTemplate,
  defaultWebhookPayloadTemplate,
  formatSocketHexInput,
  formatSocketHexBytes,
  normalizeSourceIds,
  serializeNotificationSourceSelection,
  serializeNotificationInstanceForEdit,
} from '../utils/notificationInstances.js'
import { formatTimeWithTimezone } from '../utils/time.js'

const { t } = useI18n()
const appSettingsStore = useAppSettingsStore()
const loading = ref(false)
const saving = ref(false)
const testingInstanceId = ref('')
const dialogVisible = ref(false)
const editingInstanceId = ref('')
const instances = ref([])
const availableSources = ref([])
const placeholderItems = ref([
  'site_title', 'timestamp', 'local_time', 'timezone', 'source_name', 'source_id',
  'event_type', 'event_label', 'message', 'labels', 'confidence', 'confidence_percent',
  'detection_count', 'frame_id', 'active_tracks', 'original_image', 'detected_image',
  'original_image_url', 'detected_image_url', 'has_original_image', 'has_detected_image',
  'source_rtsp_url', 'source_route_path', 'source_host', 'source_host_or_ip', 'source_ip',
  'source_port', 'source_remark', 'source_description', 'roi_id', 'roi_tag', 'roi_index',
  'roi_count', 'door_state', 'door_state_label', 'alarm_label', 'open_count', 'closed_count',
])
const SMOKE_SCENE_ID = 'smoke'
const FIRE_DOOR_SCENE_ID = 'fire_door'
const SMOKE_PLACEHOLDERS = new Set(['detection_count', 'frame_id', 'active_tracks'])
const FIRE_DOOR_PLACEHOLDERS = new Set(['roi_id', 'roi_tag', 'roi_index', 'roi_count', 'door_state', 'door_state_label', 'alarm_label', 'open_count', 'closed_count'])
const form = ref(createDefaultNotificationInstanceForm())
const socketHexInput = ref(null)

const placeholderGroups = computed(() => {
  const activePluginId = String(appSettingsStore.activePluginId || SMOKE_SCENE_ID)
  const groups = [
    { key: 'common', label: t('settings.placeholderCategoryCommon'), items: [] },
    { key: 'smoke', label: t('settings.placeholderCategorySmoke'), items: [] },
    { key: 'fireDoor', label: t('settings.placeholderCategoryFireDoor'), items: [] },
  ]
  for (const item of placeholderItems.value) {
    if (FIRE_DOOR_PLACEHOLDERS.has(item)) {
      if (activePluginId === FIRE_DOOR_SCENE_ID) groups[2].items.push(item)
    } else if (SMOKE_PLACEHOLDERS.has(item)) {
      if (activePluginId === SMOKE_SCENE_ID) groups[1].items.push(item)
    } else {
      groups[0].items.push(item)
    }
  }
  return groups.filter((group) => group.items.length)
})

function placeholderDescription(item) {
  const translated = t(`settings.placeholderDescriptions.${item}`)
  return translated === `settings.placeholderDescriptions.${item}` ? item : translated
}

function placeholderTagType(groupKey) {
  if (groupKey === 'smoke') return 'warning'
  if (groupKey === 'fireDoor') return 'success'
  return 'info'
}

function formatTimestamp(value) {
  return formatTimeWithTimezone(value, appSettingsStore.timeZone)
}

function endpointSummary(item) {
  if (item.type === 'email') {
    const host = item.config?.smtp_host || '—'
    const recipients = item.config?.to_addresses || ''
    return `${host} · ${String(recipients || '—')}`
  }
  if (item.type === 'socket') {
    const protocol = String(item.config?.protocol || 'tcp').toUpperCase()
    const host = item.config?.host || '—'
    const port = item.config?.port || '—'
    return `${protocol} · ${host}:${port}`
  }
  return `${item.config?.method || 'POST'} · ${item.config?.url || '—'}`
}

function notificationTypeLabel(type) {
  if (type === 'email') return t('settings.notificationTypeEmail')
  if (type === 'socket') return t('settings.notificationTypeSocket')
  return t('settings.notificationTypeWebhook')
}

function sourceScopeSummary(item) {
  if (item.apply_to_all_sources ?? true) {
    return t('settings.notificationAllSources')
  }
  const selectedIds = normalizeSourceIds(item.source_ids || [])
  if (!selectedIds.length) {
    return t('settings.notificationNoSourcesSelected')
  }
  const names = selectedIds.map((id) => availableSources.value.find((source) => source.id === id)?.name || id)
  if (names.length <= 2) return names.join(', ')
  return t('settings.notificationSpecificSources', { count: names.length })
}

function payloadSummary(item) {
  try {
    return JSON.stringify(item.config?.payload_template || defaultWebhookPayloadTemplate, null, 2)
  } catch {
    return '{}'
  }
}

function socketSummary(item) {
  const mode = String(item.config?.message_mode || 'string').toLowerCase()
  if (mode === 'hex') {
    return formatSocketHexBytes(item.config?.message_hex) || '—'
  }
  return item.config?.message_text || '—'
}

function tcpWaitSummary(item) {
  if (!item.config?.wait_for_response) {
    return t('settings.notificationSocketNoWait')
  }
  return t('settings.notificationSocketWaitWithTimeout', {
    seconds: item.config?.response_timeout_seconds || '3',
  })
}

const normalizedSelectedSourceIds = computed(() => normalizeSourceIds(form.value.source_ids || []))

const selectedSourceValues = computed({
  get() {
    return serializeNotificationSourceSelection(form.value)
  },
  set(values) {
    Object.assign(form.value, applyNotificationSourceSelection(form.value, values))
  },
})

const socketHexText = computed(() => formatSocketHexBytes(form.value.socket_message_hex))

function getSocketHexTextarea() {
  return socketHexInput.value?.textarea || socketHexInput.value?.$el?.querySelector?.('textarea') || null
}

function updateSocketHexText(value) {
  const textarea = getSocketHexTextarea()
  const { text, cursor } = formatSocketHexInput(value, textarea?.selectionStart ?? String(value || '').length)
  form.value.socket_message_hex = text
  nextTick(() => {
    const target = getSocketHexTextarea()
    if (!target) return
    target.setSelectionRange(cursor, cursor)
  })
}

const sourceSelectionSummary = computed(() => {
  if (form.value.apply_to_all_sources) {
    return t('settings.notificationAllSourcesAutoHint')
  }
  const names = normalizedSelectedSourceIds.value.map(
    (id) => availableSources.value.find((source) => source.id === id)?.name || id,
  )
  if (!names.length) {
    return t('settings.notificationNoSourcesSelected')
  }
  if (names.length <= 2) {
    return names.join(', ')
  }
  return t('settings.notificationSpecificSources', { count: names.length })
})

const sourceSelectionStatus = computed(() => {
  if (form.value.apply_to_all_sources) {
    return t('settings.notificationAllSources')
  }
  if (!normalizedSelectedSourceIds.value.length) {
    return t('settings.notificationNoSourcesSelected')
  }
  return t('settings.notificationSpecificSources', { count: normalizedSelectedSourceIds.value.length })
})

async function loadInstances() {
  loading.value = true
  try {
    const [loadedInstances, loadedSources] = await Promise.all([
      notificationsApi.instances(),
      sourcesApi.list(),
    ])
    instances.value = loadedInstances
    availableSources.value = loadedSources
    try {
      const placeholderData = await settingsApi.emailTemplatePlaceholders()
      if (Array.isArray(placeholderData?.placeholders)) {
        placeholderItems.value = placeholderData.placeholders
      }
    } catch (error) {
      // Keep local placeholder fallback.
      void error
    }
  } catch (err) {
    ElMessage.error(t('settings.failedToLoad', { message: err.message }))
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingInstanceId.value = ''
  form.value = createDefaultNotificationInstanceForm()
  dialogVisible.value = true
}

function openEditDialog(item) {
  editingInstanceId.value = item.id
  form.value = serializeNotificationInstanceForEdit(item)
  dialogVisible.value = true
}

async function submit() {
  saving.value = true
  try {
    const payload = buildNotificationInstancePayload(form.value, t)
    if (editingInstanceId.value) {
      await notificationsApi.updateInstance(editingInstanceId.value, payload)
    } else {
      await notificationsApi.createInstance(payload)
    }
    dialogVisible.value = false
    await loadInstances()
    ElMessage.success(t('settings.settingsSaved'))
  } catch (err) {
    ElMessage.error(err.message || t('settings.failedToSave', { message: err.message }))
  } finally {
    saving.value = false
  }
}

async function testInstance(item) {
  if (!item?.id || testingInstanceId.value) return
  testingInstanceId.value = item.id
  try {
    const result = await notificationsApi.testInstance(item.id)
    ElMessage.success(t('settings.notificationTestSuccess', { status: result?.status || result?.message || 'SUCCESS' }))
  } catch (err) {
    ElMessage.error(t('settings.notificationTestFailed', { message: err.message }))
  } finally {
    testingInstanceId.value = ''
  }
}

async function toggleEnabled(item, enabled) {
  try {
    await notificationsApi.updateInstance(item.id, { enabled })
    item.enabled = Boolean(enabled)
    ElMessage.success(t('settings.settingsSaved'))
  } catch (err) {
    ElMessage.error(t('settings.failedToSave', { message: err.message }))
  }
}

onMounted(loadInstances)
</script>

<style scoped>
.notification-instances-section__head {
  margin-bottom: 14px;
}

.notification-instances-section h2 {
  color: #e5eeff;
  font-size: 16px;
  margin-bottom: 6px;
}

.notification-instances-section .info-tip {
  margin-top: 8px;
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.45;
}

.notification-instances-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 18px;
  padding: 12px 14px;
  border: 1px solid rgba(58, 74, 114, 0.52);
  border-radius: 12px;
  background: rgba(7, 12, 26, 0.34);
}

.notification-instances-toolbar__meta {
  color: #9fb1d1;
  font-size: 12px;
  letter-spacing: 0.02em;
}

.notification-instances-section__add {
  min-width: 104px;
  flex-shrink: 0;
  border-color: rgba(64, 158, 255, 0.38);
  background: rgba(64, 158, 255, 0.12);
  color: #b8d8ff;
}

.notification-instances-section__add:hover,
.notification-instances-section__add:focus {
  border-color: rgba(64, 158, 255, 0.72);
  background: rgba(64, 158, 255, 0.2);
  color: #eef6ff;
}

.notification-instance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.notification-instance-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 18px 14px;
  border-radius: 14px;
  border: 1px solid #3a4a72;
  background: #1e2640;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.notification-instance-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: #3b82f6;
}

.notification-instance-card--email::before {
  background: #22c55e;
}

.notification-instance-card--webhook::before {
  background: #f59e0b;
}

.notification-instance-card--socket::before {
  background: #06b6d4;
}

.notification-instance-card:hover {
  border-color: #5a78b8;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
  transform: translateY(-1px);
}

.notification-instance-card.is-disabled {
  opacity: 0.62;
}

.notification-instance-card__header,
.notification-instance-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.notification-instance-card__footer {
  margin-top: auto;
}

.notification-instance-card__title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.notification-instance-card__type-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: #ffffff;
  flex-shrink: 0;
}

.notification-instance-card__type-badge--email {
  background: #16a34a;
}

.notification-instance-card__type-badge--webhook {
  background: #d97706;
}

.notification-instance-card__type-badge--socket {
  background: #0891b2;
}

.notification-instance-card__name {
  color: #f1f5f9;
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.notification-instance-card__meta-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 12px;
  border-radius: 10px;
  background: rgba(7, 12, 26, 0.55);
  border: 1px solid rgba(71, 85, 105, 0.35);
}

.notification-instance-card__meta-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
}

.notification-instance-card__meta-row dt {
  color: #94a3b8;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.notification-instance-card__meta-row dd {
  color: #e2e8f0;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  margin: 0;
}

.notification-instance-card__code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  white-space: pre-wrap;
}

.notification-instance-card__body {
  max-height: 96px;
  overflow: auto;
}

.notification-instance-card__timestamp {
  color: #94a3b8;
  font-size: 12px;
}

.notification-instance-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.notification-instance-empty {
  padding: 32px;
  border-radius: 12px;
  border: 1px dashed rgba(99, 115, 146, 0.45);
  color: #94a3b8;
  text-align: center;
  grid-column: 1 / -1;
}

.notification-instance-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 18px;
  margin-bottom: 8px;
}

.notification-instance-form-grid + .notification-instance-form-grid {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px dashed rgba(99, 115, 146, 0.35);
}

.notification-instance-form-span-full {
  grid-column: 1 / -1;
}

.source-picker-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(71, 85, 105, 0.35);
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.76), rgba(10, 16, 30, 0.82));
}

.source-picker-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.source-picker-panel__eyebrow {
  color: #9fb1d1;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.source-picker-panel__summary {
  margin: 6px 0 0;
  color: #e2e8f0;
  font-size: 13px;
  line-height: 1.5;
}

.source-picker-panel__status {
  flex-shrink: 0;
  margin-top: 2px;
}

.source-picker-panel__select :deep(.el-select__wrapper) {
  min-height: 44px;
  background: rgba(8, 13, 26, 0.68);
  box-shadow: inset 0 0 0 1px rgba(71, 85, 105, 0.45);
}

.source-picker-panel__option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0;
}

.source-picker-panel__option-hint {
  color: #8ea0c2;
  font-size: 12px;
  line-height: 1.4;
}

.source-picker-panel__empty {
  color: #94a3b8;
  font-size: 12px;
}

:deep(.notification-instance-dialog) {
  border: 1px solid rgba(71, 96, 148, 0.72);
  border-radius: 18px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(64, 158, 255, 0.16), transparent 32%),
    linear-gradient(180deg, rgba(16, 24, 44, 0.98), rgba(11, 18, 34, 0.98));
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
}

:deep(.notification-instance-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 18px 22px 14px;
  border-bottom: 1px solid rgba(87, 107, 152, 0.35);
}

:deep(.notification-instance-dialog .el-dialog__title) {
  color: #eef4ff;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

:deep(.notification-instance-dialog .el-dialog__headerbtn .el-dialog__close) {
  color: #9db4da;
}

:deep(.notification-instance-dialog .el-dialog__body) {
  padding: 18px 22px 10px;
  color: #d7e2f3;
}

:deep(.notification-instance-dialog .el-dialog__footer) {
  padding: 12px 22px 20px;
  border-top: 1px solid rgba(87, 107, 152, 0.28);
  background: rgba(7, 12, 26, 0.36);
}

:deep(.notification-instance-dialog .el-form-item__label) {
  color: #b8c8e6;
  font-weight: 600;
}

:deep(.notification-instance-dialog .el-input__wrapper),
:deep(.notification-instance-dialog .el-textarea__inner),
:deep(.notification-instance-dialog .el-select__wrapper) {
  background: rgba(8, 13, 26, 0.82);
  box-shadow: inset 0 0 0 1px rgba(83, 102, 146, 0.52);
}

:deep(.notification-instance-dialog .el-input__inner),
:deep(.notification-instance-dialog .el-textarea__inner) {
  color: #edf3ff;
}

:deep(.notification-instance-dialog .el-input__inner::placeholder),
:deep(.notification-instance-dialog .el-textarea__inner::placeholder) {
  color: #7285a9;
}

:deep(.notification-instance-dialog .el-switch__label) {
  color: #c6d5f0;
}

:deep(.notification-instance-dialog .el-button:not(.el-button--primary)) {
  border-color: rgba(86, 106, 149, 0.62);
  background: rgba(12, 18, 34, 0.72);
  color: #dbe8ff;
}

:deep(.notification-instance-dialog .el-button:not(.el-button--primary):hover),
:deep(.notification-instance-dialog .el-button:not(.el-button--primary):focus) {
  border-color: rgba(113, 139, 193, 0.82);
  background: rgba(24, 36, 66, 0.92);
  color: #f3f7ff;
}

:deep(.notification-instance-dialog .el-button--primary) {
  border-color: rgba(64, 158, 255, 0.72);
  background: linear-gradient(135deg, rgba(47, 132, 255, 0.96), rgba(30, 97, 214, 0.96));
  color: #f7fbff;
}

:deep(.notification-instance-dialog .el-button--primary:hover),
:deep(.notification-instance-dialog .el-button--primary:focus) {
  border-color: rgba(103, 181, 255, 0.9);
  background: linear-gradient(135deg, rgba(77, 156, 255, 0.98), rgba(39, 112, 232, 0.98));
}

@media (max-width: 780px) {
  .notification-instance-form-grid {
    grid-template-columns: 1fr;
  }

  .source-picker-panel__head {
    flex-direction: column;
  }
}
</style>
