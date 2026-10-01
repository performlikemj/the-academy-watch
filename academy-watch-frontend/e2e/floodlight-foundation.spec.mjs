/* global document, innerWidth */
import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true'))
})

test('home leads to working audience flows and early access, with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Every player deserves to be seen.' })).toBeVisible()
  for (const [label, href] of [['Claim your club', '/my-club'], ['Start your player profile', '/onboarding/player'], ['Open the scout desk', '/scout'], ['Explore players', '/scout']]) {
    await expect(page.getByRole('link', { name: label })).toHaveAttribute('href', href)
  }
  await expect.poll(() => page.locator('video').evaluate((video) => video.paused)).toBe(true)
  await page.getByRole('link', { name: 'Get early access', exact: true }).first().click()
  await expect(page.getByLabel('Email address')).toBeInViewport()
  await expect(page.getByLabel('Your role')).toBeVisible()
})

for (const [path, feature] of [['/clubs', 'clubs_near_you'], ['/opportunities', 'opportunities']]) {
  test(`${path} submits its feature and treats duplicates as success`, async ({ page }) => {
    let submitted
    await page.route('**/api/interest', (route) => {
      submitted = route.request().postDataJSON()
      return route.fulfill({ status: 200, json: { status: 'already' } })
    })
    await page.goto(path)
    await page.getByLabel('Email address').fill('foundation-test@example.com')
    await page.getByRole('button', { name: "I'm interested", exact: true }).click()
    await expect(page.getByRole('status')).toHaveText("You're on the list. We'll email you when it opens.")
    expect(submitted).toEqual({ email: 'foundation-test@example.com', feature, source_path: path, website: '' })
  })
}

test('early access sends the selected role and recovers from a server error', async ({ page }) => {
  let requests = 0
  await page.route('**/api/interest', (route) => {
    const payload = route.request().postDataJSON()
    expect(payload.role).toBe('parent')
    expect(payload.feature).toBe('early_access')
    requests += 1
    return route.fulfill(requests === 1 ? { status: 503, json: { error: 'Please try again.' } } : { status: 201, json: { status: 'ok' } })
  })
  await page.goto('/#early-access')
  await page.getByLabel('Your role').selectOption('parent')
  await page.getByLabel('Email address').fill('foundation-test@example.com')
  await page.getByRole('button', { name: "I'm interested", exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Please try again.')
  await page.getByRole('button', { name: "I'm interested", exact: true }).click()
  await expect(page.getByRole('status')).toContainText("You're on the list.")
})

test('mobile shell has primary destinations and closes on navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
  for (const label of ['Clubs', 'Players', 'Scouts', 'Opportunities']) {
    await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible()
  }
  await page.getByRole('link', { name: 'Clubs', exact: true }).click()
  await expect(page).toHaveURL(/\/clubs$/)
  await expect(page.getByRole('heading', { name: 'Clubs near you.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Toggle navigation menu' })).toHaveAttribute('aria-expanded', 'false')
})

test('admin interest route keeps the existing sign-in boundary', async ({ page }) => {
  await page.goto('/admin/interest')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Every player deserves to be seen.' })).toBeVisible()
})

test('admin interest summarizes rows and downloads authenticated CSV at tablet width', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 })
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'foundation-admin-test')
    localStorage.setItem('academy_watch_admin_key', 'foundation-test-key')
    localStorage.setItem('academy_watch_is_admin', 'true')
  })
  await page.route('**/api/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/auth/me') return route.fulfill({ json: {
      email: 'foundation-test@example.com', role: 'admin', display_name: 'Synthetic test admin', display_name_confirmed: true,
    } })
    if (url.pathname === '/api/admin/interest') {
      expect(route.request().headers().authorization).toBe('Bearer foundation-admin-test')
      expect(route.request().headers()['x-api-key']).toBe('foundation-test-key')
      if (url.searchParams.get('format') === 'csv') return route.fulfill({ contentType: 'text/csv', body: 'id,email,feature,role,source_path,created_at\r\n' })
      return route.fulfill({ json: { total: 0, counts: { feature: { early_access: 0 }, role: { unspecified: 0 } }, rows: [] } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/admin/interest')
  await expect(page.getByText('No sign-ups yet. New interest will appear here.')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV', exact: true }).click(),
  ])
  expect(download.suggestedFilename()).toBe('interest-signups.csv')
})
