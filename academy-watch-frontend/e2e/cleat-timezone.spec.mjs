/* global document, innerWidth, getComputedStyle, window */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const opportunityId = '00000000-0000-4000-8000-000000000051'

async function screenshot(page, name) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (!process.env.N5_SCREENSHOTS) return
  await fs.mkdir(process.env.N5_SCREENSHOTS, { recursive: true })
  await page.screenshot({ path: path.join(process.env.N5_SCREENSHOTS, `${name}.png`), fullPage: !name.startsWith('picker') })
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
    if (p === '/api/features' || p === '/api/opportunities/features') return reply({ opportunities: true, applications: true })
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
      await expect(page.locator('.cleat-loader svg')).toHaveAttribute('data-brand-logo', 'academy-watch-winged-boot')
      const frames = await page.locator('.cleat-body').evaluate(element => {
        const animation = element.getAnimations()[0]
        animation.pause()
        return [0, 1200, 2400, 3600, 4800, 6000, 7200].map(time => {
          animation.currentTime = time
          return { fill: getComputedStyle(element).fill, opacity: getComputedStyle(element).fillOpacity }
        })
      })
      expect(frames.map(frame => frame.fill)).toEqual(['rgb(15, 61, 46)', 'rgb(122, 20, 38)', 'rgb(31, 62, 115)', 'rgb(11, 14, 13)', 'rgb(227, 93, 24)', 'rgb(108, 172, 228)', 'rgb(15, 61, 46)'])
      expect(frames.every(frame => frame.opacity === '1')).toBe(true)
      const transition = await page.locator('.cleat-body').evaluate(element => {
        const animation = element.getAnimations()[0]
        return [1000, 1100, 1200].map(time => { animation.currentTime = time; return getComputedStyle(element).fill })
      })
      expect(transition[0]).toBe(frames[0].fill)
      expect(transition[2]).toBe(frames[1].fill)
      expect(transition[1]).not.toBe(transition[0])
      expect(transition[1]).not.toBe(transition[2])
      const phases = ['green', 'claret', 'navy', 'black-gold', 'orange', 'sky']
      for (const [index, phase] of phases.entries()) {
        await page.locator('.cleat-body,.cleat-accent').evaluateAll((elements, time) => {
          for (const element of elements) { const animation = element.getAnimations()[0]; animation.pause(); animation.currentTime = time }
        }, index * 1200)
        await expect(page.locator('.cleat-accent')).toHaveCSS('fill', index === 3 ? 'rgb(207, 174, 98)' : frames[index].fill)
        await expect(page.locator('.cleat-wing')).toHaveCSS('fill', 'rgb(255, 255, 255)')
        await screenshot(page, `loader-${surface}-${size}-phase-${phase}`)
      }
      await page.locator('.cleat-body,.cleat-accent').evaluateAll(elements => {
        for (const element of elements) element.getAnimations()[0].currentTime = 0
      })
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
  expect(await page.locator('.cleat-body').evaluate(element => ({ fill: getComputedStyle(element).fill, opacity: getComputedStyle(element).fillOpacity, animations: element.getAnimations().length }))).toEqual({ fill: 'rgb(15, 61, 46)', opacity: '1', animations: 0 })
  expect(await page.locator('.cleat-body,.cleat-accent').evaluateAll(elements => elements.every(element => element.getAnimations().length === 0))).toBe(true)
  await page.unroute('**/src/main.jsx*')
  await mountLoader(page, 'night')
  expect(await page.locator('.cleat-accent').evaluate(element => ({ fill: getComputedStyle(element).fill, animations: element.getAnimations().length }))).toEqual({ fill: 'rgb(15, 61, 46)', animations: 0 })
  await expect(page.locator('.cleat-wing')).toHaveCSS('fill', 'rgb(255, 255, 255)')
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

