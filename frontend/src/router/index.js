import { createRouter, createWebHistory } from 'vue-router'
import pinia from '../stores/pinia.js'
import { useAuthStore } from '../stores/auth.js'
import {
  canViewAuditLogs,
  defaultLandingFor,
  getDefaultManagementPath,
  legacySettingsSectionToManagement,
  userRoleRedirect,
} from '../utils/settingsRoutes.js'

const VideoWall = () => import('../views/VideoWall.vue')
const Messages = () => import('../views/Messages.vue')
const Settings = () => import('../views/Settings.vue')
const Auth = () => import('../views/Auth.vue')

const routes = [
  {
    path: '/',
    name: 'VideoWall',
    component: VideoWall,
  },
  {
    path: '/messages',
    name: 'Messages',
    component: Messages,
  },
  {
    path: '/processing-logs',
    name: 'AuditLogsLegacy',
    redirect: '/management/logs',
  },
  {
    path: '/management',
    name: 'ManagementRoot',
    component: Settings,
  },
  {
    path: '/management/:section(site|users|logs|vengine|notifications|plugins)',
    name: 'ManagementSection',
    component: Settings,
  },
  {
    path: '/management/plugins/:sceneId',
    name: 'ManagementPlugin',
    component: Settings,
  },
  {
    path: '/settings',
    name: 'SettingsRoot',
    redirect: '/management',
  },
  {
    path: '/settings/:section(platform|notifications|users)',
    name: 'SettingsSection',
    redirect: (to) => `/management/${legacySettingsSectionToManagement(to.params.section)}`,
  },
  {
    path: '/settings/plugin/:sceneId',
    name: 'SettingsPlugin',
    redirect: (to) => `/management/plugins/${to.params.sceneId}`,
  },
  {
    path: '/auth',
    name: 'Auth',
    component: Auth,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Listen for the API interceptor's auth-expired signal and redirect to /auth.
// 监听 API 拦截器的认证过期事件，跳转到 /auth。
if (typeof window !== 'undefined') {
  window.addEventListener('v-sentinel:auth-expired', () => {
    try {
      const authStore = useAuthStore(pinia)
      authStore.logout({ remote: false })
    } catch (_) { /* ignore */ }
    if (router.currentRoute.value.path !== '/auth') {
      router.push({ path: '/auth', query: { mode: 'login' } })
    }
  })
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)

  await authStore.fetchBootstrap()

  if (to.path === '/auth') {
    await authStore.ensureRestored()
    if (authStore.isAuthenticated) {
      const landing = defaultLandingFor(authStore.role)
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : landing
      // Don't allow a `user` to be sent anywhere except /messages or /auth.
      if (authStore.role === 'user') {
        return landing
      }
      return redirect && redirect !== '/auth' ? redirect : landing
    }

    if (authStore.isBootstrapRegistrationOpen) {
      if (to.query.mode !== 'register') {
        return {
          path: '/auth',
          query: { ...to.query, mode: 'register' },
          replace: true,
        }
      }
      return true
    }

    if (to.query.mode === 'register') {
      return {
        path: '/auth',
        query: { ...to.query, mode: 'login' },
        replace: true,
      }
    }
    return true
  }

  await authStore.ensureRestored()
  if (authStore.isAuthenticated) {
    // Restrict the `user` role to the messages page.
    // 将 `user` 角色限制为只能访问消息页面。
    const userRedirect = userRoleRedirect(authStore.role, to.path)
    if (userRedirect) {
      return { path: userRedirect, replace: true }
    }
    if (to.path === '/management') {
      const canViewLogs = canViewAuditLogs(authStore.hasPermission('audit:read'))
      const defaultSettingsPath = getDefaultManagementPath(
        authStore.hasPermission('settings:*'),
        authStore.canManageUsers,
        canViewLogs,
      )
      if (!defaultSettingsPath) {
        return true
      }
      return {
        path: defaultSettingsPath,
        replace: true,
      }
    }
    return true
  }

  return {
    path: '/auth',
    query: {
      mode: authStore.isBootstrapRegistrationOpen ? 'register' : 'login',
      redirect: to.fullPath,
    },
    replace: true,
  }
})

export default router
