import process from 'node:process'
import { defineConfig } from '@playwright/test'
import base from './playwright.config.js'

// Scout desk + watchlist: every API call is intercepted, so the spec needs only
// Vite — no backend, database or staging persona.
const port = Number(process.env.SD_E2E_PORT || 5249)
const baseURL = process.env.E2E_BASE_URL || `http://127.0.0.1:${port}`

export default defineConfig({
  ...base,
  // SD_E2E_MATCH re-runs other fully-mocked specs against the same Vite-only server.
  testMatch: process.env.SD_E2E_MATCH ? process.env.SD_E2E_MATCH.split(',') : 'scout-desk.spec.mjs',
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
