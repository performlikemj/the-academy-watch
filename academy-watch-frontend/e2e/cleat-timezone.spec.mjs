/* global document, innerWidth, getComputedStyle */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const opportunityId = '00000000-0000-4000-8000-000000000051'

async function screenshot(page, name) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (!process.env.N5_SCREENSHOTS) return
  await fs.mkdir(process.env.N5_SCREENSHOTS, { recursive: true })
  await page.screenshot({ path: path.join(process.env.N5_SCREENSHOTS, `${name}.png`), fullPage: true })
}

async function mountLoader(page, surface) {
  // Render the production component without adding a fixture route to the application.
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: `
    import React from '/node_modules/.vite/deps/react.js';
    import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import { CleatLoader } from '/src/components/CleatLoader.jsx';
    document.body.style.margin = '0';
    document.body.style.background = '${surface === 'night' ? '#0B0E0D' : '#F3F0E8'}';
    const mount = document.createElement('div');
    mount.style.cssText = 'min-height:100dvh;display:flex;align-items:center';
    document.getElementById('root').replaceWith(mount);
    ReactDOM.createRoot(mount).render(React.createElement(CleatLoader, { surface: '${surface}' }));
  ` }))
  await page.goto('/')
  await expect(page.locator(`.cleat-loader[data-surface="${surface}"]`)).toBeVisible()
}

