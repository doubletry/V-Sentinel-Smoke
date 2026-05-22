<template>
  <div class="messages-page">
    <div class="page-header">
      <div class="header-left">
        <h2>{{ t('messages.title') }}</h2>
        <el-tag type="info" size="small" effect="dark">
          {{ t('messages.manualMode') }}
        </el-tag>
        <span class="messages-updated-at">{{ t('messages.lastUpdated', { time: lastUpdatedLabel }) }}</span>
      </div>
      <div class="header-right">
        <el-select
          v-model="filterSource"
          :placeholder="t('messages.allSources')"
          clearable
          size="small"
          style="width: 200px"
          @change="handleFilterChange"
        >
          <el-option
            v-for="src in sourceStore.sources"
            :key="src.id"
            :label="src.name"
            :value="src.id"
          />
        </el-select>
        <div class="false-positive-filter">
          <span class="false-positive-filter__label">{{ t('messages.falsePositiveOnly') }}</span>
          <el-switch
            v-model="store.falsePositiveOnly"
            :aria-label="t('messages.falsePositiveOnlyHint')"
            @change="handleFalsePositiveFilterChange"
          />
        </div>
        <el-button size="small" type="primary" @click="handleManualRefresh">
          {{ t('messages.refresh') }}
        </el-button>
        <el-button size="small" @click="store.clearMessages">{{ t('messages.clear') }}</el-button>
      </div>
    </div>

    <el-scrollbar ref="scrollbar" class="messages-scroll">
      <MessageList
        :messages="store.messages"
        :resending-message-ids="resendingMessageIds"
        @mark-false-positive="handleMarkFalsePositive"
        @unmark-false-positive="handleUnmarkFalsePositive"
        @resend-notification="handleResendNotification"
      />
    </el-scrollbar>
    <div class="messages-pagination">
      <el-pagination
        background
        layout="sizes, prev, pager, next, total"
        :page-sizes="store.pageSizeOptions"
        :page-size="store.pageSize"
        :current-page="store.page"
        :total="store.total"
        :pager-count="21"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
      <span v-if="store.totalPages >= store.maxPageWindow" class="messages-pagination__hint">
        {{ t('messages.latestPageWindow', { count: store.maxPageWindow }) }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { useMessageStore } from '../stores/message.js'
import { useSourceStore } from '../stores/source.js'
import MessageList from '../components/MessageList.vue'

const store = useMessageStore()
const sourceStore = useSourceStore()
const { t } = useI18n()
const filterSource = ref('')
const scrollbar = ref(null)
const resendingMessageIds = ref({})
const lastUpdatedLabel = computed(() => {
  if (!store.lastUpdatedAt) return t('messages.notUpdatedYet')
  return new Date(store.lastUpdatedAt).toLocaleString()
})

// Auto-scroll to top (newest first)
watch(
  () => store.messages.length,
  async () => {
    await nextTick()
    scrollbar.value?.setScrollTop(0)
  }
)

async function handlePageChange(nextPage) {
  await store.fetchMessages(nextPage, store.pageSize)
}

async function handleSizeChange(nextSize) {
  await store.fetchMessages(1, nextSize)
}

async function handleFilterChange(value) {
  store.setFilterSource(value || '')
  await store.fetchMessages(1, store.pageSize)
}

async function handleFalsePositiveFilterChange(value) {
  store.setFalsePositiveOnly(value)
  await store.fetchMessages(1, store.pageSize)
}

async function handleManualRefresh() {
  await store.fetchMessages(store.page, store.pageSize)
}

async function handleMarkFalsePositive(message) {
  await store.markFalsePositive(message.id)
  await store.fetchMessages(store.page, store.pageSize)
}

async function handleUnmarkFalsePositive(message) {
  await store.unmarkFalsePositive(message.id)
  await store.fetchMessages(store.page, store.pageSize)
}

async function handleResendNotification(message) {
  if (!message?.id) return
  resendingMessageIds.value = { ...resendingMessageIds.value, [message.id]: true }
  try {
    const result = await store.resendNotification(message.id)
    if (result.status !== 'sent') {
      const detail = result.results?.[0]?.message || result.status || 'unknown'
      throw new Error(detail)
    }
    ElMessage.success(t('messages.resendNotificationSuccess', { status: result.status || 'sent' }))
  } catch (err) {
    ElMessage.error(t('messages.resendNotificationFailed', { message: err.message }))
  } finally {
    const next = { ...resendingMessageIds.value }
    delete next[message.id]
    resendingMessageIds.value = next
  }
}

onMounted(() => {
  store.fetchMessages(1, store.pageSize)
  if (!sourceStore.sources.length) {
    sourceStore.fetchSources()
  }
})
</script>

<style scoped>
.messages-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0d0d1a;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #1a1a2e;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex-wrap: wrap;
}

.header-left h2 {
  font-size: 16px;
  color: #ddd;
  font-weight: 600;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.false-positive-filter {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.false-positive-filter__label {
  color: #c8d5f0;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.messages-updated-at {
  color: #8ea3c8;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

@media (max-width: 880px) {
  .page-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .header-right {
    width: 100%;
    justify-content: flex-end;
  }
}
.messages-scroll {
  flex: 1;
  min-height: 0;
}

.messages-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px 12px;
  border-top: 1px solid #26314d;
  background: #131a2e;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.messages-pagination__hint {
  color: #8ea3c8;
  font-size: 12px;
  font-weight: 600;
}
</style>
