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
              v-for="item in localizedOperationTypes"
              :key="item.value"
              :label="item.label"
              :value="item.value"
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
        <el-table-column :label="t('auditLogs.logTime')" width="184" show-overflow-tooltip>
          <template #default="scope">
            {{ formatDateTimeWithTimezone(scope.row.created_at, appSettingsStore.timeZone) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.account')" min-width="120" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.username || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.role')" width="96" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.role || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.operationType')" min-width="160" show-overflow-tooltip>
          <template #default="scope">
            {{ localizeOperationType(scope.row.operation_type) }}
          </template>
        </el-table-column>
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
        <el-table-column :label="t('auditLogs.resource')" min-width="132" show-overflow-tooltip>
          <template #default="scope">
            {{ formatResource(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.ip')" width="132" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.ip || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('auditLogs.detail')" min-width="160" show-overflow-tooltip>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { accessApi } from '../api/index.js'
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '../constants/pagination.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { buildAuditOperationOptions, localizeAuditOperationType } from '../utils/auditLogPresentation.js'
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
const localizedOperationTypes = computed(() => buildAuditOperationOptions(t, operationTypes.value))
const filters = reactive({
  username: '',
  operationType: '',
  result: '',
  timeRange: [],
})

function localizeOperationType(value) {
  return localizeAuditOperationType(t, value)
}

function toIso(value) {
  if (!value) return ''
  if (value instanceof Date) return value.toISOString()
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
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
    if (startTime === null || endTime === null) {
      ElMessage.warning(t('auditLogs.invalidTimeRange'))
      return null
    }
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
    const params = buildParams(page)
    if (!params) return
    const data = await accessApi.auditLogs(params)
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
  --audit-page-surface: rgba(9, 17, 34, 0.9);
  --audit-page-border: rgba(103, 132, 190, 0.24);
  --audit-table-bg: rgba(10, 18, 33, 0.92);
  --audit-table-border: rgba(103, 132, 190, 0.34);
  --audit-table-header-bg: rgba(18, 29, 54, 0.96);
  --audit-table-hover-bg: rgba(35, 72, 132, 0.24);
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--audit-page-border);
  border-radius: 20px;
  background:
    radial-gradient(circle at top left, rgba(53, 102, 196, 0.18), transparent 36%),
    linear-gradient(180deg, rgba(14, 24, 45, 0.96), rgba(8, 14, 28, 0.98));
  box-shadow: 0 16px 40px rgba(3, 9, 22, 0.2);
}

.audit-logs-page--embedded {
  min-height: 620px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 0;
  flex-shrink: 0;
}

.header-left {
  min-width: 0;
}

.header-left h2 {
  margin: 0;
  color: #dce7ff;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
}

.header-left p {
  margin-top: 4px;
  color: #8ea0c8;
  font-size: 13px;
  line-height: 1.6;
}

.header-right {
  min-width: 0;
}

.table-wrap {
  flex: 1;
  min-height: 0;
  padding: 0 20px;
}

.logs-table {
  --el-table-bg-color: var(--audit-table-bg);
  --el-table-tr-bg-color: var(--audit-table-bg);
  --el-table-header-bg-color: var(--audit-table-header-bg);
  --el-table-row-hover-bg-color: var(--audit-table-hover-bg);
  --el-table-border-color: var(--audit-table-border);
  --el-table-text-color: #d9e6ff;
  --el-table-header-text-color: #9fb8e8;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--audit-table-border);
  border-radius: 16px;
  background: var(--audit-table-bg);
  box-shadow: 0 12px 30px rgba(3, 9, 22, 0.16);
}

.logs-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 0 20px 20px;
  flex-shrink: 0;
}

:deep(.logs-table .el-table__inner-wrapper::before),
:deep(.logs-table .el-table__border-left-patch) {
  background-color: var(--audit-table-border);
}

:deep(.logs-table .el-table__cell) {
  border-bottom-color: rgba(62, 82, 126, 0.48);
  padding-top: 10px;
  padding-bottom: 10px;
}

:deep(.logs-table .cell) {
  color: #d9e6ff;
  line-height: 1.5;
}

:deep(.logs-table .el-table__header-wrapper th) {
  font-weight: 700;
}

:deep(.logs-table .el-table__empty-block) {
  background: var(--audit-table-bg);
}

:deep(.logs-table .el-tag) {
  border-color: transparent;
}

@media (max-width: 1200px) {
  .page-header {
    flex-direction: column;
    padding-top: 20px;
  }

  .table-wrap,
  .logs-pagination {
    padding-left: 16px;
    padding-right: 16px;
  }

  .logs-pagination {
    justify-content: center;
  }
}

@media (max-width: 768px) {
  .audit-logs-page {
    padding: 12px;
    gap: 10px;
    border-radius: 16px;
  }

  .page-header {
    padding: 16px 16px 0;
  }

  .table-wrap,
  .logs-pagination {
    padding-left: 12px;
    padding-right: 12px;
  }
}
</style>
