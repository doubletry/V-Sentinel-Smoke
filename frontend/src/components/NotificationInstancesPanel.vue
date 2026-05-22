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
        {{ t('settings.notificationTypeEmail') }} / {{ t('settings.notificationTypeWebhook') }}
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
              {{ item.type === 'email' ? t('settings.notificationTypeEmail') : t('settings.notificationTypeWebhook') }}
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
          <div v-if="item.type === 'email'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationTemplateSubject') }}</dt>
            <dd class="notification-instance-card__code">{{ item.config?.subject_template || defaultSubjectTemplate }}</dd>
          </div>
          <div v-if="item.type === 'email'" class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationTemplateBody') }}</dt>
            <dd class="notification-instance-card__code notification-instance-card__body">{{ item.config?.body_template || defaultBodyTemplate }}</dd>
          </div>
          <div v-else class="notification-instance-card__meta-row">
            <dt>{{ t('settings.notificationWebhookPayload') }}</dt>
            <dd class="notification-instance-card__code notification-instance-card__body">
              {{ payloadSummary(item) }}
            </dd>
          </div>
        </dl>

        <footer class="notification-instance-card__footer">
          <span class="notification-instance-card__timestamp">{{ formatTimestamp(item.created_at) }}</span>
          <el-button size="small" plain @click="openEditDialog(item)">
            {{ t('common.edit') }}
          </el-button>
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
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.notificationEnabled')">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item :label="t('settings.notificationCooldownSeconds')">
            <el-input v-model="form.cooldown_seconds" placeholder="300" />
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

        <div v-else class="notification-instance-form-grid">
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
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { notificationsApi, settingsApi } from '../api/index.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { formatTimeWithTimezone } from '../utils/time.js'

const { t } = useI18n()
const appSettingsStore = useAppSettingsStore()
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingInstanceId = ref('')
const instances = ref([])
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
const defaultSubjectTemplate = '[{site_title}] {event_label} alert from {source_name}'
const defaultBodyTemplate = 'Event: {event_label}\nTime: {local_time} ({timezone})\nVideo source: {source_name} ({source_id})\nMessage: {message}'
const defaultWebhookPayloadTemplate = {
  site_title: '{site_title}',
  event_type: '{event_type}',
  event_label: '{event_label}',
  message: '{message}',
  timestamp: '{timestamp}',
  local_time: '{local_time}',
  timezone: '{timezone}',
  source: {
    id: '{source_id}',
    name: '{source_name}',
    route_path: '{source_route_path}',
    remark: '{source_remark}',
  },
  detection: {
    labels: '{labels}',
    confidence: '{confidence}',
    confidence_percent: '{confidence_percent}',
  },
  images: {
    original_url: '{original_image_url}',
    detected_url: '{detected_image_url}',
  },
}

const form = ref(createDefaultForm())

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

function createDefaultForm(type = 'email') {
  return {
    name: '',
    type,
    enabled: true,
    smtp_host: '',
    smtp_port: '587',
    use_tls: true,
    from_address: '',
    smtp_password: '',
    to_addresses: '',
    cc_addresses: '',
    url: '',
    method: 'POST',
    headers_text: '{}',
    webhook_payload_text: JSON.stringify(defaultWebhookPayloadTemplate, null, 2),
    cooldown_seconds: '300',
    subject_template: defaultSubjectTemplate,
    body_template: defaultBodyTemplate,
  }
}

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
  return `${item.config?.method || 'POST'} · ${item.config?.url || '—'}`
}

function payloadSummary(item) {
  try {
    return JSON.stringify(item.config?.payload_template || defaultWebhookPayloadTemplate, null, 2)
  } catch {
    return '{}'
  }
}

function normalizeAddressField(value) {
  return Array.isArray(value) ? value.join(',') : String(value || '')
}

async function loadInstances() {
  loading.value = true
  try {
    instances.value = await notificationsApi.instances()
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
  form.value = createDefaultForm()
  dialogVisible.value = true
}

function openEditDialog(item) {
  let headersText = '{}'
  try {
    headersText = JSON.stringify(item.config?.headers || {}, null, 2)
  } catch {
    headersText = '{}'
  }
  editingInstanceId.value = item.id
  form.value = {
    name: item.name || '',
    type: item.type || 'email',
    enabled: Boolean(item.enabled),
    smtp_host: item.config?.smtp_host || '',
    smtp_port: String(item.config?.smtp_port || '587'),
    use_tls: Boolean(item.config?.use_tls ?? true),
    from_address: item.config?.from_address || '',
    smtp_password: item.config?.smtp_password || '',
    to_addresses: normalizeAddressField(item.config?.to_addresses),
    cc_addresses: normalizeAddressField(item.config?.cc_addresses),
    url: item.config?.url || '',
    method: item.config?.method || 'POST',
    headers_text: headersText,
    webhook_payload_text: JSON.stringify(item.config?.payload_template || defaultWebhookPayloadTemplate, null, 2),
    cooldown_seconds: String(item.config?.cooldown_seconds || '300'),
    subject_template: item.config?.subject_template || defaultSubjectTemplate,
    body_template: item.config?.body_template || defaultBodyTemplate,
  }
  dialogVisible.value = true
}

function buildPayload() {
  const payload = {
    name: form.value.name.trim(),
    type: form.value.type,
    enabled: Boolean(form.value.enabled),
    config: {
      cooldown_seconds: String(form.value.cooldown_seconds || '300').trim(),
    },
  }
  if (!payload.name) {
    throw new Error(t('settings.notificationInstanceNameRequired'))
  }
  if (payload.type === 'email') {
    payload.config = {
      ...payload.config,
      subject_template: form.value.subject_template || defaultSubjectTemplate,
      body_template: form.value.body_template || defaultBodyTemplate,
      smtp_host: form.value.smtp_host.trim(),
      smtp_port: String(form.value.smtp_port || '587').trim(),
      use_tls: Boolean(form.value.use_tls),
      from_address: form.value.from_address.trim(),
      smtp_username: form.value.from_address.trim(),
      smtp_password: form.value.smtp_password,
      to_addresses: form.value.to_addresses.trim(),
      cc_addresses: form.value.cc_addresses.trim(),
    }
  } else {
    let headers = {}
    try {
      headers = JSON.parse(form.value.headers_text || '{}')
    } catch {
      throw new Error(t('settings.notificationWebhookHeadersInvalid'))
    }
    let payloadTemplate = {}
    try {
      payloadTemplate = JSON.parse(form.value.webhook_payload_text || '{}')
    } catch {
      throw new Error(t('settings.notificationWebhookPayloadInvalid'))
    }
    if (Array.isArray(payloadTemplate) || typeof payloadTemplate !== 'object') {
      throw new Error(t('settings.notificationWebhookPayloadInvalid'))
    }
    payload.config = {
      ...payload.config,
      url: form.value.url.trim(),
      method: String(form.value.method || 'POST').toUpperCase(),
      headers,
      payload_template: payloadTemplate,
    }
  }
  return payload
}

async function submit() {
  saving.value = true
  try {
    const payload = buildPayload()
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

@media (max-width: 780px) {
  .notification-instance-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
