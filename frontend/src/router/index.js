import { createRouter, createWebHistory } from 'vue-router'
import pinia from '../stores/pinia.js'
import { useAuthStore } from '../stores/auth.js'
import {
  canViewProcessingLogs,
  getDefaultManagementPath,
  legacySettingsSectionToManagement,
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
    name: 'ProcessingLogs',
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

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)

  await authStore.fetchBootstrap()

  if (to.path === '/auth') {
    await authStore.ensureRestored()
    if (authStore.isAuthenticated) {
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
      return redirect && redirect !== '/auth' ? redirect : '/'
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
    if (to.path === '/management') {
      const canViewLogs = canViewProcessingLogs(
        authStore.hasPermission('sources:operate'),
        authStore.hasPermission('settings:*'),
      )
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
