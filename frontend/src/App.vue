<template>
  <el-config-provider>
    <router-view v-if="isAuthRoute" />
    <el-container v-else class="app-container">
      <el-header v-if="!isManagementRoute" class="app-header">
        <div class="header-brand">
          <el-avatar :size="22" shape="square" :src="appSettingsStore.siteIconUrl" class="site-icon">
            <el-icon><VideoCamera /></el-icon>
          </el-avatar>
          <span class="brand-name">{{ appSettingsStore.siteTitle }}</span>
          <span class="brand-desc">{{ appSettingsStore.siteDescription }}</span>
        </div>
        <el-menu
          mode="horizontal"
          :router="true"
          :default-active="activeHeaderPath"
          background-color="#1a1a2e"
          text-color="#ccc"
          active-text-color="#409EFF"
          class="header-nav"
        >
          <el-menu-item v-if="canSeeVideoWall" index="/">
            <el-icon><Monitor /></el-icon>
            {{ t('nav.videoWall') }}
          </el-menu-item>
          <el-menu-item v-if="canSeeMessages" index="/messages">
            <el-icon><Bell /></el-icon>
            {{ t('nav.messages') }}
          </el-menu-item>
        </el-menu>

        <div class="header-tools">
          <el-button
            v-if="canSeeManagement"
            size="small"
            :type="isManagementRoute ? 'primary' : 'default'"
            plain
            class="management-button"
            @click="goToManagement"
          >
            <el-icon><Setting /></el-icon>
            <span>{{ t('nav.management') }}</span>
          </el-button>
          <el-dropdown trigger="click" @command="onAuthCommand">
            <el-button size="small" plain class="account-button">
              <span class="account-name">{{ authStore.user?.username }}</span>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu class="account-dropdown-menu">
                <el-dropdown-item disabled class="account-dropdown-title">
                  {{ authStore.user?.username || t('auth.accountMenu') }}
                </el-dropdown-item>
                <el-dropdown-item disabled>
                  {{ t('auth.signedInAs', { role: t(`auth.roles.${authStore.role}`) }) }}
                </el-dropdown-item>
                <el-dropdown-item divided command="locale:zh-CN">
                  {{ t('language.label') }} · 中文
                </el-dropdown-item>
                <el-dropdown-item command="locale:en-US">
                  {{ t('language.label') }} · English
                </el-dropdown-item>
                <el-dropdown-item divided command="change-password">
                  {{ t('auth.changePassword') }}
                </el-dropdown-item>
                <el-dropdown-item command="logout">{{ t('auth.logout') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
    <el-dialog
      v-model="passwordDialogVisible"
      :title="t('auth.changePasswordTitle')"
      width="420px"
      destroy-on-close
    >
      <el-form label-position="top" :model="passwordForm">
        <p class="password-dialog-hint">{{ t('auth.changePasswordHint') }}</p>
        <el-form-item :label="t('auth.currentPassword')" required>
          <el-input
            v-model="passwordForm.currentPassword"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item :label="t('auth.newPassword')" required>
          <el-input
            v-model="passwordForm.newPassword"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item :label="t('auth.confirmNewPassword')" required>
          <el-input
            v-model="passwordForm.confirmPassword"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="submitPasswordChange"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closePasswordDialog">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="passwordSubmitting" @click="submitPasswordChange">
          {{ t('auth.changePassword') }}
        </el-button>
      </template>
    </el-dialog>
  </el-config-provider>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { useRoute, useRouter } from 'vue-router'
import { LOCALE_STORAGE_KEY, setI18nLocale } from './i18n/index.js'
import { useAppSettingsStore } from './stores/appSettings.js'
import { useAuthStore } from './stores/auth.js'
import { canViewProcessingLogs, getDefaultManagementPath } from './utils/settingsRoutes.js'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const passwordDialogVisible = ref(false)
const passwordSubmitting = ref(false)
const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const canSeeVideoWall = computed(() =>
  authStore.isBootstrapRegistrationOpen || authStore.hasPermission('video:watch')
)
const canSeeMessages = computed(() => authStore.hasPermission('messages:read'))
const canSeeProcessingLogs = computed(() => canViewProcessingLogs(
  authStore.hasPermission('sources:operate'),
  authStore.hasPermission('settings:*'),
))
const canSeeManagement = computed(() => (
  authStore.hasPermission('settings:*') || authStore.hasPermission('users:*') || canSeeProcessingLogs.value
))
const isAuthRoute = computed(() => route.path === '/auth')
const managementEntryPath = computed(() => getDefaultManagementPath(
  authStore.hasPermission('settings:*'),
  authStore.hasPermission('users:*'),
  canSeeProcessingLogs.value,
))
const activeHeaderPath = computed(() => (
  route.path === '/' || route.path === '/messages' ? route.path : ''
))
const isManagementRoute = computed(() => route.path.startsWith('/management'))

function applyLocale(value) {
  setI18nLocale(value)
  appSettingsStore.patchSettings({ ui_language: value })
}

function syncDocumentTitle(title) {
  if (typeof document !== 'undefined' && title) {
    document.title = title
  }
}

function syncFavicon(href) {
  if (typeof document === 'undefined') return

  const iconHref = href || '/favicon.ico'
  let link = document.querySelector("link[rel*='icon']")
  if (!link) {
    link = document.createElement('link')
    link.setAttribute('rel', 'icon')
    document.head.appendChild(link)
  }
  link.setAttribute('href', iconHref)
}

watch(() => appSettingsStore.siteTitle, syncDocumentTitle, { immediate: true })
watch(() => appSettingsStore.faviconUrl, syncFavicon, { immediate: true })

function resetPasswordForm() {
  passwordForm.currentPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
}

function closePasswordDialog() {
  passwordDialogVisible.value = false
  resetPasswordForm()
}

async function submitPasswordChange() {
  if (!passwordForm.currentPassword || !passwordForm.newPassword || !passwordForm.confirmPassword) {
    ElMessage.warning(t('auth.missingFields'))
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.warning(t('auth.passwordMismatch'))
    return
  }
  passwordSubmitting.value = true
  try {
    await authStore.changePassword({
      current_password: passwordForm.currentPassword,
      new_password: passwordForm.newPassword,
    })
    ElMessage.success(t('auth.passwordChangeSuccess'))
    closePasswordDialog()
  } catch (err) {
    ElMessage.error(t('auth.passwordChangeFailed', { message: err.message }))
  } finally {
    passwordSubmitting.value = false
  }
}

function onAuthCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    ElMessage.success(t('auth.logoutSuccess'))
    return
  }
  if (command === 'change-password') {
    passwordDialogVisible.value = true
    return
  }
  if (typeof command === 'string' && command.startsWith('locale:')) {
    applyLocale(command.slice('locale:'.length))
  }
}

