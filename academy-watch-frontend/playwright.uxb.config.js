import process from 'node:process'
import { defineConfig } from '@playwright/test'
import base from './playwright.config.js'

// Deterministic browser regressions: all APIs intercepted, no database or staging personas.
export default defineConfig({
  ...base,
  testMatch: ['uxbf1.spec.mjs', 'gol-maintenance.spec.mjs'],
  webServer: process.env.E2E_BASE_URL ? undefined : {
    command: 'pnpm dev --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: false,
  },
})
