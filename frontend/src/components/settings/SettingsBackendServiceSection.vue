<template>
  <section id="section-backend_service" class="settings-section">
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
            v-for="option in pluginOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <p class="form-hint">{{ t('settings.processorPluginHint') }}</p>
      </div>
    </el-form-item>

    <div class="service-control-row">
      <el-tag :type="runningCount > 0 ? 'success' : 'info'" effect="dark">
        {{ runningCount > 0 ? t('settings.runningStatus', { count: runningCount }) : t('settings.stoppedStatus') }}
      </el-tag>
      <div class="service-buttons">
        <el-button type="success" :loading="serviceAction === 'start'" @click="$emit('start-all')">
          {{ t('settings.startAll') }}
        </el-button>
        <el-button type="warning" :loading="serviceAction === 'stop'" @click="$emit('stop-all')">
          {{ t('settings.stopAll') }}
        </el-button>
      </div>
    </div>
    <p class="service-tip">{{ t('settings.backendServiceTip') }}</p>

    <div class="settings-subsection">
      <h3>{{ t('settings.threadPools') }}</h3>
      <el-form-item :label="t('settings.maxPullWorkers')">
        <el-input v-model="form.max_pull_workers" placeholder="20" />
      </el-form-item>
      <el-form-item :label="t('settings.maxPushWorkers')">
        <el-input v-model="form.max_push_workers" placeholder="10" />
      </el-form-item>
      <el-form-item :label="t('settings.maxCpuWorkers')">
        <el-input v-model="form.max_cpu_workers" placeholder="16" />
      </el-form-item>
    </div>
  </section>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  form: { type: Object, required: true },
  pluginOptions: { type: Array, default: () => [] },
  runningCount: { type: Number, default: 0 },
  serviceAction: { type: String, default: '' },
})

defineEmits(['start-all', 'stop-all'])

const { t } = useI18n()
</script>
