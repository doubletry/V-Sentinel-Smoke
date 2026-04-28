<template>
  <div class="settings-page">
    <div class="settings-shell">
      <div class="settings-head">
        <div class="title-line">
          <el-icon :size="20"><Setting /></el-icon>
          <h1>{{ t('settings.title') }}</h1>
        </div>
        <p>{{ t('settings.subtitle') }}</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        class="settings-form"
        label-width="210px"
        label-position="right"
        v-loading="loading"
      >
        <section class="settings-section">
          <h2>{{ t('settings.interface') }}</h2>
          <el-form-item :label="t('settings.systemLanguage')">
            <el-select v-model="form.ui_language" style="width: 100%">
              <el-option
                v-for="option in languageOptions"
                :key="option.value"
                :label="t(option.labelKey)"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.timezone')">
            <el-select v-model="form.timezone" style="width: 100%" filterable allow-create default-first-option>
              <el-option
                v-for="option in timezoneOptions"
                :key="option"
                :label="option"
                :value="option"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.siteTitle')">
            <el-input v-model="form.site_title" :placeholder="t('settings.siteTitle')" />
          </el-form-item>
          <el-form-item :label="t('settings.siteDescription')">
            <el-input
              v-model="form.site_description"
              :placeholder="t('settings.siteDescription')"
            />
          </el-form-item>
          <el-form-item :label="t('settings.faviconUrl')">
            <div class="icon-upload-group">
              <el-avatar :size="28" shape="square" :src="form.favicon_url">
                <el-icon><VideoCamera /></el-icon>
              </el-avatar>
              <el-upload
                class="site-icon-upload"
                :show-file-list="false"
                :auto-upload="false"
                accept=".ico,.png,.jpg,.jpeg,.svg,.webp"
                :on-change="onSiteIconChange"
              >
                <el-button size="small">{{ t('settings.uploadSiteIcon') }}</el-button>
              </el-upload>
              <el-button size="small" @click="resetSiteIcon">{{ t('settings.resetSiteIcon') }}</el-button>
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.iconPath')">
            <el-input v-model="form.favicon_url" placeholder="/favicon.ico" />
          </el-form-item>
          <el-form-item :label="t('settings.roiTagCandidates')">
            <div class="roi-tags-editor">
              <el-tag
                v-for="tag in roiTagList"
                :key="tag"
                closable
                type="info"
                effect="dark"
                class="roi-tag-item"
                @close="removeRoiTag(tag)"
              >
                {{ tag }}
              </el-tag>
              <span v-if="!roiTagList.length" class="roi-tag-empty">
                {{ t('settings.noRoiTags') }}
              </span>
            </div>
            <div class="roi-tag-input-row">
              <el-input
                v-model="roiTagInput"
                :placeholder="t('settings.roiTagInputPlaceholder')"
                @keyup.enter="addRoiTag"
              />
              <el-button type="primary" @click="addRoiTag">
                {{ t('settings.addRoiTag') }}
              </el-button>
            </div>
            <p class="roi-tag-hint">{{ t('settings.roiTagHint') }}</p>
          </el-form-item>
        </section>

        <section class="settings-section">
          <h2>{{ t('settings.backendService') }}</h2>
          <el-form-item :label="t('settings.processorPlugin')">
            <div class="field-stack">
              <el-select
                v-model="form.processor_plugin"
                style="width: 100%"
                filterable
                allow-create
                default-first-option
              >
                <el-option
                  v-for="option in localizedProcessorPluginOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <p class="form-hint">{{ t('settings.processorPluginHint') }}</p>
            </div>
          </el-form-item>
          <div class="service-control-row">
            <el-tag :type="sourceStore.runningCount > 0 ? 'success' : 'info'" effect="dark">
              {{
                sourceStore.runningCount > 0
                  ? t('settings.runningStatus', { count: sourceStore.runningCount })
                  : t('settings.stoppedStatus')
              }}
            </el-tag>
            <div class="service-buttons">
              <el-button
                type="success"
                :loading="serviceAction === 'start'"
                @click="startAllServices"
              >
                {{ t('settings.startAll') }}
              </el-button>
              <el-button
                type="warning"
                :loading="serviceAction === 'stop'"
                @click="stopAllServices"
              >
                {{ t('settings.stopAll') }}
              </el-button>
            </div>
          </div>
          <p class="service-tip">{{ t('settings.backendServiceTip') }}</p>
        </section>

        <section class="settings-section">
          <h2>{{ t('settings.vengineServices') }}</h2>
          <el-form-item :label="t('settings.vengineHost')">
            <el-input v-model="form.vengine_host" placeholder="localhost" />
          </el-form-item>
          <el-form-item :label="t('settings.detectionPort')">
            <div class="port-switch-row">
              <el-input v-model="form.detection_port" placeholder="50051" :disabled="form.detection_enabled !== 'true'" />
              <el-switch v-model="form.detection_enabled" active-value="true" inactive-value="false" />
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.classificationPort')">
            <div class="port-switch-row">
              <el-input v-model="form.classification_port" placeholder="50052" :disabled="form.classification_enabled !== 'true'" />
              <el-switch v-model="form.classification_enabled" active-value="true" inactive-value="false" />
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.actionPort')">
            <div class="port-switch-row">
              <el-input v-model="form.action_port" placeholder="50053" :disabled="form.action_enabled !== 'true'" />
              <el-switch v-model="form.action_enabled" active-value="true" inactive-value="false" />
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.ocrPort')">
            <div class="port-switch-row">
              <el-input v-model="form.ocr_port" placeholder="50054" :disabled="form.ocr_enabled !== 'true'" />
              <el-switch v-model="form.ocr_enabled" active-value="true" inactive-value="false" />
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.uploadPort')">
            <div class="port-switch-row">
              <el-input v-model="form.upload_port" placeholder="50050" :disabled="form.upload_enabled !== 'true'" />
              <el-switch v-model="form.upload_enabled" active-value="true" inactive-value="false" />
            </div>
          </el-form-item>
          <p class="service-tip">{{ t('settings.serviceToggleTip') }}</p>
        </section>


        <section class="settings-section">
          <h2>{{ t('settings.smokeScene') }}</h2>
          <el-form-item :label="t('settings.smokeDetectionModelName')">
            <el-input v-model="form.smoke_detection_model_name" placeholder="smoke-fire-detection" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeDetectionModelVersion')">
            <el-input v-model="form.smoke_detection_model_version" :placeholder="t('settings.defaultVersionPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeDetectionConfidence')">
            <el-input v-model="form.smoke_detection_confidence" placeholder="0.35" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeDetectionNms')">
            <el-input v-model="form.smoke_detection_nms" placeholder="0.7" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeTemporalConfirmFrames')">
            <el-input v-model="form.smoke_temporal_confirm_frames" placeholder="3" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeTemporalConfirmWindow')">
            <el-input v-model="form.smoke_temporal_confirm_window" placeholder="2.0" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeMaxMissFrames')">
            <el-input v-model="form.smoke_max_miss_frames" placeholder="5" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeAlarmHoldTime')">
            <el-input v-model="form.smoke_alarm_hold_time" placeholder="3.0" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeAppearanceFilter')">
            <el-switch v-model="form.smoke_enable_appearance_filter" active-value="true" inactive-value="false" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeAdvancedThresholds')">
            <div class="smoke-threshold-grid">
              <el-input v-model="form.smoke_min_confidence_smoke" :placeholder="t('settings.smokeMinConfidenceSmoke')" />
              <el-input v-model="form.smoke_min_confidence_fire" :placeholder="t('settings.smokeMinConfidenceFire')" />
              <el-input v-model="form.smoke_min_bbox_area_ratio" :placeholder="t('settings.smokeMinBboxAreaRatio')" />
              <el-input v-model="form.smoke_max_bbox_area_ratio" :placeholder="t('settings.smokeMaxBboxAreaRatio')" />
              <el-input v-model="form.smoke_min_aspect_ratio" :placeholder="t('settings.smokeMinAspectRatio')" />
              <el-input v-model="form.smoke_max_aspect_ratio" :placeholder="t('settings.smokeMaxAspectRatio')" />
              <el-input v-model="form.smoke_motion_blur_max_speed" :placeholder="t('settings.smokeMotionBlurMaxSpeed')" />
              <el-input v-model="form.smoke_motion_blur_min_confidence" :placeholder="t('settings.smokeMotionBlurMinConfidence')" />
              <el-input v-model="form.smoke_appearance_min_score" :placeholder="t('settings.smokeAppearanceMinScore')" />
              <el-input v-model="form.smoke_appearance_min_history" :placeholder="t('settings.smokeAppearanceMinHistory')" />
              <el-input v-model="form.smoke_iou_threshold" :placeholder="t('settings.smokeIouThreshold')" />
            </div>
          </el-form-item>
        </section>

        <section class="settings-section">
          <h2>{{ t('settings.mediamtx') }}</h2>
          <el-form-item :label="t('settings.rtspAddress')">
            <el-input v-model="form.mediamtx_rtsp_addr" placeholder="rtsp://localhost:8554" />
          </el-form-item>
          <el-form-item :label="t('settings.webrtcAddress')">
            <el-input v-model="form.mediamtx_webrtc_addr" placeholder="http://localhost:8889" />
          </el-form-item>
        </section>

        <section class="settings-section">
          <h2>{{ t('settings.emailNotifications') }}</h2>
          <el-form-item :label="t('settings.emailFromAddress')">
            <el-input
              v-model="form.email_from_address"
              placeholder="sender@example.com"
            />
          </el-form-item>
          <el-form-item :label="t('settings.emailGrpcPort')">
            <el-input
              v-model="form.email_port"
              placeholder="50055"
            />
          </el-form-item>
          <el-form-item :label="t('settings.emailFromAuthCode')">
            <el-input
              v-model="form.email_from_auth_code"
              type="password"
              show-password
              placeholder="授权码 / 密码"
            />
          </el-form-item>
          <el-form-item :label="t('settings.emailToAddresses')">
            <div class="field-stack">
              <el-input
                v-model="form.email_to_addresses"
                type="textarea"
                :rows="2"
                placeholder="a@example.com,b@example.com"
              />
              <p class="form-hint">{{ t('settings.emailAddressesHint') }}</p>
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.emailCcAddresses')">
            <el-input
              v-model="form.email_cc_addresses"
              type="textarea"
              :rows="2"
              placeholder="cc1@example.com,cc2@example.com"
            />
          </el-form-item>
          <el-form-item :label="t('settings.emailEventEnabled')">
            <el-switch v-model="form.email_event_enabled" active-value="true" inactive-value="false" />
          </el-form-item>
          <el-form-item :label="t('settings.smokeEmailCooldownSeconds')">
            <el-input v-model="form.smoke_email_cooldown_seconds" placeholder="300" />
          </el-form-item>
          <el-form-item :label="t('settings.emailEventSubjectTemplate')">
            <el-input v-model="form.email_event_subject_template" />
          </el-form-item>
          <el-form-item :label="t('settings.emailEventBodyTemplate')">
            <div class="field-stack">
              <el-input
                v-model="form.email_event_body_template"
                type="textarea"
                :rows="8"
              />
              <p class="form-hint">{{ t('settings.emailTemplateHint') }}</p>
              <div class="placeholder-tags">
                <el-tag v-for="item in emailTemplatePlaceholders" :key="item" size="small" effect="dark">
                  {{ `{${item}}` }}
                </el-tag>
              </div>
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.messageRetentionDays')">
            <el-select v-model="form.message_retention_days" style="width: 100%">
              <el-option
                v-for="day in retentionDayOptions"
                :key="day"
                :label="t('settings.messageRetentionDaysOption', { days: day })"
                :value="String(day)"
              />
            </el-select>
          </el-form-item>
        </section>

        <section class="settings-section">
          <h2>{{ t('settings.threadPools') }}</h2>
          <el-form-item :label="t('settings.maxPullWorkers')">
            <el-input v-model="form.max_pull_workers" placeholder="20" />
          </el-form-item>
          <el-form-item :label="t('settings.maxPushWorkers')">
            <el-input v-model="form.max_push_workers" placeholder="10" />
          </el-form-item>
          <el-form-item :label="t('settings.maxCpuWorkers')">
            <el-input v-model="form.max_cpu_workers" placeholder="16" />
          </el-form-item>
        </section>

        <div class="settings-actions">
          <el-button @click="reload">{{ t('common.reset') }}</el-button>
          <el-button @click="testEmailConfig" :loading="testingEmail">
            {{ t('settings.testEmail') }}
          </el-button>
          <el-button type="primary" @click="save" :loading="saving">
            {{ t('settings.saveSettings') }}
          </el-button>
        </div>
      </el-form>

    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { localeOptions } from '../i18n/index.js'
