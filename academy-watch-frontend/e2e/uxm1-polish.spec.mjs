/* global window */
import { test, expect } from '@playwright/test'

const player = { player_id: -71, player_name: 'Test Community Adult', position: 'Right winger', age: 23, contactable: true, data_source: 'local-player' }
const introduction = { id: 'test-intro', player_api_id: -71, message: 'A test introduction', status: 'pending', routing_mode: 'direct', messaging_open: false,
  participants: { scout: { display_name: 'Test Scout' }, player: { display_name: 'Test Community Adult' } } }

async function mocks(page, { verified = false, signedIn = true, incoming = true, accepted = false } = {}) {
  const seen = []
  await page.addInitScript((signedIn) => {
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (signedIn) localStorage.setItem('academy_watch_user_token', 'test-token')
  }, signedIn)
  await page.route('**/api/**', async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    seen.push({ path, search: url.search, method: request.method() })
    let json = {}
    if (path === '/api/auth/me') json = { email: 'test@example.com', display_name: 'Test Viewer', role: 'user', display_name_confirmed: true }
    else if (path === '/api/features') json = { contact_rail: true }
    else if (path === '/api/meta/data-mode') json = { api_football_frozen: true }
    else if (path === '/api/seasons') json = { current_season: 2026, seasons: [{ season: 2026, label: '2026/27', is_current: true, has_rollup: true }, { season: 2025, label: '2025/26', has_rollup: true }], bounds: { min: 2025, max: 2027 } }
    else if (path === '/api/players/search') json = [{ player_api_id: -71, player_name: player.player_name, position: player.position }]
    else if (path === '/api/scout/verification') json = { verification: { status: verified ? 'approved' : 'pending' } }
    else if (path === '/api/scout/players') json = { season: Number(url.searchParams.get('season') || 2025), players: [player], total: 1, total_pages: 1 }
    else if (path === '/api/scout/leaderboards') json = { season: Number(url.searchParams.get('season') || 2025), leaderboards: { top_scorers: [], top_assists: [], most_minutes: [], best_per90: [] } }
    else if (path === '/api/scout/watchlist') json = { entries: [{ id: 1, player, player_api_id: -71 }], digest_opt_in: true }
    else if (path === '/api/scout/watchlist/ids') json = { player_ids: [] }
    else if (path === '/api/players/-71/profile') json = { name: player.player_name, position: player.position, age: 23 }
    else if (path === '/api/players/-71/stats') json = { matches: [], summary: { season: 2026 } }
    else if (path === '/api/players/-71/season-stats') json = { season: `${url.searchParams.get('season') || 2025}/2027`, appearances: 1, minutes: 90, goals: 1, assists: 0, provenance: { primary_source: 'user' } }
    else if (path === '/api/local-players/71') json = { player: { id: 71, api_player_id: -71, display_name: player.player_name, position: player.position, status: 'approved', birth_year: 2003 } }
    else if (path.endsWith('/showcase')) json = { profile: { bio: 'Test profile', contract_status: 'contracted', profile_contract_status: 'under_contract', current_club_name: 'Test Accepted Club', local_player_id: 71 }, affiliations: [], reel: [], photos: [] }
    else if (path === '/api/me/club-invitations') json = { invitations: [{ id: 'test-club', status: 'accepted', program_name: 'Test Accepted Club', program_id: 1 }], next_before: null }
    else if (path === '/api/me/claims') json = { claims: [{ id: 7, player_api_id: null, local_player_id: 71, status: 'approved', relationship_type: 'player' }] }
    else if (path === '/api/contact/requests') json = { requests: (url.searchParams.get('box') === 'inbox') === incoming ? [{ ...introduction, status: accepted ? 'accepted' : 'pending', messaging_open: accepted }] : [], total: 1 }
    else if (path.endsWith('/messages')) json = { messages: [] }
    else if (path.endsWith('/matches')) json = { matches: [], total: 0 }
    return route.fulfill({ json })
  })
  return seen
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`${viewport.width}px staging regressions`, () => {
    test.use({ viewport })
    test('desk uses position codes and one current season for boards and requests', async ({ page }) => {
      const seen = await mocks(page)
      await page.goto('/scout')
      await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
      await expect(page.getByText(/viewing 2026\/27/)).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText('2026/27')
      for (const path of ['/api/scout/players', '/api/scout/leaderboards']) {
        await expect.poll(() => seen.filter(r => r.path === path).length).toBeGreaterThan(0)
        expect(seen.filter(r => r.path === path).every(r => r.search.includes('season=2026'))).toBe(true)
      }
      await page.getByRole('combobox', { name: 'Select season' }).click()
      await page.getByRole('option', { name: '2025/26' }).click()
      await expect(page.getByText(/viewing 2025\/26/)).toBeVisible()
      expect(await page.locator('body').evaluate(el => el.scrollWidth <= window.innerWidth)).toBe(true)
    })
    test('explicit current season follows a player link despite stored history', async ({ page }) => {
      await mocks(page)
      await page.addInitScript(() => window.sessionStorage.setItem('aw.season', '2025'))
      await page.goto('/scout?season=2026')
      await page.getByRole('link', { name: /Test Community Adult/ }).click()
      await expect(page).toHaveURL(/\/players\/-71\?season=2026$/)
      await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
    })
    test('global community search result opens its signed player profile', async ({ page }) => {
      await mocks(page)
      await page.goto('/')
      await page.keyboard.press('Meta+k')
      await page.getByPlaceholder('Search players...').fill('Test Community')
      await page.getByText('Test Community Adult', { exact: true }).click()
      await expect(page).toHaveURL(/\/players\/-71$/)
      await expect(page.getByRole('heading', { name: 'Test Community Adult', exact: true })).toBeVisible()
    })
    test('watchlist uses the same position code', async ({ page }) => {
      await mocks(page)
      await page.goto('/scout/watchlist')
      await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
    })
    test('pending scout follows verification link and has no composer', async ({ page }) => {
      const seen = await mocks(page)
      await page.goto('/scout')
      await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
      await page.getByRole('link', { name: 'Get verified to introduce yourself', exact: true }).last().click()
      await expect(page).toHaveURL(/\/scout\/verification$/)
      await expect(page.getByRole('textbox', { name: /Message to/ })).toHaveCount(0)
      expect(seen.some(r => r.method === 'POST' && r.path === '/api/contact/requests')).toBe(false)
    })
    test('verified scout can still compose an introduction', async ({ page }) => {
      await mocks(page, { verified: true })
      await page.goto('/scout')
      await expect(page.getByRole('link', { name: 'Verified scout', exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Introduce yourself to Test Community Adult' }).click()
      await expect(page.getByRole('textbox', { name: 'Message to Test Community Adult' })).toBeVisible()
    })
    test('signed community player page uses stated position and avoids provider-only endpoints', async ({ page }) => {
      const seen = await mocks(page)
      await page.goto('/players/-71')
      await expect(page.getByRole('heading', { name: 'Test Community Adult', exact: true })).toBeVisible()
      await expect(page.locator('header').filter({ has: page.getByRole('heading', { name: 'Test Community Adult', exact: true }) })).toContainText('Right winger')
      await expect(page.getByText(/last updated/)).toHaveCount(0)
      expect(seen.some(r => /\/(academy-stats|comments|links|availability)$/.test(r.path))).toBe(false)
    })
    test('local owner totals use current season and accepted contract/club display', async ({ page }) => {
      const seen = await mocks(page)
      await page.goto('/local-players/71')
      await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
      await expect(page.getByText('Under contract', { exact: true })).toBeVisible()
      await expect(page.getByText('Accepted club relationship', { exact: true })).toBeVisible()
      await expect(page.getByText('Add your first club', { exact: true })).toHaveCount(0)
      expect(seen.filter(r => r.path.endsWith('/season-stats')).every(r => r.search.includes('season=2026'))).toBe(true)
    })
    test('recipient defaults to Received, sees their action, and cannot record outcome', async ({ page }) => {
      await mocks(page)
      await page.goto('/introductions')
      await expect(page.getByRole('tab', { name: 'Received' })).toHaveAttribute('aria-selected', 'true')
      await page.getByRole('button', { name: /Test Scout.*Pending/ }).click()
      await expect(page.getByText('Waiting for you to accept.', { exact: true })).toBeVisible()
      await expect(page.getByText('Record the outcome', { exact: true })).toHaveCount(0)
    })
    test('accepted recipient has messaging and no outcome form', async ({ page }) => {
      await mocks(page, { accepted: true })
      await page.goto('/introductions')
      await page.getByRole('button', { name: /Test Scout.*Accepted/ }).click()
      await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeVisible()
      await expect(page.getByText('Record the outcome', { exact: true })).toHaveCount(0)
    })
    test('sender defaults to Sent and retains outcome form', async ({ page }) => {
      await mocks(page, { incoming: false, accepted: true })
      await page.goto('/introductions')
      await expect(page.getByRole('tab', { name: 'Sent' })).toHaveAttribute('aria-selected', 'true')
      await page.getByRole('button', { name: /Test Community Adult.*Accepted/ }).click()
      await expect(page.getByText('Record the outcome', { exact: true })).toBeVisible()
    })
  })
}
