<template>
  <el-config-provider>
    <el-container class="app-container">
      <el-header class="app-header">
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
          :default-active="$route.path"
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
          <el-menu-item v-if="canSeeProcessingLogs" index="/processing-logs">
            <el-icon><Document /></el-icon>
            {{ t('nav.processingLogs') }}
          </el-menu-item>
          <el-menu-item v-if="canSeeSettings" index="/settings">
            <el-icon><Setting /></el-icon>
            {{ t('nav.settings') }}
          </el-menu-item>
        </el-menu>

        <div class="header-tools">
          <template v-if="!authStore.isAuthenticated">
            <el-button
              v-if="authStore.isBootstrapRegistrationOpen"
              size="small"
              type="primary"
              @click="goAuth('register')"
            >
              {{ t('auth.register') }}
            </el-button>
            <el-button
              v-else-if="authStore.bootstrap.has_users"
              size="small"
              type="primary"
              plain
              @click="goAuth('login')"
            >
              {{ t('auth.login') }}
            </el-button>
            <el-tag v-else type="warning" effect="dark">{{ t('auth.accountUnavailable') }}</el-tag>
            <span class="lang-label">{{ t('language.label') }}</span>
            <el-select v-model="localeModel" size="small" class="lang-select">
              <el-option
                v-for="option in localeOptions"
                :key="option.value"
                :label="t(option.labelKey)"
                :value="option.value"
              />
            </el-select>
          </template>
          <el-dropdown v-else trigger="click" @command="onAuthCommand">
            <el-button size="small" plain class="account-button">
              <span class="account-name">{{ authStore.user?.username }}</span>
              <el-tag size="small" effect="dark" class="account-role-tag">
                {{ t(`auth.roles.${authStore.role}`) }}
              </el-tag>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  {{ t('auth.currentUser', { username: authStore.user?.username || '' }) }}
                </el-dropdown-item>
                <el-dropdown-item disabled>
                  {{ t('auth.signedInAs', { role: t(`auth.roles.${authStore.role}`) }) }}
                </el-dropdown-item>
                <el-dropdown-item divided command="locale:zh-CN">中文</el-dropdown-item>
                <el-dropdown-item command="locale:en-US">English</el-dropdown-item>
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
import { localeOptions, LOCALE_STORAGE_KEY, setI18nLocale } from './i18n/index.js'
import { useAppSettingsStore } from './stores/appSettings.js'
import { useAuthStore } from './stores/auth.js'

const { t, locale } = useI18n()
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
const canSeeProcessingLogs = computed(() =>
  authStore.hasPermission('sources:operate') || authStore.hasPermission('settings:*')
)
const canSeeSettings = computed(() => authStore.hasPermission('settings:*') || authStore.hasPermission('users:*'))

function applyLocale(value) {
  setI18nLocale(value)
  appSettingsStore.patchSettings({ ui_language: value })
}

const localeModel = computed({
  get: () => locale.value,
  set: (value) => {
    applyLocale(value)
  },
})

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

function goAuth(mode) {
  router.push({
    path: '/auth',
    query: {
      mode,
      redirect: route.path === '/auth' ? '/' : route.path,
    },
  })
}

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

onMounted(async () => {
  try {
    await authStore.restore()
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

  if (authStore.isBootstrapRegistrationOpen && !authStore.isAuthenticated && route.path !== '/auth') {
    goAuth('register')
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
  gap: 8px;
}

.account-name {
  max-width: 132px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-role-tag {
  border: none;
}

.lang-label {
  color: #888;
  font-size: 12px;
  white-space: nowrap;
}

.lang-select {
  width: 118px;
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
  .brand-desc,
  .lang-label {
    display: none;
  }

  .header-brand {
    margin-right: 4px;
  }

  .brand-name {
    font-size: 15px;
  }

  .lang-select {
    width: 90px;
  }

  .account-role-tag {
    display: none;
  }
}
</style>
