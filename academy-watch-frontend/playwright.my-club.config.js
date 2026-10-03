import { defineConfig } from '@playwright/test'
import base from './playwright.config.js'

// Real application, intercepted APIs; one lane-owned server, automatically stopped.
export default defineConfig({
  ...base,
  testMatch: ['my-club-load.spec.mjs', 'club-staff-access.spec.mjs'],
  use: { ...base.use, baseURL: 'http://127.0.0.1:5189' },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 5189 --strictPort',
    url: 'http://127.0.0.1:5189',
    reuseExistingServer: false,
    timeout: 120000,
  },
})
