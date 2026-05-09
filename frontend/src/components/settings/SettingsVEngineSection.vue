<template>
  <section id="section-vengine_services" class="settings-section">
    <h2>{{ t('settings.vengineServices') }}</h2>
    <el-form-item :label="t('settings.vengineHost')">
      <el-input v-model="form.vengine_host" placeholder="localhost" />
    </el-form-item>
    <el-form-item v-for="service in services" :key="service.portKey" :label="t(service.labelKey)">
      <div class="port-switch-row">
        <el-input
          v-model="form[service.portKey]"
          :placeholder="service.placeholder"
          :disabled="form[service.enabledKey] !== 'true'"
        />
        <el-switch v-model="form[service.enabledKey]" active-value="true" inactive-value="false" />
      </div>
    </el-form-item>
    <p class="service-tip">{{ t('settings.serviceToggleTip') }}</p>
  </section>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  form: { type: Object, required: true },
})

const { t } = useI18n()
const services = [
  { portKey: 'detection_port', enabledKey: 'detection_enabled', labelKey: 'settings.detectionPort', placeholder: '50051' },
  { portKey: 'classification_port', enabledKey: 'classification_enabled', labelKey: 'settings.classificationPort', placeholder: '50052' },
  { portKey: 'action_port', enabledKey: 'action_enabled', labelKey: 'settings.actionPort', placeholder: '50053' },
  { portKey: 'ocr_port', enabledKey: 'ocr_enabled', labelKey: 'settings.ocrPort', placeholder: '50054' },
  { portKey: 'upload_port', enabledKey: 'upload_enabled', labelKey: 'settings.uploadPort', placeholder: '50050' },
]
</script>