function goToManagement() {
  if (managementEntryPath.value) {
    router.push(managementEntryPath.value)
  }
}

onMounted(async () => {
  try {
    await appSettingsStore.fetchSettings()

    if (typeof window !== 'undefined') {
      const hasSavedLocale = Boolean(window.localStorage.getItem(LOCALE_STORAGE_KEY))
      if (!hasSavedLocale) {
        applyLocale(appSettingsStore.uiLanguage)
      }
    }
  } catch (_) {
    // Keep local defaults when settings API is unavailable.
  }
})
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background: #0d0d1a;
  color: #eee;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #1a1a2e;
  border-bottom: 1px solid #333;
  padding: 0 16px;
  height: 56px !important;
  flex-shrink: 0;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 16px;
  min-width: 0;
}

.site-icon {
  border: 1px solid #3b4d7a;
  background: #101b33;
}

.brand-name {
  font-size: 18px;
  font-weight: 700;
  color: #409EFF;
}

.brand-desc {
  font-size: 12px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 340px;
}

.header-nav {
  flex: 1;
  min-width: 0;
  border-bottom: none !important;
}

.header-nav :deep(.el-menu-item) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.header-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.account-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 112px;
  max-width: 180px;
  padding: 0 14px;
}

.management-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-color: #3b4d7a;
  background: rgba(64, 158, 255, 0.08);
  color: #dce7ff;
}

.management-button.is-plain:hover,
.management-button.is-plain:focus {
  border-color: #409eff;
  color: #79bbff;
  background: rgba(64, 158, 255, 0.16);
}

.account-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-dropdown-menu {
  min-width: 196px;
}

.account-dropdown-title {
  font-weight: 600;
}

.password-dialog-hint {
  margin-bottom: 16px;
  color: #7d8fb3;
  font-size: 13px;
  line-height: 1.5;
}

.app-main {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

@media (max-width: 960px) {
  .brand-desc {
    display: none;
  }

  .header-brand {
    margin-right: 4px;
  }

  .brand-name {
    font-size: 15px;
  }

  .account-button {
    min-width: 88px;
    max-width: 132px;
  }
}
</style>
