<template>
  <div class="settings-page">
    <div class="settings-shell">
      <div v-if="!hasSettingsAccess" class="settings-section section-card">
        <div class="title-line">
          <el-icon :size="20"><Setting /></el-icon>
          <h2>{{ t('management.title') }}</h2>
        </div>
        <p class="info-tip">{{ t('management.subtitle') }}</p>
        <p class="info-tip">{{ t('settings.noPermission') }}</p>
      </div>

      <el-form
        v-else
        :model="form"
        class="settings-form"
        label-position="top"
        v-loading="loading"
      >
        <div class="settings-layout">
          <aside class="settings-sidebar">
            <section class="settings-overview-card">
              <div class="title-line">
                <el-icon :size="20"><Setting /></el-icon>
                <h1>{{ t('management.title') }}</h1>
              </div>
              <p>{{ t('management.subtitle') }}</p>
              <el-tag v-if="authStore.role" size="small" effect="dark" class="management-role-tag">
                {{ t('auth.signedInAs', { role: t(`auth.roles.${authStore.role}`) }) }}
              </el-tag>
              <div class="settings-overview-stats">
                <div v-for="item in managementOverviewCards" :key="item.key" class="settings-overview-stat">
                  <span class="settings-overview-stat__label">{{ item.label }}</span>
                  <strong class="settings-overview-stat__value">{{ item.value }}</strong>
                </div>
              </div>
            </section>

            <section class="settings-sidebar-card">
              <div class="settings-sidebar-card__head">
                <h3>{{ t('settings.quickNavigation') }}</h3>
                <p>{{ t('settings.quickNavigationHint') }}</p>
              </div>
              <div class="settings-page-nav settings-page-nav--sidebar">
                <button
                  v-for="item in settingsNavItems"
                  :key="item.key"
                  type="button"
                  class="settings-page-nav__button"
                  :class="{ 'is-active': currentSettingsPage === item.key }"
                  @click="navigateToSettingsPage(item.key)"
                >
                  <span class="settings-page-nav__label-row">
                    <span class="settings-page-nav__title-wrap">
                      <el-icon class="settings-page-nav__icon"><component :is="item.icon" /></el-icon>
                      <span class="settings-page-nav__label">{{ item.label }}</span>
                    </span>
                    <span v-if="currentSettingsPage === item.key" class="settings-page-nav__state" />
                  </span>
                  <span class="settings-page-nav__hint">{{ item.hint }}</span>
                </button>
              </div>
            </section>

            <section v-if="canManageSettings" class="management-expert-toggle">
              <div>
                <h3>{{ t('settings.configurationMode') }}</h3>
                <p>{{ t('settings.expertModeHint') }}</p>
              </div>
              <el-switch v-model="expertMode" />
            </section>
          </aside>

          <div class="settings-main">
            <section class="settings-current-panel">
              <div>
                <span class="settings-current-panel__eyebrow">{{ t('settings.currentSection') }}</span>
                <h2>{{ currentSettingsNavItem?.label || t('management.title') }}</h2>
                <p>{{ currentSettingsNavItem?.hint || t('management.subtitle') }}</p>
              </div>
            </section>

            <section v-if="isSitePage" class="settings-page-panel">
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
                  <div class="settings-inline-field-row form-grid-span-full">
                    <el-form-item :label="t('settings.siteTitle')">
                      <el-input v-model="form.site_title" :placeholder="t('settings.siteTitle')" />
                    </el-form-item>
                    <el-form-item :label="t('settings.siteDescription')">
                      <el-input
                        v-model="form.site_description"
                        :placeholder="t('settings.siteDescription')"
                      />
                    </el-form-item>
                  </div>
                  <el-form-item :label="t('settings.activePlugin')" class="form-grid-span-full">
                    <div class="field-stack">
                      <el-select v-model="form.active_plugin_id" style="width: 100%">
                        <el-option
                          v-for="scene in sceneDefinitions"
                          :key="scene.id"
                          :label="sceneTabLabel(scene.id)"
                          :value="scene.id"
                        />
                      </el-select>
                      <p class="form-hint">{{ t('settings.activePluginHint') }}</p>
                    </div>
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
                      <el-tag v-if="isEmbeddedFavicon" type="success" effect="plain" class="site-icon-uploaded-tag">
                        {{ t('settings.siteIconUploaded') }}
                      </el-tag>
                      <el-input v-else v-model="form.favicon_url" placeholder="/favicon.ico" class="icon-path-input" />
                      <p class="form-hint icon-upload-hint">
                        {{ isEmbeddedFavicon ? t('settings.siteIconUploadedHint') : t('settings.faviconUrlHint') }}
                      </p>
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
                  <div class="settings-inline-field-row form-grid-span-full">
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
                </div>
              </section>
            </el-tab-pane>
          </el-tabs>
        </section>

            <section v-else-if="isVenginePage" class="settings-page-panel">
          <section class="settings-section section-card">
            <div class="section-card__head">
              <div>
                <h2>{{ t('settings.platformSectionVengine') }}</h2>
                <p class="info-tip">{{ t('settings.serviceToggleTip') }}</p>
              </div>
              <div class="section-card__actions">
                <el-button
                  :loading="activeRestoreSection === 'platform-vengine'"
                  @click="restoreSection('platform-vengine', VENGINE_SERVICE_SETTING_KEYS)"
                >
                  {{ t('settings.restoreSection') }}
                </el-button>
                <el-button
                  type="primary"
                  :loading="activeSaveSection === 'platform-vengine'"
                  @click="saveSection('platform-vengine', VENGINE_SERVICE_SETTING_KEYS)"
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

          </section>
          <section v-if="expertMode" class="settings-section section-card">
            <div class="section-card__head">
              <div>
                <h2>{{ t('settings.threadPools') }}</h2>
                <p class="info-tip">{{ t('settings.threadPoolsHint') }}</p>
              </div>
              <div class="section-card__actions">
                <el-button
                  :loading="activeRestoreSection === 'platform-thread-pools'"
                  @click="restoreSection('platform-thread-pools', THREAD_POOL_SETTING_KEYS)"
                >
                  {{ t('settings.restoreSection') }}
                </el-button>
                <el-button
                  type="primary"
                  :loading="activeSaveSection === 'platform-thread-pools'"
                  @click="saveSection('platform-thread-pools', THREAD_POOL_SETTING_KEYS)"
                >
                  {{ t('settings.saveSection') }}
                </el-button>
              </div>
            </div>
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

            <section v-else-if="isLogsPage" class="settings-page-panel management-logs-panel">
          <ProcessingLogs embedded />
        </section>

        <section v-else-if="isNotificationsPage" class="settings-page-panel">
          <el-tabs v-model="activeNotificationTab" class="settings-top-tabs">
            <el-tab-pane :label="t('settings.notificationInstancesSection')" name="instances">
              <NotificationInstancesPanel />
            </el-tab-pane>

            <el-tab-pane :label="t('settings.notificationRetentionSection')" name="retention">
              <section class="settings-section section-card">
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
                </div>
              </section>
            </el-tab-pane>
          </el-tabs>
        </section>

            <section v-else-if="isUsersPage" class="settings-page-panel">
          <div class="users-management-layout">
            <section class="settings-section section-card users-management-main">
              <div class="section-card__head">
                <div>
                  <h2>{{ t('settings.accountList') }}</h2>
                  <p class="info-tip">{{ t('settings.userManagementHint') }}</p>
                </div>
                <div class="section-card__actions">
                  <el-space :size="10" wrap alignment="center">
                    <el-button
                      type="primary"
                      size="large"
                      :aria-label="t('settings.createUser')"
                      @click="createUserDialogVisible = true"
                    >
                      {{ t('settings.createUser') }}
                    </el-button>
                  </el-space>
                </div>
              </div>
              <div class="user-management-table-shell">
                <el-table :data="authStore.users" class="user-table user-management-table" empty-text=" " size="default">
                  <el-table-column prop="username" :label="t('settings.username')" :min-width="USER_MANAGEMENT_USERNAME_MIN_WIDTH">
                    <template #default="{ row }">
                      <span class="user-identity">
                        <span class="user-identity__name" :title="row.username">{{ row.username }}</span>
                        <el-tag v-if="row.username === authStore.user?.username" class="current-account-tag" size="small" type="info" effect="plain">
                          {{ t('settings.currentAccountTag') }}
                        </el-tag>
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('settings.userRole')" width="96">
                    <template #default="{ row }">
                      <el-tag size="small" effect="dark">{{ t(`auth.roles.${row.role}`) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('settings.userStatus')" width="96">
                    <template #default="{ row }">
                      <el-tag v-if="row.is_banned" size="small" type="danger" effect="dark">
                        {{ t('settings.statusBanned') }}
                      </el-tag>
                      <el-tag v-else-if="row.expired" size="small" type="warning" effect="dark">
                        {{ t('settings.statusExpired') }}
                      </el-tag>
                      <el-tag v-else size="small" type="success" effect="plain">
                        {{ t('settings.statusActive') }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('settings.userExpiresAt')" width="170">
                    <template #default="{ row }">
                      <span v-if="row.expires_at">{{ formatCreatedAt(row.expires_at) }}</span>
                      <span v-else class="user-created-at">{{ t('settings.userNeverExpires') }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('settings.createdAt')" width="160">
                    <template #default="{ row }">
                      <span class="user-created-at">{{ formatCreatedAt(row.created_at) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('common.actions')" width="180" align="right">
                    <template #default="{ row }">
                      <el-space :size="4" alignment="center" class="user-action-space">
                        <el-tooltip :content="t('common.edit')" placement="top">
                          <el-button
                            size="small"
                            circle
                            :icon="Edit"
                            :aria-label="t('common.edit')"
                            @click="openEditUser(row)"
                          />
                        </el-tooltip>
                        <el-tooltip :content="t('settings.resetPassword')" placement="top">
                          <el-button
                            size="small"
                            circle
                            type="warning"
                            :icon="Key"
                            :aria-label="t('settings.resetPassword')"
                            @click="openResetPassword(row)"
                          />
                        </el-tooltip>
                        <el-tooltip :content="row.is_banned ? t('settings.unbanUser') : t('settings.banUser')" placement="top">
                          <el-button
                            size="small"
                            circle
                            :type="row.is_banned ? 'success' : 'warning'"
                            :icon="row.is_banned ? Unlock : Lock"
                            :disabled="!canToggleBan(row)"
                            :aria-label="row.is_banned ? t('settings.unbanUser') : t('settings.banUser')"
                            @click="toggleUserBan(row)"
                          />
                        </el-tooltip>
                        <el-tooltip :content="t('common.delete')" placement="top">
                          <el-button
                            size="small"
                            circle
                            type="danger"
                            :icon="Delete"
                            :disabled="!canDeleteUser(row)"
                            :aria-label="t('common.delete')"
                            @click="deleteUserAccount(row)"
                          />
                        </el-tooltip>
                      </el-space>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <span v-if="!authStore.users.length" class="empty-list-message">{{ t('settings.noUsers') }}</span>
            </section>

            <div class="users-management-side">
              <section v-if="canManageSettings" class="settings-section section-card">
                <div class="section-card__head">
                  <div>
                    <h2>{{ t('settings.accountExpirationDefaults') }}</h2>
                    <p class="info-tip">{{ t('settings.accountExpirationDefaultsHint') }}</p>
                  </div>
                </div>
                <div class="numeric-setting-list">
                  <el-form-item :label="t('settings.expirationDaysUser')" class="numeric-setting-item">
                    <el-input-number
                      :model-value="Number(form.account_expiration_days_user || 0)"
                      :min="0"
                      class="themed-number-input"
                      @update:model-value="form.account_expiration_days_user = $event == null ? '' : String($event)"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.expirationDaysOperator')" class="numeric-setting-item">
                    <el-input-number
                      :model-value="Number(form.account_expiration_days_operator || 0)"
                      :min="0"
                      class="themed-number-input"
                      @update:model-value="form.account_expiration_days_operator = $event == null ? '' : String($event)"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.expirationDaysAdmin')" class="numeric-setting-item">
                    <el-input-number
                      :model-value="Number(form.account_expiration_days_admin || 0)"
                      :min="0"
                      class="themed-number-input"
                      @update:model-value="form.account_expiration_days_admin = $event == null ? '' : String($event)"
                    />
                  </el-form-item>
                </div>
                <div class="settings-action-footer">
                  <el-button
                    type="primary"
                    :loading="activeSaveSection === 'accountExpiration'"
                    @click="saveAccountExpirationSettings"
                  >
                    {{ t('common.save') }}
                  </el-button>
                </div>
              </section>

              <section v-if="canManageSettings" class="settings-section section-card">
                <div class="section-card__head">
                  <div>
                    <h2>{{ t('settings.loginSecurity') }}</h2>
                    <p class="info-tip">{{ t('settings.loginSecurityHint') }}</p>
                  </div>
                </div>
                <div class="numeric-setting-list">
                  <el-form-item :label="t('settings.lockoutMaxAttempts')" class="numeric-setting-item">
                    <el-input-number
                      :model-value="Number(form.login_lockout_max_attempts || 0)"
                      :min="0"
                      class="themed-number-input"
                      @update:model-value="form.login_lockout_max_attempts = $event == null ? '' : String($event)"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.lockoutWindowSeconds')" class="numeric-setting-item">
                    <el-input-number
                      :model-value="Number(form.login_lockout_window_seconds || 0)"
                      :min="0"
                      class="themed-number-input"
                      @update:model-value="form.login_lockout_window_seconds = $event == null ? '' : String($event)"
                    />
                  </el-form-item>
                  <el-form-item :label="t('settings.lockoutDurationSeconds')" class="numeric-setting-item">
                    <el-input-number
                      :model-value="Number(form.login_lockout_duration_seconds || 0)"
                      :min="0"
                      class="themed-number-input"
                      @update:model-value="form.login_lockout_duration_seconds = $event == null ? '' : String($event)"
                    />
                  </el-form-item>
                </div>
                <p class="info-tip info-tip--block">{{ t('settings.lockoutDurationSecondsHint') }}</p>
                <div class="settings-action-footer">
                  <el-button
                    type="primary"
                    :loading="activeSaveSection === 'loginSecurity'"
                    @click="saveLoginSecuritySettings"
                  >
                    {{ t('common.save') }}
                  </el-button>
                </div>

                <el-divider />

                <div class="section-card__head">
                  <div>
                    <h3>{{ t('settings.blockedIps') }}</h3>
                    <p class="info-tip">{{ t('settings.blockedIpsHint') }}</p>
                  </div>
                  <div class="section-card__actions">
                    <el-button type="warning" size="small" @click="manualBlockDialogVisible = true">
                      {{ t('settings.manualBlockIp') }}
                    </el-button>
                    <el-button size="small" @click="reloadBlockedIps">{{ t('common.refresh') }}</el-button>
                  </div>
                </div>
                <div class="user-management-table-shell">
                  <el-table :data="blockedIps" class="user-management-table" empty-text=" " size="default">
                    <el-table-column prop="ip" label="IP" />
                    <el-table-column :label="t('settings.blockedAt')">
                      <template #default="{ row }">
                        <span>{{ formatCreatedAt(row.blocked_at) }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column :label="t('settings.blockedUntil')">
                      <template #default="{ row }">
                        <span v-if="row.blocked_until">{{ formatCreatedAt(row.blocked_until) }}</span>
                        <span v-else>{{ t('settings.blockedUntilManual') }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column prop="reason" :label="t('settings.blockedReason')" />
                    <el-table-column :label="t('common.actions')" width="140" align="right">
                      <template #default="{ row }">
                        <el-button size="small" type="success" @click="unblockIp(row)">
                          {{ t('settings.unblockIp') }}
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
                <span v-if="!blockedIps.length" class="empty-list-message">{{ t('settings.noBlockedIps') }}</span>

              </section>
            </div>
          </div>
        </section>

            <section v-else-if="isPluginPage" class="settings-page-panel">
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
              </div>
            </section>
          </div>
            </section>
          </div>
        </div>

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
                <template v-else-if="currentPluginScene.id === FIRE_DOOR_SCENE_ID">
                  <section class="settings-section section-card">
                    <div class="section-card__head">
                      <div>
                        <h2>{{ t('settings.fireDoorScene') }}</h2>
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
                      <el-form-item :label="t('settings.fireDoorClassificationModelName')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_classification_model_name" placeholder="fire-door-classification" />
                          <p class="form-hint">{{ t('settings.fireDoorClassificationModelNameHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorClassificationConfidence')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_classification_confidence" placeholder="0.50" />
                          <p class="form-hint">{{ t('settings.fireDoorClassificationConfidenceHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorOpenLabels')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_open_labels" placeholder="open,OPEN,Opened" />
                          <p class="form-hint">{{ t('settings.fireDoorOpenLabelsHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorClosedLabels')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_closed_labels" placeholder="closed,CLOSED,Close" />
                          <p class="form-hint">{{ t('settings.fireDoorClosedLabelsHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorAlarmLabels')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_alarm_labels" placeholder="open" />
                          <p class="form-hint">{{ t('settings.fireDoorAlarmLabelsHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorTemporalConfirmFrames')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_temporal_confirm_frames" placeholder="1" />
                          <p class="form-hint">{{ t('settings.fireDoorTemporalConfirmFramesHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorTemporalConfirmWindow')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_temporal_confirm_window" placeholder="2.0" />
                          <p class="form-hint">{{ t('settings.fireDoorTemporalConfirmWindowHint') }}</p>
                        </div>
                      </el-form-item>
                      <el-form-item :label="t('settings.fireDoorAlarmHoldTime')">
                        <div class="field-stack">
                          <el-input v-model="form.fire_door_alarm_hold_time" placeholder="3.0" />
                          <p class="form-hint">{{ t('settings.fireDoorAlarmHoldTimeHint') }}</p>
                        </div>
                      </el-form-item>
                    </div>
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

            </el-tabs>
          </template>
        </el-dialog>

        <el-dialog
          v-model="createUserDialogVisible"
          :title="t('settings.createUser')"
          width="min(520px, calc(100vw - 32px))"
          class="user-management-dialog"
          destroy-on-close
        >
          <el-form label-position="top" class="user-dialog-form" size="large">
            <p class="plugin-dialog-hint">{{ t('settings.temporaryPasswordHint') }}</p>
            <el-row :gutter="16" class="dialog-compact-grid">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('settings.username')" required>
                  <el-input
                    v-model="userForm.username"
                    autocomplete="username"
                    aria-required="true"
                    @keyup.enter="createUserAccount"
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('settings.userRole')">
                  <el-select v-model="userForm.role" class="dialog-compact-control">
                    <el-option value="user" :label="t('auth.roles.user')" />
                    <el-option value="operator" :label="t('auth.roles.operator')" />
                    <el-option value="admin" :label="t('auth.roles.admin')" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('settings.temporaryPassword')" required>
                  <el-input
                    v-model="userForm.password"
                    type="password"
                    show-password
                    autocomplete="new-password"
                    aria-required="true"
                    @keyup.enter="createUserAccount"
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('settings.userExpiresAt')">
                  <el-date-picker
                    v-model="userForm.expires_at"
                    type="datetime"
                    class="dialog-compact-control"
                    :placeholder="t('settings.userExpiresAtPlaceholder')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ssZ"
                  />
                  <p class="info-tip">{{ t('settings.userExpiresAtHint') }}</p>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
          <template #footer>
            <div class="user-dialog-footer">
              <el-space :size="10" wrap alignment="center">
                <el-button @click="createUserDialogVisible = false">{{ t('common.cancel') }}</el-button>
                <el-button type="primary" :loading="creatingUser" @click="createUserAccount">
                  {{ t('settings.createUser') }}
                </el-button>
              </el-space>
            </div>
          </template>
        </el-dialog>

        <el-dialog
          v-model="editUserDialog.visible"
          :title="t('settings.editUserTitle', { username: editUserDialog.username })"
          width="min(520px, calc(100vw - 32px))"
          class="user-management-dialog"
          destroy-on-close
        >
          <el-form label-position="top" class="user-dialog-form" size="large">
            <el-row :gutter="16" class="dialog-compact-grid">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('settings.userRole')">
                  <el-select v-model="editUserDialog.role" class="dialog-compact-control">
                    <el-option value="user" :label="t('auth.roles.user')" />
                    <el-option value="operator" :label="t('auth.roles.operator')" />
                    <el-option value="admin" :label="t('auth.roles.admin')" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="t('settings.userExpiresAt')">
                  <el-date-picker
                    v-model="editUserDialog.expires_at"
                    type="datetime"
                    class="dialog-compact-control"
                    :placeholder="t('settings.userExpiresAtPlaceholder')"
                    format="YYYY-MM-DD HH:mm"
                    value-format="YYYY-MM-DDTHH:mm:ssZ"
                    clearable
                  />
                  <p class="info-tip">{{ t('settings.userExpiresAtHint') }}</p>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
          <template #footer>
            <div class="user-dialog-footer">
              <el-space :size="10" wrap alignment="center">
                <el-button @click="editUserDialog.visible = false">{{ t('common.cancel') }}</el-button>
                <el-button type="primary" @click="submitEditUser">{{ t('common.save') }}</el-button>
              </el-space>
            </div>
          </template>
        </el-dialog>

        <el-dialog
          v-model="resetPasswordDialog.visible"
          :title="t('settings.resetPasswordTitle', { username: resetPasswordDialog.username })"
          width="min(520px, calc(100vw - 32px))"
          class="user-management-dialog"
          destroy-on-close
        >
          <el-form label-position="top" class="user-dialog-form" size="large">
            <el-form-item :label="t('auth.newPassword')" required>
              <el-input
                v-model="resetPasswordDialog.new_password"
                type="password"
                show-password
                autocomplete="new-password"
                class="dialog-password-input"
                @keyup.enter="submitResetPassword"
              />
            </el-form-item>
          </el-form>
          <template #footer>
            <div class="user-dialog-footer">
              <el-space :size="10" wrap alignment="center">
                <el-button @click="resetPasswordDialog.visible = false">{{ t('common.cancel') }}</el-button>
                <el-button type="primary" @click="submitResetPassword">{{ t('settings.resetPassword') }}</el-button>
              </el-space>
            </div>
          </template>
        </el-dialog>

        <el-dialog
          v-model="manualBlockDialogVisible"
          :title="t('settings.manualBlockIp')"
          width="min(520px, calc(100vw - 32px))"
          class="user-management-dialog"
          destroy-on-close
        >
          <el-form label-position="top" class="user-dialog-form" size="large">
            <el-form-item label="IP" required>
              <el-input v-model="manualBlockForm.ip" placeholder="e.g. 192.168.1.42" @keyup.enter="manualBlockIp" />
            </el-form-item>
            <el-form-item :label="t('settings.lockoutDurationSeconds')">
              <el-input-number
                :model-value="Number(manualBlockForm.duration_seconds || 0)"
                :min="0"
                class="themed-number-input themed-number-input--dialog"
                @update:model-value="manualBlockForm.duration_seconds = $event == null ? '' : String($event)"
              />
              <p class="info-tip">{{ t('settings.lockoutDurationSecondsHint') }}</p>
            </el-form-item>
            <el-form-item :label="t('settings.blockedReason')">
              <el-input v-model="manualBlockForm.reason" @keyup.enter="manualBlockIp" />
            </el-form-item>
          </el-form>
          <template #footer>
            <div class="user-dialog-footer">
              <el-space :size="10" wrap alignment="center">
                <el-button @click="manualBlockDialogVisible = false">{{ t('common.cancel') }}</el-button>
                <el-button type="warning" @click="manualBlockIp">{{ t('settings.manualBlockIp') }}</el-button>
              </el-space>
            </div>
          </template>
        </el-dialog>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bell, Crop, Delete, Document, Edit, Key, Lock, Monitor, Setting, Unlock, User } from '@element-plus/icons-vue'
import ElMessage from 'element-plus/es/components/message/index'
import ElMessageBox from 'element-plus/es/components/message-box/index'
import { useRoute, useRouter } from 'vue-router'
import { localeOptions } from '../i18n/index.js'
import { accessApi, scenesApi } from '../api/index.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { useAuthStore } from '../stores/auth.js'
import { useSourceStore } from '../stores/source.js'
import { canViewProcessingLogs, getDefaultManagementSection } from '../utils/settingsRoutes.js'
import { sceneScopedRoiTagLabel } from '../utils/roiTags.js'
import { formatSortableDateTimeWithTimezone } from '../utils/time.js'
import NotificationInstancesPanel from '../components/NotificationInstancesPanel.vue'
import ProcessingLogs from './ProcessingLogs.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const USER_MANAGEMENT_USERNAME_MIN_WIDTH = 180
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const sourceStore = useSourceStore()
const languageOptions = localeOptions
const retentionDayOptions = [7, 15, 21, 30]
// Also referenced by the template to decide whether to render smoke-specific fields.
// 模板中也会使用它判断是否渲染烟火插件专属字段。
const SMOKE_SCENE_ID = 'smoke'
const FIRE_DOOR_SCENE_ID = 'fire_door'
const activePlatformTab = ref('overview')
const activeNotificationTab = ref('instances')
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
    id: 'fire_door',
    label_zh: '消防门检测',
    label_en: 'Fire Door Detection',
    description: 'Classifies one or more fire-door ROIs and alerts when a configured open state is confirmed.',
    default_roi_tags: ['fire_door'],
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
const emailTemplatePlaceholders = ref(['site_title', 'timestamp', 'local_time', 'timezone', 'source_name', 'source_id', 'event_type', 'event_label', 'message', 'labels', 'confidence', 'confidence_percent', 'detection_count', 'frame_id', 'active_tracks', 'original_image', 'detected_image', 'original_image_url', 'detected_image_url', 'has_original_image', 'has_detected_image', 'source_rtsp_url', 'source_route_path', 'source_host', 'source_host_or_ip', 'source_ip', 'source_port', 'source_remark', 'source_description', 'roi_id', 'roi_tag', 'roi_index', 'roi_count', 'door_state', 'door_state_label', 'alarm_label', 'open_count', 'closed_count'])
const SMOKE_PLACEHOLDERS = new Set(['detection_count', 'frame_id', 'active_tracks'])
const FIRE_DOOR_PLACEHOLDERS = new Set(['roi_id', 'roi_tag', 'roi_index', 'roi_count', 'door_state', 'door_state_label', 'alarm_label', 'open_count', 'closed_count'])
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
const ACTIVE_PLUGIN_SETTING_KEYS = ['active_plugin_id']
const PROCESSOR_RESTART_SETTING_KEYS = [
  ...ACTIVE_PLUGIN_SETTING_KEYS,
  'smoke_detection_model_name',
  'smoke_detection_model_version',
  'smoke_detection_confidence',
  'smoke_detection_nms',
  'smoke_temporal_confirm_frames',
  'smoke_temporal_confirm_window',
  'smoke_max_miss_frames',
  'smoke_alarm_hold_time',
  'fire_door_classification_model_name',
  'fire_door_classification_confidence',
  'fire_door_open_labels',
  'fire_door_closed_labels',
  'fire_door_alarm_labels',
  'fire_door_temporal_confirm_frames',
  'fire_door_temporal_confirm_window',
  'fire_door_alarm_hold_time',
  ...Object.keys(SMOKE_ADVANCED_DEFAULTS),
]
const emailTemplatePlaceholderGroups = computed(() => {
  const activePluginId = String(form.value.active_plugin_id || SMOKE_SCENE_ID)
  const groups = [
    { key: 'common', label: t('settings.placeholderCategoryCommon'), items: [] },
    { key: 'smoke', label: t('settings.placeholderCategorySmoke'), items: [] },
    { key: 'fireDoor', label: t('settings.placeholderCategoryFireDoor'), items: [] },
  ]
  for (const item of emailTemplatePlaceholders.value) {
    if (FIRE_DOOR_PLACEHOLDERS.has(item)) {
      if (activePluginId === FIRE_DOOR_SCENE_ID) {
        groups[2].items.push(item)
      }
    } else if (SMOKE_PLACEHOLDERS.has(item)) {
      if (activePluginId === SMOKE_SCENE_ID) {
        groups[1].items.push(item)
      }
    } else {
      groups[0].items.push(item)
    }
  }
  return groups.filter((group) => group.items.length)
})

function placeholderDescription(item) {
  const translated = t(`settings.placeholderDescriptions.${item}`)
  return translated === `settings.placeholderDescriptions.${item}` ? item : translated
}

function placeholderTagType(groupKey) {
  if (groupKey === 'smoke') return 'warning'
  if (groupKey === 'fireDoor') return 'success'
  return 'info'
}
// These keys are saved from the Site Settings UI and also included in
// PROCESSOR_RESTART_SETTING_KEYS so running sources switch to the new plugin.
const UI_SETTING_KEYS = ['ui_language', 'timezone', 'site_title', 'site_description', 'favicon_url', ...ACTIVE_PLUGIN_SETTING_KEYS]
const VENGINE_SERVICE_SETTING_KEYS = [
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
]
const THREAD_POOL_SETTING_KEYS = [
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
const FIRE_DOOR_PLUGIN_SETTING_KEYS = [
  'fire_door_classification_model_name',
  'fire_door_classification_confidence',
  'fire_door_open_labels',
  'fire_door_closed_labels',
  'fire_door_alarm_labels',
  'fire_door_temporal_confirm_frames',
  'fire_door_temporal_confirm_window',
  'fire_door_alarm_hold_time',
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
  expires_at: '',
})
const createUserDialogVisible = ref(false)
const editUserDialog = ref({
  visible: false,
  username: '',
  role: 'operator',
  expires_at: '',
})
const resetPasswordDialog = ref({
  visible: false,
  username: '',
  new_password: '',
})
const blockedIps = ref([])
const manualBlockDialogVisible = ref(false)
const userManagementLoaded = ref(false)
const userManagementLoadPromise = ref(null)
const manualBlockForm = ref({
  ip: '',
  duration_seconds: '',
  reason: '',
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
  active_plugin_id: SMOKE_SCENE_ID,
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
  fire_door_classification_model_name: 'fire-door-classification',
  fire_door_classification_confidence: '0.50',
  fire_door_open_labels: 'open',
  fire_door_closed_labels: 'closed',
  fire_door_alarm_labels: 'open',
  fire_door_temporal_confirm_frames: '1',
  fire_door_temporal_confirm_window: '2.0',
  fire_door_alarm_hold_time: '3.0',
  message_retention_days: '7',
  max_pull_workers: '',
  max_push_workers: '',
  max_cpu_workers: '',
  account_expiration_days_user: '0',
  account_expiration_days_operator: '0',
  account_expiration_days_admin: '0',
  login_lockout_max_attempts: '5',
  login_lockout_window_seconds: '300',
  login_lockout_duration_seconds: '900',
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
const isEmbeddedFavicon = computed(() => String(form.value.favicon_url || '').startsWith('data:'))
const settingsNavItems = computed(() => {
  const items = []
  if (canManageSettings.value) {
    items.push(
      { key: 'site', label: t('management.siteSettings'), hint: t('management.siteSettingsHint'), icon: Setting },
    )
  }
  if (authStore.canManageUsers) {
    items.push({ key: 'users', label: t('settings.userManagement'), hint: t('settings.userManagementHint'), icon: User })
  }
  if (canViewLogs.value) {
    items.push({ key: 'logs', label: t('management.processingLogs'), hint: t('processingLogs.subtitle'), icon: Document })
  }
  if (canManageSettings.value) {
    items.push(
      { key: 'vengine', label: t('management.vengineSettings'), hint: t('settings.serviceToggleTip'), icon: Monitor },
      { key: 'notifications', label: t('management.notificationSettings'), hint: t('settings.subtitle'), icon: Bell },
      { key: 'plugins', label: t('management.pluginSettings'), hint: t('settings.pluginSectionHint'), icon: Crop },
    )
  }
  return items
})
const currentSettingsNavItem = computed(() => (
  settingsNavItems.value.find((item) => item.key === currentSettingsPage.value) || null
))
const managementOverviewCards = computed(() => ([
  {
    key: 'sections',
    label: t('settings.availableModules'),
    value: String(settingsNavItems.value.length),
  },
  {
    key: 'plugins',
    label: t('settings.pluginSceneCount'),
    value: String(sceneDefinitions.value.length),
  },
]))

function sceneById(sceneId) {
  return sceneDefinitions.value.find((scene) => scene.id === sceneId)
}

function sceneTabLabel(sceneId) {
  const scene = sceneById(sceneId)
  if (!scene) return sceneId
  return locale.value === 'en-US' ? scene.label_en : scene.label_zh
}

function roiTagLabel(scene, tag) {
  return sceneScopedRoiTagLabel(scene, tag, locale.value)
}

function formatCreatedAt(value) {
  return formatSortableDateTimeWithTimezone(value, appSettingsStore.timeZone)
}

function pluginSettingKeys(sceneId) {
  if (sceneId === SMOKE_SCENE_ID) return SMOKE_PLUGIN_SETTING_KEYS
  if (sceneId === FIRE_DOOR_SCENE_ID) return FIRE_DOOR_PLUGIN_SETTING_KEYS
  return []
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
    }
    ensureValidSettingsRoute()
  } catch (err) {
    ElMessage.error(t('settings.failedToLoad', { message: err.message }))
  } finally {
    loading.value = false
  }
}

async function restoreSection(sectionId, keys) {
  try {
    await ElMessageBox.confirm(
      t('settings.restoreSectionConfirmMessage'),
      t('settings.restoreSectionConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('settings.restoreSection'),
        cancelButtonText: t('common.cancel'),
      }
    )
  } catch (_) {
    return
  }
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
    await authStore.createUser({
      username: userForm.value.username,
      password: userForm.value.password,
      role: userForm.value.role,
      ...(userForm.value.expires_at ? { expires_at: userForm.value.expires_at } : {}),
    })
    userForm.value = {
      username: '',
      password: '',
      role: 'operator',
      expires_at: '',
    }
    createUserDialogVisible.value = false
    ElMessage.success(t('settings.createUserSuccess'))
  } catch (err) {
    ElMessage.error(t('settings.createUserFailed', { message: err.message }))
  } finally {
    creatingUser.value = false
  }
}

function canDeleteUser(row) {
  if (!row) return false
  if (row.username === authStore.user?.username) return false
  if (row.role === 'admin') {
    const adminCount = (authStore.users || []).filter((u) => u.role === 'admin').length
    if (adminCount <= 1) return false
  }
  return true
}

function canToggleBan(row) {
  if (!row) return false
  if (row.username === authStore.user?.username) return false
  if (!row.is_banned && row.role === 'admin') {
    const activeAdmins = (authStore.users || []).filter((u) => u.role === 'admin' && !u.is_banned).length
    if (activeAdmins <= 1) return false
  }
  return true
}

async function toggleUserBan(row) {
  try {
    await authStore.updateUser(row.username, { is_banned: !row.is_banned })
    ElMessage.success(t(!row.is_banned ? 'settings.banSuccess' : 'settings.unbanSuccess'))
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  }
}

async function deleteUserAccount(row) {
  try {
    await ElMessageBox.confirm(
      t('settings.deleteUserConfirmMessage', { username: row.username }),
      t('settings.deleteUserConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('common.delete'),
        cancelButtonText: t('common.cancel'),
      },
    )
  } catch (_) {
    return
  }
  try {
    await authStore.deleteUser(row.username)
    ElMessage.success(t('settings.deleteUserSuccess'))
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  }
}

function openEditUser(row) {
  editUserDialog.value = {
    visible: true,
    username: row.username,
    role: row.role,
    expires_at: row.expires_at || '',
  }
}

async function submitEditUser() {
  const payload = {
    role: editUserDialog.value.role,
  }
  if (editUserDialog.value.expires_at) {
    payload.expires_at = editUserDialog.value.expires_at
  } else {
    payload.clear_expires_at = true
  }
  try {
    await authStore.updateUser(editUserDialog.value.username, payload)
    editUserDialog.value.visible = false
    ElMessage.success(t('settings.editUserSuccess'))
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  }
}

function openResetPassword(row) {
  resetPasswordDialog.value = {
    visible: true,
    username: row.username,
    new_password: '',
  }
}

async function submitResetPassword() {
  if (!resetPasswordDialog.value.new_password) {
    ElMessage.warning(t('settings.missingFields'))
    return
  }
  try {
    await authStore.adminResetPassword(
      resetPasswordDialog.value.username,
      resetPasswordDialog.value.new_password,
    )
    resetPasswordDialog.value.visible = false
    ElMessage.success(t('settings.resetPasswordSuccess'))
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  }
}

async function saveAccountExpirationSettings() {
  await saveSection('accountExpiration', [
    'account_expiration_days_user',
    'account_expiration_days_operator',
    'account_expiration_days_admin',
  ])
}

async function saveLoginSecuritySettings() {
  await saveSection('loginSecurity', [
    'login_lockout_max_attempts',
    'login_lockout_window_seconds',
    'login_lockout_duration_seconds',
  ])
}

async function reloadBlockedIps() {
  if (!authStore.canManageUsers) return
  try {
    blockedIps.value = await accessApi.listBlockedIps()
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  }
}

async function reloadUserManagementData({ force = false } = {}) {
  if (!authStore.canManageUsers) {
    userManagementLoaded.value = false
    blockedIps.value = []
    return
  }
  if (!force && userManagementLoaded.value) return
  if (!force && userManagementLoadPromise.value) {
    return userManagementLoadPromise.value
  }

  userManagementLoadPromise.value = (async () => {
    await authStore.fetchUsers()
    await reloadBlockedIps()
    userManagementLoaded.value = true
  })()

  try {
    await userManagementLoadPromise.value
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  } finally {
    userManagementLoadPromise.value = null
  }
}

async function unblockIp(row) {
  try {
    await accessApi.unblockIp(row.ip)
    ElMessage.success(t('settings.unblockIpSuccess'))
    await reloadBlockedIps()
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
  }
}

async function manualBlockIp() {
  if (!manualBlockForm.value.ip) {
    ElMessage.warning(t('settings.missingFields'))
    return
  }
  const payload = { ip: manualBlockForm.value.ip, reason: manualBlockForm.value.reason || '' }
  const duration = Number(manualBlockForm.value.duration_seconds)
  if (!Number.isNaN(duration) && duration > 0) {
    payload.duration_seconds = duration
  }
  try {
    await accessApi.blockIp(payload)
    manualBlockForm.value = { ip: '', duration_seconds: '', reason: '' }
    manualBlockDialogVisible.value = false
    ElMessage.success(t('settings.manualBlockIpSuccess'))
    await reloadBlockedIps()
  } catch (err) {
    ElMessage.error(err.message || t('settings.actionFailed'))
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
    const activePluginChanged = (
      keys.includes('active_plugin_id')
      && String(previousSettings.active_plugin_id || '') !== String(form.value.active_plugin_id || '')
    )
    let runningSourceIds = []
    if (processorConfigChanged || mediamtxRtspChanged) {
      await sourceStore.syncProcessorStatus()
      runningSourceIds = sourceStore.getRunningSourceIdsSnapshot()
    }

    const data = await appSettingsStore.updateSettings(pickFormValues(keys))
    Object.assign(form.value, data)
    appSettingsStore.applyLanguage(form.value.ui_language)
    if (mediamtxRtspChanged || mediamtxWebrtcChanged || activePluginChanged) {
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

async function resetSiteIcon() {
  try {
    await ElMessageBox.confirm(
      t('settings.resetSiteIconConfirmMessage'),
      t('settings.resetSiteIconConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('settings.resetSiteIcon'),
        cancelButtonText: t('common.cancel'),
      }
    )
  } catch (_) {
    return
  }
  form.value.favicon_url = '/favicon.ico'
  ElMessage.success(t('common.reset'))
}

async function resetSmokeAdvancedThresholds() {
  try {
    await ElMessageBox.confirm(
      t('settings.resetAdvancedThresholdsConfirmMessage'),
      t('settings.resetAdvancedThresholdsConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('settings.resetAdvancedThresholds'),
        cancelButtonText: t('common.cancel'),
      }
    )
  } catch (_) {
    return
  }
  Object.assign(form.value, SMOKE_ADVANCED_DEFAULTS)
  ElMessage.success(t('common.reset'))
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
    if (isUsersPage.value) {
      reloadUserManagementData()
    }
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
  --users-management-side-card-bg-start: rgba(25, 35, 60, 0.86);
  --users-management-side-card-bg-end: rgba(14, 20, 36, 0.94);
  --users-management-side-card-border: rgba(77, 101, 154, 0.55);
  --users-management-side-card-shadow: rgba(4, 10, 24, 0.22);
  --users-management-table-bg: rgba(9, 15, 30, 0.82);
  --users-management-table-border: rgba(62, 82, 126, 0.65);
  --users-management-cell-color: #d9e6ff;
  --users-management-control-bg: rgba(9, 15, 30, 0.72);
  --users-management-control-border: rgba(103, 132, 190, 0.5);
  --users-management-control-button-bg: rgba(20, 31, 55, 0.94);
  --users-management-control-button-hover: rgba(64, 158, 255, 0.18);
  --user-identity-name-color: #edf4ff;
  --current-account-tag-border: rgba(124, 194, 255, 0.48);
  --current-account-tag-bg: rgba(64, 158, 255, 0.12);
  --current-account-tag-color: #9dd3ff;
  --users-management-action-button-min-width: 112px;
  --users-management-compact-input-short: 132px;
  --users-management-compact-input-medium: 240px;
  --users-management-dialog-input-width: 224px;
  --users-management-compact-action-padding: 18px;
  --user-created-at-color: #8aa6d9;
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
  gap: 16px;
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

.settings-overview-card > p {
  margin-top: 6px;
  color: #9ba8be;
  font-size: 13px;
  line-height: 1.6;
}

.management-role-tag {
  margin-top: 10px;
}

.settings-form {
  background: rgba(16, 21, 37, 0.92);
  border: 1px solid #26314d;
  border-radius: 24px;
  padding: 20px;
}

.settings-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.settings-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: sticky;
  top: 0;
  max-height: calc(100vh - 24px);
  overflow-y: auto;
  padding-right: 4px;
}

.settings-main {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.settings-overview-card,
.settings-sidebar-card,
.settings-current-panel {
  border: 1px solid #2b3550;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(20, 28, 48, 0.92), rgba(12, 18, 33, 0.94));
  box-shadow: 0 18px 40px rgba(5, 10, 24, 0.22);
}

.settings-overview-card {
  padding: 20px;
}

.settings-overview-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.settings-overview-stat {
  padding: 12px;
  border: 1px solid rgba(74, 94, 138, 0.45);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
}

.settings-overview-stat__label {
  display: block;
  color: #8ea2c9;
  font-size: 12px;
  margin-bottom: 6px;
}

.settings-overview-stat__value {
  display: block;
  color: #eef4ff;
  font-size: 14px;
  line-height: 1.4;
}

.settings-sidebar-card {
  padding: 16px;
}

.settings-sidebar-card__head {
  margin-bottom: 14px;
}

.settings-sidebar-card__head h3 {
  color: #e4edff;
  font-size: 15px;
  margin-bottom: 4px;
}

.settings-sidebar-card__head p {
  color: #8f9fbe;
  font-size: 12px;
  line-height: 1.5;
}

.settings-page-nav {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.management-expert-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid #2f3a5b;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.12), rgba(255, 255, 255, 0.03));
  box-shadow: 0 18px 40px rgba(5, 10, 24, 0.22);
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
  min-height: 78px;
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

.settings-page-nav__title-wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.settings-page-nav__icon {
  font-size: 16px;
  color: #7cc2ff;
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

.settings-current-panel {
  padding: 18px 20px;
}

.settings-current-panel__eyebrow {
  display: inline-block;
  margin-bottom: 8px;
  color: #7cc2ff;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.settings-current-panel h2 {
  color: #eef4ff;
  font-size: 22px;
  margin-bottom: 6px;
}

.settings-current-panel p {
  color: #93a3bf;
  font-size: 13px;
  line-height: 1.6;
}

.management-logs-panel {
  min-height: 720px;
}

.settings-section {
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid #30364d;
  border-radius: 20px;
  padding: 20px 20px 16px;
  margin-bottom: 0;
  box-shadow: 0 14px 32px rgba(7, 12, 26, 0.18);
}

.settings-section h2 {
  font-size: 16px;
  color: #e5eeff;
  margin-bottom: 6px;
}

.settings-top-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.settings-top-tabs :deep(.el-tabs__nav) {
  display: inline-flex;
  align-items: center;
  padding: 4px;
  border-radius: 999px;
  background: rgba(9, 14, 28, 0.72);
}

.settings-top-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: transparent;
}

.settings-top-tabs :deep(.el-tabs__nav .el-tabs__item) {
  display: inline-flex;
  align-items: center; /* Center tab text vertically within each pill */
  justify-content: center;
  box-sizing: border-box;
  height: 38px;
  line-height: 1;
  color: #aebbd7;
  padding: 0 18px;
  border-radius: 999px;
}

.settings-top-tabs :deep(.el-tabs__nav .el-tabs__item.is-top:nth-child(2)),
.settings-top-tabs :deep(.el-tabs__nav .el-tabs__item.is-top:last-child) {
  padding: 0 18px; /* Keep active pill text horizontally centered despite Element Plus edge-tab padding */
}

.settings-top-tabs :deep(.el-tabs__item.is-active) {
  color: #eef4ff;
  background: rgba(64, 158, 255, 0.14);
}

.settings-top-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.settings-top-tabs :deep(.el-tabs__item:focus-visible) {
  outline: 2px solid rgba(124, 194, 255, 0.6);
  outline-offset: 2px;
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

.settings-inline-field-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr)); /* Pair related settings on one line */
  gap: 14px 20px;
  align-items: stretch;
}

.settings-inline-field-row :deep(.el-form-item) {
  margin-bottom: 0;
}

.settings-inline-field-row :deep(.el-form-item__label) {
  display: flex;
  align-items: flex-end; /* Keep labels in multi-column rows aligned before controls */
  min-height: 24px;
  padding-bottom: 6px;
}

.settings-inline-field-row :deep(.el-form-item__content) {
  max-width: min(100%, 440px);
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

.site-icon-uploaded-tag {
  min-height: 32px;
  padding: 0 12px;
}

.icon-upload-hint {
  flex-basis: 100%;
  margin-top: 0;
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

.placeholder-group-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.placeholder-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.placeholder-group__title {
  color: #9aa6c0;
  font-size: 12px;
  font-weight: 700;
}

.placeholder-tag {
  cursor: help;
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

.plugin-launcher-card :deep(.el-button + .el-button) {
  margin-left: 0;
}

.plugin-dialog-hint {
  margin-bottom: 14px;
  color: #8f9fbe;
  font-size: 13px;
  line-height: 1.5;
}

:global(.plugin-settings-dialog) {
  border: 1px solid #2b3550;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(20, 28, 48, 0.98), rgba(12, 18, 33, 0.98));
  box-shadow: 0 24px 60px rgba(5, 10, 24, 0.45);
  overflow: hidden;
}

:global(.plugin-settings-dialog .el-dialog__header) {
  margin: 0;
  padding: 18px 22px;
  border-bottom: 1px solid #2b3550;
  background: rgba(12, 18, 33, 0.92);
}

:global(.plugin-settings-dialog .el-dialog__title) {
  color: #eef4ff;
  font-weight: 700;
}

:global(.plugin-settings-dialog .el-dialog__headerbtn .el-dialog__close) {
  color: #9fb0cf;
}

:global(.plugin-settings-dialog .el-dialog__headerbtn:hover .el-dialog__close) {
  color: #79bbff;
}

:global(.plugin-settings-dialog .el-dialog__body) {
  padding: 20px 22px 24px;
  background:
    radial-gradient(circle at 0% 0%, rgba(64, 158, 255, 0.10), transparent 40%),
    rgba(12, 18, 33, 0.98);
  color: #dbe7ff;
}

.settings-split-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.users-management-layout {
  display: flex;
  flex-direction: column;
  gap: 22px; /* Vertical spacing between management sections */
}

.users-management-main {
  min-width: 0;
  overflow: hidden;
}

.users-management-side {
  display: flex;
  flex-direction: column;
  gap: 22px; /* Vertical spacing between side cards */
}

.users-management-layout .section-card {
  background:
    linear-gradient(
      180deg,
      var(--users-management-side-card-bg-start),
      var(--users-management-side-card-bg-end)
    ),
    rgba(255, 255, 255, 0.025);
  border-color: rgba(103, 132, 190, 0.42);
  box-shadow: 0 20px 48px rgba(4, 10, 24, 0.18); /* Reduced shadow intensity for card elevation */
}

.users-management-layout .section-card + .section-card {
  margin-top: 0;
}

.users-management-side .section-card__head {
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}

.users-management-side .section-card__actions.single-action {
  justify-content: flex-end; /* Realigned confirmation buttons */
  margin-top: 18px;
}

.users-management-side .section-card__actions.single-action .el-button {
  min-width: var(--users-management-action-button-min-width);
  margin-left: 0;
}

.settings-compact-fields {
  row-gap: 16px; /* Use Element Plus row gutters with consistent vertical rhythm */
}

.settings-compact-fields :deep(.el-form-item) {
  margin-bottom: 0;
}

.settings-compact-fields :deep(.el-input),
.settings-compact-fields :deep(.el-select),
.settings-compact-fields :deep(.el-date-editor) {
  width: 100%;
}

.settings-compact-fields--inline-actions :deep(.el-form-item__content) {
  align-items: flex-start;
}

.settings-compact-fields--inline-actions .info-tip {
  flex-basis: 100%;
}

/* Keep role-default / login-security fields and their save button on one row */
.settings-compact-fields--single-line {
  flex-wrap: nowrap;
}

.settings-compact-fields--single-line :deep(.el-form-item__label) {
  white-space: nowrap;
}

.numeric-setting-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 520px;
}

.numeric-setting-item {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 178px;
  align-items: center;
  gap: 18px;
  margin-bottom: 0;
  padding: 10px 12px;
  border: 1px solid rgba(103, 132, 190, 0.22);
  border-radius: 14px;
  background: rgba(9, 15, 30, 0.34);
}

.numeric-setting-item :deep(.el-form-item__label) {
  display: flex;
  align-items: center;
  height: 32px;
  margin: 0;
  padding: 0;
  color: #c6d6f4;
  line-height: 1.35;
}

.numeric-setting-item :deep(.el-form-item__content) {
  justify-content: flex-end;
  width: 178px;
  line-height: 1;
}

.themed-number-input {
  width: 178px;
  --el-input-number-controls-height: 34px;
}

.themed-number-input :deep(.el-input__wrapper) {
  background: var(--users-management-control-bg);
  box-shadow: 0 0 0 1px var(--users-management-control-border) inset;
}

.themed-number-input :deep(.el-input__inner) {
  color: #edf4ff;
  font-weight: 700;
}

.themed-number-input :deep(.el-input-number__decrease),
.themed-number-input :deep(.el-input-number__increase) {
  border-color: var(--users-management-control-border);
  background: var(--users-management-control-button-bg);
  color: #9dd3ff;
}

.themed-number-input :deep(.el-input-number__decrease:hover),
.themed-number-input :deep(.el-input-number__increase:hover) {
  background: var(--users-management-control-button-hover);
  color: #d8ecff;
}

.themed-number-input--dialog {
  width: 100%;
  max-width: 220px;
}

.info-tip--block {
  margin-top: 10px;
}

.short-number-input {
  max-width: var(--users-management-compact-input-short); /* Keep short numeric settings visually compact */
}

.medium-text-input {
  max-width: var(--users-management-compact-input-medium); /* Avoid overlong single-line controls */
}

.compact-action-col {
  display: flex;
  align-items: flex-end;
}

.compact-row-actions {
  display: flex;
  justify-content: flex-end; /* Merge save/submit buttons into the same control row */
  width: 100%;
  padding-bottom: var(--users-management-compact-action-padding);
}

.settings-action-footer {
  display: flex;
  justify-content: flex-end;
  max-width: 520px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(103, 132, 190, 0.16); /* Visual separator between form fields and actions */
}

.user-management-table {
  --el-table-bg-color: var(--users-management-table-bg);
  --el-table-tr-bg-color: var(--users-management-table-bg);
  --el-table-header-bg-color: rgba(18, 29, 54, 0.96);
  --el-table-row-hover-bg-color: rgba(35, 72, 132, 0.28);
  --el-table-border-color: var(--users-management-table-border);
  --el-table-text-color: #d9e6ff;
  --el-table-header-text-color: #9fb8e8;
  overflow: hidden;
  border: 1px solid rgba(103, 132, 190, 0.38);
  border-radius: 16px;
  background: var(--users-management-table-bg);
  box-shadow: 0 12px 30px rgba(3, 9, 22, 0.16); /* Shadow effect for table container */
}

.user-management-table-shell {
  overflow-x: visible; /* Account list now fits in one row without horizontal scroll */
  border-radius: 16px;
}

.user-management-table :deep(.cell) {
  color: var(--users-management-cell-color);
  line-height: 1.45;
}

.user-management-table :deep(.el-table__inner-wrapper::before),
.user-management-table :deep(.el-table__border-left-patch) {
  background-color: var(--users-management-table-border);
}

.user-management-table :deep(.el-table__cell) {
  border-bottom-color: rgba(62, 82, 126, 0.48);
  padding-top: 12px; /* Add breathing room inside rows */
  padding-bottom: 12px;
}

.user-management-table :deep(.el-table__empty-block) {
  background: var(--users-management-table-bg);
}

.user-management-table :deep(.el-table__header-wrapper th) {
  font-weight: 700;
}

.user-identity {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  min-width: 0;
  white-space: nowrap;
  vertical-align: middle;
}

.user-identity__name {
  min-width: 0;
  overflow: hidden;
  color: var(--user-identity-name-color);
  font-weight: 600;
  text-overflow: ellipsis;
}

.current-account-tag {
  flex: 0 0 auto;
  border-color: var(--current-account-tag-border);
  background: var(--current-account-tag-bg);
  color: var(--current-account-tag-color);
}

.user-action-space {
  justify-content: flex-end;
}

.user-action-space :deep(.el-button + .el-button) {
  margin-left: 0; /* Let el-space handle button spacing */
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
  color: var(--user-created-at-color);
  font-size: 12px;
  white-space: nowrap;
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

.section-card__actions :deep(.el-button + .el-button) {
  margin-left: 0; /* Prevent spacing conflicts with el-space */
}

:deep(.user-management-dialog) {
  border: 1px solid rgba(103, 132, 190, 0.44);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(21, 30, 52, 0.98), rgba(13, 20, 37, 0.98));
  box-shadow: 0 24px 64px rgba(4, 10, 24, 0.42); /* Enhanced shadow for dialog elevation */
  overflow: hidden;
}

:deep(.user-management-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 20px 24px 16px;
  border-bottom: 1px solid rgba(103, 132, 190, 0.18);
}

:deep(.user-management-dialog .el-dialog__title) {
  color: #eef4ff;
  font-weight: 700;
}

:deep(.user-management-dialog .el-dialog__body) {
  padding: 20px 24px 8px;
}

:deep(.user-management-dialog .el-dialog__footer) {
  padding: 16px 24px 22px;
  border-top: 1px solid rgba(103, 132, 190, 0.14);
}

.user-dialog-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-dialog-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.dialog-compact-grid {
  row-gap: 8px; /* Pair related dialog fields in the same row */
}

.dialog-compact-grid :deep(.el-input),
.dialog-compact-control,
.dialog-password-input {
  width: 100%;
  max-width: var(--users-management-dialog-input-width);
}

.dialog-compact-grid .info-tip {
  flex-basis: 100%;
}

.user-dialog-footer {
  display: flex;
  justify-content: flex-end; /* Realigned dialog confirmation buttons */
}

.user-dialog-footer :deep(.el-button + .el-button) {
  margin-left: 0;
}

.expert-card {
  margin-top: 18px;
  padding: 16px;
  border: 1px solid #2f3a5b;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
}

.expert-card > h3 {
  color: #e5eeff;
  font-size: 16px;
  margin-bottom: 14px;
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

  .settings-layout {
    grid-template-columns: 1fr;
  }

  .settings-sidebar {
    position: static;
    max-height: none;
    overflow: visible;
    padding-right: 0;
  }

  .settings-overview-stats {
    grid-template-columns: 1fr;
  }

  .plugin-launcher-grid {
    grid-template-columns: 1fr;
  }

  .settings-compact-fields,
  .manual-block-fields {
    grid-template-columns: 1fr;
  }

  .short-number-input,
  .medium-text-input,
  .dialog-compact-grid :deep(.el-input),
  .dialog-compact-control,
  .dialog-password-input {
    max-width: 100%;
  }

  .compact-row-actions {
    justify-content: flex-start;
    padding-bottom: 0;
  }

  .settings-form {
    padding: 14px;
  }

  .settings-page-nav {
    gap: 8px;
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

  .settings-inline-field-row {
    grid-template-columns: 1fr;
  }
}
</style>
