import { defineConfig, devices } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import dotenv from 'dotenv'

const rootDir = path.resolve(process.cwd(), '..')
const envPath = path.join(rootDir, '.env')

dotenv.config({ path: envPath })

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const apiBaseURL = process.env.E2E_API_URL || 'http://127.0.0.1:5001/api'
const apiHealthURL = apiBaseURL.replace(/\/api$/, '/api/health')
const backendRootVenvPython = path.join(rootDir, '.loan', 'bin', 'python')
const backendBackendVenvPython = path.join(rootDir, 'loan-army-backend', '.venv', 'bin', 'python')
const backendPython = process.env.E2E_BACKEND_PYTHON
  || (fs.existsSync(backendRootVenvPython) ? backendRootVenvPython : null)
  || (fs.existsSync(backendBackendVenvPython) ? backendBackendVenvPython : null)
  || 'python3'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 120000,
  expect: {
    timeout: 15000,
  },
  reporter: [['list'], ['html', { open: 'never', outputFolder: path.join(rootDir, 'playwright-report') }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'pnpm dev -- --host 127.0.0.1 --port 5173',
      url: baseURL,
      reuseExistingServer: true,
      timeout: 120000,
      env: {
        ...process.env,
      },
    },
    {
      command: `"${backendPython}" src/main.py`,
      cwd: path.join(rootDir, 'loan-army-backend'),
      url: apiHealthURL,
      reuseExistingServer: true,
      timeout: 120000,
      env: {
        ...process.env,
        API_USE_STUB_DATA: process.env.API_USE_STUB_DATA || 'true',
      },
    },
  ],
})
