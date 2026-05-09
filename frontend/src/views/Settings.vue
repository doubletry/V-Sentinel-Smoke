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

      <SettingsSectionNav :sections="settingsNavSections" @jump="scrollToSection" />

      <el-form
        :model="form"
        class="settings-form"
        label-width="210px"
        label-position="right"
        v-loading="loading"
      >
        <SettingsInterfaceSection
          :form="form"
          :language-options="languageOptions"
          :timezone-options="timezoneOptions"
          :roi-tag-list="roiTagList"
          :roi-tag-input="roiTagInput"
          :upload-site-icon="onSiteIconChange"
          :reset-site-icon="resetSiteIcon"
          :add-roi-tag="addRoiTag"
          :remove-roi-tag="removeRoiTag"
          @update:roi-tag-input="roiTagInput = $event"
        />

        <SettingsBackendServiceSection
          :form="form"
          :plugin-options="localizedProcessorPluginOptions"
          :running-count="sourceStore.runningCount"
          :service-action="serviceAction"
          @start-all="startAllServices"
          @stop-all="stopAllServices"
        />

        <SettingsVEngineSection :form="form" />

        <SettingsSmokeSection
          :form="form"
          :smoke-advanced-fields="smokeAdvancedFields"
          @reset-advanced="resetSmokeAdvancedThresholds"
        />

        <SettingsMediaMtxSection :form="form" />

        <SettingsNotificationsSection
          :form="form"
          :placeholders="emailTemplatePlaceholders"
          :retention-day-options="retentionDayOptions"
        />

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
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { localeOptions } from '../i18n/index.js'
import { processorApi, settingsApi } from '../api/index.js'
import SettingsBackendServiceSection from '../components/settings/SettingsBackendServiceSection.vue'
import SettingsInterfaceSection from '../components/settings/SettingsInterfaceSection.vue'
import SettingsMediaMtxSection from '../components/settings/SettingsMediaMtxSection.vue'
import SettingsNotificationsSection from '../components/settings/SettingsNotificationsSection.vue'
import SettingsSectionNav from '../components/settings/SettingsSectionNav.vue'
import SettingsSmokeSection from '../components/settings/SettingsSmokeSection.vue'
import SettingsVEngineSection from '../components/settings/SettingsVEngineSection.vue'
import { useAppSettingsStore, parseRoiTagOptions } from '../stores/appSettings.js'
import { useSourceStore } from '../stores/source.js'

