import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import { LEGACY_PUBLIC_ROUTES, isLegacyPublicRoute } from '../src/lib/legacyRoutes.js'

async function mockApi(page, requests) {
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem('gol-recent-searches', JSON.stringify([
      { type: 'team', id: 7, name: 'Hidden team' },
      { type: 'newsletter', id: 7, name: 'Hidden newsletter' },
      { type: 'journalist', id: 7, name: 'Hidden writer' },
      { type: 'writeup', id: 7, name: 'Hidden writeup' },
      { type: 'player', id: 42, name: 'Test Prospect' },
    ]))
  })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    requests.push(url.pathname)
    const payloads = {
      '/api/features': { contact_rail: false },
      '/api/meta/data-mode': { mode: 'frozen' },
      '/api/players/42/profile': { player_id: 42, name: 'Test Prospect', position: 'Midfielder', age: 22, nationality: 'England', parent_team_name: 'Test Academy', current_club_name: 'Test Club' },
      '/api/players/42/stats': [],
      '/api/players/42/season-stats': null,
      '/api/players/42/academy-stats': null,
      '/api/players/42/availability': { season: 2026, absences: [] },
      '/api/players/42/journey/map': null,
      '/api/players/42/commentaries': { total_count: 1, authors: [{ id: 7, display_name: 'Hidden Writer' }], commentaries: [{ id: 7, title: 'Hidden writeup' }] },
      '/api/programs/test-club': { program: { id: 7, slug: 'test-club', name: 'Test Club', city: 'Leeds', country: 'England', platform_status: 'approved', is_verified_program: true, provenance: { label: 'Self-reported' }, program_provided: { label: 'Program-provided', summary: 'Test club for the route regression.', age_groups: ['Adults'], activities: [] }, roster_links: { team_page: '/teams/test-club' }, brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' }, updates: [] } },
      '/api/local-players/7': { player: { id: 7, display_name: 'Test Local Prospect', birth_year: 2004, position: 'Midfielder', country: 'England', status: 'approved' } },
      '/api/seasons': { current_season: 2026, bounds: { min: 2026, max: 2026 }, seasons: [{ season: 2026, label: '2026/27', is_current: true }] },
      '/api/sponsors': [],
      '/api/scout/watchlist/ids': { player_ids: [] },
    }
    if (url.pathname.includes('/search')) return route.fulfill({ json: [{ player_api_id: 42, player_name: 'Test Prospect', team_name: 'Test Club' }] })
    if (url.pathname in payloads) return route.fulfill({ json: payloads[url.pathname] })
    if (url.pathname.includes('/comments')) return route.fulfill({ json: { comments: [], total: 0 } })
    return route.fulfill({ json: {} })
  })
}

for (const pattern of LEGACY_PUBLIC_ROUTES) {
  test(`legacy redirect without legacy requests: ${pattern}`, async ({ page }) => {
    const requests = []
    await mockApi(page, requests)
    const legacyPath = pattern.replace(/:[^/]+/g, '42')
    await page.goto(`${legacyPath}?legacy=1`)
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Every player deserves')
    await expect(page.locator('meta[name="robots"]')).toHaveCount(0)
    expect(requests.filter((url) => /^\/api\/(teams|newsletters|journalists|cohorts|commentaries|community-takes|public-formations)(\/|$)/.test(url))).toEqual([])
    await page.getByRole('link', { name: 'Explore players', exact: true }).click()
    await expect(page).toHaveURL(/\/scout$/)
    await expect(page.locator('meta[name="robots"]')).toHaveCount(0)
  })
}

test('in-app legacy navigation returns to home without noindex', async ({ page }) => {
  await mockApi(page, [])
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Every player deserves')
  for (const pattern of LEGACY_PUBLIC_ROUTES) {
    await page.evaluate((pathname) => {
      globalThis.history.pushState(null, '', pathname)
      globalThis.dispatchEvent(new globalThis.PopStateEvent('popstate'))
    }, pattern.replace(/:[^/]+/g, '42'))
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Every player deserves')
    await expect(page.locator('meta[name="robots"]')).toHaveCount(0)
    expect(await page.evaluate(() => globalThis.history.state?.usr?.legacyPublicRedirect)).toBeUndefined()
  }
})

