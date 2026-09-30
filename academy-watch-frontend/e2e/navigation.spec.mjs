/* global document, innerWidth */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const primary = ['Clubs', 'Players', 'Scouts', 'Opportunities']
const removed = ['Home', 'Dream XI', 'Academy tracker', 'Teams', 'Newsletters', 'Journalists', 'Pricing']
const displayName = 'Synthetic Long Display Name For Navigation Review'

async function mockSession(page, { audience = 'visitor', contactRail = true, key = true, roles = false } = {}) {
  await page.addInitScript(({ audience, key, roles, displayName }) => {
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (audience !== 'visitor') {
      localStorage.setItem('academy_watch_user_token', 'synthetic-navigation-token')
      localStorage.setItem('academy_watch_display_name', displayName)
      localStorage.setItem('academy_watch_display_name_confirmed', 'true')
      localStorage.setItem('academy_watch_is_admin', String(audience === 'admin'))
      localStorage.setItem('academy_watch_is_journalist', String(roles))
      localStorage.setItem('academy_watch_is_curator', String(roles))
      if (audience === 'admin' && key) localStorage.setItem('academy_watch_admin_key', 'synthetic-navigation-key')
    }
  }, { audience, key, roles, displayName })
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/auth/me') return route.fulfill({ json: {
      email: 'synthetic-navigation@example.test', display_name: displayName, display_name_confirmed: true,
      role: audience === 'admin' ? 'admin' : 'user', account_role: audience === 'manager' ? 'club_manager' : 'scout',
      is_journalist: roles, is_curator: roles,
    } })
    if (pathname === '/api/features') return route.fulfill({ json: { contact_rail: contactRail } })
    if (pathname === '/api/meta/data-mode') return route.fulfill({ json: { api_football_frozen: false } })
    return route.fulfill({ json: {} })
  })
}

async function screenshot(page, slug) {
  if (!process.env.N1_SCREENSHOTS) return
  await fs.mkdir(process.env.N1_SCREENSHOTS, { recursive: true })
  await page.addStyleTag({ content: 'agentation, [data-agentation-root] { display: none !important; }' })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: path.join(process.env.N1_SCREENSHOTS, `${slug}.png`), fullPage: true, animations: 'disabled' })
}

for (const width of [1440, 390]) {
  for (const audience of ['visitor', 'scout', 'manager', 'admin']) {
    test(`${audience} navigation, search and logout at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await mockSession(page, { audience })
      await page.goto('/')
      const mobile = width === 390
      const nav = page.getByRole('navigation', { name: 'Main navigation' })
      if (mobile) await nav.getByRole('button', { name: 'Toggle navigation menu' }).click()
      const surface = mobile ? page.getByRole('dialog') : nav
      for (const label of primary) await expect(surface.getByRole('link', { name: label, exact: true })).toBeVisible()
      for (const label of removed) await expect(surface.getByRole('link', { name: label, exact: true })).toHaveCount(0)
      await expect(surface.getByRole('button', { name: 'More', exact: true })).toHaveCount(0)
      if (audience === 'visitor') {
        await expect(surface.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible()
        await expect(surface.getByRole('link', { name: 'Get early access', exact: true })).toBeVisible()
      } else {
        if (!mobile) await nav.getByRole('button', { name: displayName, exact: true }).click()
        const items = mobile ? surface.locator('a').filter({ hasNotText: /^Get early access$/ }) : page.getByRole('menuitem')
        const account = ['My club', 'Lists', 'Introductions', 'Settings', 'Billing', ...(audience === 'admin' ? ['Admin'] : [])]
        await expect(items).toHaveText(mobile ? [...primary, ...account] : [...account, 'Log out'])
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.evaluate(() => document.fonts.ready)
      if (audience !== 'visitor' && !mobile && !(await page.getByRole('menu').isVisible())) await nav.getByRole('button', { name: displayName, exact: true }).click()
      if (audience !== 'visitor' && !mobile) await expect(page.getByRole('menu')).toBeVisible()
      await screenshot(page, `${audience}-${mobile ? 'mobile' : 'desktop'}-menu-open`)
      if (audience !== 'visitor' && !mobile) await page.keyboard.press('Escape')
      await surface.getByRole('button', { name: 'Search', exact: true }).click()
      const search = page.getByRole('dialog', { name: 'Search', exact: true })
      await expect(search).toBeVisible()
      await page.keyboard.press('Escape')
      if (mobile) await nav.getByRole('button', { name: 'Toggle navigation menu' }).click()
      if (audience !== 'visitor') {
        if (!mobile) await nav.getByRole('button', { name: displayName, exact: true }).click()
        await page.getByRole(mobile ? 'button' : 'menuitem', { name: 'Log out', exact: true }).click()
        await expect.poll(() => page.evaluate(() => localStorage.getItem('academy_watch_user_token'))).toBeNull()
        if (mobile) await nav.getByRole('button', { name: 'Toggle navigation menu' }).click()
        await expect((mobile ? page.getByRole('dialog') : nav).getByRole('button', { name: 'Sign In', exact: true })).toBeVisible()
      } else if (mobile) {
        await page.keyboard.press('Escape')
      }
      if (mobile && audience !== 'visitor') await page.keyboard.press('Escape')
      await expect(page.locator('footer').getByRole('link', { name: 'Pricing', exact: true })).toHaveAttribute('href', '/pricing')
    })
  }
}

test('account menu supports keyboard navigation, gated roles and feature flags', async ({ page }) => {
  await mockSession(page, { audience: 'admin', roles: true, contactRail: false })
  await page.goto('/')
  const trigger = page.getByRole('button', { name: displayName, exact: true })
  await trigger.focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('menuitem')).toHaveText(['My club', 'Lists', 'Settings', 'Billing', 'Writer dashboard', 'Curator', 'Admin', 'Log out'])
  await expect(page.getByRole('menuitem', { name: 'My club', exact: true })).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('menuitem', { name: 'Lists', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByRole('menuitem', { name: 'Lists', exact: true }).click()
  await expect(page).toHaveURL(/\/scout\/lists$/)
  await expect(page.getByRole('menu')).toHaveCount(0)
})

for (const width of [1440, 390]) {
  test(`admin key controls still unlock the account entry at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockSession(page, { audience: 'admin', key: false })
    await page.goto('/')
    const mobile = width === 390
    if (mobile) await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
    else await page.getByRole('button', { name: displayName, exact: true }).click()
    await expect(page.getByRole(mobile ? 'link' : 'menuitem', { name: 'Admin', exact: true })).toHaveCount(0)
    if (!mobile) await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'API key needed', exact: true }).click()
    await page.getByLabel('API key', { exact: true }).fill('synthetic-new-key')
    await page.getByRole('button', { name: 'Save key', exact: true }).click()
    await expect(page.getByText('Admin ready', { exact: true })).toBeVisible()
    if (!mobile) await page.getByRole('button', { name: displayName, exact: true }).click()
    await expect(page.getByRole(mobile ? 'link' : 'menuitem', { name: 'Admin', exact: true })).toHaveAttribute('href', '/admin')
  })
}