const { t, locale } = useI18n()
const appSettingsStore = useAppSettingsStore()
const sourceStore = useSourceStore()
const languageOptions = localeOptions
const processorPluginOptions = ref([])
const emailTemplatePlaceholders = ref([
  'site_title',
  'local_time',
  'timezone',
  'source_name',
  'source_id',
  'event_type',
  'event_label',
  'labels',
  'confidence_percent',
  'detection_count',
  'frame_id',
  'active_tracks',
])
const timezoneOptions = ['Asia/Shanghai', 'UTC', 'Asia/Tokyo', 'Europe/London', 'America/New_York']
const processorRestartSettingKeys = [
  'processor_plugin',
  'smoke_detection_model_name',
  'smoke_detection_model_version',
  'smoke_detection_confidence',
  'smoke_detection_nms',
  'smoke_temporal_confirm_frames',
  'smoke_temporal_confirm_window',
  'smoke_max_miss_frames',
  'smoke_alarm_hold_time',
  'smoke_email_cooldown_seconds',
]
const smokeAdvancedFields = [
  { key: 'smoke_min_confidence_smoke', labelKey: 'settings.smokeMinConfidenceSmoke', hintKey: 'settings.smokeMinConfidenceSmokeHint', placeholder: '0.35' },
  { key: 'smoke_min_confidence_fire', labelKey: 'settings.smokeMinConfidenceFire', hintKey: 'settings.smokeMinConfidenceFireHint', placeholder: '0.40' },
  { key: 'smoke_min_bbox_area_ratio', labelKey: 'settings.smokeMinBboxAreaRatio', hintKey: 'settings.smokeMinBboxAreaRatioHint', placeholder: '0.0005' },
  { key: 'smoke_max_bbox_area_ratio', labelKey: 'settings.smokeMaxBboxAreaRatio', hintKey: 'settings.smokeMaxBboxAreaRatioHint', placeholder: '0.60' },
  { key: 'smoke_min_aspect_ratio', labelKey: 'settings.smokeMinAspectRatio', hintKey: 'settings.smokeMinAspectRatioHint', placeholder: '0.2' },
  { key: 'smoke_max_aspect_ratio', labelKey: 'settings.smokeMaxAspectRatio', hintKey: 'settings.smokeMaxAspectRatioHint', placeholder: '8.0' },
  { key: 'smoke_motion_blur_max_speed', labelKey: 'settings.smokeMotionBlurMaxSpeed', hintKey: 'settings.smokeMotionBlurMaxSpeedHint', placeholder: '100.0' },
  { key: 'smoke_motion_blur_min_confidence', labelKey: 'settings.smokeMotionBlurMinConfidence', hintKey: 'settings.smokeMotionBlurMinConfidenceHint', placeholder: '0.65' },
  { key: 'smoke_appearance_min_score', labelKey: 'settings.smokeAppearanceMinScore', hintKey: 'settings.smokeAppearanceMinScoreHint', placeholder: '0.42' },
  { key: 'smoke_appearance_min_history', labelKey: 'settings.smokeAppearanceMinHistory', hintKey: 'settings.smokeAppearanceMinHistoryHint', placeholder: '2' },
  { key: 'smoke_appearance_high_confidence_bypass', labelKey: 'settings.smokeAppearanceHighConfidenceBypass', hintKey: 'settings.smokeAppearanceHighConfidenceBypassHint', placeholder: '0.82' },
  { key: 'smoke_overexposed_ratio_threshold', labelKey: 'settings.smokeOverexposedRatioThreshold', hintKey: 'settings.smokeOverexposedRatioThresholdHint', placeholder: '0.18' },
  { key: 'smoke_white_object_ratio_threshold', labelKey: 'settings.smokeWhiteObjectRatioThreshold', hintKey: 'settings.smokeWhiteObjectRatioThresholdHint', placeholder: '0.62' },
  { key: 'smoke_hard_boundary_density_threshold', labelKey: 'settings.smokeHardBoundaryDensityThreshold', hintKey: 'settings.smokeHardBoundaryDensityThresholdHint', placeholder: '0.14' },
  { key: 'smoke_hard_laplacian_threshold', labelKey: 'settings.smokeHardLaplacianThreshold', hintKey: 'settings.smokeHardLaplacianThresholdHint', placeholder: '520.0' },
  { key: 'smoke_fast_motion_energy_threshold', labelKey: 'settings.smokeFastMotionEnergyThreshold', hintKey: 'settings.smokeFastMotionEnergyThresholdHint', placeholder: '0.16' },
  { key: 'smoke_static_confirm_frames', labelKey: 'settings.smokeStaticConfirmFrames', hintKey: 'settings.smokeStaticConfirmFramesHint', placeholder: '5' },
  { key: 'smoke_static_max_center_shift', labelKey: 'settings.smokeStaticMaxCenterShift', hintKey: 'settings.smokeStaticMaxCenterShiftHint', placeholder: '10.0' },
  { key: 'smoke_static_max_area_change_ratio', labelKey: 'settings.smokeStaticMaxAreaChangeRatio', hintKey: 'settings.smokeStaticMaxAreaChangeRatioHint', placeholder: '0.08' },
  { key: 'smoke_iou_threshold', labelKey: 'settings.smokeIouThreshold', hintKey: 'settings.smokeIouThresholdHint', placeholder: '0.3' },
]
const fallbackSectionTitles = {
  interface: 'settings.interface',
  backend_service: 'settings.backendService',
  vengine_services: 'settings.vengineServices',
  smoke_scene: 'settings.smokeScene',
  mediamtx: 'settings.mediamtx',
  notifications: 'settings.emailNotifications',
}
const smokeAdvancedFallbacks = {
  smoke_enable_appearance_filter: 'true',
  smoke_min_confidence_smoke: '0.35',
  smoke_min_confidence_fire: '0.40',
  smoke_min_bbox_area_ratio: '0.0005',
  smoke_max_bbox_area_ratio: '0.60',
  smoke_min_aspect_ratio: '0.2',
  smoke_max_aspect_ratio: '8.0',
  smoke_motion_blur_max_speed: '100.0',
  smoke_motion_blur_min_confidence: '0.65',
  smoke_appearance_min_score: '0.42',
  smoke_appearance_min_history: '2',
  smoke_appearance_high_confidence_bypass: '0.82',
  smoke_overexposed_ratio_threshold: '0.18',
  smoke_white_object_ratio_threshold: '0.62',
  smoke_hard_boundary_density_threshold: '0.14',
  smoke_hard_laplacian_threshold: '520.0',
  smoke_fast_motion_energy_threshold: '0.16',
  smoke_static_confirm_frames: '5',
  smoke_static_max_center_shift: '10.0',
  smoke_static_max_area_change_ratio: '0.08',
  smoke_iou_threshold: '0.3',
}

