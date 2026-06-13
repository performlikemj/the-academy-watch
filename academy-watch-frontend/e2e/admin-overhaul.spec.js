import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import { createDbClient } from './helpers/db.js'
import { loginWithCode, setAdminKey } from './helpers/auth.js'

let dbClient

// Smoke coverage for the admin overhaul: every page in the new IA renders,
// the sidebar exposes the new structure, and the operations console loads
// real data. No mutating actions are triggered.
test.describe.serial('Admin overhaul smoke', () => {
  test.beforeAll(async () => {
    if (!env.adminKey) {
      throw new Error('ADMIN_API_KEY is required for admin E2E tests')
    }
    dbClient = createDbClient()
    await dbClient.connect()
  })

  test.afterAll(async () => {
    if (dbClient) await dbClient.end()
  })

  test('sidebar exposes the new information architecture', async ({ page }) => {
    await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(page, env.adminKey)
    await page.goto('/admin/dashboard')

    for (const label of [
      'Dashboard', 'Inbox', 'Players', 'Teams', 'Youth Leagues', 'Cohorts',
      'Seeding & Rebuild', 'Newsletters', 'Sponsors', 'Users & Writers',
      'Film Room', 'Operations', 'API & Configs', 'Classifier Tester', 'Settings',
    ]) {
      await expect(page.getByRole('link', { name: label, exact: false }).first()).toBeVisible()
    }
  })

  test('every page in the new IA renders without crashing', async ({ page }) => {
    await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(page, env.adminKey)

    const pages = [
      ['/admin/dashboard', /Admin|Dashboard|Welcome/i],
      ['/admin/inbox', /Inbox/i],
      ['/admin/operations', /Operations/i],
      ['/admin/seeding', /Seeding/i],
      ['/admin/players', /Players/i],
      ['/admin/teams', /Teams/i],
      ['/admin/academy', /Youth|Academy/i],
      ['/admin/cohorts', /Cohort/i],
      ['/admin/newsletters', /Newsletters/i],
      ['/admin/sponsors', /Sponsor/i],
      ['/admin/users', /Users|Writers/i],
      ['/admin/video', /Film Room|Video/i],
      ['/admin/tools', /API|Config|Tools/i],
      ['/admin/sandbox', /Classifier/i],
      ['/admin/settings', /Settings/i],
    ]

    const consoleErrors = []
    page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

    for (const [path, headingPattern] of pages) {
      await page.goto(path)
      await expect(
        page.locator('main h1, main h2').filter({ hasText: headingPattern }).first()
      ).toBeVisible({ timeout: 15000 })
    }

    expect(consoleErrors, `Uncaught page errors: ${consoleErrors.join('; ')}`).toHaveLength(0)
  })

  test('operations console loads system status and duties', async ({ page }) => {
    await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(page, env.adminKey)
    await page.goto('/admin/operations')

    // System status renders real ops/overview numbers (active tracked count)
    await expect(page.getByText(/active tracked|active players|Active/i).first()).toBeVisible({ timeout: 15000 })
    // The repair runners exist but are not triggered
    await expect(page.getByTestId('cursor-runner-dry').first()).toBeVisible()
  })

  test('legacy routes redirect into the inbox', async ({ page }) => {
    await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(page, env.adminKey)

    await page.goto('/admin/curation')
    await expect(page).toHaveURL(/\/admin\/inbox\?tab=takes/)
    await page.goto('/admin/flags')
    await expect(page).toHaveURL(/\/admin\/inbox\?tab=flags/)
    await page.goto('/admin/old')
    await expect(page).not.toHaveURL(/admin\/old/)
  })

  test('inbox tabs switch and load', async ({ page }) => {
    await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(page, env.adminKey)
    await page.goto('/admin/inbox')
    await expect(page.getByRole('heading', { name: /Inbox/i }).first()).toBeVisible()

    for (const tab of ['takes', 'submissions', 'flags', 'tracking', 'links']) {
      await page.goto(`/admin/inbox?tab=${tab}`)
      await expect(page.locator('[role="tablist"]')).toBeVisible({ timeout: 10000 })
    }
  })
})
