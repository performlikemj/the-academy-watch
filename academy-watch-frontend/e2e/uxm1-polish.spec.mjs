/* global window */
import { test, expect } from '@playwright/test'

const player = { player_id: -71, player_name: 'Test Community Adult', position: 'Right winger', age: 23, contactable: true, data_source: 'local-player' }
const introduction = { id: 'test-intro', player_api_id: -71, message: 'A test introduction', status: 'pending', routing_mode: 'direct', messaging_open: false,
  participants: { scout: { display_name: 'Test Scout' }, player: { display_name: 'Test Community Adult' } } }

async function mocks(page, { verified = false, signedIn = true, incoming = true, accepted = false, displaySeason = 2026, verificationMode, failIntroductions = false } = {}) {
  const seen = []
  await page.addInitScript((signedIn) => {
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    // These checks read the desk's table; the desk now starts on cards.
    localStorage.setItem('aw.scout.view', 'table')
    if (signedIn) localStorage.setItem('academy_watch_user_token', 'test-token')
  }, signedIn)
  await page.route('**/api/**', async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    seen.push({ path, search: url.search, method: request.method() })
    let json = {}
    if (path === '/api/auth/me') json = { email: 'test@example.com', display_name: 'Test Viewer', role: 'user', display_name_confirmed: true }
    else if (path === '/api/features') json = { contact_rail: true }
    else if (path === '/api/meta/data-mode') json = { api_football_frozen: true }
    else if (path === '/api/seasons') json = { current_season: 2026, display_season: displaySeason, seasons: [{ season: 2026, label: '2026/27', is_current: true, has_rollup: true }, { season: 2025, label: '2025/26', has_rollup: true }], bounds: { min: 2025, max: 2027 } }
    else if (path === '/api/players/search') json = [{ player_api_id: -71, player_name: player.player_name, position: player.position }]
    else if (path === '/api/scout/verification') {
      if (verificationMode === 'failed') return route.fulfill({ status: 500, json: { error: 'Unavailable' } })
      json = { verification: { status: verified ? 'approved' : 'pending' } }
    }
    else if (path === '/api/scout/players') json = { season: Number(url.searchParams.get('season') || 2025), players: [player], total: 1, total_pages: 1 }
    else if (path === '/api/scout/leaderboards') json = { season: Number(url.searchParams.get('season') || 2025), leaderboards: { top_scorers: [], top_assists: [], most_minutes: [], best_per90: [] } }
    else if (path === '/api/scout/watchlist') json = { entries: [{ id: 1, player, player_api_id: -71 }], digest_opt_in: true }
    else if (path === '/api/scout/watchlist/ids') json = { player_ids: [] }
    else if (path === '/api/players/-71/profile') json = { name: player.player_name, position: player.position, age: 23 }
    else if (path === '/api/players/-71/stats') json = { matches: [], summary: { season: 2026 } }
    else if (path === '/api/players/-71/season-stats') json = { season: `${url.searchParams.get('season') || displaySeason}/${Number(url.searchParams.get('season') || displaySeason) + 1}`, appearances: 1, minutes: 90, goals: 1, assists: 0, provenance: { primary_source: 'user' } }
    else if (path === '/api/local-players/71') json = { player: { id: 71, api_player_id: -71, display_name: player.player_name, position: player.position, status: 'approved', birth_year: 2003 } }
    else if (path.endsWith('/showcase')) json = { profile: { bio: 'Test profile', contract_status: 'contracted', profile_contract_status: 'under_contract', current_club_name: 'Test Accepted Club', local_player_id: 71 }, affiliations: [], reel: [], photos: [] }
    else if (path === '/api/me/club-invitations') json = { invitations: [{ id: 'test-club', status: 'accepted', program_name: 'Test Accepted Club', program_id: 1 }], next_before: null }
    else if (path === '/api/me/claims') json = { claims: [{ id: 7, player_api_id: null, local_player_id: 71, status: 'approved', relationship_type: 'player' }] }
    else if (path === '/api/contact/requests') {
      if (failIntroductions) {
        failIntroductions = false
        return route.fulfill({ status: 500, json: { error: 'First load failed' } })
      }
      json = { requests: (url.searchParams.get('box') === 'inbox') === incoming ? [{ ...introduction, status: accepted ? 'accepted' : 'pending', messaging_open: accepted }] : [], total: 1 }
    }
    else if (path.endsWith('/availability')) json = { season: displaySeason, absences: [], summary: { total_absences: 0 } }
    else if (path.endsWith('/messages')) json = { messages: [] }
    else if (path.endsWith('/matches')) json = { matches: [], total: 0 }
    return route.fulfill({ json })
  })
  return seen
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`${viewport.width}px staging regressions`, () => {
    test.use({ viewport })
    test('desk labels the default season without explicitly scoping requests', async ({ page }) => {
      const seen = await mocks(page)
      await page.goto('/scout')
      await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText('2026/27')
      await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText('2026/27')
      for (const path of ['/api/scout/players', '/api/scout/leaderboards']) {
        await expect.poll(() => seen.filter(r => r.path === path).length).toBeGreaterThan(0)
        expect(seen.filter(r => r.path === path).every(r => !new URLSearchParams(r.search).has('season'))).toBe(true)
      }
      await page.getByRole('combobox', { name: 'Select season' }).click()
      await page.getByRole('option', { name: '2025/26' }).click()
      await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText('2025/26')
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
    for (const pick of [2025, 2026]) {
      test(`explicit ${pick} season survives a player link during calendar lag`, async ({ page }) => {
        const seen = await mocks(page, { displaySeason: 2025 })
        await page.goto('/scout')
        await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
        // Move away first so picking the displayed default is an explicit change too.
        if (pick === 2025) {
          await page.getByRole('combobox', { name: 'Select season' }).click()
          await page.getByRole('option', { name: /2026\/27/ }).click()
        }
        await page.getByRole('combobox', { name: 'Select season' }).click()
        await page.getByRole('option', { name: pick === 2026 ? /2026\/27/ : '2025/26' }).click()
        await expect(page).toHaveURL(new RegExp(`season=${pick}$`))
        for (const path of ['/api/scout/players', '/api/scout/leaderboards']) {
          await expect.poll(() => seen.some(r => r.path === path && new URLSearchParams(r.search).get('season') === String(pick))).toBe(true)
        }
        await page.getByRole('link', { name: /Test Community Adult/ }).click()
        await expect(page).toHaveURL(new RegExp(`/players/-71\\?season=${pick}$`))
        await expect(page.getByRole('heading', { name: `${pick}/${String(pick + 1).slice(-2)} Totals` })).toBeVisible()
        for (const path of ['/api/players/-71/stats', '/api/players/-71/season-stats']) {
          expect(seen.filter(r => r.path === path).length).toBeGreaterThan(0)
          expect(seen.filter(r => r.path === path).every(r => new URLSearchParams(r.search).get('season') === String(pick))).toBe(true)
        }
      })
    }
    test('global community search result opens its signed player profile', async ({ page }) => {
      await mocks(page)
      await page.goto('/')
      await page.keyboard.press('Meta+k')
      await page.getByPlaceholder('Search players...').fill('Test Community')
      await page.getByText('Test Community Adult', { exact: true }).click()
      await expect(page).toHaveURL(/\/players\/-71$/)
      await expect(page.getByRole('heading', { name: 'Test Community Adult', exact: true })).toBeVisible()
    })
    test('watchlist states the position and age in words', async ({ page }) => {
      await mocks(page)
      await page.goto('/scout/watchlist')
      await expect(page.getByTestId('watchlist-row')).toContainText('Right winger · 23')
    })
    test('signed-out scout sees Get verified and can open sign-in from a row', async ({ page }) => {
      const seen = await mocks(page, { signedIn: false })
      await page.goto('/scout')
      await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Get verified', exact: true })).toBeVisible()
      await expect(page.getByText('Checking verification…', { exact: true })).toHaveCount(0)
      expect(seen.some(r => r.path === '/api/scout/verification')).toBe(false)
      await page.getByRole('button', { name: 'Introduce yourself to Test Community Adult' }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await expect(page.getByRole('textbox', { name: 'Message to Test Community Adult' })).toHaveCount(0)
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
      expect(seen.filter(r => r.path.endsWith('/season-stats')).every(r => !new URLSearchParams(r.search).has('season'))).toBe(true)
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

for (const verificationMode of ['slow', 'failed']) {
  test(`verification ${verificationMode} keeps neutral copy and allows composer`, async ({ page }) => {
    await mocks(page, { verified: true, verificationMode })
    let finishVerification
    if (verificationMode === 'slow') {
      const waiting = new Promise(resolve => { finishVerification = resolve })
      await page.route('**/api/scout/verification', async route => {
        await waiting
        await route.fulfill({ json: { verification: { status: 'approved' } } })
      })
    }
    await page.goto('/scout')
    await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Get verified to introduce yourself', exact: true })).toHaveCount(0)
    await expect(page.getByRole('link', { name: verificationMode === 'slow' ? 'Checking verification…' : 'Scout verification', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Introduce yourself to Test Community Adult' }).click()
    await expect(page.getByRole('textbox', { name: 'Message to Test Community Adult' })).toBeVisible()
    finishVerification?.()
    if (verificationMode === 'slow') {
      await page.keyboard.press('Escape')
      await expect(page.getByRole('link', { name: 'Verified scout', exact: true })).toBeVisible()
    }
  })
}

test('fixtures lagging the calendar label defaults without sending a season', async ({ page }) => {
  const seen = await mocks(page, { displaySeason: 2025 })
  await page.route('**/api/players/42/profile', route => route.fulfill({ json: { name: 'Tracked Adult', position: 'Midfielder', age: 23 } }))
  await page.route('**/api/players/42/stats*', route => {
    seen.push({ path: '/api/players/42/stats', search: new URL(route.request().url()).search })
    return route.fulfill({ json: { matches: [], summary: { season: 2025 } } })
  })
  await page.route('**/api/players/42/season-stats*', route => {
    seen.push({ path: '/api/players/42/season-stats', search: new URL(route.request().url()).search })
    return route.fulfill({ json: { season: '2025/2026', appearances: 1, minutes: 90, goals: 1 } })
  })
  await page.goto('/scout')
  await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText('2025/26')
  await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
  for (const path of ['/api/scout/players', '/api/scout/leaderboards']) {
    await expect.poll(() => seen.some(r => r.path === path)).toBe(true)
    expect(seen.filter(r => r.path === path).every(r => !new URLSearchParams(r.search).has('season'))).toBe(true)
  }
  await page.goto('/players/42')
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toBeVisible()
  for (const path of ['/api/players/42/stats', '/api/players/42/season-stats']) {
    expect(seen.filter(r => r.path === path).length).toBeGreaterThan(0)
    expect(seen.filter(r => r.path === path).every(r => !new URLSearchParams(r.search).has('season'))).toBe(true)
  }
})

test('community games stay unfiltered while totals ignore stored history', async ({ page }) => {
  const seen = await mocks(page)
  await page.addInitScript(() => window.sessionStorage.setItem('aw.season', '2025'))
  await page.goto('/local-players/71')
  await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
  await expect.poll(() => seen.some(r => r.path.endsWith('/matches'))).toBe(true)
  expect(seen.filter(r => r.path.endsWith('/matches')).every(r => !new URLSearchParams(r.search).has('season'))).toBe(true)
})

for (const incoming of [true, false]) {
  test(`introductions loads each box once with incoming=${incoming}`, async ({ page }) => {
    const seen = await mocks(page, { incoming })
    await page.goto('/introductions')
    await expect(page.getByRole('button', { name: incoming ? /Test Scout.*Pending/ : /Test Community Adult.*Pending/ })).toBeVisible()
    for (const box of ['sent', 'inbox']) {
      expect(seen.filter(r => r.path === '/api/contact/requests' && new URLSearchParams(r.search).get('box') === box)).toHaveLength(1)
    }
    await page.getByRole('tab', { name: incoming ? 'Sent' : 'Received', exact: true }).click()
    await expect(page.getByText(incoming ? 'Nothing sent yet.' : 'No introductions yet.', { exact: false })).toBeVisible()
    expect(seen.filter(r => r.path === '/api/contact/requests')).toHaveLength(3)
  })
}

test('introductions failed first load can be retried on the visible tab', async ({ page }) => {
  const seen = await mocks(page, { failIntroductions: true })
  await page.goto('/introductions')
  await expect(page.getByText('First load failed', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('button', { name: /Test Scout.*Pending/ })).toBeVisible()
  expect(seen.filter(r => r.path === '/api/contact/requests')).toHaveLength(3)
})


test('adding an older community game keeps it visible and refreshes the display totals', async ({ page }) => {
  const seen = await mocks(page)
  let saved
  const gamesRequests = []
  await page.route('**/api/players/-71/matches*', async route => {
    gamesRequests.push(new URL(route.request().url()))
    if (route.request().method() === 'POST') {
      saved = { ...route.request().postDataJSON(), id: 73, player_api_id: -71, season: 2025,
        source: 'self', status: 'self_reported', editable: true,
        provenance: { source_category: 'self', primary_source: 'user', source_label: 'Self-reported' } }
      return route.fulfill({ json: { match: saved, season_stats: { season: '2025/2026', appearances: 1, minutes: 90 } } })
    }
    return route.fulfill({ json: { matches: saved ? [saved] : [], total: saved ? 1 : 0 } })
  })
  await page.goto('/local-players/71')
  await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
  const initialTotalsReads = seen.filter(r => r.path.endsWith('/season-stats')).length
  await page.getByRole('button', { name: 'Add a game', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Match date').fill('2025-09-01')
  await dialog.getByLabel('Opponent').fill('Older Season United')
  await dialog.getByLabel('Minutes').fill('90')
  await dialog.getByRole('button', { name: 'Add game', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'vs Older Season United', exact: true })).toBeVisible()
  await expect.poll(() => seen.filter(r => r.path.endsWith('/season-stats') && !new URLSearchParams(r.search).has('season')).length).toBeGreaterThan(initialTotalsReads)
  await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toHaveCount(0)
  expect(gamesRequests.every(url => !url.searchParams.has('season'))).toBe(true)
})


for (const path of ['/scout', '/players/-71', '/local-players/71']) {
  for (const pick of ['', '?season=2026']) {
    for (const directory of ['held', 'failed']) {
      test(`${path}${pick} reads independently of a ${directory} season directory`, async ({ page }) => {
        const seen = await mocks(page)
        let release
        const waiting = new Promise(resolve => { release = resolve })
        await page.route('**/api/seasons', async route => {
          if (directory === 'held') await waiting
          await route.fulfill({ status: 500, json: { error: 'Directory unavailable' } })
        })
        try {
          await page.goto(`${path}${pick}`)
          const paths = path === '/scout' ? ['/api/scout/players', '/api/scout/leaderboards']
            : ['/api/players/-71/season-stats']
          for (const readPath of paths) {
            await expect.poll(() => seen.some(r => r.path === readPath), { timeout: 2500 }).toBe(true)
            expect(seen.filter(r => r.path === readPath).every(r =>
              new URLSearchParams(r.search).get('season') === (pick ? '2026' : null))).toBe(true)
          }
          if (path === '/scout') await expect(page.getByRole('cell', { name: 'RW', exact: true })).toBeVisible()
          else await expect(page.getByRole('heading', { name: 'Test Community Adult', exact: true })).toBeVisible()
        } finally { release() }
      })
    }
  }
}

for (const width of [1440, 390]) {
  test.describe(`${width}px cross-season mutations`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } })
    for (const id of [-71, 42]) {
      for (const picked of [false, true]) {
        for (const action of ['add', 'edit', 'delete']) {
          test(`${id} ${action} across seasons preserves ${picked ? 'explicit' : 'default'} totals and games scope`, async ({ page }) => {
            await mocks(page)
            if (id > 0) {
              await page.route('**/api/me/claims', route => route.fulfill({ json: { claims: [{ id: 7, player_api_id: id, status: 'approved', relationship_type: 'player' }] } }))
              await page.route(`**/api/players/${id}/profile`, route => route.fulfill({ json: { name: 'Test Provider Adult', position: 'Midfielder' } }))
              await page.route(`**/api/players/${id}/stats*`, route => route.fulfill({ json: { matches: [], summary: { season: 2026 } } }))
            }
            const totalsReads = []
            await page.route(`**/api/players/${id}/season-stats*`, route => {
              totalsReads.push(new URL(route.request().url()))
              return route.fulfill({ json: { season: '2026/2027', appearances: 5, minutes: 450, goals: 1 } })
            })
            let game = { id: 73, player_api_id: id, match_date: '2026-09-01', opponent: 'Current Season United',
              season: 2026, minutes: 90, home_away: 'home', source: 'self', status: 'self_reported', editable: true,
              provenance: { source_category: 'self', primary_source: 'user', source_label: 'Self-reported' } }
            let games = action === 'add' ? [] : [game]
            const gameReads = []
            await page.route(`**/api/players/${id}/matches**`, route => {
              const request = route.request(), url = new URL(request.url())
              if (request.method() === 'GET') {
                gameReads.push(url)
                const filtered = games.filter(g => !url.searchParams.has('season') || String(g.season) === url.searchParams.get('season'))
                return route.fulfill({ json: { matches: filtered, total: filtered.length } })
              }
              if (request.method() === 'DELETE') games = []
              else {
                game = { ...game, ...request.postDataJSON(), season: 2025 }
                games = [game]
              }
              return route.fulfill({ json: { match: game, season_stats: { season: '2025/2026', appearances: 7, minutes: 630 } } })
            })
            await page.goto(`/players/${id}${picked ? '?season=2026' : ''}`)
            await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
            await expect.poll(() => gameReads.length).toBeGreaterThan(0)
            const initial = totalsReads.length
            if (action === 'delete') {
              await page.getByRole('button', { name: 'Delete game against Current Season United' }).click()
              await page.getByRole('dialog').getByRole('button', { name: 'Delete game', exact: true }).click()
            } else {
              await page.getByRole('button', { name: action === 'add' ? 'Add a game' : 'Edit game against Current Season United', exact: true }).click()
              const dialog = page.getByRole('dialog')
              await dialog.getByLabel('Match date').fill('2025-09-01')
              await dialog.getByLabel('Opponent').fill('Older Season United')
              await dialog.getByLabel('Minutes').fill('90')
              await dialog.getByRole('button', { name: action === 'add' ? 'Add game' : 'Save changes', exact: true }).click()
            }
            await expect(page.getByRole('dialog')).toHaveCount(0)
            await expect.poll(() => totalsReads.length).toBeGreaterThan(initial)
            await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
            await expect(page.getByText('Appearances', { exact: true }).locator('..').locator('.display')).toHaveText('5')
            expect(gameReads.every(url => url.searchParams.get('season') === (id > 0 || picked ? '2026' : null))).toBe(true)
            expect(totalsReads.slice(initial).some(url => url.searchParams.get('season') === (picked ? '2026' : null))).toBe(true)
            await expect(page.getByRole('heading', { name: 'vs Older Season United', exact: true })).toHaveCount(
              action !== 'delete' && id < 0 && !picked ? 1 : 0)
            expect(await page.locator('body').evaluate(el => el.scrollWidth <= window.innerWidth)).toBe(true)
            if (process.env.UXM1_SHOTS && action === 'add') await page.screenshot({ path: `${process.env.UXM1_SHOTS}/mutation-${id}-${picked ? 'picked' : 'default'}-${width}.png`, fullPage: true })
          })
        }
      }
    }
  })
}
