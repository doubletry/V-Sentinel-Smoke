<template>
  <div class="audit-logs-page" :class="{ 'audit-logs-page--embedded': embedded }">
    <div class="page-header">
      <div class="header-left">
        <h2>{{ t('auditLogs.title') }}</h2>
        <p>{{ t('auditLogs.subtitle') }}</p>
      </div>
      <div class="header-right">
        <el-space :size="10" wrap alignment="center">
          <el-input
            v-model="filters.username"
            size="small"
            clearable
            style="width: 180px"
            :placeholder="t('auditLogs.accountPlaceholder')"
            @keyup.enter="loadLogs(1)"
          />
          <el-select
            v-model="filters.operationType"
            size="small"
            clearable
            filterable
            style="width: 220px"
            :placeholder="t('auditLogs.operationTypePlaceholder')"
          >
            <el-option
              v-for="item in operationTypes"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
          <el-select
            v-model="filters.result"
            size="small"
            clearable
            style="width: 140px"
            :placeholder="t('auditLogs.resultPlaceholder')"
          >
            <el-option :label="t('auditLogs.resultSuccess')" value="SUCCESS" />
            <el-option :label="t('auditLogs.resultFailure')" value="FAILURE" />
          </el-select>
          <el-date-picker
            v-model="filters.timeRange"
            type="datetimerange"
            size="small"
            style="width: 360px"
            :range-separator="t('auditLogs.rangeSeparator')"
            :start-placeholder="t('auditLogs.startTime')"
            :end-placeholder="t('auditLogs.endTime')"
          />
          <el-button size="small" :loading="logsLoading" @click="loadLogs(1)">
            {{ t('auditLogs.search') }}
          </el-button>
          <el-button size="small" @click="resetFilters">
            {{ t('common.reset') }}
          </el-button>
        </el-space>
      </div>
    </div>

    <div class="table-wrap">
      <el-table
        :data="logItems"
        size="small"
        height="100%"
        v-loading="logsLoading"
        class="logs-table"
        :empty-text="t('auditLogs.noLogs')"
      >
        <el-table-column :label="t('auditLogs.logTime')" width="190">
          <template #default="scope">
            {{ formatDateTimeWithTimezone(scope.row.created_at, appSettingsStore.timeZone) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.account')" min-width="150">
          <template #default="scope">
            {{ scope.row.username || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.role')" width="110">
          <template #default="scope">
            {{ scope.row.role || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.operationType')" min-width="220" prop="operation_type" />
        <el-table-column :label="t('auditLogs.result')" width="110">
          <template #default="scope">
            <el-tag
              size="small"
              :type="scope.row.result === 'SUCCESS' ? 'success' : 'danger'"
              effect="dark"
            >
              {{ scope.row.result === 'SUCCESS' ? t('auditLogs.resultSuccess') : t('auditLogs.resultFailure') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.resource')" min-width="180">
          <template #default="scope">
            {{ formatResource(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.ip')" width="150">
          <template #default="scope">
            {{ scope.row.ip || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.detail')" min-width="260">
          <template #default="scope">
            {{ scope.row.detail || '-' }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="logs-pagination">
      <el-pagination
        background
        layout="sizes, prev, pager, next, total"
        :total="logTotal"
        :page-sizes="logPageSizeOptions"
        :page-size="logPageSize"
        :current-page="logPage"
        @current-change="loadLogs"
        @size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { accessApi } from '../api/index.js'
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '../constants/pagination.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { formatDateTimeWithTimezone } from '../utils/time.js'

defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})

const { t } = useI18n()
const appSettingsStore = useAppSettingsStore()
const logsLoading = ref(false)
const logItems = ref([])
const logTotal = ref(0)
const logPage = ref(1)
const logPageSize = ref(DEFAULT_PAGE_SIZE)
const logPageSizeOptions = PAGE_SIZE_OPTIONS
const operationTypes = ref([])
const filters = reactive({
  username: '',
  operationType: '',
  result: '',
  timeRange: [],
})

function toIso(value) {
  if (!value) return ''
  if (value instanceof Date) return value.toISOString()
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString()
}

function buildParams(page = 1) {
  const params = {
    page,
    page_size: logPageSize.value,
  }
  if (filters.username.trim()) {
    params.username = filters.username.trim()
  }
  if (filters.operationType) {
    params.operation_type = filters.operationType
  }
  if (filters.result) {
    params.result = filters.result
  }
  if (Array.isArray(filters.timeRange) && filters.timeRange.length === 2) {
    const [start, end] = filters.timeRange
    const startTime = toIso(start)
    const endTime = toIso(end)
    if (startTime) params.start_time = startTime
    if (endTime) params.end_time = endTime
  }
  return params
}

function formatResource(row) {
  const type = String(row.resource_type || '').trim()
  const id = String(row.resource_id || '').trim()
  if (type && id) return `${type}:${id}`
  return type || id || '-'
}

async function loadLogs(page = 1) {
  logPage.value = page
  logsLoading.value = true
  try {
    const data = await accessApi.auditLogs(buildParams(page))
    logItems.value = data.items || []
    logTotal.value = Number(data.total || 0)
    operationTypes.value = data.operation_types || []
  } catch (err) {
    ElMessage.error(t('auditLogs.failedLoad', { message: err.message }))
  } finally {
    logsLoading.value = false
  }
}

async function handlePageSizeChange(size) {
  logPageSize.value = Number(size)
  await loadLogs(1)
}

function resetFilters() {
  filters.username = ''
  filters.operationType = ''
  filters.result = ''
  filters.timeRange = []
  loadLogs(1)
}

onMounted(() => {
  loadLogs(1)
})
</script>

<style scoped>
.audit-logs-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0d0d1a;
}

.audit-logs-page--embedded {
  min-height: 620px;
  border: 1px solid #30364d;
  border-radius: 16px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.02);
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #1a1a2e;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.header-left {
  min-width: 0;
}

.header-left h2 {
  color: #dce7ff;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
}

.header-left p {
  margin-top: 4px;
  color: #8ea0c8;
  font-size: 12px;
}

.table-wrap {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.logs-table {
  width: 100%;
}

.logs-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 8px 12px 12px;
  border-top: 1px solid #26314d;
  background: #131a2e;
  flex-shrink: 0;
}

:deep(.logs-table .el-table__cell) {
  padding-top: 6px;
  padding-bottom: 6px;
}

@media (max-width: 1200px) {
  .page-header {
    flex-direction: column;
  }

  .logs-pagination {
    justify-content: center;
  }
}
</style>
