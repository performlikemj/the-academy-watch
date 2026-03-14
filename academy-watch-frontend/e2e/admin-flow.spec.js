import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import { createDbClient, getFirstTeam, insertEmptyNewsletter } from './helpers/db.js'
import { loginWithCode, setAdminKey } from './helpers/auth.js'

let dbClient
let team
let emptyNewsletter

test.describe.serial('Admin workflows', () => {
  test.beforeAll(async () => {
    if (!env.adminKey) {
      throw new Error('ADMIN_API_KEY is required for admin E2E tests')
    }

    dbClient = createDbClient()
    await dbClient.connect()
    team = await getFirstTeam(dbClient)
    emptyNewsletter = await insertEmptyNewsletter(dbClient, team.id)
  })

  test.afterAll(async () => {
    if (dbClient) {
      await dbClient.end()
    }
  })

  test('generate newsletter and delete empty newsletter', async ({ page }) => {
    await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(page, env.adminKey)

    await page.goto('/admin/newsletters')
    await expect(page.getByRole('heading', { name: 'Newsletters' })).toBeVisible()

    const toDateInput = (value) => {
      const year = value.getFullYear()
      const month = String(value.getMonth() + 1).padStart(2, '0')
      const day = String(value.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }
    const lastSunday = new Date()
    const day = lastSunday.getDay()
    const diff = day === 0 ? 7 : day
    lastSunday.setDate(lastSunday.getDate() - diff)
    await page.getByLabel('Target Week Date').fill(toDateInput(lastSunday))

    const teamSelect = page.getByRole('combobox').filter({ hasText: /Select teams/i })
    await teamSelect.click()
    const teamSearch = page.getByPlaceholder('Search teams or leagues…')
    await teamSearch.fill(team.name)
    const teamOption = page.locator('[data-slot="command-item"]').filter({ hasText: team.name }).first()
    await expect(teamOption).toBeVisible()
    await teamOption.click()
    await page.getByRole('button', { name: /^Done$/i }).click()

    await page.getByRole('button', { name: /Generate for Selected/i }).click()
    const statusAlert = page.getByRole('alert')
    await expect(statusAlert).toContainText(/Generated \d+ newsletter/i, { timeout: 60000 })

    const row = page.locator('tr', { hasText: `#${emptyNewsletter.id}` })
    await expect(row).toHaveCount(1, { timeout: 10000 })
    await row.getByTitle('Delete').click()
    await page.getByRole('button', { name: /^Delete$/i }).click()

    await expect(page.getByText('Newsletter deleted')).toBeVisible()
    await expect(page.locator('tr', { hasText: `#${emptyNewsletter.id}` })).toHaveCount(0)
  })
})
