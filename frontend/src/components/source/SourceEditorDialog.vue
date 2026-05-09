<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="400px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form :model="form" label-width="80px" @submit.prevent="$emit('submit')">
      <el-form-item :label="t('sourceList.name')" required>
        <el-input v-model="form.name" :placeholder="t('sourceList.name')" />
      </el-form-item>
      <el-form-item :label="t('sourceList.routePath')" required>
        <el-input v-model="form.route_path" :placeholder="t('sourceList.routePlaceholder')" />
      </el-form-item>
      <div class="route-hint">{{ t('sourceList.routeHint', { base: rtspBase }) }}</div>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="loading" @click="$emit('submit')">
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, required: true },
  submitLabel: { type: String, required: true },
  form: { type: Object, required: true },
  loading: { type: Boolean, default: false },
  rtspBase: { type: String, default: '' },
})

defineEmits(['update:modelValue', 'submit'])

const { t } = useI18n()
</script>