import { processorApi, settingsApi } from '../api/index.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useSourceStore } from '../stores/source.js'

const { t, locale } = useI18n()
const appSettingsStore = useAppSettingsStore()
const sourceStore = useSourceStore()
const languageOptions = localeOptions
const processorPluginOptions = ref([])
const retentionDayOptions = [7, 15, 21, 30]
const emailTemplatePlaceholders = ref(['site_title', 'local_time', 'timezone', 'source_name', 'source_id', 'event_type', 'event_label', 'labels', 'confidence_percent', 'detection_count', 'frame_id', 'active_tracks'])
const timezoneOptions = ['Asia/Shanghai', 'UTC', 'Asia/Tokyo', 'Europe/London', 'America/New_York']

const loading = ref(false)
const saving = ref(false)
const testingEmail = ref(false)
const serviceAction = ref('')
const roiTagInput = ref('')
const roiTagList = ref([])
const form = ref({
  ui_language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  processor_plugin: 'smoke',
  site_title: '',
  site_description: '',
  favicon_url: '/favicon.ico',
  roi_tag_options: '[]',
  vengine_host: '',
  detection_port: '',
  classification_port: '',
  action_port: '',
  ocr_port: '',
  upload_port: '',
  detection_enabled: 'true',
  classification_enabled: 'false',
  action_enabled: 'false',
  ocr_enabled: 'false',
  upload_enabled: 'false',
  mediamtx_rtsp_addr: '',
  mediamtx_webrtc_addr: '',
  email_from_address: '',
  email_from_auth_code: '',
  email_to_addresses: '',
  email_cc_addresses: '',
  email_port: '50055',
  email_event_enabled: 'true',
  email_timed_enabled: 'false',
  email_event_subject_template: '[{site_title}] {event_label} alert from {source_name}',
  email_event_body_template: 'Event: {event_label}\nTime: {local_time} ({timezone})\nVideo source: {source_name} ({source_id})\nLabels: {labels}\nHighest confidence: {confidence_percent}\nDetection count: {detection_count}\nFrame ID: {frame_id}\nActive tracks: {active_tracks}',
  smoke_detection_model_name: 'smoke-fire-detection',
  smoke_detection_model_version: '',
  smoke_detection_confidence: '0.35',
  smoke_detection_nms: '0.7',
  smoke_min_confidence_smoke: '0.35',
  smoke_min_confidence_fire: '0.40',
  smoke_temporal_confirm_frames: '3',
  smoke_temporal_confirm_window: '2.0',
  smoke_max_miss_frames: '5',
  smoke_min_bbox_area_ratio: '0.0005',
  smoke_max_bbox_area_ratio: '0.60',
  smoke_min_aspect_ratio: '0.2',
  smoke_max_aspect_ratio: '8.0',
  smoke_motion_blur_max_speed: '100.0',
  smoke_motion_blur_min_confidence: '0.65',
  smoke_enable_appearance_filter: 'true',
  smoke_appearance_min_score: '0.42',
  smoke_appearance_min_history: '2',
  smoke_iou_threshold: '0.3',
  smoke_alarm_hold_time: '3.0',
  smoke_email_cooldown_seconds: '300',
  message_retention_days: '7',
  max_pull_workers: '',
  max_push_workers: '',
  max_cpu_workers: '',
})

