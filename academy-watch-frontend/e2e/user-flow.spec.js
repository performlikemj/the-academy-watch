import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import { createDbClient, waitForEmailToken, getFirstTeam } from './helpers/db.js'
import { generateNewsletter } from './helpers/api.js'
import { loginWithCode } from './helpers/auth.js'

let dbClient
let team
let newsletterId

test.describe.serial('User experience flow', () => {
  test.beforeAll(async () => {
    dbClient = createDbClient()
    await dbClient.connect()
    team = await getFirstTeam(dbClient)

    const targetDate = new Date().toISOString().slice(0, 10)
    const generated = await generateNewsletter(team.id, targetDate)
    newsletterId = generated?.newsletter?.id
    if (!newsletterId) {
      throw new Error('Failed to generate newsletter for user flow')
    }
  })

  test.afterAll(async () => {
    if (dbClient) {
      await dbClient.end()
    }
  })

  test('subscribe to team updates and verify email token', async ({ page }) => {
    await page.goto('/teams')

    await page.getByRole('button', { name: /Subscribe to Team Updates/i }).click()

    await page.getByRole('combobox').filter({ hasText: /Search and select teams/i }).click()
    await page.getByPlaceholder('Search teams or leagues…').fill(team.name)
    await page.getByText(team.name, { exact: true }).first().click()
    await page.getByRole('button', { name: /^Done$/i }).click()

    await page.getByLabel('Email Address').fill(env.userEmail)
    await page.locator('button', { hasText: 'Subscribe (' }).click()

    await expect(page.getByText(/Successfully subscribed/i)).toBeVisible()

    const token = await waitForEmailToken(dbClient, env.userEmail, 'subscribe_confirm')
    await page.goto(`/verify?token=${token}`)
    await expect(page.getByText(/Subscriptions confirmed/i)).toBeVisible()
  })

  test('sign in and post a newsletter comment', async ({ page }) => {
    await loginWithCode(page, env.userEmail, dbClient, { displayName: 'E2E Supporter' })

    await page.goto(`/newsletters/${newsletterId}`)

    const openPreview = page.getByRole('button', { name: /Open quick preview/i }).first()
    if (await openPreview.isVisible().catch(() => false)) {
      await openPreview.click()
    }

    await page.getByPlaceholder('What stood out to you this week?').fill('Great roundup from the loan report.')
    await page.getByRole('button', { name: /Post Comment/i }).click()

    await expect(page.locator('div', { hasText: 'Great roundup from the loan report.' }).first()).toBeVisible()
  })
})
