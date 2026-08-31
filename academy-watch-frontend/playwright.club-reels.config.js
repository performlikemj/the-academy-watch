import { defineConfig, devices } from '@playwright/test'

const baseURL = 'http://127.0.0.1:5275'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: './test-results/club-reels',
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 5275',
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
