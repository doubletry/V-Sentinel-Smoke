import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '../api/index.js'
import { AUTH_TOKEN_STORAGE_KEY } from '../utils/authStorage.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref('')
  const user = ref(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const role = computed(() => user.value?.role || '')

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

  function logout() {
    persistToken('')
    user.value = null
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    role,
    restore,
    login,
    logout,
  }
})
