import { createRouter, createWebHistory } from 'vue-router'
import pinia from '../stores/pinia.js'
import { useAuthStore } from '../stores/auth.js'

const VideoWall = () => import('../views/VideoWall.vue')
const Messages = () => import('../views/Messages.vue')
const ProcessingLogs = () => import('../views/ProcessingLogs.vue')
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
    component: ProcessingLogs,
  },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings,
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

let restorePromise = null

async function ensureSession(authStore) {
  if (authStore.isAuthenticated) return authStore.user
  if (!restorePromise) {
    restorePromise = authStore.restore().finally(() => {
      restorePromise = null
    })
  }
  return restorePromise
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)

  await authStore.fetchBootstrap()

  if (to.path === '/auth') {
    await ensureSession(authStore)
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

  await ensureSession(authStore)
  if (authStore.isAuthenticated) {
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
