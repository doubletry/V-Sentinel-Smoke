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
              {{ t('auth.registerFirstAdmin') }}
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
          </template>
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
  </el-config-provider>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
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

function goAuth(mode) {
  router.push({
    path: '/auth',
    query: {
      mode,
      redirect: route.path === '/auth' ? '/' : route.path,
    },
  })
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
