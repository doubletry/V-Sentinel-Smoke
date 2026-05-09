<template>
  <section id="section-interface" class="settings-section">
    <h2>{{ t('settings.interface') }}</h2>
    <el-form-item :label="t('settings.systemLanguage')">
      <el-select v-model="form.ui_language" style="width: 100%">
        <el-option
          v-for="option in languageOptions"
          :key="option.value"
          :label="t(option.labelKey)"
          :value="option.value"
        />
      </el-select>
    </el-form-item>
    <el-form-item :label="t('settings.timezone')">
      <el-select v-model="form.timezone" style="width: 100%" filterable allow-create default-first-option>
        <el-option
          v-for="option in timezoneOptions"
          :key="option"
          :label="option"
          :value="option"
        />
      </el-select>
    </el-form-item>
    <el-form-item :label="t('settings.siteTitle')">
      <el-input v-model="form.site_title" :placeholder="t('settings.siteTitle')" />
    </el-form-item>
    <el-form-item :label="t('settings.siteDescription')">
      <el-input v-model="form.site_description" :placeholder="t('settings.siteDescription')" />
    </el-form-item>
    <el-form-item :label="t('settings.faviconUrl')">
      <div class="icon-upload-group">
        <el-avatar :size="28" shape="square" :src="form.favicon_url">
          <el-icon><VideoCamera /></el-icon>
        </el-avatar>
        <el-upload
          class="site-icon-upload"
          :show-file-list="false"
          :auto-upload="false"
          accept=".ico,.png,.jpg,.jpeg,.svg,.webp"
          :on-change="uploadSiteIcon"
        >
          <el-button size="small">{{ t('settings.uploadSiteIcon') }}</el-button>
        </el-upload>
        <el-button size="small" @click="resetSiteIcon">{{ t('settings.resetSiteIcon') }}</el-button>
      </div>
    </el-form-item>
    <el-form-item :label="t('settings.iconPath')">
      <el-input v-model="form.favicon_url" placeholder="/favicon.ico" />
    </el-form-item>
    <el-form-item :label="t('settings.roiTagCandidates')">
      <div class="roi-tags-editor">
        <el-tag
          v-for="tag in roiTagList"
          :key="tag"
          closable
          type="info"
          effect="dark"
          class="roi-tag-item"
          @close="removeRoiTag(tag)"
        >
          {{ tag }}
        </el-tag>
        <span v-if="!roiTagList.length" class="roi-tag-empty">
          {{ t('settings.noRoiTags') }}
        </span>
      </div>
      <div class="roi-tag-input-row">
        <el-input
          v-model="localRoiTagInput"
          :placeholder="t('settings.roiTagInputPlaceholder')"
          @keyup.enter="addRoiTag"
        />
        <el-button type="primary" @click="addRoiTag">
          {{ t('settings.addRoiTag') }}
        </el-button>
      </div>
      <p class="roi-tag-hint">{{ t('settings.roiTagHint') }}</p>
    </el-form-item>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  form: { type: Object, required: true },
  languageOptions: { type: Array, default: () => [] },
  timezoneOptions: { type: Array, default: () => [] },
  roiTagList: { type: Array, default: () => [] },
  roiTagInput: { type: String, default: '' },
  uploadSiteIcon: { type: Function, required: true },
  resetSiteIcon: { type: Function, required: true },
  addRoiTag: { type: Function, required: true },
  removeRoiTag: { type: Function, required: true },
})

const emit = defineEmits(['update:roiTagInput'])
const { t } = useI18n()

const localRoiTagInput = computed({
  get: () => props.roiTagInput,
  set: (value) => emit('update:roiTagInput', value),
})
</script>