const localizedProcessorPluginOptions = computed(() =>
  processorPluginOptions.value.map((option) => ({
    ...option,
    label: locale.value === 'en-US' ? option.label_en : option.label_zh,
  }))
)

function parseRoiTagOptions(raw) {
  if (Array.isArray(raw)) {
    return Array.from(new Set(raw.map((item) => String(item || '').trim()).filter(Boolean)))
  }

  const text = String(raw || '').trim()
  if (!text) return []

  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) {
      return Array.from(
        new Set(parsed.map((item) => String(item || '').trim()).filter(Boolean))
      )
    }
  } catch (_) {
    // Fallback for legacy comma-separated values.
  }

  return Array.from(new Set(text.split(',').map((item) => item.trim()).filter(Boolean)))
}

function syncRoiTagOptionsToForm() {
  form.value.roi_tag_options = JSON.stringify(roiTagList.value)
}

function addRoiTag() {
  const tag = roiTagInput.value.trim()
  if (!tag) return

  if (roiTagList.value.includes(tag)) {
    ElMessage.warning(t('settings.roiTagExists'))
    return
  }

  roiTagList.value.push(tag)
  roiTagInput.value = ''
  syncRoiTagOptionsToForm()
}

function removeRoiTag(tag) {
  roiTagList.value = roiTagList.value.filter((item) => item !== tag)
  syncRoiTagOptionsToForm()
}