async function recruitingFixture(page, { saved, locked = false, itemZone = 'Europe/London' } = {}) {
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem('academy_watch_user_token', 'synthetic-n5-token')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    localStorage.setItem('academy_watch_display_name', 'Synthetic N5 Manager')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
  })
  const program = { id: 7, name: 'Synthetic N5 Club', slug: 'synthetic-n5', platform_status: 'approved', timezone: saved, brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
  const opportunity = { id: opportunityId, program_id: 7, type: 'trial', title: 'Synthetic N5 trial', description: 'Only a synthetic browser fixture.', venue: 'Test pitch', timezone: itemZone, starts_at: '2026-10-20T10:00:00Z', closes_at: '2026-10-18T10:00:00Z', status: 'published', gender_program: 'all', version: 2, application_count: locked ? 1 : 0 }
  const writes = []
  await page.route('**/api/**', route => {
    const req = route.request(), p = new URL(req.url()).pathname
    const reply = json => route.fulfill({ json })
    if (p.startsWith('/api/club/7/opportunities') && ['POST', 'PATCH'].includes(req.method())) { writes.push(req.postDataJSON()); return reply({ opportunity }) }
    if (p === '/api/opportunities/features') return reply({ opportunities: true, applications: true })
    if (p === '/api/club/7/opportunities') return reply({ opportunities: [opportunity], has_more: false })
    if (p.endsWith('/applications')) return reply({ applications: [], has_more: false })
    if (p === '/api/funding/claims/me') return reply({ claims: [{ id: 51, status: 'approved', relationship_type: 'club_official', program }] })
    if (p === '/api/me/club-claims') return reply({ claims: [] })
    if (p === '/api/me/club') return reply({ clubs: [] })
    if (p === '/api/club/7/roster') return reply({ program, members: [], count: 0 })
    if (p === '/api/club/7/map') return reply({ program, squads: [], staff: [], unassigned_count: 0 })
    if (p === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (p === '/api/auth/me') return reply({ email: 'n5@example.test', display_name: 'Synthetic N5 Manager', display_name_confirmed: true, role: 'user' })
    return reply({})
  })
  await page.goto('/my-club?view=recruiting')
  await expect(page.getByRole('heading', { name: 'Synthetic N5 trial', exact: true })).toBeVisible()
  return writes
}

for (const width of [1440, 390]) {
  const size = width === 390 ? 'mobile' : 'desktop'
  for (const surface of ['chalk', 'night']) {
    test(`cleat loader on ${surface}, ${size}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await mountLoader(page, surface)
      await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
      await expect(page.locator('.cleat-loader svg')).toHaveAttribute('stroke-width', '2')
      const frames = await page.locator('.cleat-accent').evaluate(element => {
        const animation = element.getAnimations()[0]
        animation.pause()
        return [0, 1200, 2400, 3600, 4800, 6000, 7200].map(time => {
          animation.currentTime = time
          return { fill: getComputedStyle(element).fill, stroke: getComputedStyle(element).stroke }
        })
      })
      expect(frames.map(frame => frame.fill)).toEqual(['rgb(15, 61, 46)', 'rgb(122, 20, 38)', 'rgb(31, 62, 115)', 'rgb(11, 14, 13)', 'rgb(227, 93, 24)', 'rgb(108, 172, 228)', 'rgb(15, 61, 46)'])
      expect(frames[3].stroke).toBe('rgb(207, 174, 98)')
      await page.locator('.cleat-body').evaluate(element => { const animation = element.getAnimations()[0]; animation.pause(); animation.currentTime = 0 })
      await screenshot(page, `loader-${surface}-${size}`)
    })
  }

  test(`time-zone picker searches aliases and saves canonical selection, ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    const writes = await recruitingFixture(page, { saved: 'Europe/London' })
    await page.getByRole('button', { name: 'New opportunity' }).click()
    const picker = page.getByRole('combobox', { name: 'Time zone', exact: true })
    await expect(picker).toContainText('Europe/London')
    await picker.click()
    await expect(page.getByRole('combobox', { name: 'Search time zones' })).toBeFocused()
    await expect(page.getByText('Europe', { exact: true })).toBeVisible()
    await screenshot(page, `picker-open-${size}`)
    await page.getByRole('combobox', { name: 'Search time zones' }).fill('Calcutta')
    await expect(page.getByRole('listbox', { name: 'Time zones' }).getByRole('option')).toHaveCount(1)
    await expect(page.getByRole('listbox', { name: 'Time zones' }).getByRole('option')).toContainText('Kolkata — UTC+05:30 (now)')
    await page.getByRole('combobox', { name: 'Search time zones' }).press('ArrowDown')
    await page.getByRole('combobox', { name: 'Search time zones' }).press('Enter')
    await expect(picker).toContainText('Asia/Kolkata')
    await expect(picker).toBeFocused()
    await page.getByLabel('Title', { exact: true }).fill('Synthetic N5 vacancy')
    await page.getByLabel('About this opportunity', { exact: true }).fill('Only a browser test vacancy.')
    await page.getByLabel('Opportunity type').selectOption('position')
    await page.getByLabel('Venue', { exact: true }).fill('Test pitch')
    await page.getByLabel('Applications close (Asia/Kolkata)', { exact: true }).fill('2026-10-18T12:00')
    await page.getByRole('button', { name: 'Save opportunity' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(writes.at(-1).timezone).toBe('Asia/Kolkata')
    expect(writes.at(-1).closes_at).toBe('2026-10-18T06:30:00.000Z')
  })
}

test('reduced motion keeps both React and boot loaders still green', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.route('**/src/main.jsx*', route => route.abort())
  await page.goto('/')
  await expect(page.getByRole('status', { name: 'Loading' })).toBeVisible()
  expect(await page.locator('.cleat-accent').evaluate(element => ({ fill: getComputedStyle(element).fill, stroke: getComputedStyle(element).stroke, animations: element.getAnimations().length }))).toEqual({ fill: 'rgb(15, 61, 46)', stroke: 'rgb(15, 61, 46)', animations: 0 })
  await page.unroute('**/src/main.jsx*')
  await mountLoader(page, 'night')
  expect(await page.locator('.cleat-accent').evaluate(element => ({ fill: getComputedStyle(element).fill, animations: element.getAnimations().length }))).toEqual({ fill: 'rgb(15, 61, 46)', animations: 0 })
})

test('club saved zone wins over browser; editing retains the post zone', async ({ page }) => {
  await recruitingFixture(page, { saved: 'Asia/Calcutta', itemZone: 'Europe/Kiev' })
  await page.getByRole('button', { name: 'New opportunity' }).click()
  await expect(page.getByRole('combobox', { name: 'Time zone', exact: true })).toContainText('Asia/Kolkata')
  await page.getByRole('button', { name: 'Close editor' }).click()
  await page.getByRole('button', { name: 'Edit opportunity' }).click()
  await expect(page.getByRole('combobox', { name: 'Time zone', exact: true })).toContainText('Europe/Kyiv')
})

test('locked post disables picker and omits locked fields from save', async ({ page }) => {
  const writes = await recruitingFixture(page, { locked: true })
  await page.getByRole('button', { name: 'Edit opportunity' }).click()
  await expect(page.getByRole('combobox', { name: 'Time zone', exact: true })).toBeDisabled()
  await expect(page.getByRole('combobox', { name: 'Time zone', exact: true })).toContainText('Europe/London')
  await expect(page.getByLabel('Starts (Europe/London)', { exact: true })).toHaveValue('2026-10-20T11:00')
  await page.getByRole('button', { name: 'Save opportunity' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(writes.at(-1)).toEqual({ status: 'published', expected_version: 2 })
})

test('picker empty search, Escape and pointer selection work in native modal', async ({ page }) => {
  await recruitingFixture(page)
  await page.getByRole('button', { name: 'New opportunity' }).click()
  const picker = page.getByRole('combobox', { name: 'Time zone', exact: true })
  await picker.click()
  await page.getByRole('combobox', { name: 'Search time zones' }).fill('not-a-zone')
  await expect(page.getByText('No time zones found.')).toBeVisible()
  await page.getByRole('combobox', { name: 'Search time zones' }).press('Escape')
  await expect(page.getByRole('dialog', { name: 'New opportunity' })).toBeVisible()
  await expect(picker).toBeFocused()
  await picker.click()
  await page.getByRole('combobox', { name: 'Search time zones' }).fill('Tokyo')
  await page.getByRole('listbox', { name: 'Time zones' }).getByRole('option').click()
  await expect(picker).toContainText('Asia/Tokyo')
})

test('real club route uses the shared loader while waiting for clubs', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('academy_watch_user_token', 'synthetic-n5-token'))
  await page.route('**/api/**', route => {
    const p = new URL(route.request().url()).pathname
    if (p === '/api/me/club') return new Promise(() => {})
    if (p === '/api/auth/me') return route.fulfill({ json: { email: 'n5@example.test', role: 'user' } })
    return route.fulfill({ json: {} })
  })
  await page.goto('/my-club')
  await expect(page.locator('.cleat-loader svg')).toBeVisible()
})
