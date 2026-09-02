import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const disableHmrOverlay = process.env.E2E_DISABLE_HMR_OVERLAY === 'true'
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:5001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(),tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    hmr: disableHmrOverlay ? { overlay: false } : undefined,
    watch: {
      ignored: ['**/playwright-report/**', '**/test-results/**'],
    },
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
