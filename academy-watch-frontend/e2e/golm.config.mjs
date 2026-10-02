import { defineConfig } from '@playwright/test'
import base from '../playwright.config.js'

export default defineConfig({
  ...base,
  testDir: '.',
  testMatch: 'gol-maintenance.spec.mjs',
  workers: 2,
  use: { ...base.use, baseURL: 'http://127.0.0.1:5207' },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 5207 --strictPort',
    url: 'http://127.0.0.1:5207',
    reuseExistingServer: false,
    timeout: 120000,
  },
})
