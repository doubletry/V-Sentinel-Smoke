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

<style scoped>
.source-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-bottom: 1px solid #333;
  background: rgba(255, 255, 255, 0.02);
}

.source-summary__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.source-summary__stat,
.source-summary__route {
  border: 1px solid #33405f;
  border-radius: 10px;
  padding: 8px 10px;
  background: rgba(10, 12, 24, 0.35);
  color: #dce7ff;
}

.source-summary__route {
  grid-column: 1 / -1;
  font-size: 12px;
  color: #a9b9dd;
  word-break: break-all;
}

.source-summary__label {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  color: #7f8bad;
}

.source-summary__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 920px) {
  .source-summary__stats {
    grid-template-columns: 1fr;
  }
}
</style>
