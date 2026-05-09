<template>
  <div class="source-summary">
    <div class="source-summary__stats">
      <div class="source-summary__stat">
        <span class="source-summary__label">{{ t('sourceList.totalSources') }}</span>
        <strong>{{ totalSources }}</strong>
      </div>
      <div class="source-summary__stat">
        <span class="source-summary__label">{{ t('sourceList.runningSources') }}</span>
        <strong>{{ runningCount }}</strong>
      </div>
      <div class="source-summary__route">{{ t('sourceList.routeBase', { base: rtspBase || '-' }) }}</div>
    </div>
    <div class="source-summary__actions">
      <el-button type="primary" size="small" @click="$emit('add')">
        <el-icon><Plus /></el-icon>
        {{ t('common.add') }}
      </el-button>
      <el-button size="small" type="success" :loading="bulkAction === 'start'" @click="$emit('start-all')">
        {{ t('sourceList.startAll') }}
      </el-button>
      <el-button size="small" type="warning" :loading="bulkAction === 'stop'" @click="$emit('stop-all')">
        {{ t('sourceList.stopAll') }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  totalSources: { type: Number, default: 0 },
  runningCount: { type: Number, default: 0 },
  rtspBase: { type: String, default: '' },
  bulkAction: { type: String, default: '' },
})

defineEmits(['add', 'start-all', 'stop-all'])

const { t } = useI18n()
</script>
