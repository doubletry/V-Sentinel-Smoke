<template>
  <div class="auth-page">
    <div class="auth-shell">
      <section class="auth-hero">
        <p class="auth-brand">{{ appSettingsStore.siteTitle }}</p>
        <h1>{{ pageTitle }}</h1>
        <p v-if="heroDescription">{{ heroDescription }}</p>
      </section>

      <section class="auth-card">
        <div class="auth-card-header">
          <h2>{{ isRegisterMode ? t('auth.register') : t('auth.login') }}</h2>
        </div>

        <el-skeleton
          v-if="bootstrapLoading"
          :rows="4"
          animated
          class="auth-skeleton"
        />

        <el-form
          v-else-if="isRegisterMode"
          :model="registerForm"
          label-position="top"
          class="auth-form"
          @submit.prevent="submitRegister"
        >
          <el-form-item :label="t('auth.username')" required>
            <el-input v-model="registerForm.username" size="large" autocomplete="username" />
          </el-form-item>
          <el-form-item :label="t('auth.password')" required>
            <el-input
              v-model="registerForm.password"
              size="large"
              type="password"
              show-password
              autocomplete="new-password"
            />
          </el-form-item>
          <el-form-item :label="t('auth.confirmPassword')" required>
            <el-input
              v-model="registerForm.confirmPassword"
              size="large"
              type="password"
              show-password
              autocomplete="new-password"
              @keyup.enter="submitRegister"
            />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            class="auth-submit"
            :loading="authStore.loading"
            @click="submitRegister"
          >
            {{ t('auth.register') }}
          </el-button>
        </el-form>

        <el-form
          v-else
          :model="loginForm"
          label-position="top"
          class="auth-form"
          @submit.prevent="submitLogin"
        >
          <el-form-item :label="t('auth.username')" required>
            <el-input v-model="loginForm.username" size="large" autocomplete="username" />
          </el-form-item>
          <el-form-item :label="t('auth.password')" required>
            <el-input
              v-model="loginForm.password"
              size="large"
              type="password"
              show-password
              autocomplete="current-password"
              @keyup.enter="submitLogin"
            />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            class="auth-submit"
            :loading="authStore.loading"
            @click="submitLogin"
          >
            {{ t('auth.login') }}
          </el-button>
        </el-form>

        <el-button
          v-if="!isRegisterMode && authStore.isBootstrapRegistrationOpen"
          link
          type="primary"
          class="auth-switch"
          @click="switchMode('register')"
        >
          {{ t('auth.register') }}
        </el-button>
        <el-button
          v-if="isRegisterMode && authStore.bootstrap.has_users"
          link
          type="primary"
          class="auth-switch"
          @click="switchMode('login')"
        >
          {{ t('auth.hasAccountLogin') }}
        </el-button>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ElMessage from 'element-plus/es/components/message/index'
import { useAuthStore } from '../stores/auth.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { defaultLandingFor } from '../utils/settingsRoutes.js'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const appSettingsStore = useAppSettingsStore()
const bootstrapLoading = ref(true)

const loginForm = reactive({
  username: '',
  password: '',
})
const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

const isRegisterMode = computed(() => {
  if (route.query.mode === 'register') return true
  if (route.query.mode === 'login') return false
  return authStore.isBootstrapRegistrationOpen
})
const heroDescription = computed(() => appSettingsStore.siteDescription || '')
const pageTitle = computed(() => (
  isRegisterMode.value
    ? t('auth.registerPageTitle', { title: appSettingsStore.siteTitle })
    : t('auth.loginPageTitle', { title: appSettingsStore.siteTitle })
))

function redirectTarget() {
  const fallback = defaultLandingFor(authStore.role)
  if (authStore.role === 'user') return fallback
  const value = String(route.query.redirect || '')
  if (!value || !value.startsWith('/') || value.startsWith('//')) return fallback
  try {
    const decoded = decodeURIComponent(value)
    const normalized = decoded.trim().toLowerCase()
    const normalizedWithoutLeadingSlash = normalized.replace(/^\/+/, '')
    if (
      normalized.startsWith('//')
      || normalized.includes('://')
      || /^(javascript|data|vbscript):/.test(normalizedWithoutLeadingSlash)
    ) {
      return fallback
    }
    const resolved = router.resolve(decoded)
    return resolved.matched.length && resolved.path !== '/auth' ? resolved.path : fallback
  } catch (_) {
    return fallback
  }
}

async function finishAuth(successMessageKey) {
  ElMessage.success(t(successMessageKey))
  await router.replace(redirectTarget())
}

