<template>
  <section id="section-notifications" class="settings-section">
    <h2>{{ t('settings.emailNotifications') }}</h2>
    <el-form-item :label="t('settings.emailFromAddress')">
      <el-input v-model="form.email_from_address" placeholder="sender@example.com" />
    </el-form-item>
    <el-form-item :label="t('settings.emailGrpcPort')">
      <el-input v-model="form.email_port" placeholder="50055" />
    </el-form-item>
    <el-form-item :label="t('settings.emailFromAuthCode')">
      <el-input
        v-model="form.email_from_auth_code"
        type="password"
        show-password
        :placeholder="t('settings.emailAuthCodePlaceholder')"
      />
    </el-form-item>
    <el-form-item :label="t('settings.emailToAddresses')">
      <div class="field-stack">
        <el-input v-model="form.email_to_addresses" type="textarea" :rows="2" placeholder="a@example.com,b@example.com" />
        <p class="form-hint">{{ t('settings.emailAddressesHint') }}</p>
      </div>
    </el-form-item>
    <el-form-item :label="t('settings.emailCcAddresses')">
      <el-input v-model="form.email_cc_addresses" type="textarea" :rows="2" placeholder="cc1@example.com,cc2@example.com" />
    </el-form-item>
    <el-form-item :label="t('settings.emailEventEnabled')">
      <el-switch v-model="form.email_event_enabled" active-value="true" inactive-value="false" />
    </el-form-item>
    <el-form-item :label="t('settings.smokeEmailCooldownSeconds')">
      <el-input v-model="form.smoke_email_cooldown_seconds" placeholder="300" />
    </el-form-item>
    <el-form-item :label="t('settings.emailEventSubjectTemplate')">
      <el-input v-model="form.email_event_subject_template" />
    </el-form-item>
    <el-form-item :label="t('settings.emailEventBodyTemplate')">
      <div class="field-stack">
        <el-input v-model="form.email_event_body_template" type="textarea" :rows="8" />
        <p class="form-hint">{{ t('settings.emailTemplateHint') }}</p>
        <div class="placeholder-tags">
          <el-tag v-for="item in placeholders" :key="item" size="small" effect="dark">
            {{ '{' + item + '}' }}
          </el-tag>
        </div>
      </div>
    </el-form-item>
    <el-form-item :label="t('settings.messageRetentionDays')">
      <el-select v-model="form.message_retention_days" style="width: 100%">
        <el-option
          v-for="day in retentionDayOptions"
          :key="String(day)"
          :label="t('settings.messageRetentionDaysOption', { days: day })"
          :value="String(day)"
        />
      </el-select>
    </el-form-item>
  </section>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  form: { type: Object, required: true },
  placeholders: { type: Array, default: () => [] },
  retentionDayOptions: { type: Array, default: () => [] },
})

const { t } = useI18n()
</script>