const loading = ref(false)
const saving = ref(false)
const testingEmail = ref(false)
const serviceAction = ref('')
const roiTagInput = ref('')
const roiTagList = ref([])
const form = ref({ ...appSettingsStore.settingsDefaults })

const localizedProcessorPluginOptions = computed(() =>
  processorPluginOptions.value.map((option) => ({
    ...option,
    label: locale.value === 'en-US' ? option.label_en : option.label_zh,
  }))
)

const settingsNavSections = computed(() => {
  const schemaById = new Map(
    (appSettingsStore.settingsSections || []).map((section) => [section.id, section])
  )
  return Object.keys(fallbackSectionTitles).map((id) => ({
    id,
    label: t(schemaById.get(id)?.title_key || fallbackSectionTitles[id]),
  }))
})

const settingsFieldMap = computed(() => Object.fromEntries(
  (appSettingsStore.settingsSections || []).flatMap((section) =>
    (section.fields || []).map((field) => [field.key, field])
  )
))

const retentionDayOptions = computed(() => {
  const options = settingsFieldMap.value.message_retention_days?.options
  if (Array.isArray(options) && options.length) {
    return options.map((value) => Number(value)).filter((value) => Number.isFinite(value))
  }
  return [7, 14, 30]
})

const smokeAdvancedDefaults = computed(() => Object.fromEntries(
  Object.entries(smokeAdvancedFallbacks).map(([key, fallback]) => [
    key,
    String(appSettingsStore.settingsDefaults?.[key] ?? fallback),
  ])
))

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

function assignForm(data = {}) {
  form.value = {
    ...appSettingsStore.settingsDefaults,
    ...data,
  }
  roiTagList.value = parseRoiTagOptions(form.value.roi_tag_options)
  syncRoiTagOptionsToForm()
}