async function submitLogin() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning(t('auth.missingFields'))
    return
  }
  try {
    await authStore.login(loginForm)
    loginForm.password = ''
    await finishAuth('auth.loginSuccess')
  } catch (err) {
    if (err?.status === 403 && err?.detail && typeof err.detail === 'object' && err.detail.code === 'IP_BLOCKED') {
      const blockedUntil = err.detail.blocked_until
      if (blockedUntil) {
        ElMessage.error(t('auth.ipBlockedUntil', { time: blockedUntil }))
      } else {
        ElMessage.error(t('auth.ipBlockedManual'))
      }
      return
    }
    if (err?.status === 401 && typeof err?.detail === 'string') {
      const detail = err.detail.toLowerCase()
      if (detail.includes('banned')) {
        ElMessage.error(t('auth.accountBanned'))
        return
      }
      if (detail.includes('expired')) {
        ElMessage.error(t('auth.accountExpired'))
        return
      }
    }
    ElMessage.error(t('auth.loginFailed', { message: err.message }))
  }
}

async function submitRegister() {
  if (!registerForm.username || !registerForm.password) {
    ElMessage.warning(t('auth.missingFields'))
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
    registerForm.username = ''
    registerForm.password = ''
    registerForm.confirmPassword = ''
    await finishAuth('auth.registerSuccess')
  } catch (err) {
    ElMessage.error(t('auth.registerFailed', { message: err.message }))
  }
}

function switchMode(mode) {
  router.replace({ path: '/auth', query: { ...route.query, mode } })
}

watch(
  () => authStore.bootstrap.registration_open,
  (registrationOpen) => {
    if (!registrationOpen && route.query.mode === 'register') {
      switchMode('login')
    }
  }
)

onMounted(async () => {
  try {
    await Promise.all([
      authStore.fetchBootstrap(),
      appSettingsStore.fetchSettings().catch(() => null),
    ])
  } finally {
    bootstrapLoading.value = false
  }
  if (authStore.isAuthenticated) {
    await router.replace(redirectTarget())
  }
})
</script>

<style scoped>
.auth-page {
  min-height: 100%;
  overflow-y: auto;
  padding: 48px 24px;
  background:
    radial-gradient(circle at 15% 15%, rgba(64, 158, 255, 0.24), transparent 32%),
    radial-gradient(circle at 82% 72%, rgba(103, 194, 58, 0.14), transparent 30%),
    linear-gradient(135deg, #090d18 0%, #10172a 52%, #07101c 100%);
}

.auth-shell {
  max-width: 1100px;
  min-height: min(700px, calc(100vh - 152px));
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.8fr);
  gap: 28px;
  align-items: stretch;
}

.auth-hero,
.auth-card {
  border: 1px solid rgba(120, 156, 220, 0.28);
  border-radius: 24px;
  box-shadow: 0 22px 80px rgba(0, 0, 0, 0.32);
}

.auth-hero {
  --decorative-orb-right: -60px;
  --decorative-orb-bottom: -100px;

  position: relative;
  overflow: hidden;
  padding: 48px;
  background:
    linear-gradient(145deg, rgba(33, 78, 141, 0.72), rgba(17, 25, 45, 0.92)),
    radial-gradient(circle at 72% 22%, rgba(255, 255, 255, 0.12), transparent 30%);
}

.auth-brand {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #8fb6ff;
  margin-bottom: 18px;
}

.auth-hero::after {
  content: '';
  position: absolute;
  inset: auto var(--decorative-orb-right) var(--decorative-orb-bottom) auto;
  width: 280px;
  height: 280px;
  border-radius: 50%;
  background: rgba(64, 158, 255, 0.18);
}

.auth-badge {
  margin-bottom: 26px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(12, 20, 38, 0.7);
}

.auth-hero h1 {
  position: relative;
  z-index: 1;
  max-width: 620px;
  color: #f2f7ff;
  font-size: 42px;
  line-height: 1.16;
  margin-bottom: 18px;
}

.auth-hero p {
  position: relative;
  z-index: 1;
  max-width: 620px;
  color: #c4d4ef;
  font-size: 15px;
  line-height: 1.8;
}

.auth-card {
  padding: 34px;
  background: rgba(15, 22, 38, 0.94);
  backdrop-filter: blur(16px);
}

.auth-card-header {
  margin-bottom: 26px;
}

.auth-card-header h2 {
  color: #f4f7ff;
  font-size: 24px;
  margin-bottom: 10px;
}

.auth-card-header p {
  color: #9eb0ce;
  font-size: 13px;
  line-height: 1.7;
}

.auth-form :deep(.el-form-item__label) {
  color: #b9c8e5;
}

.auth-skeleton {
  padding: 4px 0 12px;
}

.auth-submit {
  width: 100%;
  margin-top: 8px;
}

.auth-switch {
  margin-top: 18px;
}

@media (max-width: 900px) {
  .auth-shell {
    grid-template-columns: 1fr;
  }

  .auth-hero {
    padding: 32px;
  }

  .auth-hero h1 {
    font-size: 30px;
  }
}
</style>
