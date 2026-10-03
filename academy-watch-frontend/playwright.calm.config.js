import process from 'node:process'
import { defineConfig } from '@playwright/test'
import base from './playwright.config.js'

// Calm admin area + shared filter bar: every API call is intercepted, so the
// specs need only Vite — no backend or database.
const port = Number(process.env.CALM_E2E_PORT || 5261)
const baseURL = process.env.E2E_BASE_URL || `http://127.0.0.1:${port}`

export default defineConfig({
  ...base,
  // CALM_E2E_MATCH re-runs other fully-mocked specs against the same Vite-only server.
  testMatch: process.env.CALM_E2E_MATCH ? process.env.CALM_E2E_MATCH.split(',') : 'calm-admin.spec.mjs',
  fullyParallel: true,
  workers: 2,
  use: { ...base.use, baseURL },
  webServer: process.env.E2E_BASE_URL ? undefined : {
    command: `pnpm dev --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120000,
  },
})