async function reload() {
  loading.value = true
  try {
    const [data, plugins] = await Promise.all([
      appSettingsStore.fetchSettings(true),
      processorApi.plugins(),
    ])
    Object.assign(form.value, data)
    processorPluginOptions.value = Array.isArray(plugins) ? plugins : []
    try {
      const placeholderData = await settingsApi.emailTemplatePlaceholders()
      if (Array.isArray(placeholderData?.placeholders)) {
        emailTemplatePlaceholders.value = placeholderData.placeholders
      }
    } catch (_) {
      // Keep built-in placeholder list when the backend endpoint is unavailable.
    }
    roiTagList.value = parseRoiTagOptions(form.value.roi_tag_options)
    syncRoiTagOptionsToForm()
  } catch (err) {
    ElMessage.error(t('settings.failedToLoad', { message: err.message }))
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  const previousPlugin = appSettingsStore.settings?.processor_plugin || 'smoke'
  try {
    syncRoiTagOptionsToForm()
    const pluginChanged = previousPlugin !== form.value.processor_plugin
    let runningSourceIds = []
    if (pluginChanged) {
      await sourceStore.syncProcessorStatus()
      runningSourceIds = sourceStore.getRunningSourceIdsSnapshot()
    }

    const data = await appSettingsStore.updateSettings(form.value)
    Object.assign(form.value, data)
    roiTagList.value = parseRoiTagOptions(form.value.roi_tag_options)
    appSettingsStore.applyLanguage(form.value.ui_language)

    if (!pluginChanged) {
      ElMessage.success(t('settings.settingsSaved'))
      return
    }

    if (!runningSourceIds.length) {
      ElMessage.success(t('settings.settingsSavedRestartRequired'))
      return
    }

    const restartResult = await sourceStore.restartProcessing(runningSourceIds)
    if (restartResult.status === 'partial') {
      ElMessage.warning(
        t('settings.settingsSavedRestartPartial', {
          restarted: restartResult.restarted,
          failed: restartResult.failed.length,
        })
      )
      return
    }

    ElMessage.success(
      t('settings.settingsSavedRestarted', { count: restartResult.restarted })
    )
  } catch (err) {
    ElMessage.error(t('settings.failedToSave', { message: err.message }))
  } finally {
    saving.value = false
  }
}

async function testEmailConfig() {
  testingEmail.value = true
  try {
    const payload = {
      vengine_host: form.value.vengine_host,
      email_port: form.value.email_port,
      email_from_address: form.value.email_from_address,
      email_from_auth_code: form.value.email_from_auth_code,
      email_to_addresses: form.value.email_to_addresses,
      email_cc_addresses: form.value.email_cc_addresses,
    }
    const result = await appSettingsStore.testEmail(payload)
    ElMessage.success(
      t('settings.testEmailSuccess', {
        status: result.status || 'SUCCESS',
      })
    )
  } catch (err) {
    ElMessage.error(t('settings.testEmailFailed', { message: err.message }))
  } finally {
    testingEmail.value = false
  }
}

function onSiteIconChange(uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return

  const maxBytes = 1024 * 1024
  if (raw.size > maxBytes) {
    ElMessage.warning(t('settings.iconTooLarge'))
    return
  }

  const reader = new FileReader()
  reader.onload = () => {
    if (typeof reader.result === 'string') {
      form.value.favicon_url = reader.result
    }
  }
  reader.readAsDataURL(raw)
}

function resetSiteIcon() {
  form.value.favicon_url = '/favicon.ico'
}

async function startAllServices() {
  serviceAction.value = 'start'
  try {
    await sourceStore.startAllProcessing()
  } finally {
    serviceAction.value = ''
  }
}

async function stopAllServices() {
  serviceAction.value = 'stop'
  try {
    await sourceStore.stopAllProcessing()
  } finally {
    serviceAction.value = ''
  }
}

onMounted(async () => {
  await Promise.all([
    reload(),
    sourceStore.syncProcessorStatus(),
  ])
})
</script>

<style scoped>
.settings-page {
  height: 100%;
  overflow-y: auto;
  padding: 20px 24px 28px;
  background:
    radial-gradient(circle at 0% 0%, rgba(64, 158, 255, 0.13), transparent 42%),
    radial-gradient(circle at 100% 100%, rgba(0, 178, 169, 0.12), transparent 40%),
    #0d0d1a;
}

.settings-shell {
  max-width: 980px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-head {
  padding: 4px 4px 0;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-line h1 {
  font-size: 22px;
  font-weight: 700;
  color: #e9f0ff;
}

.settings-head p {
  margin-top: 6px;
  color: #9ba8be;
  font-size: 13px;
}

.settings-form {
  background: rgba(16, 21, 37, 0.92);
  border: 1px solid #26314d;
  border-radius: 14px;
  padding: 16px;
}

.settings-section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid #30364d;
  border-radius: 12px;
  padding: 16px 12px 6px;
  margin-bottom: 14px;
}

.settings-section h2 {
  font-size: 14px;
  color: #9ab2df;
  margin-bottom: 10px;
}

.icon-upload-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.roi-tags-editor {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.roi-tag-item {
  margin: 0;
}

.roi-tag-empty {
  color: #7f8bad;
  font-size: 12px;
}

.roi-tag-input-row {
  display: flex;
  gap: 8px;
}

.placeholder-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.smoke-threshold-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  width: 100%;
}

.roi-tag-hint {
  margin-top: 6px;
  color: #8f9fbe;
  font-size: 12px;
}

.service-control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.service-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.service-tip {
  margin-top: 8px;
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.45;
}


.field-stack {
  width: 100%;
}

.form-hint {
  margin-top: 6px;
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.45;
}

.port-switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.port-switch-row .el-input {
  flex: 1;
}

.settings-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  position: sticky;
  bottom: 0;
  padding-top: 10px;
  padding-bottom: 4px;
  background: linear-gradient(to bottom, rgba(16, 21, 37, 0), rgba(16, 21, 37, 0.96) 26%);
}

:deep(.el-form-item__label) {
  color: #aab7d2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 768px) {
  .settings-page {
    padding: 12px 12px 20px;
  }

  .settings-form {
    padding: 12px;
  }

  .title-line h1 {
    font-size: 18px;
  }

  :deep(.el-form-item) {
    margin-bottom: 14px;
  }

  :deep(.el-form-item__label) {
    width: 100% !important;
    justify-content: flex-start;
    margin-bottom: 4px;
    line-height: 1.4;
  }

  :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }

  .roi-tag-input-row {
    flex-wrap: wrap;
  }
}
</style>
