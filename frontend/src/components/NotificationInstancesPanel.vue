<template>
  <section class="settings-section section-card">
    <div class="section-card__head">
      <div>
        <h2>{{ t('settings.notificationInstancesSection') }}</h2>
        <p class="info-tip">{{ t('settings.notificationInstancesHint') }}</p>
      </div>
      <div class="section-card__actions">
        <el-button type="primary" @click="openCreateDialog">
          {{ t('settings.addNotificationInstance') }}
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="notification-instance-grid">
      <article
        v-for="item in instances"
        :key="item.id"
        class="notification-instance-card"
      >
        <div class="notification-instance-card__header">
          <div class="notification-instance-card__title-wrap">
            <h3>{{ item.name }}</h3>
            <el-tag size="small" effect="dark" :type="item.type === 'email' ? 'success' : 'warning'">
              {{ item.type === 'email' ? t('settings.notificationTypeEmail') : t('settings.notificationTypeWebhook') }}
            </el-tag>
          </div>
          <el-switch
            :model-value="item.enabled"
            @change="toggleEnabled(item, $event)"
          />
        </div>

        <div class="notification-instance-card__meta">
          <div class="notification-instance-card__meta-label">{{ t('settings.notificationEndpoint') }}</div>
          <div class="notification-instance-card__meta-value">{{ endpointSummary(item) }}</div>
        </div>

        <div class="notification-instance-card__meta">
          <div class="notification-instance-card__meta-label">{{ t('settings.notificationTemplateSubject') }}</div>
          <div class="notification-instance-card__meta-value notification-instance-card__code">
            {{ item.config?.subject_template || defaultSubjectTemplate }}
          </div>
        </div>

        <div class="notification-instance-card__meta">
          <div class="notification-instance-card__meta-label">{{ t('settings.notificationTemplateBody') }}</div>
          <div class="notification-instance-card__meta-value notification-instance-card__code notification-instance-card__body">
            {{ item.config?.body_template || defaultBodyTemplate }}
          </div>
        </div>

        <div class="notification-instance-card__footer">
          <span class="notification-instance-card__timestamp">{{ formatTimestamp(item.created_at) }}</span>
          <el-button size="small" plain @click="openEditDialog(item)">
            {{ t('common.edit') }}
          </el-button>
        </div>
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
        </div>

        <div class="notification-instance-form-grid">
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
    } catch (_) {
      // Keep local placeholder fallback.
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
      subject_template: form.value.subject_template || defaultSubjectTemplate,
      body_template: form.value.body_template || defaultBodyTemplate,
    },
  }
  if (!payload.name) {
    throw new Error(t('settings.notificationInstanceNameRequired'))
  }
  if (payload.type === 'email') {
    payload.config = {
      ...payload.config,
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
    payload.config = {
      ...payload.config,
      url: form.value.url.trim(),
      method: String(form.value.method || 'POST').toUpperCase(),
      headers,
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
.notification-instance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.notification-instance-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(71, 85, 105, 0.52);
  background: linear-gradient(180deg, rgba(14, 21, 40, 0.9), rgba(11, 17, 31, 0.72));
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.18);
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
}

.notification-instance-card__title-wrap h3 {
  color: #eff6ff;
  font-size: 16px;
  font-weight: 700;
}

.notification-instance-card__meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.notification-instance-card__meta-label {
  color: #8ea3c8;
  font-size: 12px;
  font-weight: 700;
}

.notification-instance-card__meta-value {
  color: #dbeafe;
  font-size: 13px;
  line-height: 1.55;
  word-break: break-word;
}

.notification-instance-card__code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  white-space: pre-wrap;
}

.notification-instance-card__body {
  max-height: 132px;
  overflow: auto;
}

.notification-instance-card__timestamp {
  color: #8ea3c8;
  font-size: 12px;
  font-weight: 600;
}

.notification-instance-empty {
  padding: 28px;
  border-radius: 14px;
  border: 1px dashed rgba(99, 115, 146, 0.45);
  color: #8ea3c8;
  text-align: center;
}

.notification-instance-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 16px;
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
