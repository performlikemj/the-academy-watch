import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import { createDbClient, waitForEmailToken, createLoginToken } from './helpers/db.js'
import { inviteJournalist, verifyLoginCode } from './helpers/api.js'

let dbClient
let adminToken

test.describe.serial('Writer portal flow', () => {
  test.beforeAll(async () => {
    if (!env.adminKey) {
      throw new Error('ADMIN_API_KEY is required for writer E2E tests')
    }

    dbClient = createDbClient()
    await dbClient.connect()

    const adminCode = await createLoginToken(dbClient, env.adminEmail)
    const adminAuth = await verifyLoginCode(env.adminEmail, adminCode)
    adminToken = adminAuth?.token

    if (!adminToken) {
      throw new Error('Failed to resolve admin bearer token for writer setup')
    }

    await inviteJournalist(env.writerEmail, { adminKey: env.adminKey, token: adminToken, bio: 'E2E writer' })
  })

  test.afterAll(async () => {
    if (dbClient) {
      await dbClient.end()
    }
  })

  test('login and reach writer dashboard', async ({ page }) => {
    await page.goto('/writer/login')

    await page.getByLabel('Email').fill(env.writerEmail)
    await page.getByRole('button', { name: /Send Login Code/i }).click()

    const code = await waitForEmailToken(dbClient, env.writerEmail, 'login')
    await page.getByLabel('Verification Code').fill(code)
    await page.getByRole('button', { name: /Verify & Login/i }).click()

    await expect(page.getByRole('heading', { name: /Writer Dashboard/i })).toBeVisible()
  })
})
