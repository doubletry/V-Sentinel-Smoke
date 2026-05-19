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
          <el-button
            v-if="!authStore.isAuthenticated && authStore.isBootstrapRegistrationOpen"
            size="small"
            type="primary"
            @click="showRegisterDialog = true"
          >
            {{ t('auth.registerFirstAdmin') }}
          </el-button>
          <el-button
            v-if="!authStore.isAuthenticated && authStore.bootstrap.has_users"
            size="small"
            type="primary"
            plain
            @click="showLoginDialog = true"
          >
            {{ t('auth.login') }}
          </el-button>
          <el-dropdown v-else trigger="click" @command="onAuthCommand">
            <el-button size="small" plain>
              {{ t('auth.signedInAs', { role: t(`auth.roles.${authStore.role}`) }) }}
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">{{ t('auth.logout') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span class="lang-label">{{ t('language.label') }}</span>
          <el-select v-model="localeModel" size="small" class="lang-select">
            <el-option
              v-for="option in localeOptions"
              :key="option.value"
              :label="t(option.labelKey)"
              :value="option.value"
            />
          </el-select>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>

    <el-dialog
      v-model="showLoginDialog"
      :title="t('auth.loginTitle')"
      width="360px"
      :close-on-click-modal="false"
    >
      <el-form :model="loginForm" label-width="90px" @submit.prevent="submitLogin">
        <el-form-item :label="t('auth.username')" required>
          <el-input v-model="loginForm.username" autocomplete="username" />
        </el-form-item>
        <el-form-item :label="t('auth.role')" required>
          <el-select v-model="loginForm.role" style="width: 100%">
            <el-option value="operator" :label="t('auth.roles.operator')" />
            <el-option value="admin" :label="t('auth.roles.admin')" />
            <el-option value="user" :label="t('auth.roles.user')" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('auth.password')" required>
          <el-input
            v-model="loginForm.password"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="submitLogin"
          />
        </el-form-item>
        <p class="auth-hint">{{ t('auth.loginHint') }}</p>
      </el-form>
      <template #footer>
        <el-button @click="showLoginDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="authStore.loading" @click="submitLogin">
          {{ t('auth.login') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showRegisterDialog"
      :title="t('auth.registerTitle')"
      width="380px"
      :close-on-click-modal="false"
    >
      <el-form :model="registerForm" label-width="110px" @submit.prevent="submitRegister">
        <el-form-item :label="t('auth.username')" required>
          <el-input v-model="registerForm.username" autocomplete="username" />
        </el-form-item>
        <el-form-item :label="t('auth.password')" required>
          <el-input
            v-model="registerForm.password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>
        <el-form-item :label="t('auth.confirmPassword')" required>
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="submitRegister"
          />
        </el-form-item>
        <p class="auth-hint">{{ t('auth.registerHint') }}</p>
      </el-form>
      <template #footer>
        <el-button @click="showRegisterDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="authStore.loading" @click="submitRegister">
          {{ t('auth.registerFirstAdmin') }}
        </el-button>
      </template>
    </el-dialog>
  </el-config-provider>
</template>

<script setup>
import { computed, reactive, ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { localeOptions, LOCALE_STORAGE_KEY, setI18nLocale } from './i18n/index.js'
import { useAppSettingsStore } from './stores/appSettings.js'
import { useAuthStore } from './stores/auth.js'

const { t, locale } = useI18n()
const appSettingsStore = useAppSettingsStore()
const authStore = useAuthStore()
const REGISTER_PROMPT_SESSION_KEY = 'v_sentinel_register_prompt_seen'
const showLoginDialog = ref(false)
const showRegisterDialog = ref(false)
const loginForm = reactive({
  username: 'operator',
  role: 'operator',
  password: '',
})
const registerForm = reactive({
  username: '',
  password: '',
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

const localeModel = computed({
  get: () => locale.value,
  set: (value) => {
    setI18nLocale(value)
    appSettingsStore.patchSettings({ ui_language: value })
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

async function submitLogin() {
  try {
    await authStore.login(loginForm)
    showLoginDialog.value = false
    loginForm.password = ''
    ElMessage.success(t('auth.loginSuccess'))
  } catch (err) {
    ElMessage.error(t('auth.loginFailed', { message: err.message }))
  }
}

async function submitRegister() {
  if (!registerForm.username || !registerForm.password) {
    ElMessage.warning(t('auth.registerMissingFields'))
    return
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    ElMessage.warning(t('auth.passwordMismatch'))
    return
  }
  try {
    await authStore.register({
      username: registerForm.username,
      password: registerForm.password,
    })
    showRegisterDialog.value = false
    registerForm.username = ''
    registerForm.password = ''
    registerForm.confirmPassword = ''
    ElMessage.success(t('auth.registerSuccess'))
  } catch (err) {
    ElMessage.error(t('auth.registerFailed', { message: err.message }))
  }
}

function onAuthCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    ElMessage.success(t('auth.logoutSuccess'))
  }
}

onMounted(async () => {
  try {
    await authStore.restore()
    await appSettingsStore.fetchSettings()

    if (typeof window !== 'undefined') {
      const hasSavedLocale = Boolean(window.localStorage.getItem(LOCALE_STORAGE_KEY))
      if (!hasSavedLocale) {
        setI18nLocale(appSettingsStore.uiLanguage)
      }
    }
  } catch (_) {
    // Keep local defaults when settings API is unavailable.
  }

  if (
    authStore.isBootstrapRegistrationOpen
    && !authStore.isAuthenticated
    && typeof window !== 'undefined'
    && !window.sessionStorage.getItem(REGISTER_PROMPT_SESSION_KEY)
  ) {
    window.sessionStorage.setItem(REGISTER_PROMPT_SESSION_KEY, '1')
    showRegisterDialog.value = true
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

.lang-label {
  color: #888;
  font-size: 12px;
  white-space: nowrap;
}

.lang-select {
  width: 118px;
}

.app-main {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.auth-hint {
  margin: 4px 0 0;
  color: #8b98b6;
  font-size: 12px;
  line-height: 1.5;
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
}
</style>
