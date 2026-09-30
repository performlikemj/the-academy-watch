/* global document, getComputedStyle */
import { test, expect } from '@playwright/test'

const longName = 'Synthetic Long Display Name For Floodlight Review'
const clubName = 'NorthamptonshireAcademy'

async function mockApp(page, { primary = '#767676', admin = false } = {}) {
  await page.addInitScript(({ admin }) => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-review-token')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (admin) {
      localStorage.setItem('academy_watch_admin_key', 'synthetic-key')
      localStorage.setItem('academy_watch_is_admin', 'true')
    }
  }, { admin })
  const program = { id: 7, name: clubName, slug: 'synthetic-review', platform_status: 'approved', brand: { primary_color: primary, accent_color: '#CFAE62' } }
  const member = { id: 8, available: true, display_name: 'Synthetic Player', subject_type: 'local', local_player_id: 8, squad_id: 1, shirt_number: 8 }
  const squads = [{ id: 1, name: 'Synthetic Reserves', member_count: 1, lead_staff_id: 1 }, { id: 2, name: 'Synthetic Juniors', member_count: 0 }]
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const reply = json => route.fulfill({ json })
    if (path === '/api/auth/me') return reply({ email: 'synthetic@example.test', role: admin ? 'admin' : 'user', display_name: longName, display_name_confirmed: true, account_role: 'club_manager' })
    if (path === '/api/funding/claims/me') return reply({ claims: [{ id: 1, status: 'approved', relationship_type: 'club_official', program }] })
    if (path === '/api/me/club-claims') return reply({ claims: [] })
    if (path === '/api/me/club') return reply({ clubs: [] })
    if (path === '/api/club/7/roster') return reply({ program, members: [member], count: 1 })
    if (path === '/api/club/7/map') return reply({ program, squads, staff: [{ id: 1, display_name: 'Synthetic Coach', title: 'Coach' }], unassigned_count: 0 })
    if (path === '/api/club/7/roster/8/profile') return reply({ identity: member, film: [], development: [], results: {} })
    if (path === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    if (path === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (path === '/api/admin/interest') return reply({ total: 0, counts: { feature: {}, role: {} }, rows: [] })
    return reply({})
  })
}

// Measure computed browser styles rather than assuming the chosen CSS tokens work.
async function ratio(locator, property, background) {
  return locator.evaluate((node, { property, background }) => {
    const luminance = colour => {
      const values = colour.match(/[\d.]+/g).slice(0, 3).map(Number).map(c => c / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
      return values[0] * .2126 + values[1] * .7152 + values[2] * .0722
    }
    const style = getComputedStyle(node)
    const painted = node.closest(background)
    const a = luminance(style[property]), b = luminance(getComputedStyle(painted).backgroundColor)
    return { contrast: (Math.max(a, b) + .05) / (Math.min(a, b) + .05), opacity: style.opacity, outlineStyle: style.outlineStyle }
  }, { property, background })
}

for (const primary of ['#0F3D2E', '#767676']) {
  test(`club text, selected rows and keyboard focus remain readable on ${primary}`, async ({ page }) => {
    await mockApp(page, { primary })
    await page.goto('/my-club?view=map')
    await expect(page.locator('.ch-node.squad').first()).toContainText('1 player')
    await expect(page.locator('.ch-club-id')).toContainText('Verified club · 1 player')
    for (const [selector, surface] of [['.ch-banner p', '.ch-banner'], ['.ch-club-id small', '.ch-sidebar'], ['.ch-sidebar .ch-eyebrow', '.ch-sidebar'], ['.ch-sidebar button small', '.ch-sidebar'], ['.ch-pitch-note', '.ch-pitch'], ['.ch-node.squad small', '.ch-node.squad']]) {
      const result = await ratio(page.locator(selector).first(), 'color', surface)
      expect(result.contrast, selector).toBeGreaterThanOrEqual(4.5)
      expect(result.opacity, selector).toBe('1')
    }
    const selected = page.locator('.ch-sidebar > button.active').first()
    await selected.hover()
    expect((await ratio(selected, 'color', '.active')).contrast).toBeGreaterThanOrEqual(4.5)
    const hovered = page.locator('.ch-sidebar').getByRole('button', { name: 'Staff', exact: true })
    await hovered.hover()
    expect((await ratio(hovered, 'color', 'button')).contrast).toBeGreaterThanOrEqual(4.5)
    await page.keyboard.press('Tab')
    for (const [selector, surface] of [['.ch-banner-edit', '.ch-banner'], ['.ch-node.staff', '.ch-pitch'], ['.ch-tree-scroll', '.ch-pitch'], ['.ch-content > .ch-heading .ch-btn', '.club-home']]) {
      const target = page.locator(selector); await target.focus()
      const result = await ratio(target, 'outlineColor', surface)
      expect(result.outlineStyle).toBe('solid')
      expect(result.contrast, selector).toBeGreaterThanOrEqual(3)
    }
    expect(await page.locator('.ch-pitch').evaluate(node => getComputedStyle(node, '::after').content)).toBe('none')
    const clubFilter = page.locator('.ch-pills button[aria-pressed=true]'); await clubFilter.focus()
    expect((await ratio(clubFilter, 'outlineColor', 'button')).contrast).toBeGreaterThanOrEqual(3)
    await page.goto('/my-club?program=7&player=8')
    await expect(page.locator('.ch-player-identity')).toBeVisible()
    expect(await page.locator('.ch-player-hero').evaluate(node => getComputedStyle(node).backgroundImage)).toBe('none')
    for (const selector of ['.ch-player-identity p', '.ch-breadcrumb', '.ch-btn.outline']) expect((await ratio(page.locator(selector).first(), 'color', '.ch-player-hero')).contrast).toBeGreaterThanOrEqual(4.5)
    await page.keyboard.press('Tab'); const upload = page.getByRole('button', { name: 'Upload photo', exact: true }); await upload.focus()
    expect((await ratio(upload, 'outlineColor', '.ch-player-hero')).contrast).toBeGreaterThanOrEqual(3)
  })
}

for (const width of [1440, 1024, 390]) {
  test(`signed-in header fits a long name and keeps logout reachable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockApp(page)
    await page.goto('/my-club?view=map')
    await expect(page.locator('.ch-banner h1')).toHaveText(clubName)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
    if (width === 390) await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
    await expect(page.getByRole('link', { name: 'Get early access', exact: true })).toHaveCount(0)
    const name = page.getByText(longName, { exact: true }); await expect(name).toBeVisible()
    const logout = page.getByRole('button', { name: 'Log Out', exact: true }); await expect(logout).toBeVisible()
    if (width !== 390) {
      expect(await name.evaluate(node => node.scrollWidth > node.clientWidth && getComputedStyle(node).textOverflow === 'ellipsis')).toBe(true)
      const nameBox = await name.boundingBox(), logoutBox = await logout.boundingBox()
      expect(nameBox.x + nameBox.width).toBeLessThanOrEqual(logoutBox.x)
      expect(logoutBox.x + logoutBox.width).toBeLessThanOrEqual(width)
    }
    await logout.click()
    if (width === 390) await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
    await expect(page.getByRole('link', { name: 'Get early access', exact: true })).toBeVisible()
  })
}

test('admin uses its own chrome without the public header', async ({ page }) => {
  await mockApp(page, { admin: true })
  await page.goto('/admin/interest')
  await expect(page.getByText('No sign-ups yet. New interest will appear here.')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Log out', exact: true })).toBeVisible()
})
