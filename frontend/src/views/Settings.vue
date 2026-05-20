<template>
  <div class="settings-page">
    <div class="settings-shell">
      <div class="settings-head">
        <div class="title-line">
          <el-icon :size="20"><Setting /></el-icon>
          <h1>{{ t('management.title') }}</h1>
        </div>
        <p>{{ t('management.subtitle') }}</p>
        <el-tag v-if="authStore.role" size="small" effect="dark" class="management-role-tag">
          {{ t('auth.signedInAs', { role: t(`auth.roles.${authStore.role}`) }) }}
        </el-tag>
      </div>

      <div v-if="!hasSettingsAccess" class="settings-section section-card">
        <h2>{{ t('management.title') }}</h2>
        <p class="info-tip">{{ t('settings.noPermission') }}</p>
      </div>

      <el-form
        v-else
        :model="form"
        class="settings-form"
        label-position="top"
        v-loading="loading"
      >
        <div class="settings-page-toolbar">
          <div class="settings-page-nav">
            <button
              v-for="item in settingsNavItems"
              :key="item.key"
              type="button"
              class="settings-page-nav__button"
              :class="{ 'is-active': currentSettingsPage === item.key }"
              @click="navigateToSettingsPage(item.key)"
            >
              <span class="settings-page-nav__label-row">
                <span class="settings-page-nav__label">{{ item.label }}</span>
                <span v-if="currentSettingsPage === item.key" class="settings-page-nav__state" />
              </span>
              <span class="settings-page-nav__hint">{{ item.hint }}</span>
            </button>
          </div>
          <div v-if="canManageSettings" class="management-expert-toggle">
            <div>
              <h3>{{ t('settings.configurationMode') }}</h3>
              <p>{{ t('settings.expertModeHint') }}</p>
            </div>
            <el-switch v-model="expertMode" />
          </div>
        </div>

        <section v-if="isSitePage" class="settings-page-panel">
          <div class="settings-page-panel__head">
            <div>
              <h2>{{ t('management.siteSettings') }}</h2>
              <p>{{ t('management.siteSettingsHint') }}</p>
            </div>
          </div>
          <el-tabs v-model="activePlatformTab" class="settings-top-tabs">
            <el-tab-pane :label="t('settings.platformSectionInterface')" name="overview">
              <section class="settings-section section-card">
                <div class="section-card__head">
                  <div>
                    <h2>{{ t('settings.platformSectionInterface') }}</h2>
                    <p class="info-tip">{{ t('settings.sceneTabsStartupHint') }}</p>
                  </div>
                  <div class="section-card__actions">
                    <el-button
                      :loading="activeRestoreSection === 'platform-interface'"
                      @click="restoreSection('platform-interface', UI_SETTING_KEYS)"
                    >
                      {{ t('settings.restoreSection') }}
                    </el-button>
                    <el-button
                      type="primary"
                      :loading="activeSaveSection === 'platform-interface'"
                      @click="saveSection('platform-interface', UI_SETTING_KEYS)"
                    >
                      {{ t('settings.saveSection') }}
                    </el-button>
                  </div>
                </div>

                <div class="settings-form-grid wide-grid">
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
                    <el-input
                      v-model="form.site_description"
                      :placeholder="t('settings.siteDescription')"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.faviconUrl')" class="form-grid-span-full">
                    <div class="icon-upload-group">
                      <el-avatar :size="32" shape="square" :src="form.favicon_url">
                        <el-icon><VideoCamera /></el-icon>
                      </el-avatar>
                      <el-upload
                        class="site-icon-upload"
                        :show-file-list="false"
                        :auto-upload="false"
                        accept=".ico,.png,.jpg,.jpeg,.svg,.webp"
                        :on-change="onSiteIconChange"
                      >
                        <el-button>{{ t('settings.uploadSiteIcon') }}</el-button>
                      </el-upload>
                      <el-button @click="resetSiteIcon">{{ t('settings.resetSiteIcon') }}</el-button>
                      <el-input v-model="form.favicon_url" placeholder="/favicon.ico" class="icon-path-input" />
                    </div>
                  </el-form-item>
                </div>
              </section>
            </el-tab-pane>

            <el-tab-pane :label="t('settings.platformSectionMediaMtx')" name="mediamtx">
              <section class="settings-section section-card">
                <div class="section-card__head">
                  <div>
                    <h2>{{ t('settings.platformSectionMediaMtx') }}</h2>
                    <p class="info-tip">{{ t('settings.mediamtxAddressSyncHint') }}</p>
                  </div>
                  <div class="section-card__actions">
                    <el-button
                      :loading="activeRestoreSection === 'platform-mediamtx'"
                      @click="restoreSection('platform-mediamtx', MEDIAMTX_SETTING_KEYS)"
                    >
                      {{ t('settings.restoreSection') }}
                    </el-button>
                    <el-button
                      type="primary"
                      :loading="activeSaveSection === 'platform-mediamtx'"
                      @click="saveSection('platform-mediamtx', MEDIAMTX_SETTING_KEYS)"
                    >
                      {{ t('settings.saveSection') }}
                    </el-button>
                  </div>
                </div>

                <div class="settings-form-grid wide-grid">
                  <el-form-item :label="t('settings.rtspAddress')">
                    <el-input v-model="form.mediamtx_rtsp_addr" placeholder="rtsp://localhost:8554" />
                  </el-form-item>
                  <el-form-item :label="t('settings.webrtcAddress')">
                    <el-input v-model="form.mediamtx_webrtc_addr" placeholder="http://localhost:8889" />
                  </el-form-item>
                  <el-form-item :label="t('settings.mediamtxUsername')">
                    <el-input v-model="form.mediamtx_username" placeholder="stream-user" />
                  </el-form-item>
                  <el-form-item :label="t('settings.mediamtxPassword')">
                    <el-input
                      v-model="form.mediamtx_password"
                      type="password"
                      show-password
                      placeholder="stream-pass"
                    />
                  </el-form-item>
                </div>
              </section>
            </el-tab-pane>
          </el-tabs>
        </section>

        <section v-else-if="isVenginePage" class="settings-page-panel">
          <div class="settings-page-panel__head">
            <div>
              <h2>{{ t('management.vengineSettings') }}</h2>
              <p>{{ t('settings.serviceToggleTip') }}</p>
            </div>
          </div>
          <section class="settings-section section-card">
            <div class="section-card__head">
              <div>
                <h2>{{ t('settings.platformSectionVengine') }}</h2>
                <p class="info-tip">{{ t('settings.serviceToggleTip') }}</p>
              </div>
              <div class="section-card__actions">
                <el-button
                  :loading="activeRestoreSection === 'platform-vengine'"
                  @click="restoreSection('platform-vengine', VENGINE_SETTING_KEYS)"
                >
                  {{ t('settings.restoreSection') }}
                </el-button>
                <el-button
                  type="primary"
                  :loading="activeSaveSection === 'platform-vengine'"
                  @click="saveSection('platform-vengine', VENGINE_SETTING_KEYS)"
                >
                  {{ t('settings.saveSection') }}
                </el-button>
              </div>
            </div>

            <div class="settings-form-grid wide-grid">
              <el-form-item :label="t('settings.vengineHost')">
                <el-input v-model="form.vengine_host" placeholder="localhost" />
              </el-form-item>
              <el-form-item :label="t('settings.detectionPort')">
                <div class="port-switch-row">
                  <el-input v-model="form.detection_port" placeholder="50051" :disabled="form.detection_enabled !== 'true'" />
                  <el-switch v-model="form.detection_enabled" active-value="true" inactive-value="false" />
                </div>
              </el-form-item>
              <el-form-item :label="t('settings.classificationPort')">
                <div class="port-switch-row">
                  <el-input v-model="form.classification_port" placeholder="50052" :disabled="form.classification_enabled !== 'true'" />
                  <el-switch v-model="form.classification_enabled" active-value="true" inactive-value="false" />
                </div>
              </el-form-item>
              <el-form-item :label="t('settings.actionPort')">
                <div class="port-switch-row">
                  <el-input v-model="form.action_port" placeholder="50053" :disabled="form.action_enabled !== 'true'" />
                  <el-switch v-model="form.action_enabled" active-value="true" inactive-value="false" />
                </div>
              </el-form-item>
              <el-form-item :label="t('settings.ocrPort')">
                <div class="port-switch-row">
                  <el-input v-model="form.ocr_port" placeholder="50054" :disabled="form.ocr_enabled !== 'true'" />
                  <el-switch v-model="form.ocr_enabled" active-value="true" inactive-value="false" />
                </div>
              </el-form-item>
              <el-form-item :label="t('settings.uploadPort')">
                <div class="port-switch-row">
                  <el-input v-model="form.upload_port" placeholder="50050" :disabled="form.upload_enabled !== 'true'" />
                  <el-switch v-model="form.upload_enabled" active-value="true" inactive-value="false" />
                </div>
              </el-form-item>
            </div>

            <section v-if="expertMode" class="expert-card">
              <h3>{{ t('settings.threadPools') }}</h3>
              <div class="settings-form-grid compact-grid">
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
          </section>
        </section>

        <section v-else-if="isLogsPage" class="settings-page-panel management-logs-panel">
          <div class="settings-page-panel__head">
            <div>
              <h2>{{ t('management.processingLogs') }}</h2>
              <p>{{ t('processingLogs.subtitle') }}</p>
            </div>
          </div>
          <ProcessingLogs embedded />
        </section>

        <section v-else-if="isNotificationsPage" class="settings-page-panel">
          <div class="settings-page-panel__head">
            <div>
              <h2>{{ t('settings.notificationManagement') }}</h2>
              <p>{{ t('settings.subtitle') }}</p>
            </div>
          </div>
          <el-tabs v-model="activeNotificationTab" class="settings-top-tabs">
            <el-tab-pane :label="t('settings.notificationEmailSection')" name="email">
              <section class="settings-section section-card">
                <div class="section-card__head">
                  <div>
                    <h2>{{ t('settings.notificationEmailSection') }}</h2>
                    <p class="info-tip">{{ t('settings.emailAddressesHint') }}</p>
                  </div>
                  <div class="section-card__actions">
                    <el-button
                      :loading="activeRestoreSection === 'notifications-email'"
                      @click="restoreSection('notifications-email', NOTIFICATION_EMAIL_KEYS)"
                    >
                      {{ t('settings.restoreSection') }}
                    </el-button>
                    <el-button :loading="testingEmail" @click="testEmailConfig">
                      {{ t('settings.testEmail') }}
                    </el-button>
                    <el-button
                      type="primary"
                      :loading="activeSaveSection === 'notifications-email'"
                      @click="saveSection('notifications-email', NOTIFICATION_EMAIL_KEYS)"
                    >
                      {{ t('settings.saveSection') }}
                    </el-button>
                  </div>
                </div>

                <div class="settings-form-grid wide-grid">
                  <el-form-item :label="t('settings.emailFromAddress')">
                    <el-input v-model="form.email_from_address" placeholder="sender@example.com" />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailSmtpHost')">
                    <el-input v-model="form.email_smtp_host" placeholder="smtp.example.com" />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailSmtpPort')">
                    <el-input v-model="form.email_smtp_port" placeholder="587" />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailSmtpUseTls')">
                    <el-switch v-model="form.email_smtp_use_tls" active-value="true" inactive-value="false" />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailFromAuthCode')">
                    <el-input
                      v-model="form.email_smtp_password"
                      type="password"
                      show-password
                      placeholder="授权码 / 密码"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailEventEnabled')">
                    <el-switch v-model="form.email_event_enabled" active-value="true" inactive-value="false" />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailToAddresses')" class="form-grid-span-full">
                    <div class="field-stack">
                      <el-input
                        v-model="form.email_to_addresses"
                        type="textarea"
                        :rows="2"
                        placeholder="a@example.com,b@example.com"
                      />
                      <p class="form-hint">{{ t('settings.emailAddressesHint') }}</p>
                    </div>
                  </el-form-item>
                  <el-form-item :label="t('settings.emailCcAddresses')" class="form-grid-span-full">
                    <el-input
                      v-model="form.email_cc_addresses"
                      type="textarea"
                      :rows="2"
                      placeholder="cc1@example.com,cc2@example.com"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailEventSubjectTemplate')" class="form-grid-span-full">
                    <el-input v-model="form.email_event_subject_template" />
                  </el-form-item>
                  <el-form-item :label="t('settings.emailEventBodyTemplate')" class="form-grid-span-full">
                    <div class="field-stack">
                      <el-input
                        v-model="form.email_event_body_template"
                        type="textarea"
                        :rows="8"
                      />
                      <p class="form-hint">{{ t('settings.emailTemplateHint') }}</p>
                      <div class="placeholder-tags">
                        <el-tag v-for="item in emailTemplatePlaceholders" :key="item" size="small" effect="dark">
                          {{ '{' + item + '}' }}
                        </el-tag>
                      </div>
                    </div>
                  </el-form-item>
                </div>
              </section>
            </el-tab-pane>

            <el-tab-pane :label="t('settings.notificationRetentionSection')" name="retention">
              <section class="settings-section section-card compact-section">
                <div class="section-card__head">
                  <div>
                    <h2>{{ t('settings.notificationRetentionSection') }}</h2>
                    <p class="info-tip">{{ t('settings.notificationRetentionHint') }}</p>
                  </div>
                  <div class="section-card__actions">
                    <el-button
                      :loading="activeRestoreSection === 'notifications-retention'"
                      @click="restoreSection('notifications-retention', NOTIFICATION_RETENTION_KEYS)"
                    >
                      {{ t('settings.restoreSection') }}
                    </el-button>
                    <el-button
                      type="primary"
                      :loading="activeSaveSection === 'notifications-retention'"
                      @click="saveSection('notifications-retention', NOTIFICATION_RETENTION_KEYS)"
                    >
                      {{ t('settings.saveSection') }}
                    </el-button>
                  </div>
                </div>
                <div class="settings-form-grid compact-grid">
                  <el-form-item :label="t('settings.messageRetentionDays')">
                    <el-select v-model="form.message_retention_days" style="width: 100%">
                      <el-option
                        v-for="day in retentionDayOptions"
                        :key="day"
                        :label="t('settings.messageRetentionDaysOption', { days: day })"
                        :value="String(day)"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item :label="t('settings.smokeEmailCooldownSeconds')">
                    <el-input v-model="form.smoke_email_cooldown_seconds" placeholder="300" />
                  </el-form-item>
                </div>
              </section>
            </el-tab-pane>
          </el-tabs>
        </section>

        <section v-else-if="isUsersPage" class="settings-page-panel">
          <div class="settings-page-panel__head">
            <div>
              <h2>{{ t('settings.userManagement') }}</h2>
              <p>{{ t('settings.userManagementHint') }}</p>
            </div>
          </div>
          <div class="settings-split-grid">
            <section class="settings-section section-card">
              <div class="section-card__head">
                <div>
                  <h2>{{ t('settings.accountList') }}</h2>
                  <p class="info-tip">{{ t('settings.userManagementHint') }}</p>
                </div>
              </div>
              <div class="user-list">
                <div v-for="item in authStore.users" :key="item.username" class="user-list-item">
                  <span>{{ item.username }}</span>
                  <el-tag size="small" effect="dark">{{ t(`auth.roles.${item.role}`) }}</el-tag>
                  <span class="user-created-at">{{ formatCreatedAt(item.created_at) }}</span>
                </div>
                <span v-if="!authStore.users.length" class="empty-list-message">{{ t('settings.noUsers') }}</span>
              </div>
            </section>

            <section class="settings-section section-card">
              <div class="section-card__head">
                <div>
                  <h2>{{ t('settings.createUser') }}</h2>
                  <p class="info-tip">{{ t('settings.temporaryPasswordHint') }}</p>
                </div>
              </div>
              <el-form-item :label="t('settings.username')">
                <el-input v-model="userForm.username" autocomplete="username" />
              </el-form-item>
              <el-form-item :label="t('settings.userRole')">
                <el-select v-model="userForm.role" style="width: 100%">
                  <el-option value="user" :label="t('auth.roles.user')" />
                  <el-option value="operator" :label="t('auth.roles.operator')" />
                  <el-option value="admin" :label="t('auth.roles.admin')" />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('settings.temporaryPassword')">
                <el-input v-model="userForm.password" type="password" show-password autocomplete="new-password" />
              </el-form-item>
              <div class="section-card__actions single-action">
                <el-button type="primary" :loading="creatingUser" @click="createUserAccount">
                  {{ t('settings.createUser') }}
                </el-button>
              </div>
            </section>
          </div>
        </section>

        <section v-else-if="isPluginPage" class="settings-page-panel">
          <div class="settings-page-panel__head">
            <div>
              <h2>{{ t('settings.pluginSettingsOverview') }}</h2>
              <p>{{ t('settings.pluginSectionHint') }}</p>
            </div>
          </div>
          <div class="plugin-launcher-grid">
            <section
              v-for="scene in sceneDefinitions"
              :key="scene.id"
              class="settings-section section-card plugin-launcher-card"
            >
              <div class="section-card__head">
                <div>
                  <h2>{{ sceneTabLabel(scene.id) }}</h2>
                  <p class="info-tip">{{ scene.description || t('settings.templateSceneHint') }}</p>
                </div>
                <div class="section-card__actions">
                  <el-button
                    type="primary"
                    :aria-label="`${t('settings.openPluginSettings')} - ${sceneTabLabel(scene.id)}`"
                    @click="navigateToPluginSettingsDialog(scene.id)"
                  >
                    {{ t('settings.openPluginSettings') }}
                  </el-button>
                  <el-button
                    plain
                    :aria-label="`${t('settings.pluginRoiTags')} - ${sceneTabLabel(scene.id)}`"
                    @click="navigateToPluginSettingsDialog(scene.id, 'roi-tags')"
                  >
                    {{ t('settings.pluginRoiTags') }}
                  </el-button>
                  <el-button
                    plain
                    :aria-label="`${t('settings.pluginDefaultConfig')} - ${sceneTabLabel(scene.id)}`"
                    @click="navigateToPluginSettingsDialog(scene.id, 'defaults')"
                  >
                    {{ t('settings.pluginDefaultConfig') }}
                  </el-button>
                </div>
              </div>
              <div class="plugin-launcher-card__summary">
                <div class="plugin-launcher-card__group">
                  <span class="plugin-launcher-card__label">{{ t('settings.pluginRoiTags') }}</span>
                  <div class="plugin-tag-list">
                    <el-tag v-for="tag in scene.default_roi_tags" :key="tag" effect="dark" :title="tag">
                      {{ roiTagLabel(scene, tag) }}
                    </el-tag>
                    <span v-if="!scene.default_roi_tags.length" class="roi-tag-empty">{{ t('settings.noRoiTags') }}</span>
                  </div>
                </div>
                <div class="plugin-launcher-card__group">
                  <span class="plugin-launcher-card__label">{{ t('settings.pluginDefaultConfig') }}</span>
                  <div class="plugin-config-list">
                    <el-tag v-for="item in previewConfigRowsByScene[scene.id] || []" :key="item.key" type="info">
                      {{ item.key }}: {{ item.value }}
                    </el-tag>
                    <span v-if="!sceneDefaultConfigRows(scene.id).length" class="roi-tag-empty">{{ t('settings.noPluginConfig') }}</span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </section>

        <el-dialog
          v-model="pluginDialogVisible"
          :title="currentPluginSceneLabel"
          width="min(1080px, calc(100vw - 32px))"
          class="plugin-settings-dialog"
          destroy-on-close
          @closed="handlePluginDialogClosed"
        >
          <template v-if="currentPluginScene">
            <p class="plugin-dialog-hint">
              {{ currentPluginScene.description || t('settings.templateSceneHint') }}
            </p>
            <el-tabs v-model="activePluginTab" class="settings-top-tabs">
              <el-tab-pane :label="t('settings.savePluginSection')" name="config">
                <template v-if="currentPluginScene.id === SMOKE_SCENE_ID">
                  <section class="settings-section section-card">
                    <div class="section-card__head">
                      <div>
                        <h2>{{ t('settings.smokeScene') }}</h2>
                        <p class="info-tip">{{ currentPluginScene.description }}</p>
                      </div>
                      <div class="section-card__actions">
                        <el-button
                          :loading="activeRestoreSection === `plugin-${currentPluginScene.id}`"
                          @click="restoreSection(`plugin-${currentPluginScene.id}`, pluginSettingKeys(currentPluginScene.id))"
                        >
                          {{ t('settings.restoreSection') }}
                        </el-button>
                        <el-button
                          type="primary"
                          :loading="activeSaveSection === `plugin-${currentPluginScene.id}`"
                          @click="saveSection(`plugin-${currentPluginScene.id}`, pluginSettingKeys(currentPluginScene.id))"
                        >
                          {{ t('settings.savePluginSection') }}
                        </el-button>
                      </div>
                    </div>

                    <div class="settings-form-grid wide-grid">
                      <el-form-item :label="t('settings.smokeDetectionModelName')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_detection_model_name" placeholder="smoke-fire-detection" />
                          <p class="form-hint">{{ t('settings.smokeDetectionModelNameHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeDetectionModelVersion')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_detection_model_version" :placeholder="t('settings.defaultVersionPlaceholder')" />
                          <p class="form-hint">{{ t('settings.smokeDetectionModelVersionHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeDetectionConfidence')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_detection_confidence" placeholder="0.35" />
                          <p class="form-hint">{{ t('settings.smokeDetectionConfidenceHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeDetectionNms')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_detection_nms" placeholder="0.7" />
                          <p class="form-hint">{{ t('settings.smokeDetectionNmsHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeTemporalConfirmFrames')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_temporal_confirm_frames" placeholder="3" />
                          <p class="form-hint">{{ t('settings.smokeTemporalConfirmFramesHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeTemporalConfirmWindow')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_temporal_confirm_window" placeholder="2.0" />
                          <p class="form-hint">{{ t('settings.smokeTemporalConfirmWindowHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeMaxMissFrames')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_max_miss_frames" placeholder="5" />
                          <p class="form-hint">{{ t('settings.smokeMaxMissFramesHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeAlarmHoldTime')">
                        <div class="field-stack">
                          <el-input v-model="form.smoke_alarm_hold_time" placeholder="3.0" />
                          <p class="form-hint">{{ t('settings.smokeAlarmHoldTimeHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.smokeAppearanceFilter')" class="form-grid-span-full">
                        <div class="field-stack switch-field-stack">
                          <el-switch v-model="form.smoke_enable_appearance_filter" active-value="true" inactive-value="false" />
                          <p class="form-hint">{{ t('settings.smokeAppearanceFilterHint') }}</p>
                        </div>
                      </el-form-item>
                    </div>

                    <section v-if="expertMode" class="expert-card plugin-advanced-card">
                      <div class="section-card__head threshold-head">
                        <div>
                          <h3>{{ t('settings.smokeAdvancedThresholds') }}</h3>
                          <p class="info-tip">{{ t('settings.smokeAdvancedThresholdsHint') }}</p>
                        </div>
                        <el-button @click="resetSmokeAdvancedThresholds">
                          {{ t('settings.resetAdvancedThresholds') }}
                        </el-button>
                      </div>
                      <div class="smoke-threshold-grid">
                        <div v-for="item in smokeAdvancedFields" :key="item.key" class="field-stack smoke-threshold-item">
                          <span class="smoke-threshold-label">{{ t(item.labelKey) }}</span>
                          <el-input v-model="form[item.key]" :placeholder="item.placeholder" />
                          <p class="form-hint">{{ t(item.hintKey) }}</p>
                        </div>
                      </div>
                    </section>
                  </section>
                </template>
                <section v-else class="settings-section section-card">
                  <div class="section-card__head">
                    <div>
                      <h2>{{ currentPluginSceneLabel }}</h2>
                      <p class="info-tip">{{ currentPluginScene.description || t('settings.templateSceneHint') }}</p>
                    </div>
                    <div class="section-card__actions">
                      <el-button
                        :loading="activeRestoreSection === `plugin-${currentPluginScene.id}`"
                        @click="restoreSection(`plugin-${currentPluginScene.id}`, pluginSettingKeys(currentPluginScene.id))"
                      >
                        {{ t('settings.restoreSection') }}
                      </el-button>
                      <el-button
                        type="primary"
                        :loading="activeSaveSection === `plugin-${currentPluginScene.id}`"
                        @click="saveSection(`plugin-${currentPluginScene.id}`, pluginSettingKeys(currentPluginScene.id))"
                      >
                        {{ t('settings.savePluginSection') }}
                      </el-button>
                    </div>
                  </div>
                  <p class="info-tip">{{ t('settings.noPluginConfig') }}</p>
                </section>
              </el-tab-pane>

              <el-tab-pane :label="t('settings.pluginRoiTags')" name="roi-tags">
                <section class="settings-section section-card">
                  <div class="section-card__head">
                    <div>
                      <h2>{{ t('settings.pluginRoiTags') }}</h2>
                      <p class="scene-scope-line">
                        {{ t('settings.pluginRoiTagsScene', { scene: currentPluginSceneLabel, id: currentPluginScene.id }) }}
                      </p>
                    </div>
                  </div>
                  <p v-if="currentPluginScene.id !== SMOKE_SCENE_ID" class="info-tip">
                    {{ currentPluginScene.description || t('settings.templateSceneHint') }}
                  </p>
                  <div class="plugin-tag-list">
                    <el-tag v-for="tag in currentPluginScene.default_roi_tags" :key="tag" effect="dark" :title="tag">
                      {{ roiTagLabel(currentPluginScene, tag) }}
                    </el-tag>
                    <span v-if="!currentPluginScene.default_roi_tags.length" class="roi-tag-empty">{{ t('settings.noRoiTags') }}</span>
                  </div>
                  <p class="info-tip">{{ t('settings.pluginRoiTagsHint') }}</p>
                </section>
              </el-tab-pane>

              <el-tab-pane :label="t('settings.pluginDefaultConfig')" name="defaults">
                <section class="settings-section section-card">
                  <div class="section-card__head">
                    <div>
                      <h2>{{ t('settings.pluginDefaultConfig') }}</h2>
                      <p v-if="currentPluginScene.id !== SMOKE_SCENE_ID" class="info-tip">
                        {{ currentPluginScene.description || t('settings.templateSceneHint') }}
                      </p>
                    </div>
                  </div>
                  <div class="plugin-config-list">
                    <el-tag v-for="item in sceneDefaultConfigRows(currentPluginScene.id)" :key="item.key" type="info">
                      {{ item.key }}: {{ item.value }}
                    </el-tag>
                    <span v-if="!sceneDefaultConfigRows(currentPluginScene.id).length" class="roi-tag-empty">{{ t('settings.noPluginConfig') }}</span>
                  </div>
                </section>
              </el-tab-pane>
            </el-tabs>
          </template>
        </el-dialog>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { useRoute, useRouter } from 'vue-router'
import { localeOptions } from '../i18n/index.js'
import { scenesApi, settingsApi } from '../api/index.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useAuthStore } from '../stores/auth.js'
import { useSourceStore } from '../stores/source.js'
import { canViewProcessingLogs, getDefaultManagementSection } from '../utils/settingsRoutes.js'
import { sceneScopedRoiTagLabel } from '../utils/roiTags.js'
import { formatTimeWithTimezone } from '../utils/time.js'
import ProcessingLogs from './ProcessingLogs.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const sourceStore = useSourceStore()
const languageOptions = localeOptions
const retentionDayOptions = [7, 15, 21, 30]
// Also referenced by the template to decide whether to render smoke-specific fields.
// 模板中也会使用它判断是否渲染烟火插件专属字段。
const SMOKE_SCENE_ID = 'smoke'
const activePlatformTab = ref('overview')
const activeNotificationTab = ref('email')
const activePluginTab = ref('config')
const DEFAULT_SCENE_DEFINITIONS = [
  {
    id: 'smoke',
    label_zh: '烟火检测',
    label_en: 'Smoke/Fire Detection',
    description: 'Detects smoke and fire with temporal post-processing.',
    default_roi_tags: ['smoke_zone', 'fire_zone'],
    default_config: {},
  },
  {
    id: 'template',
    label_zh: '场景模板',
    label_en: 'Scene Template',
    description: 'Template scene for custom frame processing, result return, notification dispatch, and message persistence.',
    default_roi_tags: [],
    default_config: {},
  },
]
const sceneDefinitions = ref(DEFAULT_SCENE_DEFINITIONS)
const emailTemplatePlaceholders = ref(['site_title', 'local_time', 'timezone', 'source_name', 'source_id', 'event_type', 'event_label', 'labels', 'confidence_percent', 'detection_count', 'frame_id', 'active_tracks'])
const timezoneOptions = ['Asia/Shanghai', 'UTC', 'Asia/Tokyo', 'Europe/London', 'America/New_York']
const SMOKE_ADVANCED_DEFAULTS = {
  smoke_enable_appearance_filter: 'true',
  smoke_min_confidence_smoke: '0.35',
  smoke_min_confidence_fire: '0.40',
  smoke_min_bbox_area_ratio: '0.0005',
  smoke_max_bbox_area_ratio: '0.60',
  smoke_min_aspect_ratio: '0.2',
  smoke_max_aspect_ratio: '8.0',
  smoke_motion_blur_max_speed: '100.0',
  smoke_motion_blur_min_confidence: '0.65',
  smoke_appearance_min_score: '0.42',
  smoke_appearance_min_history: '2',
  smoke_appearance_high_confidence_bypass: '0.82',
  smoke_overexposed_ratio_threshold: '0.18',
  smoke_white_object_ratio_threshold: '0.62',
  smoke_hard_boundary_density_threshold: '0.14',
  smoke_hard_laplacian_threshold: '520.0',
  smoke_fast_motion_energy_threshold: '0.16',
  smoke_static_confirm_frames: '5',
  smoke_static_max_center_shift: '10.0',
  smoke_static_max_area_change_ratio: '0.08',
  smoke_iou_threshold: '0.3',
}
const PROCESSOR_RESTART_SETTING_KEYS = [
  'smoke_detection_model_name',
  'smoke_detection_model_version',
  'smoke_detection_confidence',
  'smoke_detection_nms',
  'smoke_temporal_confirm_frames',
  'smoke_temporal_confirm_window',
  'smoke_max_miss_frames',
  'smoke_alarm_hold_time',
  'smoke_email_cooldown_seconds',
  ...Object.keys(SMOKE_ADVANCED_DEFAULTS),
]
const UI_SETTING_KEYS = ['ui_language', 'timezone', 'site_title', 'site_description', 'favicon_url']
const VENGINE_SETTING_KEYS = [
  'vengine_host',
  'detection_port',
  'classification_port',
  'action_port',
  'ocr_port',
  'upload_port',
  'detection_enabled',
  'classification_enabled',
  'action_enabled',
  'ocr_enabled',
  'upload_enabled',
  'max_pull_workers',
  'max_push_workers',
  'max_cpu_workers',
]
const MEDIAMTX_SETTING_KEYS = [
  'mediamtx_rtsp_addr',
  'mediamtx_webrtc_addr',
  'mediamtx_username',
  'mediamtx_password',
]
const NOTIFICATION_EMAIL_KEYS = [
  'email_from_address',
  'email_smtp_password',
  'email_to_addresses',
  'email_cc_addresses',
  'email_smtp_host',
  'email_smtp_port',
  'email_smtp_use_tls',
  'email_event_enabled',
  'email_event_subject_template',
  'email_event_body_template',
]
const NOTIFICATION_RETENTION_KEYS = [
  'message_retention_days',
  'smoke_email_cooldown_seconds',
]
const SMOKE_PLUGIN_SETTING_KEYS = [
  'smoke_detection_model_name',
  'smoke_detection_model_version',
  'smoke_detection_confidence',
  'smoke_detection_nms',
  'smoke_temporal_confirm_frames',
  'smoke_temporal_confirm_window',
  'smoke_max_miss_frames',
  'smoke_alarm_hold_time',
  'smoke_enable_appearance_filter',
  ...Object.keys(SMOKE_ADVANCED_DEFAULTS),
]
const smokeAdvancedFields = [
  { key: 'smoke_min_confidence_smoke', labelKey: 'settings.smokeMinConfidenceSmoke', hintKey: 'settings.smokeMinConfidenceSmokeHint', placeholder: '0.35' },
  { key: 'smoke_min_confidence_fire', labelKey: 'settings.smokeMinConfidenceFire', hintKey: 'settings.smokeMinConfidenceFireHint', placeholder: '0.40' },
  { key: 'smoke_min_bbox_area_ratio', labelKey: 'settings.smokeMinBboxAreaRatio', hintKey: 'settings.smokeMinBboxAreaRatioHint', placeholder: '0.0005' },
  { key: 'smoke_max_bbox_area_ratio', labelKey: 'settings.smokeMaxBboxAreaRatio', hintKey: 'settings.smokeMaxBboxAreaRatioHint', placeholder: '0.60' },
  { key: 'smoke_min_aspect_ratio', labelKey: 'settings.smokeMinAspectRatio', hintKey: 'settings.smokeMinAspectRatioHint', placeholder: '0.2' },
  { key: 'smoke_max_aspect_ratio', labelKey: 'settings.smokeMaxAspectRatio', hintKey: 'settings.smokeMaxAspectRatioHint', placeholder: '8.0' },
  { key: 'smoke_motion_blur_max_speed', labelKey: 'settings.smokeMotionBlurMaxSpeed', hintKey: 'settings.smokeMotionBlurMaxSpeedHint', placeholder: '100.0' },
  { key: 'smoke_motion_blur_min_confidence', labelKey: 'settings.smokeMotionBlurMinConfidence', hintKey: 'settings.smokeMotionBlurMinConfidenceHint', placeholder: '0.65' },
  { key: 'smoke_appearance_min_score', labelKey: 'settings.smokeAppearanceMinScore', hintKey: 'settings.smokeAppearanceMinScoreHint', placeholder: '0.42' },
  { key: 'smoke_appearance_min_history', labelKey: 'settings.smokeAppearanceMinHistory', hintKey: 'settings.smokeAppearanceMinHistoryHint', placeholder: '2' },
  { key: 'smoke_appearance_high_confidence_bypass', labelKey: 'settings.smokeAppearanceHighConfidenceBypass', hintKey: 'settings.smokeAppearanceHighConfidenceBypassHint', placeholder: '0.82' },
  { key: 'smoke_overexposed_ratio_threshold', labelKey: 'settings.smokeOverexposedRatioThreshold', hintKey: 'settings.smokeOverexposedRatioThresholdHint', placeholder: '0.18' },
  { key: 'smoke_white_object_ratio_threshold', labelKey: 'settings.smokeWhiteObjectRatioThreshold', hintKey: 'settings.smokeWhiteObjectRatioThresholdHint', placeholder: '0.62' },
  { key: 'smoke_hard_boundary_density_threshold', labelKey: 'settings.smokeHardBoundaryDensityThreshold', hintKey: 'settings.smokeHardBoundaryDensityThresholdHint', placeholder: '0.14' },
  { key: 'smoke_hard_laplacian_threshold', labelKey: 'settings.smokeHardLaplacianThreshold', hintKey: 'settings.smokeHardLaplacianThresholdHint', placeholder: '520.0' },
  { key: 'smoke_fast_motion_energy_threshold', labelKey: 'settings.smokeFastMotionEnergyThreshold', hintKey: 'settings.smokeFastMotionEnergyThresholdHint', placeholder: '0.16' },
  { key: 'smoke_static_confirm_frames', labelKey: 'settings.smokeStaticConfirmFrames', hintKey: 'settings.smokeStaticConfirmFramesHint', placeholder: '5' },
  { key: 'smoke_static_max_center_shift', labelKey: 'settings.smokeStaticMaxCenterShift', hintKey: 'settings.smokeStaticMaxCenterShiftHint', placeholder: '10.0' },
  { key: 'smoke_static_max_area_change_ratio', labelKey: 'settings.smokeStaticMaxAreaChangeRatio', hintKey: 'settings.smokeStaticMaxAreaChangeRatioHint', placeholder: '0.08' },
  { key: 'smoke_iou_threshold', labelKey: 'settings.smokeIouThreshold', hintKey: 'settings.smokeIouThresholdHint', placeholder: '0.3' },
]

const loading = ref(false)
const testingEmail = ref(false)
const creatingUser = ref(false)
const expertMode = ref(false)
const pluginDialogVisible = ref(false)
const activeSaveSection = ref('')
const activeRestoreSection = ref('')
const userForm = ref({
  username: '',
  password: '',
  role: 'operator',
})
const canManageSettings = computed(() => authStore.hasPermission('settings:*'))
const canViewLogs = computed(() => canViewProcessingLogs(
  authStore.hasPermission('sources:operate'),
  canManageSettings.value,
))
const hasSettingsAccess = computed(() => canManageSettings.value || authStore.canManageUsers || canViewLogs.value)
const form = ref({
  ui_language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  site_title: '',
  site_description: '',
  favicon_url: '/favicon.ico',
  vengine_host: '',
  detection_port: '',
  classification_port: '',
  action_port: '',
  ocr_port: '',
  upload_port: '',
  detection_enabled: 'true',
  classification_enabled: 'false',
  action_enabled: 'false',
  ocr_enabled: 'false',
  upload_enabled: 'false',
  mediamtx_rtsp_addr: '',
  mediamtx_webrtc_addr: '',
  mediamtx_username: '',
  mediamtx_password: '',
  email_from_address: '',
  email_smtp_password: '',
  email_to_addresses: '',
  email_cc_addresses: '',
  email_smtp_host: '',
  email_smtp_port: '587',
  email_smtp_use_tls: 'true',
  email_event_enabled: 'true',
  email_timed_enabled: 'false',
  email_event_subject_template: '[{site_title}] {event_label} alert from {source_name}',
  email_event_body_template: 'Event: {event_label}\nTime: {local_time} ({timezone})\nVideo source: {source_name} ({source_id})\nLabels: {labels}\nHighest confidence: {confidence_percent}\nDetection count: {detection_count}\nFrame ID: {frame_id}\nActive tracks: {active_tracks}',
  smoke_detection_model_name: 'smoke-fire-detection',
  smoke_detection_model_version: '',
  smoke_detection_confidence: '0.35',
  smoke_detection_nms: '0.7',
  smoke_min_confidence_smoke: '0.35',
  smoke_min_confidence_fire: '0.40',
  smoke_temporal_confirm_frames: '3',
  smoke_temporal_confirm_window: '2.0',
  smoke_max_miss_frames: '5',
  smoke_min_bbox_area_ratio: '0.0005',
  smoke_max_bbox_area_ratio: '0.60',
  smoke_min_aspect_ratio: '0.2',
  smoke_max_aspect_ratio: '8.0',
  smoke_motion_blur_max_speed: '100.0',
  smoke_motion_blur_min_confidence: '0.65',
  smoke_enable_appearance_filter: 'true',
  smoke_appearance_min_score: '0.42',
  smoke_appearance_min_history: '2',
  smoke_appearance_high_confidence_bypass: '0.82',
  smoke_overexposed_ratio_threshold: '0.18',
  smoke_white_object_ratio_threshold: '0.62',
  smoke_hard_boundary_density_threshold: '0.14',
  smoke_hard_laplacian_threshold: '520.0',
  smoke_fast_motion_energy_threshold: '0.16',
  smoke_static_confirm_frames: '5',
  smoke_static_max_center_shift: '10.0',
  smoke_static_max_area_change_ratio: '0.08',
  smoke_iou_threshold: '0.3',
  smoke_alarm_hold_time: '3.0',
  smoke_email_cooldown_seconds: '300',
  message_retention_days: '7',
  max_pull_workers: '',
  max_push_workers: '',
  max_cpu_workers: '',
})
const firstAllowedSectionKey = computed(() => {
  return getDefaultManagementSection(canManageSettings.value, authStore.canManageUsers, canViewLogs.value)
})
const currentSettingsPage = computed(() => (
  route.name === 'ManagementPlugin'
    ? 'plugins'
    : (route.params.section || '')
))
const currentPluginSceneId = computed(() => (
  route.name === 'ManagementPlugin' ? String(route.params.sceneId || '') : ''
))
const currentPluginScene = computed(() => sceneById(currentPluginSceneId.value))
const currentPluginSceneLabel = computed(() => (
  currentPluginScene.value ? sceneTabLabel(currentPluginScene.value.id) : ''
))
const isSitePage = computed(() => currentSettingsPage.value === 'site')
const isVenginePage = computed(() => currentSettingsPage.value === 'vengine')
const isNotificationsPage = computed(() => currentSettingsPage.value === 'notifications')
const isUsersPage = computed(() => currentSettingsPage.value === 'users')
const isLogsPage = computed(() => currentSettingsPage.value === 'logs')
const isPluginPage = computed(() => currentSettingsPage.value === 'plugins')
const settingsNavItems = computed(() => {
  const items = []
  if (canManageSettings.value) {
    items.push(
      { key: 'site', label: t('management.siteSettings'), hint: t('management.siteSettingsHint') },
    )
  }
  if (authStore.canManageUsers) {
    items.push({ key: 'users', label: t('settings.userManagement'), hint: t('settings.userManagementHint') })
  }
  if (canViewLogs.value) {
    items.push({ key: 'logs', label: t('management.processingLogs'), hint: t('processingLogs.subtitle') })
  }
  if (canManageSettings.value) {
    items.push(
      { key: 'vengine', label: t('management.vengineSettings'), hint: t('settings.serviceToggleTip') },
      { key: 'notifications', label: t('management.notificationSettings'), hint: t('settings.subtitle') },
      { key: 'plugins', label: t('management.pluginSettings'), hint: t('settings.pluginSectionHint') },
    )
  }
  return items
})

function sceneById(sceneId) {
  return sceneDefinitions.value.find((scene) => scene.id === sceneId)
}

function sceneTabLabel(sceneId) {
  const scene = sceneById(sceneId)
  if (!scene) return sceneId
  return locale.value === 'en-US' ? scene.label_en : scene.label_zh
}

const pluginCardPreviewLimit = 4

function sceneDefaultConfigRows(sceneId) {
  const config = sceneById(sceneId)?.default_config || {}
  return Object.entries(config).map(([key, value]) => ({
    key,
    value: formatConfigValue(value),
  }))
}

const previewConfigRowsByScene = computed(() => (
  Object.fromEntries(
    sceneDefinitions.value.map((scene) => [
      scene.id,
      sceneDefaultConfigRows(scene.id).slice(0, pluginCardPreviewLimit),
    ])
  )
))

function roiTagLabel(scene, tag) {
  return sceneScopedRoiTagLabel(scene, tag, locale.value)
}

function formatCreatedAt(value) {
  return formatTimeWithTimezone(value, appSettingsStore.timeZone)
}

function formatConfigValue(value) {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function pluginSettingKeys(sceneId) {
  return sceneId === SMOKE_SCENE_ID ? SMOKE_PLUGIN_SETTING_KEYS : []
}

function pickFormValues(keys) {
  return Object.fromEntries(keys.map((key) => [key, form.value[key]]))
}

function applyFormValues(data, keys) {
  keys.forEach((key) => {
    if (data[key] !== undefined) {
      form.value[key] = data[key]
    }
  })
}

function firstAllowedSettingsRoute() {
  return firstAllowedSectionKey.value
    ? { name: 'ManagementSection', params: { section: firstAllowedSectionKey.value } }
    : null
}

function replaceSettingsRoute(location) {
  const target = router.resolve(location)
  if (target.fullPath !== route.fullPath) {
    router.replace(location)
  }
}

function navigateToSettingsPage(pageKey) {
  router.push({ name: 'ManagementSection', params: { section: pageKey } })
}

function navigateToPluginScene(sceneId) {
  router.push({ name: 'ManagementPlugin', params: { sceneId } })
}

function navigateToPluginSettingsDialog(sceneId, tab = 'config') {
  navigateToPluginScene(sceneId)
  activePluginTab.value = tab
  pluginDialogVisible.value = true
}

function handlePluginDialogClosed() {
  if (route.name === 'ManagementPlugin') {
    router.push({ name: 'ManagementSection', params: { section: 'plugins' } })
  }
}

function ensureValidSettingsRoute() {
  const fallback = firstAllowedSettingsRoute()
  if (!fallback) {
    return
  }

  if (route.name === 'ManagementPlugin') {
    if (!canManageSettings.value) {
      replaceSettingsRoute(fallback)
      return
    }
    if (!currentPluginScene.value) {
      replaceSettingsRoute({ name: 'ManagementSection', params: { section: 'plugins' } })
      return
    }
    return
  }

  const section = route.params.section || ''
  if ((section === 'site' || section === 'vengine' || section === 'notifications') && canManageSettings.value) {
    return
  }
  if (section === 'users' && authStore.canManageUsers) {
    return
  }
  if (section === 'logs' && canViewLogs.value) {
    return
  }
  if (section === 'plugins' && canManageSettings.value) {
    return
  }
  replaceSettingsRoute(fallback)
}

async function reload() {
  loading.value = true
  try {
    if (canManageSettings.value) {
      const [data, scenes] = await Promise.all([
        appSettingsStore.fetchSettings(true),
        scenesApi.list(),
      ])
      Object.assign(form.value, data)
      sceneDefinitions.value = Array.isArray(scenes)
        ? scenes
        : DEFAULT_SCENE_DEFINITIONS
      expertMode.value = [
        data.max_pull_workers,
        data.max_push_workers,
        data.max_cpu_workers,
      ].some((value) => String(value ?? '').trim() !== '')
      try {
        const placeholderData = await settingsApi.emailTemplatePlaceholders()
        if (Array.isArray(placeholderData?.placeholders)) {
          emailTemplatePlaceholders.value = placeholderData.placeholders
        }
      } catch (_) {
        // Keep built-in placeholder list when the backend endpoint is unavailable.
      }
    }
    ensureValidSettingsRoute()
    if (authStore.canManageUsers) {
      await authStore.fetchUsers()
    }
  } catch (err) {
    ElMessage.error(t('settings.failedToLoad', { message: err.message }))
  } finally {
    loading.value = false
  }
}

async function restoreSection(sectionId, keys) {
  activeRestoreSection.value = sectionId
  try {
    const data = await appSettingsStore.fetchSettings(true)
    applyFormValues(data, keys)
    appSettingsStore.applyLanguage(form.value.ui_language)
    ElMessage.success(t('common.reset'))
  } catch (err) {
    ElMessage.error(t('settings.failedToLoad', { message: err.message }))
  } finally {
    activeRestoreSection.value = ''
  }
}

async function createUserAccount() {
  if (!userForm.value.username || !userForm.value.password) {
    ElMessage.warning(t('settings.missingFields'))
    return
  }
  creatingUser.value = true
  try {
    await authStore.createUser(userForm.value)
    userForm.value = {
      username: '',
      password: '',
      role: 'operator',
    }
    ElMessage.success(t('settings.createUserSuccess'))
  } catch (err) {
    ElMessage.error(t('settings.createUserFailed', { message: err.message }))
  } finally {
    creatingUser.value = false
  }
}

async function saveSection(sectionId, keys) {
  activeSaveSection.value = sectionId
  const previousSettings = appSettingsStore.settings || {}
  try {
    const processorConfigChanged = (
      keys.some(
        (key) => PROCESSOR_RESTART_SETTING_KEYS.includes(key)
          && String(previousSettings[key] || '') !== String(form.value[key] || '')
      )
    )
    const mediamtxRtspChanged = (
      keys.some((key) => ['mediamtx_rtsp_addr', 'mediamtx_username', 'mediamtx_password'].includes(key))
      && (
        String(previousSettings.mediamtx_rtsp_addr || '') !== String(form.value.mediamtx_rtsp_addr || '')
        || String(previousSettings.mediamtx_username || '') !== String(form.value.mediamtx_username || '')
        || String(previousSettings.mediamtx_password || '') !== String(form.value.mediamtx_password || '')
      )
    )
    const mediamtxWebrtcChanged = (
      keys.some((key) => ['mediamtx_webrtc_addr', 'mediamtx_username', 'mediamtx_password'].includes(key))
      && (
        String(previousSettings.mediamtx_webrtc_addr || '') !== String(form.value.mediamtx_webrtc_addr || '')
        || String(previousSettings.mediamtx_username || '') !== String(form.value.mediamtx_username || '')
        || String(previousSettings.mediamtx_password || '') !== String(form.value.mediamtx_password || '')
      )
    )
    let runningSourceIds = []
    if (processorConfigChanged || mediamtxRtspChanged) {
      await sourceStore.syncProcessorStatus()
      runningSourceIds = sourceStore.getRunningSourceIdsSnapshot()
    }

    const data = await appSettingsStore.updateSettings(pickFormValues(keys))
    Object.assign(form.value, data)
    appSettingsStore.applyLanguage(form.value.ui_language)
    if (mediamtxRtspChanged || mediamtxWebrtcChanged) {
      await sourceStore.fetchSources()
      sourceStore.syncAssignedSourceReferences()
    }

    if (!processorConfigChanged && !mediamtxRtspChanged) {
      ElMessage.success(t('settings.settingsSaved'))
      return
    }

    if (!runningSourceIds.length) {
      ElMessage.success(
        processorConfigChanged
          ? t('settings.settingsSavedRestartRequired')
          : t('settings.settingsSavedSourceUrlsSynced')
      )
      return
    }

    const restartResult = await sourceStore.restartProcessing(runningSourceIds)
    if (restartResult.status === 'partial') {
      ElMessage.warning(
        t('settings.settingsSavedRestartPartial', {
          restarted: restartResult.restarted,
          failed: restartResult.failed.length,
        })
      )
      return
    }

    ElMessage.success(
      t('settings.settingsSavedRestarted', { count: restartResult.restarted })
    )
  } catch (err) {
    ElMessage.error(t('settings.failedToSave', { message: err.message }))
  } finally {
    activeSaveSection.value = ''
  }
}

async function testEmailConfig() {
  testingEmail.value = true
  try {
    const payload = {
      email_smtp_host: form.value.email_smtp_host,
      email_smtp_port: form.value.email_smtp_port,
      email_smtp_use_tls: form.value.email_smtp_use_tls,
      email_from_address: form.value.email_from_address,
      email_smtp_password: form.value.email_smtp_password,
      email_to_addresses: form.value.email_to_addresses,
      email_cc_addresses: form.value.email_cc_addresses,
    }
    const result = await appSettingsStore.testEmail(payload)
    ElMessage.success(
      t('settings.testEmailSuccess', {
        status: result.status || 'SUCCESS',
      })
    )
  } catch (err) {
    ElMessage.error(t('settings.testEmailFailed', { message: err.message }))
  } finally {
    testingEmail.value = false
  }
}

function onSiteIconChange(uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return

  const maxBytes = 1024 * 1024
  if (raw.size > maxBytes) {
    ElMessage.warning(t('settings.iconTooLarge'))
    return
  }

  const reader = new FileReader()
  reader.onload = () => {
    if (typeof reader.result === 'string') {
      form.value.favicon_url = reader.result
    }
  }
  reader.readAsDataURL(raw)
}

function resetSiteIcon() {
  form.value.favicon_url = '/favicon.ico'
}

function resetSmokeAdvancedThresholds() {
  Object.assign(form.value, SMOKE_ADVANCED_DEFAULTS)
}

watch(
  [
    () => route.fullPath,
    canManageSettings,
    () => authStore.canManageUsers,
    () => sceneDefinitions.value.length,
  ],
  () => {
    ensureValidSettingsRoute()
    pluginDialogVisible.value = route.name === 'ManagementPlugin' && Boolean(currentPluginScene.value)
  },
  { immediate: true }
)

onMounted(async () => {
  await reload()
  ensureValidSettingsRoute()
})
</script>

<style scoped>
.settings-page {
  --management-nav-card-bg-start: rgba(14, 21, 40, 0.92);
  --management-nav-card-bg-end: rgba(11, 17, 31, 0.78);
  --management-nav-card-active-start: rgba(34, 74, 148, 0.85);
  --management-nav-card-active-end: rgba(15, 28, 58, 0.95);
  height: 100%;
  overflow-y: auto;
  padding: 24px 28px 32px;
  background:
    radial-gradient(circle at 0% 0%, rgba(64, 158, 255, 0.13), transparent 42%),
    radial-gradient(circle at 100% 100%, rgba(0, 178, 169, 0.12), transparent 40%),
    #0d0d1a;
}

.settings-shell {
  max-width: 1360px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.settings-head {
  padding: 4px 4px 0;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-line h1 {
  font-size: 24px;
  font-weight: 700;
  color: #e9f0ff;
}

.settings-head p {
  margin-top: 6px;
  color: #9ba8be;
  font-size: 13px;
}

.management-role-tag {
  margin-top: 10px;
}

.settings-form {
  background: rgba(16, 21, 37, 0.92);
  border: 1px solid #26314d;
  border-radius: 18px;
  padding: 18px;
}

.settings-page-toolbar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 18px;
}

.settings-page-nav {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.management-expert-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid #2f3a5b;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.08), rgba(255, 255, 255, 0.02));
}

.management-expert-toggle h3 {
  color: #dbe7ff;
  font-size: 14px;
  margin-bottom: 4px;
}

.management-expert-toggle p {
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.45;
}

.settings-page-nav__button {
  appearance: none;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  min-height: 84px;
  padding: 14px 16px;
  border: 1px solid #2f3a5b;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--management-nav-card-bg-start), var(--management-nav-card-bg-end));
  color: #dbe7ff;
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.settings-page-nav__button:hover {
  transform: translateY(-1px);
  border-color: #4b6198;
  box-shadow: 0 12px 28px rgba(6, 10, 24, 0.28);
}

.settings-page-nav__button.is-active {
  border-color: rgba(64, 158, 255, 0.7);
  background: linear-gradient(135deg, var(--management-nav-card-active-start), var(--management-nav-card-active-end));
  box-shadow: 0 16px 32px rgba(19, 50, 103, 0.3);
}

.settings-page-nav__label-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.settings-page-nav__label {
  font-size: 15px;
  font-weight: 700;
}

.settings-page-nav__state {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #7cc2ff;
  box-shadow: 0 0 0 4px rgba(124, 194, 255, 0.18);
}

.settings-page-nav__hint {
  color: #9fb0cf;
  font-size: 12px;
  line-height: 1.5;
}

.settings-page-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.management-logs-panel {
  min-height: 720px;
}

.settings-page-panel__head {
  padding: 4px 4px 0;
}

.settings-page-panel__head h2 {
  margin-bottom: 6px;
  color: #eef4ff;
  font-size: 18px;
}

.settings-page-panel__head p {
  color: #93a3bf;
  font-size: 13px;
}

.settings-section {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid #30364d;
  border-radius: 16px;
  padding: 18px 18px 14px;
  margin-bottom: 16px;
}

.settings-section h2 {
  font-size: 16px;
  color: #e5eeff;
  margin-bottom: 6px;
}

.settings-top-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.settings-top-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: #2d3853;
}

.settings-top-tabs :deep(.el-tabs__item) {
  color: #aebbd7;
  padding: 0 18px;
}

.settings-top-tabs :deep(.el-tabs__item.is-active) {
  color: #eef4ff;
}

.settings-top-tabs :deep(.el-tabs__active-bar) {
  background-color: #409eff;
}

.settings-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px 18px;
}

.settings-form-grid.wide-grid {
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.settings-form-grid.compact-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.form-grid-span-full {
  grid-column: 1 / -1;
}

.icon-upload-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.icon-path-input {
  min-width: min(420px, 100%);
  flex: 1 1 320px;
}

.roi-tags-editor {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.roi-tag-item {
  margin: 0;
}

.roi-tag-empty {
  color: #7f8bad;
  font-size: 12px;
}

.empty-list-message {
  color: #7f8bad;
  font-size: 12px;
}

.scene-scope-line {
  color: #8aa6d9;
  font-size: 12px;
  margin: -2px 0 10px;
}

.roi-tag-input-row {
  display: flex;
  gap: 8px;
}

.placeholder-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.plugin-tag-list,
.plugin-config-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 24px;
}

.plugin-launcher-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.plugin-launcher-card {
  margin-bottom: 0;
}

.plugin-launcher-card__summary {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.plugin-launcher-card__group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plugin-launcher-card__label {
  color: #c7d5ef;
  font-size: 12px;
  font-weight: 600;
}

.plugin-dialog-hint {
  margin-bottom: 14px;
  color: #8f9fbe;
  font-size: 13px;
  line-height: 1.5;
}

.settings-split-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.settings-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.user-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #30364d;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  color: #d7e3ff;
  font-size: 13px;
}

.user-created-at {
  margin-left: auto;
  color: #8aa6d9;
  font-size: 12px;
}

.section-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.section-card__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.section-card__actions.single-action {
  justify-content: flex-end;
}

.expert-card {
  margin-top: 18px;
  padding: 16px;
  border: 1px solid #2f3a5b;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
}

.compact-section {
  max-width: 760px;
}

.switch-field-stack {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.smoke-threshold-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
  width: 100%;
}

.smoke-threshold-item {
  padding: 12px;
  border: 1px solid #2d3650;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
}

.smoke-threshold-label {
  color: #c8d5f0;
  font-size: 12px;
  margin-bottom: 6px;
}

.roi-tag-hint {
  margin-top: 6px;
  color: #8f9fbe;
  font-size: 12px;
}

.info-tip {
  margin-top: 8px;
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.45;
}


.field-stack {
  width: 100%;
}

.form-hint {
  margin-top: 6px;
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.45;
}

.port-switch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.port-switch-row .el-input {
  flex: 1;
}

:deep(.el-form-item__label) {
  color: #aab7d2;
  white-space: normal;
  line-height: 1.5;
}

:deep(.el-form-item__content) {
  width: 100%;
}

@media (max-width: 768px) {
  .settings-page {
    padding: 14px 14px 24px;
  }

  .plugin-launcher-grid {
    grid-template-columns: 1fr;
  }

  .settings-form {
    padding: 14px;
  }

  .settings-page-nav {
    grid-template-columns: 1fr;
  }

  .title-line h1 {
    font-size: 18px;
  }

  .section-card__head,
  .management-expert-toggle {
    flex-direction: column;
    align-items: stretch;
  }

  .port-switch-row,
  .switch-field-stack,
  .icon-upload-group,
  .roi-tag-input-row {
    flex-wrap: wrap;
  }

  .icon-path-input {
    min-width: 100%;
  }
}
</style>
