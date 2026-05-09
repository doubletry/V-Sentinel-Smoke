<template>
  <section id="section-mediamtx" class="settings-section">
    <h2>{{ t('settings.mediamtx') }}</h2>
    <el-form-item :label="t('settings.rtspAddress')">
      <el-input v-model="form.mediamtx_rtsp_addr" placeholder="rtsp://localhost:8554" />
    </el-form-item>
    <el-form-item :label="t('settings.rtspUsername')">
      <el-input v-model="form.mediamtx_rtsp_username" placeholder="stream-user" />
    </el-form-item>
    <el-form-item :label="t('settings.rtspPassword')">
      <el-input v-model="form.mediamtx_rtsp_password" type="password" show-password placeholder="stream-pass" />
    </el-form-item>
    <el-form-item :label="t('settings.webrtcAddress')">
      <el-input v-model="form.mediamtx_webrtc_addr" placeholder="http://localhost:8889" />
    </el-form-item>
    <el-form-item :label="t('settings.webrtcUsername')">
      <el-input v-model="form.mediamtx_webrtc_username" placeholder="viewer" />
    </el-form-item>
    <el-form-item :label="t('settings.webrtcPassword')">
      <el-input v-model="form.mediamtx_webrtc_password" type="password" show-password placeholder="viewer-pass" />
    </el-form-item>
    <p class="service-tip">{{ t('settings.mediamtxAddressSyncHint') }}</p>
  </section>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  form: { type: Object, required: true },
})

const { t } = useI18n()
</script>
