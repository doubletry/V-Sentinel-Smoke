<template>
  <section id="section-smoke_scene" class="settings-section">
    <h2>{{ t('settings.smokeScene') }}</h2>
    <el-form-item v-for="item in primaryFields" :key="item.key" :label="t(item.labelKey)">
      <div class="field-stack">
        <component
          :is="item.component || 'el-input'"
          v-model="form[item.key]"
          v-bind="item.bind || {}"
          :placeholder="item.placeholder"
        />
        <p class="form-hint">{{ t(item.hintKey) }}</p>
      </div>
    </el-form-item>
    <el-form-item :label="t('settings.smokeAdvancedThresholds')">
      <div class="field-stack">
        <div class="settings-inline-actions">
          <p class="form-hint">{{ t('settings.smokeAdvancedThresholdsHint') }}</p>
          <el-button size="small" @click="$emit('reset-advanced')">
            {{ t('settings.resetAdvancedThresholds') }}
          </el-button>
        </div>
        <div class="smoke-threshold-grid">
          <div v-for="item in smokeAdvancedFields" :key="item.key" class="field-stack smoke-threshold-item">
            <span class="smoke-threshold-label">{{ t(item.labelKey) }}</span>
            <el-input v-model="form[item.key]" :placeholder="item.placeholder" />
            <p class="form-hint">{{ t(item.hintKey) }}</p>
          </div>
        </div>
      </div>
    </el-form-item>
  </section>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  form: { type: Object, required: true },
  smokeAdvancedFields: { type: Array, default: () => [] },
})

defineEmits(['reset-advanced'])

const { t } = useI18n()

const primaryFields = [
  { key: 'smoke_detection_model_name', labelKey: 'settings.smokeDetectionModelName', hintKey: 'settings.smokeDetectionModelNameHint', placeholder: 'smoke-fire-detection' },
  { key: 'smoke_detection_model_version', labelKey: 'settings.smokeDetectionModelVersion', hintKey: 'settings.smokeDetectionModelVersionHint', placeholder: '' },
  { key: 'smoke_detection_confidence', labelKey: 'settings.smokeDetectionConfidence', hintKey: 'settings.smokeDetectionConfidenceHint', placeholder: '0.35' },
  { key: 'smoke_detection_nms', labelKey: 'settings.smokeDetectionNms', hintKey: 'settings.smokeDetectionNmsHint', placeholder: '0.7' },
  { key: 'smoke_temporal_confirm_frames', labelKey: 'settings.smokeTemporalConfirmFrames', hintKey: 'settings.smokeTemporalConfirmFramesHint', placeholder: '3' },
  { key: 'smoke_temporal_confirm_window', labelKey: 'settings.smokeTemporalConfirmWindow', hintKey: 'settings.smokeTemporalConfirmWindowHint', placeholder: '2.0' },
  { key: 'smoke_max_miss_frames', labelKey: 'settings.smokeMaxMissFrames', hintKey: 'settings.smokeMaxMissFramesHint', placeholder: '5' },
  { key: 'smoke_alarm_hold_time', labelKey: 'settings.smokeAlarmHoldTime', hintKey: 'settings.smokeAlarmHoldTimeHint', placeholder: '3.0' },
  {
    key: 'smoke_enable_appearance_filter',
    labelKey: 'settings.smokeAppearanceFilter',
    hintKey: 'settings.smokeAppearanceFilterHint',
    component: 'el-switch',
    bind: { activeValue: 'true', inactiveValue: 'false' },
  },
]
</script>