test('home ignores redirect state left by an older client', async ({ page }) => {
  await mockApi(page, [])
  await page.addInitScript(() => {
    globalThis.history.replaceState({ usr: { legacyPublicRedirect: true }, key: 'old-redirect', idx: 0 }, '', '/')
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Every player deserves')
  await expect(page.locator('meta[name="robots"]')).toHaveCount(0)
})

for (const width of [1440, 390]) {
  for (const [slug, route, heading] of [
    ['home', '/', 'Every player deserves'],
    ['player', '/players/42', 'Test Prospect'],
    ['club', '/programs/test-club', 'Test Club'],
    ['local-player', '/local-players/7', 'Test Local Prospect'],
  ]) {
    test(`${slug} has no hidden links at ${width}px`, async ({ page }) => {
      const requests = []
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await mockApi(page, requests)
      await page.goto(route)
      await expect(page.getByRole('heading', { level: 1 })).toContainText(heading)
      await expect(page.locator('meta[name="robots"]')).toHaveCount(0)
      const hrefs = await page.locator('a[href]').evaluateAll((anchors) => anchors.map((anchor) => anchor.getAttribute('href')))
      expect(hrefs.filter(isLegacyPublicRoute)).toEqual([])
      await expect(page.getByText('Writer Coverage', { exact: true })).toHaveCount(0)
      expect(requests).not.toContain('/api/players/42/commentaries')
      if (process.env.N2_SCREENSHOTS && ['home', 'player'].includes(slug)) {
        await fs.mkdir(process.env.N2_SCREENSHOTS, { recursive: true })
        await page.evaluate(() => globalThis.document.fonts.ready)
        await page.addStyleTag({ content: 'agentation, [data-agentation-root] { display: none !important; }' })
        await page.screenshot({ path: path.join(process.env.N2_SCREENSHOTS, `${slug}-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' })
      }
      if (width === 390) {
        await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
        const menuHrefs = await page.locator('a[href]').evaluateAll((anchors) => anchors.map((anchor) => anchor.getAttribute('href')))
        expect(menuHrefs.filter(isLegacyPublicRoute)).toEqual([])
      }
      await page.getByRole('button', { name: 'Search', exact: true }).click()
      const search = page.getByRole('dialog', { name: 'Search', exact: true })
      await expect(search).toBeVisible()
      await expect(search.getByText(/Hidden (team|newsletter|writer|writeup)/)).toHaveCount(0)
      await expect(search.getByText(/Browse Teams|Newsletters|Journalists/)).toHaveCount(0)
      await search.getByPlaceholder('Search players...').fill('Test')
      await expect(search.getByRole('option').filter({ hasText: 'Test Prospect' })).toBeVisible()
      await search.getByRole('option').filter({ hasText: 'Test Prospect' }).click()
      await expect(page).toHaveURL(/\/players\/42$/)
    })
  }
}

const followedWriters = [
  { id: 71, journalist_id: 7, journalist_name: 'Followed Writer' },
  { id: 82, journalist_id: 8, journalist_name: 'Another Writer' },
]

async function mockSettings(page) {
  await mockApi(page, [])
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'test-token')
    localStorage.setItem('academy_watch_display_name', 'Test Scout')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { email: 'test@example.test', user_id: 42, display_name: 'Test Scout', display_name_confirmed: true } }))
  await page.route('**/api/user/all-subscriptions', (route) => route.fulfill({ json: { free_subscriptions: [], paid_subscriptions: [], journalist_follows: followedWriters } }))
}

for (const width of [1440, 390]) {
  test(`settings unfollows a writer and has no hidden links at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mockSettings(page)
    let unsubscribeRoute
    await page.route('**/api/journalists/*/unsubscribe', (route) => { unsubscribeRoute = route })
    await page.goto('/settings')
    const unfollow = page.getByRole('button', { name: 'Unfollow Followed Writer', exact: true })
    await expect(unfollow).toBeVisible()
    const hrefs = await page.locator('a[href]').evaluateAll((anchors) => anchors.map((anchor) => anchor.getAttribute('href')))
    expect(hrefs.filter(isLegacyPublicRoute)).toEqual([])
    expect(await page.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.innerWidth)).toBe(true)
    if (process.env.N2_SCREENSHOTS) {
      await fs.mkdir(process.env.N2_SCREENSHOTS, { recursive: true })
      await page.evaluate(() => globalThis.document.fonts.ready)
      await page.addStyleTag({ content: 'agentation, [data-agentation-root] { display: none !important; }' })
      await page.screenshot({ path: path.join(process.env.N2_SCREENSHOTS, `settings-following-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' })
    }
    await unfollow.click()
    await expect(unfollow).toBeDisabled()
    await expect(unfollow).toHaveAttribute('aria-busy', 'true')
    await expect(unfollow).toHaveText('Unfollowing…')
    await expect(page.getByText('Followed Writer', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Unfollow Another Writer' })).toBeEnabled()
    await expect.poll(() => Boolean(unsubscribeRoute)).toBe(true)
    expect(new URL(unsubscribeRoute.request().url()).pathname).toBe('/api/journalists/7/unsubscribe')
    expect(unsubscribeRoute.request().method()).toBe('POST')
    expect(unsubscribeRoute.request().headers().authorization).toBe('Bearer test-token')
    await unsubscribeRoute.fulfill({ json: { message: 'Unsubscribed successfully' } })
    await expect(page.getByText('Followed Writer', { exact: true })).toHaveCount(0)
    await expect(unfollow).toHaveCount(0)
    await expect(page.getByText('Another Writer', { exact: true })).toBeVisible()
    await page.route('**/api/journalists/8/unsubscribe', (route) => route.fulfill({ json: { message: 'Unsubscribed successfully' } }))
    await page.getByRole('button', { name: 'Unfollow Another Writer' }).click()
    await expect(page.getByText('Journalists You Follow', { exact: true })).toHaveCount(0)
  })

  test(`settings keeps the followed writer after an unsubscribe error and allows retry at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mockSettings(page)
    let attempts = 0
    await page.route('**/api/journalists/7/unsubscribe', (route) => {
      attempts += 1
      return route.fulfill(attempts === 1
        ? { status: 500, json: { error: 'Unable to unfollow. Please try again.' } }
        : { json: { message: 'Unsubscribed successfully' } })
    })
    await page.goto('/settings')
    const unfollow = page.getByRole('button', { name: 'Unfollow Followed Writer', exact: true })
    await unfollow.click()
    await expect(page.getByRole('alert')).toHaveText('Unable to unfollow. Please try again.')
    await expect(page.getByText('Followed Writer', { exact: true })).toBeVisible()
    await expect(unfollow).toBeEnabled()
    await expect(unfollow).toHaveAttribute('aria-busy', 'false')
    await unfollow.click()
    await expect(page.getByText('Followed Writer', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('alert')).toHaveCount(0)
    expect(attempts).toBe(2)
  })
}

test('GOL keeps hidden links as text while player and external links work', async ({ page }) => {
  await mockApi(page, [])
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'test-token')
    localStorage.setItem('academy_watch_display_name', 'Test Scout')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { email: 'test@example.test', user_id: 42, display_name: 'Test Scout', display_name_confirmed: true } }))
  await page.route('**/api/gol/suggestions', (route) => route.fulfill({ json: { suggestions: ['Compare player pathways'] } }))
  await page.route('**/api/gol/chat', (route) => route.fulfill({ contentType: 'text/event-stream', body: `event: token\ndata: ${JSON.stringify({ content: '[Hidden coverage](/newsletters/42) and [Hidden team](https://theacademywatch.com/teams/test). [Player record](/players/42) and [External team](https://external.example/teams/test).' })}\n\nevent: done\ndata: {}\n\n` }))
  await page.goto('/')
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await page.getByPlaceholder('Ask about any player or team…').fill('Show the records')
  await page.getByRole('button', { name: 'Send message' }).dispatchEvent('click')
  await expect(page.getByText('Hidden coverage', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Hidden coverage|Hidden team/ })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Player record' })).toHaveAttribute('href', '/players/42')
  await expect(page.getByRole('link', { name: 'External team' })).toHaveAttribute('href', 'https://external.example/teams/test')
})