for (const failure of ['zone', 'shortOffset']) {
  for (const mode of ['New', 'Edit']) {
    test(`unsupported Intl ${failure}: ${mode} editor opens and saves`, async ({ page }) => {
      await page.addInitScript(failure => {
        const original = Intl.DateTimeFormat
        Intl.DateTimeFormat = function (locale, options) {
          if (failure === 'zone' && options?.timeZone === 'America/Coyhaique') throw new RangeError('unsupported zone')
          if (failure === 'shortOffset' && options?.timeZoneName === 'shortOffset') throw new RangeError('unsupported offset')
          return new original(locale, options)
        }
      }, failure)
      const writes = await recruitingFixture(page, { saved: 'Europe/London' })
      await page.getByRole('button', { name: `${mode} opportunity` }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
      const picker = page.getByRole('combobox', { name: 'Time zone', exact: true })
      await expect(picker).toContainText('Europe/London')
      await picker.click()
      const search = page.getByRole('combobox', { name: 'Search time zones' })
      if (failure === 'zone') {
        await search.fill('Coyhaique')
        await expect(page.getByText('No time zones found.')).toBeVisible()
      } else {
        await search.fill('London')
        await expect(page.getByRole('listbox', { name: 'Time zones' }).getByRole('option')).toHaveCount(1)
        await expect(page.getByRole('listbox', { name: 'Time zones' }).getByRole('option')).not.toContainText('(now)')
      }
      await search.fill('Tokyo')
      await page.getByRole('listbox', { name: 'Time zones' }).getByRole('option').click()
      await page.getByLabel('Title', { exact: true }).fill('Synthetic compatibility post')
      await page.getByLabel('About this opportunity').fill('Synthetic compatibility regression.')
      await page.getByLabel('Opportunity type').selectOption('position')
      await page.getByLabel('Venue', { exact: true }).fill('Test pitch')
      await page.getByLabel('Applications close (Asia/Tokyo)', { exact: true }).fill('2026-10-18T12:00')
      await page.getByRole('button', { name: 'Save opportunity' }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      expect(writes.at(-1).timezone).toBe('Asia/Tokyo')
    })
  }
}

test('unsupported saved selection keeps its canonical trigger label', async ({ page }) => {
  await page.addInitScript(() => {
    const original = Intl.DateTimeFormat
    Intl.DateTimeFormat = function (locale, options) {
      if (options?.timeZone === 'America/Coyhaique') throw new RangeError('unsupported zone')
      return new original(locale, options)
    }
  })
  await recruitingFixture(page, { itemZone: 'America/Coyhaique' })
  await page.getByRole('button', { name: 'Edit opportunity' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Time zone', exact: true })).toContainText('America/Coyhaique')
})

for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }, { width: 320, height: 568 }]) {
  test(`current selection is visible; Enter preserves it; UTC and offsets search, ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await recruitingFixture(page, { saved: 'Europe/London' })
    await page.getByRole('button', { name: 'New opportunity' }).click()
    const picker = page.getByRole('combobox', { name: 'Time zone', exact: true })
    await picker.click()
    const search = page.getByRole('combobox', { name: 'Search time zones' })
    const active = page.locator('[cmdk-item][data-selected=true]')
    await expect(active).toContainText('Europe/London')
    await expect(active).toBeInViewport({ ratio: 1 })
    expect(await active.evaluate(element => getComputedStyle(element).boxShadow)).not.toBe('none')
    const list = page.getByRole('listbox', { name: 'Time zones' })
    expect((await list.boundingBox()).height).toBeGreaterThanOrEqual(156)
    const popover = await page.locator('.opp-timezone-popover').boundingBox()
    expect(popover.y).toBeGreaterThanOrEqual(0)
    expect(popover.y + popover.height).toBeLessThanOrEqual(viewport.height)
    await screenshot(page, `picker-selected-${viewport.width}`)
    await search.press('Enter')
    await expect(picker).toContainText('Europe/London')
    await picker.click()
    await search.fill('UTC')
    await expect(list.getByRole('option')).toHaveCount(1)
    await expect(list.getByRole('option')).toContainText('UTC — UTC+00:00 (now)')
    await search.fill('+05:30')
    await expect(list.getByRole('option', { name: /Kolkata/ })).toBeVisible()
    await search.fill('UTC+05:30')
    await expect(list.getByRole('option', { name: /Kolkata/ })).toBeVisible()
  })
}

test('reopening the picker reuses current-offset formatters', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-01T00:00:10Z') })
  await page.addInitScript(() => {
    const original = Intl.DateTimeFormat
    window.n5OffsetCalls = 0
    Intl.DateTimeFormat = function (locale, options) {
      if (options?.timeZoneName === 'shortOffset') window.n5OffsetCalls += 1
      return new original(locale, options)
    }
  })
  await recruitingFixture(page, { saved: 'Europe/London' })
  await page.getByRole('button', { name: 'New opportunity' }).click()
  const picker = page.getByRole('combobox', { name: 'Time zone', exact: true })
  const initial = await page.evaluate(() => window.n5OffsetCalls)
  expect(initial).toBeGreaterThan(300)
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 })
  const openMs = []
  for (let index = 0; index < 3; index += 1) {
    const start = Date.now()
    await picker.click()
    await expect(page.getByRole('combobox', { name: 'Search time zones' })).toBeVisible()
    openMs.push(Date.now() - start)
    await page.getByRole('combobox', { name: 'Search time zones' }).press('Escape')
  }
  expect(await page.evaluate(() => window.n5OffsetCalls)).toBe(initial)
  console.log('N5F2 warm opens at 6× CPU:', JSON.stringify({ openMs, offsetCalls: initial }))
})

test('inline splash fills viewport when external styles and scripts fail', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  // Exercise the committed boot with a render-blocking external stylesheet that fails.
  const html = await fs.readFile(new URL('../index.html', import.meta.url), 'utf8')
  const blockedStyles = []
  await page.route('**/*', route => {
    const type = route.request().resourceType()
    if (type === 'document') return route.fulfill({ contentType: 'text/html', body: html.replace('</head>', '<link rel="stylesheet" href="/assets/n5-unavailable.css"></head>') })
    if (type === 'stylesheet') { blockedStyles.push(route.request().url()); return route.abort() }
    return type === 'script' ? route.abort() : route.continue()
  })
  await page.goto('/')
  await expect(page.getByRole('status', { name: 'Loading' })).toBeVisible()
  expect(await page.locator('#root>.cleat-loader').boundingBox()).toEqual({ x: 0, y: 0, width: 390, height: 844 })
  expect(await page.evaluate(() => ({ margin: getComputedStyle(document.body).margin, background: getComputedStyle(document.body).backgroundColor, height: document.documentElement.scrollHeight }))).toEqual({ margin: '0px', background: 'rgb(243, 240, 232)', height: 844 })
  expect(blockedStyles.some(url => url.endsWith('/assets/n5-unavailable.css'))).toBe(true)
  await screenshot(page, 'splash-without-css')
})

test('exact UTC search excludes universal offset labels', async ({ page }) => {
  await recruitingFixture(page, { saved: 'Europe/London' })
  await page.getByRole('button', { name: 'New opportunity' }).click()
  await page.getByRole('combobox', { name: 'Time zone', exact: true }).click()
  await page.getByRole('combobox', { name: 'Search time zones' }).fill('UTC')
  await expect(page.getByRole('listbox', { name: 'Time zones' }).getByRole('option')).toHaveCount(1)
  await expect(page.getByRole('listbox', { name: 'Time zones' }).getByRole('option')).toContainText('UTC — UTC+00:00 (now)')
})

test('keyboard row has an ink indicator and landscape list has three rows', async ({ page }) => {
  await page.setViewportSize({ width: 844, height: 390 })
  await recruitingFixture(page, { saved: 'Europe/London' })
  await page.getByRole('button', { name: 'New opportunity' }).click()
  await page.getByRole('combobox', { name: 'Time zone', exact: true }).click()
  expect(await page.locator('[cmdk-item][data-selected=true]').evaluate(element => getComputedStyle(element).boxShadow)).not.toBe('none')
  expect((await page.getByRole('listbox', { name: 'Time zones' }).boundingBox()).height).toBeGreaterThanOrEqual(156)
})

test('player loading retains contextual copy without a second visible caption', async ({ page }) => {
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.startsWith('/api/players/123/')) return new Promise(() => {})
    return route.fulfill({ json: {} })
  })
  await page.goto('/players/123')
  await expect(page.getByText('Loading player data...', { exact: true })).toBeVisible()
  await expect(page.getByRole('status', { name: 'Loading' })).toBeVisible()
  await expect(page.locator('.cleat-caption')).toHaveCount(0)
  await screenshot(page, 'player-loading-context')
})
