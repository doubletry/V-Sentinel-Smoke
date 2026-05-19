import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, usersApi } from '../api/index.js'
import { AUTH_TOKEN_STORAGE_KEY } from '../utils/authStorage.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref('')
  const user = ref(null)
  const bootstrap = ref({ has_users: false, registration_open: false })
  const users = ref([])
  const loading = ref(false)
  const usersLoading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const role = computed(() => user.value?.role || '')
  const permissions = computed(() => user.value?.permissions || [])
  const isBootstrapRegistrationOpen = computed(() => bootstrap.value.registration_open)
  const canManageUsers = computed(() => hasPermission('users:*'))

  function loadTokenFromStorage() {
    if (typeof window === 'undefined') return ''
    return window.localStorage?.getItem(AUTH_TOKEN_STORAGE_KEY) || ''
  }

  function persistToken(nextToken) {
    token.value = nextToken || ''
    if (typeof window === 'undefined') return
    if (token.value) {
      window.localStorage?.setItem(AUTH_TOKEN_STORAGE_KEY, token.value)
    } else {
      window.localStorage?.removeItem(AUTH_TOKEN_STORAGE_KEY)
    }
  }

  async function restore() {
    await fetchBootstrap()
    const savedToken = loadTokenFromStorage()
    if (!savedToken) return null
    token.value = savedToken
    try {
      user.value = await authApi.me()
      return user.value
    } catch (_) {
      logout()
      return null
    }
  }

  async function login(credentials) {
    loading.value = true
    try {
      const response = await authApi.login(credentials)
      persistToken(response.access_token)
      user.value = await authApi.me()
      return user.value
    } finally {
      loading.value = false
    }
  }

  async function register(payload) {
    loading.value = true
    try {
      const response = await authApi.register(payload)
      persistToken(response.access_token)
      user.value = await authApi.me()
      await fetchBootstrap()
      return user.value
    } finally {
      loading.value = false
    }
  }

  async function fetchBootstrap() {
    bootstrap.value = await authApi.bootstrap()
    return bootstrap.value
  }

  async function fetchUsers() {
    if (!canManageUsers.value) {
      users.value = []
      return []
    }
    usersLoading.value = true
    try {
      users.value = await usersApi.list()
      return users.value
    } finally {
      usersLoading.value = false
    }
  }

  async function createUser(payload) {
    const created = await usersApi.create(payload)
    users.value.push(created)
    users.value.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
    return created
  }

  function hasPermission(permission) {
    const value = String(permission || '')
    if (!value) return false
    const [namespace] = value.split(':', 1)
    return permissions.value.includes(value) || permissions.value.includes(`${namespace}:*`)
  }

  function logout() {
    persistToken('')
    user.value = null
  }

  return {
    token,
    user,
    bootstrap,
    users,
    loading,
    usersLoading,
    isAuthenticated,
    permissions,
    role,
    isBootstrapRegistrationOpen,
    canManageUsers,
    restore,
    login,
    register,
    fetchBootstrap,
    fetchUsers,
    createUser,
    hasPermission,
    logout,
  }
})
