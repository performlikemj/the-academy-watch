/* global document, innerWidth */
import { expect, test } from '@playwright/test'

// Synthetic API data only. Exercise the production console and existing URL views.
async function club(page, { unassigned = 2, matchError = false, matches = [{ id: 41, status: 'created' }, { id: 42, status: 'finalized' }] } = {}) {
  await page.addInitScript(() => localStorage.setItem('academy_watch_user_token', 'synthetic-manager'))
  const program = { id: 7, name: 'Synthetic Floodlight Club', slug: 'synthetic-floodlight-club', platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const reply = json => route.fulfill({ json })
    if (url.pathname === '/api/funding/claims/me') return reply({ claims: [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] })
    if (url.pathname === '/api/me/club-claims') return reply({ claims: [] })
    if (url.pathname === '/api/me/club') return reply({ clubs: [] })
    if (url.pathname === '/api/club/7/roster') return reply({ program, members: [], count: 0 })
    if (url.pathname === '/api/club/7/map') return reply({ program, squads: [], staff: [], unassigned_count: unassigned })
    if (url.pathname === '/api/club/7/matches') return matchError ? route.fulfill({ status: 500, json: { error: 'synthetic_unavailable' } }) : reply({ matches, total: matches.length })
    if (url.pathname === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    return reply({})
  })
}

for (const width of [1440, 390]) {
  test(`Today only counts supported tasks and recruiting stays a teaser at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await club(page)
    await page.goto('/my-club?view=today')
    await expect(page.locator('.ch-task')).toHaveCount(2)
    await expect(page.locator('.ch-task').filter({ hasText: 'Give every player a squad' }).locator('.ch-task-number')).toHaveText('2')
    await expect(page.locator('.ch-task').filter({ hasText: 'Bring the match into Film Room' }).locator('.ch-task-number')).toHaveText('1')
    await expect(page.locator('.ch-task')).not.toContainText(['trial', 'application', 'staff invite', 'highlight'])
    await expect(page.getByRole('button', { name: 'Review club affiliations' })).toHaveCount(0)
    if (width === 390) await page.getByRole('button', { name: 'Squads & club navigation' }).click()
    await page.getByRole('button', { name: 'Recruiting', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'The next player. The right place.' })).toBeVisible()
    await expect(page.getByRole('button', { name: "I'm interested", exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })
}

test('failed match loading never creates an upload task or an all-clear claim', async ({ page }) => {
  await club(page, { unassigned: 0, matchError: true })
  await page.goto('/my-club?view=today')
  await expect(page.getByText('Some club information could not be checked. Open the relevant section to retry.')).toBeVisible()
  await expect(page.locator('.ch-task')).toHaveCount(0)
})

test('player applications sign-up sends the existing feature and fixed role', async ({ page }) => {
  let submitted
  await page.route('**/api/**', async route => {
    if (new URL(route.request().url()).pathname === '/api/interest') {
      submitted = route.request().postDataJSON()
      return route.fulfill({ status: 201, json: { status: 'ok' } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/onboarding/player')
  await page.getByLabel('Email address', { exact: true }).fill('synthetic-player@example.test')
  await page.getByRole('button', { name: "I'm interested", exact: true }).click()
  await expect(page.getByText("You're on the list. We'll email you when it opens.")).toBeVisible()
  expect(submitted).toMatchObject({ feature: 'player_applications', role: 'player', source_path: '/onboarding/player' })
})
