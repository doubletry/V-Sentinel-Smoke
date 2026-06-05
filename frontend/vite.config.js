import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { normalizeAppBasePath } from './src/utils/appPath.js'

// Backend port for the dev-server proxy.  Reads from VITE_BACKEND_PORT env
// variable so that it works when the backend runs on a non-default port.
const backendPort = process.env.VITE_BACKEND_PORT || '8000'
const backendOrigin = `http://localhost:${backendPort}`
const appBasePath = normalizeAppBasePath(process.env.VITE_APP_BASE_PATH || '/')
const apiProxyPath = appBasePath ? `${appBasePath}/api` : '/api'
const wsProxyPath = appBasePath ? `${appBasePath}/ws` : '/ws'

export default defineConfig({
  base: './',
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          if (id.includes('@element-plus/icons-vue')) {
            return 'vendor-element-icons'
          }

          if (id.includes('element-plus')) {
            return 'vendor-ui'
          }

          if (
            id.includes('/vue/')
            || id.includes('vue-router')
            || id.includes('pinia')
            || id.includes('vue-i18n')
          ) {
            return 'vendor-vue'
          }

          if (id.includes('axios')) {
            return 'vendor-http'
          }

          return 'vendor'
        },
      },
    },
  },
  server: {
    proxy: {
      [apiProxyPath]: backendOrigin,
      [wsProxyPath]: {
        target: backendOrigin.replace('http', 'ws'),
        ws: true,
      },
    },
  },
})
