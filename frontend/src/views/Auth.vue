<template>
  <div class="auth-page">
    <div class="auth-shell">
      <section class="auth-hero">
        <el-tag effect="dark" class="auth-badge">{{ t('auth.platformAccount') }}</el-tag>
        <h1>{{ isRegisterMode ? t('auth.registerPageTitle') : t('auth.loginPageTitle') }}</h1>
        <p>{{ isRegisterMode ? t('auth.registerPageSubtitle') : t('auth.loginPageSubtitle') }}</p>
        <div class="auth-feature-list">
          <div class="auth-feature-item">
            <span class="auth-feature-dot" />
            {{ t('auth.featureSecureAuth') }}
          </div>
          <div class="auth-feature-item">
            <span class="auth-feature-dot" />
            {{ t('auth.featureRoleAccess') }}
          </div>
          <div class="auth-feature-item">
            <span class="auth-feature-dot" />
            {{ t('auth.featurePermissionUi') }}
          </div>
        </div>
      </section>

      <section class="auth-card">
        <div class="auth-card-header">
          <h2>{{ isRegisterMode ? t('auth.register') : t('auth.login') }}</h2>
          <p>{{ isRegisterMode ? t('auth.registerHint') : t('auth.loginHint') }}</p>
        </div>

        <el-form
          v-if="isRegisterMode"
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
import { computed, onMounted, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ElMessage from 'element-plus/es/components/message/index'
import { useAuthStore } from '../stores/auth.js'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

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

function redirectTarget() {
  const value = String(route.query.redirect || '')
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/'
  try {
    const decoded = decodeURIComponent(value)
    const normalized = decoded.trim().toLowerCase()
    const normalizedWithoutLeadingSlash = normalized.replace(/^\/+/, '')
    if (
      normalized.startsWith('//')
      || normalized.includes('://')
      || /^(javascript|data|vbscript):/.test(normalizedWithoutLeadingSlash)
    ) {
      return '/'
    }
    const resolved = router.resolve(decoded)
    return resolved.matched.length && resolved.path !== '/auth' ? resolved.path : '/'
  } catch (_) {
    return '/'
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
  await authStore.fetchBootstrap()
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
  max-width: 1120px;
  min-height: min(720px, calc(100vh - 152px));
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

.auth-hero::after {
  /* Keep the glow partially outside the card to create a soft overflow halo. */
  /* A slight right overflow keeps the orb visible without covering form content. */
  /* A larger bottom overflow makes the halo fade out below the hero card. */
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
  max-width: 620px;
  color: #f2f7ff;
  font-size: 42px;
  line-height: 1.16;
  margin-bottom: 18px;
}

.auth-hero p {
  max-width: 620px;
  color: #c4d4ef;
  font-size: 15px;
  line-height: 1.8;
}

.auth-feature-list {
  position: relative;
  z-index: 1;
  margin-top: 44px;
  display: grid;
  gap: 14px;
}

.auth-feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #e8f1ff;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.07);
  backdrop-filter: blur(8px);
}

.auth-feature-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #67c23a;
  box-shadow: 0 0 0 5px rgba(103, 194, 58, 0.16);
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