async function reload() {
  loading.value = true
  try {
    const [data, plugins] = await Promise.all([
      appSettingsStore.fetchSettings(true),
      processorApi.plugins(),
    ])
    assignForm(data)
    processorPluginOptions.value = Array.isArray(plugins) ? plugins : []
    try {
      const placeholderData = await settingsApi.emailTemplatePlaceholders()
      if (Array.isArray(placeholderData?.placeholders)) {
        emailTemplatePlaceholders.value = placeholderData.placeholders
      }
    } catch (_) {
      // Keep built-in placeholder list when the backend endpoint is unavailable.
    }
  } catch (err) {
    ElMessage.error(t('settings.failedToLoad', { message: err.message }))
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  const previousPlugin = appSettingsStore.settings?.processor_plugin || 'smoke'
  const previousSettings = appSettingsStore.settings || {}
  try {
    syncRoiTagOptionsToForm()
    const processorConfigChanged = (
      previousPlugin !== form.value.processor_plugin
      || processorRestartSettingKeys.some(
        (key) => String(previousSettings[key] || '') !== String(form.value[key] || '')
      )
      || smokeAdvancedFields.some(
        (item) => String(previousSettings[item.key] || '') !== String(form.value[item.key] || '')
      )
    )
    const mediamtxRtspChanged = (
      String(previousSettings.mediamtx_rtsp_addr || '') !== String(form.value.mediamtx_rtsp_addr || '')
      || String(previousSettings.mediamtx_rtsp_username || '') !== String(form.value.mediamtx_rtsp_username || '')
      || String(previousSettings.mediamtx_rtsp_password || '') !== String(form.value.mediamtx_rtsp_password || '')
    )
    const mediamtxWebrtcChanged = (
      String(previousSettings.mediamtx_webrtc_addr || '') !== String(form.value.mediamtx_webrtc_addr || '')
      || String(previousSettings.mediamtx_webrtc_username || '') !== String(form.value.mediamtx_webrtc_username || '')
      || String(previousSettings.mediamtx_webrtc_password || '') !== String(form.value.mediamtx_webrtc_password || '')
    )

    let runningSourceIds = []
    if (processorConfigChanged || mediamtxRtspChanged) {
      await sourceStore.syncProcessorStatus()
      runningSourceIds = sourceStore.getRunningSourceIdsSnapshot()
    }

    const data = await appSettingsStore.updateSettings(form.value)
    assignForm(data)
    appSettingsStore.applyLanguage(form.value.ui_language)

    if (mediamtxRtspChanged || mediamtxWebrtcChanged) {
      await sourceStore.fetchSources()
      sourceStore.syncAssignedSourceReferences()
    }

    if (!processorConfigChanged && !mediamtxRtspChanged) {
      ElMessage.success(t('settings.settingsSaved'))
      return
    }

    if (!runningSourceIds.length) {
      ElMessage.success(
        processorConfigChanged
          ? t('settings.settingsSavedRestartRequired')
          : t('settings.settingsSavedSourceUrlsSynced')
      )
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
  form.value.favicon_url = String(appSettingsStore.settingsDefaults?.favicon_url || '/favicon.ico')
}

function resetSmokeAdvancedThresholds() {
  Object.assign(form.value, smokeAdvancedDefaults.value)
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

function scrollToSection(sectionId) {
  if (typeof document === 'undefined') return
  document.getElementById(`section-${sectionId}`)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

onMounted(async () => {
  await Promise.all([
    reload(),
    sourceStore.syncProcessorStatus(),
  ])
})
</script>

<style>
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

.settings-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #26314d;
  border-radius: 14px;
  background: rgba(16, 21, 37, 0.78);
  position: sticky;
  top: 0;
  z-index: 5;
  backdrop-filter: blur(12px);
}

.settings-nav__button {
  color: #c8d5f0;
}

.settings-nav__button:hover {
  color: #ffffff;
}

.settings-form {
  background: rgba(16, 21, 37, 0.92);
  border: 1px solid #26314d;
  border-radius: 14px;
  padding: 16px;
}

.settings-section {
  scroll-margin-top: 88px;
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

.settings-subsection {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #30364d;
}

.settings-subsection h3 {
  font-size: 13px;
  color: #c8d5f0;
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

.settings-inline-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.smoke-threshold-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  width: 100%;
}

.smoke-threshold-item {
  padding: 10px;
  border: 1px solid #2d3650;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.smoke-threshold-label {
  color: #c8d5f0;
  font-size: 12px;
  margin-bottom: 6px;
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

.settings-form .el-form-item__label {
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

  .settings-form .el-form-item {
    margin-bottom: 14px;
  }

  .settings-form .el-form-item__label {
    width: 100% !important;
    justify-content: flex-start;
    margin-bottom: 4px;
    line-height: 1.4;
  }

  .settings-form .el-form-item__content {
    margin-left: 0 !important;
  }

  .roi-tag-input-row,
  .settings-actions {
    flex-wrap: wrap;
  }
}
</style>
