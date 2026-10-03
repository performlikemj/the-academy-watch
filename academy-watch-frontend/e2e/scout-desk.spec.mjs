/* global document, window, PopStateEvent */
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { test, expect } from '@playwright/test'
import { RESULT_VIEW_KEY, viewOwnerTag } from '../src/lib/scout-desk.js'

// Every person, club and league below is fictional (the staging story's world).
// Screenshots are written only when SD_SHOTS_DIR is set.
const SHOTS = process.env.SD_SHOTS_DIR || null
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 900 },
  { name: '390', width: 390, height: 844 },
]
const TODAY = new Date('2026-10-03T12:00:00Z')

const seasonsDirectory = {
  current_season: 2026,
  display_season: 2026,
  bounds: { min: 2024, max: 2026 },
  seasons: [
    { season: 2026, label: '2026/27', has_rollup: true, is_current: true },
    { season: 2025, label: '2025/26', has_rollup: true, is_current: false },
  ],
}

function silhouette(background, figure, box = '0 0 600 768') {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box}"><rect width="600" height="768" fill="${background}"/><circle cx="300" cy="300" r="150" fill="${figure}"/><path d="M10 768 C24 580 150 500 300 500 C450 500 576 580 590 768 Z" fill="${figure}"/></svg>`
}
const PHOTOS = {
  '/fixture-photos/portrait.svg': silhouette('#C8C2B3', '#A9A293'),
  '/fixture-photos/headshot.svg': silhouette('#D9D4C7', '#9AA39C', '120 120 360 360'),
}

const CLUB = { source_category: 'club', source_label: 'Club-confirmed', primary_source: 'club' }
const SELF = { source_category: 'self', source_label: 'Self-reported', primary_source: 'user' }
const MIXED = { source_category: 'club', source_label: 'Club-confirmed', primary_source: 'matches' }
const API = { source_category: 'api', source_label: 'API-reported', primary_source: 'journey' }

// Rows as /scout/players returns them with the merged-lines contract
// (approved_photo_url, club_confirmed, bio_line) and this lane's card fields
// (availability, introduction).
const LONG_NAME = 'Maximilian-Alexander Oluwaseun Featherstonehaugh-Abernathy'
const LONG_CLUB = 'Quillmere Athletic & Wendleshire Community Sports Association'
const deskRows = [
  { id: 1, player_id: -12, player_name: 'Kofi Asante-Reid', position: 'RB · RWB', age: 27, primary_team_name: 'Quillmere Athletic', approved_photo_url: '/fixture-photos/portrait.svg', club_confirmed: true, appearances: 1, minutes_played: 90, provenance: CLUB, availability: 'not_looking', contactable: true, introduction: { state: 'none', can_ask: true } },
  { id: 2, player_id: -15, player_name: 'Reuben Castellane', position: 'CM · AM', age: 23, primary_team_name: 'Quillmere Athletic', appearances: 1, minutes_played: 72, goals: 1, provenance: SELF, availability: 'open_to_moves', contactable: true, introduction: { state: 'none', can_ask: true } },
  { id: 3, player_id: -21, player_name: 'Tobi Olawale', position: 'Left-back', age: 24, primary_team_name: 'Quillmere Athletic', provenance: SELF, contactable: true, introduction: { state: 'pending', request_id: 'r-tobi', waiting_on: 'club', can_ask: false } },
  { id: 4, player_id: -22, player_name: 'Nabil Ferhane', position: 'Attack', age: 20, primary_team_name: 'Quillmere Athletic', provenance: SELF, contactable: true, introduction: { state: 'accepted', request_id: 'r-nabil', conversation_open: true, can_ask: false } },
  { id: 5, player_id: -23, player_name: 'Emeka Nwosu-Clarke', position: 'Centre-back', age: 19, primary_team_name: 'Quillmere Athletic', provenance: SELF, contactable: false, introduction: { state: 'none', can_ask: false } },
  { id: 6, player_id: -24, player_name: 'Seren Maddox', position: 'Centre-back', age: 26, primary_team_name: 'Thrandby Wrens', provenance: SELF, contactable: false, introduction: { state: 'none', can_ask: false } },
  { id: 7, player_id: -17, player_name: LONG_NAME, position: 'Attacking midfielder / second striker', age: 22, primary_team_name: LONG_CLUB, appearances: 3, minutes_played: 254, goals: 1, assists: 1, club_confirmed: true, provenance: MIXED, availability: 'trial_available', contactable: true, introduction: { state: 'declined', request_id: 'r-max', can_ask: false, ask_again_from: '2026-10-25T09:00:00' } },
  { id: 8, player_id: 42, player_name: 'Test Prospect', position: 'Midfielder', age: 20, primary_team_name: 'Test Academy', loan_team_name: 'Test Town', status: 'on_loan', player_photo: '/fixture-photos/headshot.svg', appearances: 30, minutes_played: 2412, goals: 6, assists: 4, avg_rating: 7.12, provenance: API, contactable: false, pc2: false },
].map(({ pc2 = true, ...row }) => ({
  nationality: 'England', status: null, recent_form: [], goals: 0, assists: 0, appearances: 0, minutes_played: 0, avg_rating: null,
  player_photo: null, availability: null,
  ...(pc2 ? { approved_photo_url: null, bio_line: null, club_confirmed: false } : {}),
  ...row,
}))

const NOTE_400 = 'Came from nowhere — signed off an open trial in July. Saw him against Skerraby: goal, assist, ran the game for an hour. Only a handful of senior games, so see him twice more before saying anything to the gaffer. Left foot is for standing on. Presses like he means it, and talks the whole ninety minutes. Ask the Skerraby manager what he thought of him afterwards, and whether the knee strapping is new — it was not there in July. END'

const byId = (id) => deskRows.find((row) => row.player_id === id)
const entry = (id, note, introduction) => ({ player_api_id: id, note, created_at: '2026-09-01T10:00:00', player: byId(id), ...(introduction ? { introduction } : {}) })

function watchlistEntries() {
  return [
    entry(-21, 'Left-back, 24, final-year student, so available full-time from June. Recovery pace is the best I have seen this year. Crossing is poor.', { state: 'pending', request_id: 'r-tobi', created_at: '2026-09-30T09:00:00', via_club: 'Quillmere Athletic', waiting_on: 'club', conversation_open: false, can_ask: false }),
    entry(-15, NOTE_400, { state: 'accepted', request_id: 'r-reuben', created_at: '2026-09-20T09:00:00', responded_at: '2026-09-28T09:00:00', conversation_open: true, can_ask: false }),
    entry(-22, 'Left-footed ten, Quillmere U21. Plays half a second ahead of everyone at that level.', { state: 'accepted', request_id: 'r-nabil', created_at: '2026-08-20T09:00:00', responded_at: '2026-08-24T09:00:00', via_club: 'Quillmere Athletic', waiting_on: 'club', conversation_open: false, can_ask: false }),
    entry(-12, null, { state: 'none', can_ask: true }),
    entry(-23, 'Centre-back, 19. Wins everything in the air. One for next season.', { state: 'none', can_ask: false }),
    entry(-17, 'Second striker who drifts left. Watch the cup tie.', { state: 'declined', request_id: 'r-max', created_at: '2026-09-18T09:00:00', responded_at: '2026-09-25T09:00:00', declined_by: 'player', can_ask: false, ask_again_from: '2026-10-25T09:00:00' }),
    entry(-24, 'For the women’s section: centre-back at Thrandby Wrens, back after six years out.', { state: 'withdrawn', request_id: 'r-seren', created_at: '2026-09-10T09:00:00', can_ask: true }),
    { player_api_id: -30, note: 'Asked in August, never heard back.', created_at: '2026-08-01T10:00:00', player: { ...byId(-23), id: 30, player_id: -30, player_name: 'Idris Vantongeren', position: 'Goalkeeper', age: 21 }, introduction: { state: 'expired', request_id: 'r-idris', created_at: '2026-08-30T09:00:00', expires_at: '2026-09-13T09:00:00', can_ask: true } },
    entry(42, 'On loan at Test Town. Thirty games already — the engine is real.'),
    { player_api_id: 1005, note: 'Released in the summer; find out where he went.', created_at: '2026-07-01T10:00:00', player: null },
  ]
}

function leaderboards() {
  const scorers = [byId(42), byId(-15), byId(-17)]
  return { top_scorers: scorers, top_assists: [byId(42), byId(-17)], most_minutes: [byId(42), byId(-17), byId(-12)], best_per90: [] }
}

async function installApiMocks(page, {
  frozen = false, contactRail = true, watched = [], verification = { status: 'approved' }, rows = deskRows,
  boards = {}, entries = [], holdPlayers = null, playersStatus = () => 200, sent = [],
} = {}) {
  const calls = []
  const state = { entries: structuredClone(entries), rows: structuredClone(rows), posts: [] }
  await page.route('**/fixture-photos/*', (route) => {
    const body = PHOTOS[new URL(route.request().url()).pathname]
    return body ? route.fulfill({ contentType: 'image/svg+xml', body }) : route.fulfill({ status: 404, body: '' })
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    const method = request.method()
    calls.push({ method, pathname, params: url.searchParams, body: request.postData() })
    if (pathname === '/api/seasons') return route.fulfill({ json: seasonsDirectory })
    if (pathname === '/api/features') return route.fulfill({ json: { contact_rail: contactRail } })
    if (pathname === '/api/meta/data-mode') return route.fulfill({ json: { api_football_frozen: frozen, newsletters_frozen: frozen } })
    if (pathname === '/api/scout/watchlist/ids') return route.fulfill({ json: { player_ids: watched } })
    if (pathname === '/api/scout/verification') return route.fulfill({ json: { verification } })
    if (pathname === '/api/scout/players') {
      if (holdPlayers) await holdPlayers
      const status = playersStatus()
      if (status !== 200) return route.fulfill({ status, json: { error: 'temporarily unavailable' } })
      // The server filters; the mock does the same so a chip is proven by its request AND its result.
      const params = url.searchParams
      let result = state.rows
      if (params.get('search')) result = result.filter((row) => row.player_name.toLowerCase().includes(params.get('search').toLowerCase()))
      if (params.get('contactable') === '1') result = result.filter((row) => row.contactable)
      if (params.get('source')) result = result.filter((row) => row.provenance.source_category === params.get('source'))
      if (params.get('max_age')) result = result.filter((row) => row.age <= Number(params.get('max_age')))
      if (params.get('position')) result = result.filter((row) => row.position === params.get('position'))
      return route.fulfill({ json: { season: 2026, players: result, total: result.length, total_pages: result.length ? 1 : 0 } })
    }
    if (pathname === '/api/scout/leaderboards') return route.fulfill({ json: { season: 2026, leaderboards: boards } })
    if (pathname === '/api/scout/watchlist' && method === 'GET') return route.fulfill({ json: { entries: state.entries, digest_opt_in: true, scout_tier: 'free' } })
    if (pathname === '/api/scout/watchlist/settings') return route.fulfill({ json: JSON.parse(request.postData()) })
    if (pathname === '/api/scout/export.csv') return route.fulfill({ contentType: 'text/csv', body: 'player_id,name\n-21,Tobi Olawale\n' })
    const watchRow = /^\/api\/scout\/watchlist\/(-?\d+)$/.exec(pathname)
    if (watchRow && method === 'PATCH') {
      const note = (JSON.parse(request.postData()).note || '').trim() || null
      const target = state.entries.find((item) => item.player_api_id === Number(watchRow[1]))
      if (target) target.note = note
      // As the server does: the answer carries the note, not the introduction.
      return route.fulfill({ json: { entry: { player_api_id: Number(watchRow[1]), note, created_at: target?.created_at, player: target?.player } } })
    }
    if (watchRow && method === 'DELETE') {
      state.entries = state.entries.filter((item) => item.player_api_id !== Number(watchRow[1]))
      return route.fulfill({ json: { removed: true } })
    }
    if (pathname === '/api/contact/requests' && method === 'POST') {
      const body = JSON.parse(request.postData())
      state.posts.push(body)
      const target = state.entries.find((item) => item.player_api_id === body.player_api_id)
      const pending = { state: 'pending', request_id: 'r-new', created_at: '2026-10-03T11:00:00', waiting_on: 'player', conversation_open: false, can_ask: false }
      if (target) target.introduction = pending
      const deskRow = state.rows.find((item) => item.player_id === body.player_api_id)
      if (deskRow) deskRow.introduction = pending
      return route.fulfill({ status: 201, json: { contact_request: { id: 'r-new', player_api_id: body.player_api_id, status: 'pending' } } })
    }
    if (pathname === '/api/contact/requests') {
      return route.fulfill({ json: { requests: url.searchParams.get('box') === 'sent' ? sent : [], total: sent.length } })
    }
    if (/^\/api\/contact\/requests\/[^/]+\/messages$/.test(pathname)) return route.fulfill({ json: { messages: [] } })
    return route.fulfill({ json: {} })
  })
  return { calls, state }
}

async function shot(page, name) {
  if (!SHOTS) return
  fs.mkdirSync(SHOTS, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

async function signIn(page, token = 'mock-user-token') {
  await page.addInitScript((value) => {
    localStorage.setItem('academy_watch_user_token', value)
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  }, token)
}

async function changeViewer(page, token) {
  await page.evaluate(async (next) => {
    const { APIService } = await import('/src/lib/api.js')
    if (next) APIService.setUserToken(next)
    else APIService.logout()
  }, token)
}

async function expectNoSidewaysScroll(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
}

const lastPlayersQuery = (calls) => calls.filter((call) => call.pathname === '/api/scout/players').at(-1)?.params
const cardsOf = (page) => page.getByTestId('player-card')

async function openDesk(page, viewport, options) {
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize({ width: viewport.width, height: viewport.height })
  await signIn(page)
  const mocks = await installApiMocks(page, options)
  await page.goto('/scout')
  return mocks
}

async function openWatchlist(page, viewport, options) {
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize({ width: viewport.width, height: viewport.height })
  await signIn(page)
  const mocks = await installApiMocks(page, options)
  await page.goto('/scout/watchlist')
  return mocks
}

for (const viewport of VIEWPORTS) {
  const phone = viewport.width < 768

  test.describe(`${viewport.name}px · Discover`, () => {
    test('cards: photo, no photo, no matches and long names, each with only real data', async ({ page }) => {
      await openDesk(page, viewport, { watched: [-15] })

      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Who are you looking for?')
      await expect(page.getByText('Adult players who chose to be seen, with numbers their clubs stand behind.')).toBeVisible()
      await expect(page.getByText(/Every tracked academy and loan player/)).toHaveCount(0)
      // Cards are the starting view on phones and, with no stored choice, on desktop.
      const view = page.getByRole('group', { name: 'Show players as' })
      await expect(view.getByRole('button', { name: 'Cards' })).toHaveAttribute('aria-pressed', 'true')
      await expect(page.getByTestId('scout-result-count')).toHaveText(`${deskRows.length} players`)
      const cards = cardsOf(page)
      await expect(cards).toHaveCount(deskRows.length)

      // Approved photo, club-confirmed tick, apps / minutes with the source word, published availability.
      const kofi = cards.filter({ hasText: 'Kofi Asante-Reid' })
      await expect(kofi).toHaveAttribute('data-photo', 'yes')
      await expect(kofi.getByRole('link', { name: 'Kofi Asante-Reid' })).toHaveAttribute('href', '/players/-12')
      await expect(kofi.getByRole('img', { name: 'Club-confirmed' })).toBeVisible()
      await expect(kofi).toContainText('RB · RWB')
      await expect(kofi).toContainText('Quillmere Athletic · 27')
      await expect(kofi).toContainText('1 app')
      await expect(kofi).toContainText('90 min')
      await expect(kofi).toContainText('club-confirmed')
      await expect(kofi).toContainText('Not looking')

      // No photo: initials. No tick unless the club confirmed.
      const reuben = cards.filter({ hasText: 'Reuben Castellane' })
      await expect(reuben).toHaveAttribute('data-photo', 'no')
      await expect(reuben.getByRole('img', { name: 'Reuben Castellane — no photo yet' })).toContainText('RC')
      await expect(reuben.getByRole('img', { name: 'Club-confirmed' })).toHaveCount(0)
      await expect(reuben).toContainText('self-reported')
      await expect(reuben).toContainText('Open to moves')
      await expect(reuben.getByRole('button', { name: 'Unwatch Reuben Castellane' })).toHaveText('Watching')

      // No matches: said plainly, no zero counters. The scout's own introduction is the status line.
      const tobi = cards.filter({ hasText: 'Tobi Olawale' })
      await expect(tobi).toContainText('No matches recorded yet')
      await expect(tobi).not.toContainText(/\b0 (apps?|min)\b/)
      await expect(tobi).toContainText('Introduction pending')
      await expect(cards.filter({ hasText: 'Nabil Ferhane' })).toContainText('In conversation')
      // Nothing to say: no status line at all.
      const emeka = cards.filter({ hasText: 'Emeka Nwosu-Clarke' })
      await expect(emeka.locator('.pc-card-status')).toHaveCount(0)
      await expect(emeka.getByRole('button', { name: 'Watch Emeka Nwosu-Clarke' })).toHaveText('Watch')

      // Merged club + self-only totals say so; the provider-tracked player keeps provider numbers and headshot.
      await expect(cards.filter({ hasText: LONG_NAME })).toContainText('club + self-reported')
      const provider = cards.filter({ hasText: 'Test Prospect' })
      await expect(provider).toContainText('30 apps')
      await expect(provider).toContainText('2,412 min')
      await expect(provider).toContainText('public match data')
      await expect(provider).toContainText('On loan')
      await expect(provider.locator('img.pc-noimg-face')).toHaveAttribute('src', '/fixture-photos/headshot.svg')

      // Long names and clubs wrap inside the card; controls keep 44px targets.
      const long = cards.filter({ hasText: LONG_NAME })
      const cardBox = await long.boundingBox()
      for (const inner of [long.getByRole('link', { name: LONG_NAME }), long.locator('.pc-card-meta'), long.locator('.pc-card-chip')]) {
        const box = await inner.boundingBox()
        expect(box.x).toBeGreaterThanOrEqual(cardBox.x)
        expect(box.x + box.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 0.5)
      }
      for (const control of [kofi.getByRole('button', { name: 'Watch Kofi Asante-Reid' }), kofi.getByRole('button', { name: 'Compare Kofi Asante-Reid' }), kofi.getByRole('button', { name: 'Introduce yourself to Kofi Asante-Reid' })]) {
        const box = await control.boundingBox()
        expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44)
      }
      await expect(emeka.getByRole('button', { name: /Introduce yourself/ })).toHaveCount(0)
      // The introduction control is what the server would accept: the existing thread for a
      // pending / accepted request (never a second request), nothing during a decline cool-off.
      await expect(tobi.getByRole('link', { name: 'Open your introduction to Tobi Olawale' })).toHaveAttribute('href', '/introductions?request=r-tobi')
      await expect(cards.filter({ hasText: 'Nabil Ferhane' }).getByRole('link', { name: 'Open your introduction to Nabil Ferhane' })).toHaveAttribute('href', '/introductions?request=r-nabil')
      await expect(page.getByRole('button', { name: /Introduce yourself to (Tobi Olawale|Nabil Ferhane|Maximilian)/ })).toHaveCount(0)
      await expect(long.getByRole('link', { name: /introduction/i })).toHaveCount(0)
      await expectNoSidewaysScroll(page)
      await shot(page, `01-discover-cards-${viewport.name}`)
    })

    test('table view keeps the sortable columns; the choice is remembered on wider screens only', async ({ page }) => {
      const { calls } = await openDesk(page, viewport)
      await expect(cardsOf(page)).toHaveCount(deskRows.length)
      await page.getByRole('group', { name: 'Show players as' }).getByRole('button', { name: 'Table' }).click()

      const table = page.getByRole('table')
      await expect(table).toBeVisible()
      for (const header of ['Player', 'Apps', 'G', 'A', 'Mins', 'Rating', 'G+A/90']) {
        await expect(table.getByRole('columnheader', { name: header, exact: true })).toBeVisible()
      }
      await table.getByRole('columnheader', { name: 'Mins', exact: true }).click()
      await expect.poll(() => lastPlayersQuery(calls)?.get('sort')).toBe('minutes')
      // The table's own tools are still there.
      await expect(page.getByRole('combobox', { name: 'Filter by pathway status' })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Filter by stats source' })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Sort by' })).toBeVisible()
      await shot(page, `02-discover-table-${viewport.name}`)

      await page.reload()
      await expect(page.getByRole('group', { name: 'Show players as' }).getByRole('button', { name: phone ? 'Cards' : 'Table' })).toHaveAttribute('aria-pressed', 'true')
    })

    test('each filter chip is a server filter: the request carries it and the count is of the filtered set', async ({ page }) => {
      const { calls } = await openDesk(page, viewport)
      await expect(cardsOf(page)).toHaveCount(deskRows.length)
      const chips = page.getByRole('group', { name: 'Filters' })
      const expectations = [
        ['Open to an introduction', 'contactable', '1', deskRows.filter((row) => row.contactable).length, 'open'],
        ['Club-confirmed numbers', 'source', 'club', deskRows.filter((row) => row.provenance.source_category === 'club').length, 'club'],
        ['Under 21', 'max_age', '20', deskRows.filter((row) => row.age <= 20).length, 'u21'],
        ['Under 23', 'max_age', '22', deskRows.filter((row) => row.age <= 22).length, 'u23'],
      ]
      for (const [label, param, value, expected, slug] of expectations) {
        const chip = chips.getByRole('button', { name: label, exact: true })
        expect((await chip.boundingBox()).height).toBeGreaterThanOrEqual(44)
        await chip.click()
        await expect(chip).toHaveAttribute('aria-pressed', 'true')
        await expect.poll(() => lastPlayersQuery(calls)?.get(param)).toBe(value)
        await expect(page.getByTestId('scout-result-count')).toHaveText(`${expected} ${expected === 1 ? 'player' : 'players'}`)
        await expect(cardsOf(page)).toHaveCount(expected)
        // Leaders are asked the same question.
        await expect.poll(() => calls.filter((call) => call.pathname === '/api/scout/leaderboards').at(-1)?.params.get(param)).toBe(value)
        await shot(page, `03-filter-${slug}-${viewport.name}`)
        await chip.click()
        await expect(chip).toHaveAttribute('aria-pressed', 'false')
        await expect.poll(() => lastPlayersQuery(calls)?.get(param) ?? null).toBe(null)
      }
      // Under 21 and Under 23 are one choice.
      await chips.getByRole('button', { name: 'Under 21', exact: true }).click()
      await chips.getByRole('button', { name: 'Under 23', exact: true }).click()
      await expect(chips.getByRole('button', { name: 'Under 21', exact: true })).toHaveAttribute('aria-pressed', 'false')
      await expect.poll(() => lastPlayersQuery(calls)?.get('max_age')).toBe('22')
    })

    test('position group and name search go to the server too', async ({ page }) => {
      const { calls } = await openDesk(page, viewport)
      await expect(cardsOf(page)).toHaveCount(deskRows.length)
      await page.getByRole('radio', { name: 'Defence view' }).click()
      await expect.poll(() => lastPlayersQuery(calls)?.get('position')).toBe('Defender')
      await page.getByRole('radio', { name: 'All view' }).click()
      await page.getByRole('textbox', { name: 'Search players' }).fill('castellane')
      await expect.poll(() => lastPlayersQuery(calls)?.get('search')).toBe('castellane')
      await expect(cardsOf(page)).toHaveCount(1)
    })

    test('zero results: said plainly, with a way on', async ({ page }) => {
      await openDesk(page, viewport)
      await expect(cardsOf(page)).toHaveCount(deskRows.length)
      await page.getByRole('textbox', { name: 'Search players' }).fill('nobody by this name')
      await expect(page.getByText('No players match these filters.')).toBeVisible()
      await expect(page.getByTestId('scout-result-count')).toHaveText('0 players')
      await expect(page.getByRole('link', { name: 'Add a local player' })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Search worldwide' })).toBeVisible()
      await expectNoSidewaysScroll(page)
      await shot(page, `04-zero-results-${viewport.name}`)
    })

    test('loading: placeholders hold the cards’ place — nothing below the header moves', async ({ page }) => {
      let release
      const held = new Promise((resolve) => { release = resolve })
      await openDesk(page, viewport, { holdPlayers: held })
      const skeletons = page.getByTestId('scout-card-skeletons')
      await expect(skeletons).toBeVisible()
      await expect(page.getByTestId('scout-result-count')).toHaveText('Loading…')
      await page.evaluate(() => document.fonts.ready)
      const before = await skeletons.boundingBox()
      const firstSkeleton = await skeletons.locator('li').first().boundingBox()
      await shot(page, `05-loading-${viewport.name}`)

      release()
      const grid = page.getByTestId('scout-player-cards')
      await expect(grid).toBeVisible()
      const after = await grid.boundingBox()
      const firstCard = await cardsOf(page).first().boundingBox()
      expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1)
      expect(Math.abs(after.x - before.x)).toBeLessThanOrEqual(1)
      expect(Math.abs(firstCard.width - firstSkeleton.width)).toBeLessThanOrEqual(1)
      expect(Math.abs(firstCard.height - firstSkeleton.height)).toBeLessThanOrEqual(24)
    })

    test('a failed read is an error with "Try again", never "no players match"', async ({ page }) => {
      let status = 503
      await openDesk(page, viewport, { playersStatus: () => status })
      await expect(page.getByText('Players could not be loaded.')).toBeVisible()
      await expect(page.getByText('No players match these filters.')).toHaveCount(0)
      status = 200
      await page.getByRole('button', { name: 'Try again' }).click()
      await expect(cardsOf(page)).toHaveCount(deskRows.length)
    })

    test('leaders sit below the results and only boards with rows are drawn', async ({ page }) => {
      await openDesk(page, viewport, { boards: leaderboards() })
      const leaders = page.getByTestId('scout-leaders')
      await expect(leaders).toBeVisible()
      await expect(leaders.getByRole('heading', { name: 'Leaders' })).toBeVisible()
      for (const title of ['Top Scorers', 'Top Assists', 'Most Minutes']) {
        await expect(leaders.getByRole('heading', { name: title })).toBeVisible()
      }
      // The board with no rows is not drawn at all.
      await expect(leaders.getByRole('heading', { name: 'Best G+A / 90' })).toHaveCount(0)
      await expect(page.getByText('No data yet')).toHaveCount(0)
      const results = await page.getByTestId('scout-player-cards').boundingBox()
      const board = await leaders.boundingBox()
      expect(board.y).toBeGreaterThan(results.y + results.height)
      await shot(page, `06-leaders-with-rows-${viewport.name}`)
    })

    test('a season with no leaders shows no boards and no skeleton boards', async ({ page }) => {
      await openDesk(page, viewport, { boards: { top_scorers: [], top_assists: [], most_minutes: [], best_per90: [] } })
      await expect(cardsOf(page)).toHaveCount(deskRows.length)
      await expect(page.getByTestId('scout-leaders')).toHaveCount(0)
      await expect(page.getByRole('heading', { name: 'Top Scorers' })).toHaveCount(0)
      await shot(page, `07-leaders-without-rows-${viewport.name}`)
    })
  })

  test.describe(`${viewport.name}px · Watchlist`, () => {
    test('one row per player: the note in full, numbers only when they exist, every introduction state', async ({ page }) => {
      await openWatchlist(page, viewport, { entries: watchlistEntries() })

      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Players you’re watching')
      await expect(page.getByText('Watchlist · 10 players')).toBeVisible()
      await expect(page.getByRole('table')).toHaveCount(0)
      const rows = page.getByTestId('watchlist-row')
      await expect(rows).toHaveCount(10)
      const row = (name) => rows.filter({ hasText: name })
      const intro = (name) => row(name).getByTestId('watchlist-introduction')

      // The 400-character note is printed whole and is not clipped.
      expect(NOTE_400.length).toBeGreaterThanOrEqual(400)
      const note = row('Reuben Castellane').getByTestId('watchlist-note').locator('p').nth(1)
      await expect(note).toHaveText(NOTE_400)
      expect(await note.evaluate((node) => node.scrollHeight <= node.clientHeight + 1 && node.scrollWidth <= node.clientWidth + 1)).toBe(true)

      // Numbers only when they exist, with where they come from.
      await expect(row('Reuben Castellane')).toContainText('1 app')
      await expect(row('Reuben Castellane')).toContainText('72 min')
      await expect(row('Reuben Castellane')).toContainText('1 G+A')
      await expect(row('Reuben Castellane')).toContainText('Self-reported, not yet confirmed by the club')
      await expect(row('Tobi Olawale')).toContainText('No matches recorded yet')
      await expect(row('Tobi Olawale')).toContainText('Left-back · 24')

      // Every introduction state, with the one next step the rules allow.
      await expect(intro('Tobi Olawale')).toContainText('Pending')
      await expect(intro('Tobi Olawale')).toContainText('Sent 30 Sep, through Quillmere Athletic. Waiting on the club.')
      await expect(intro('Tobi Olawale').getByRole('link', { name: 'Open thread: Tobi Olawale' })).toHaveAttribute('href', '/introductions?request=r-tobi')
      await expect(intro('Reuben Castellane')).toContainText('Accepted 28 Sep. Conversation open.')
      await expect(intro('Nabil Ferhane')).toContainText('Accepted 24 Aug. Waiting on the club.')
      await expect(intro('Kofi Asante-Reid')).toContainText('Not asked')
      await expect(intro('Kofi Asante-Reid').getByRole('button', { name: 'Ask: introduction to Kofi Asante-Reid' })).toBeVisible()
      await expect(intro('Emeka Nwosu-Clarke')).toContainText('This player is not taking introductions here.')
      await expect(intro('Emeka Nwosu-Clarke').getByRole('button', { name: /^Ask/ })).toHaveCount(0)
      await expect(intro(LONG_NAME)).toContainText('Declined on 25 Sep. You can ask again from 25 Oct.')
      await expect(intro(LONG_NAME).getByRole('button', { name: /^Ask/ })).toHaveCount(0)
      await expect(intro('Seren Maddox')).toContainText('Withdrawn')
      await expect(intro('Seren Maddox').getByRole('button', { name: 'Ask again: introduction to Seren Maddox' })).toBeVisible()
      await expect(intro('Idris Vantongeren')).toContainText('No answer by 13 Sep, so the request lapsed.')
      await expect(intro('Idris Vantongeren').getByRole('button', { name: 'Ask again: introduction to Idris Vantongeren' })).toBeVisible()

      // Provider-tracked: provider numbers and headshot as before; no introduction block without a state.
      const provider = row('Test Prospect')
      await expect(provider).toContainText('30 apps')
      await expect(provider).toContainText('2,412 min')
      await expect(provider).toContainText('10 G+A')
      await expect(provider).toContainText('7.12 rating')
      await expect(provider).toContainText('Public match data')
      await expect(provider).toContainText('Test Town · from Test Academy')
      await expect(provider.locator('img.pc-mini-face')).toHaveAttribute('src', '/fixture-photos/headshot.svg')
      await expect(provider.getByText('Introduction', { exact: true })).toHaveCount(0)

      // No longer tracked: the note stays, and the row can still be removed.
      const gone = row('Player 1005')
      await expect(gone).toContainText('No longer tracked')
      await expect(gone).toContainText('Released in the summer; find out where he went.')
      await expect(gone.getByRole('button', { name: 'Stop watching Player 1005' })).toBeVisible()

      for (const control of [intro('Tobi Olawale').getByRole('link', { name: /Open thread/ }), row('Tobi Olawale').getByRole('button', { name: 'Stop watching Tobi Olawale' }), row('Tobi Olawale').getByRole('button', { name: 'Edit note for Tobi Olawale' })]) {
        const box = await control.boundingBox()
        expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44)
      }
      await expectNoSidewaysScroll(page)
      await shot(page, `10-watchlist-all-states-${viewport.name}`)
      await row('Player 1005').scrollIntoViewIfNeeded()
    })

    test('the note is edited in place and saved as before', async ({ page }) => {
      const { calls } = await openWatchlist(page, viewport, { entries: watchlistEntries() })
      const row = page.getByTestId('watchlist-row').filter({ hasText: 'Kofi Asante-Reid' })
      await expect(row.getByText('No note yet.')).toBeVisible()
      await row.getByRole('button', { name: 'Add a note for Kofi Asante-Reid' }).click()
      await row.getByRole('textbox', { name: 'Note for Kofi Asante-Reid' }).fill('Defends properly.\nOverlaps all day.')
      await shot(page, `11-watchlist-note-editing-${viewport.name}`)
      await row.getByRole('button', { name: 'Save' }).click()
      await expect(row.getByTestId('watchlist-note')).toContainText('Defends properly.')
      const patch = calls.find((call) => call.method === 'PATCH' && call.pathname === '/api/scout/watchlist/-12')
      expect(JSON.parse(patch.body)).toEqual({ note: 'Defends properly.\nOverlaps all day.' })
      // Saving a note does not lose the introduction block.
      await expect(row.getByTestId('watchlist-introduction')).toContainText('Not asked')

      // Cancel leaves the saved note alone; Clear empties it.
      await row.getByRole('button', { name: 'Edit note for Kofi Asante-Reid' }).click()
      await row.getByRole('textbox', { name: 'Note for Kofi Asante-Reid' }).fill('scrap')
      await row.getByRole('button', { name: 'Cancel' }).click()
      await expect(row.getByTestId('watchlist-note')).toContainText('Defends properly.')
      await row.getByRole('button', { name: 'Edit note for Kofi Asante-Reid' }).click()
      await row.getByRole('button', { name: 'Clear' }).click()
      await expect(row.getByText('No note yet.')).toBeVisible()
    })

    test('empty watchlist', async ({ page }) => {
      await openWatchlist(page, viewport, { entries: [] })
      await expect(page.getByRole('heading', { name: 'Nothing watched yet' })).toBeVisible()
      await expect(page.getByText('Watchlist · 0 players')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Export CSV' })).toBeDisabled()
      await expectNoSidewaysScroll(page)
      await shot(page, `12-watchlist-empty-${viewport.name}`)
    })

    test('"No longer tracked" keeps the note and the way out', async ({ page }) => {
      const { calls } = await openWatchlist(page, viewport, { entries: watchlistEntries().slice(-2) })
      const gone = page.getByTestId('watchlist-row').filter({ hasText: 'Player 1005' })
      await expect(gone).toContainText('No longer tracked')
      await shot(page, `13-watchlist-no-longer-tracked-${viewport.name}`)
      await gone.getByRole('button', { name: 'Stop watching Player 1005' }).click()
      await expect(page.getByTestId('watchlist-row')).toHaveCount(1)
      expect(calls.some((call) => call.method === 'DELETE' && call.pathname === '/api/scout/watchlist/1005')).toBe(true)
    })
  })
}

const storeView = (page, token, view) => page.addInitScript(([key, owner, value]) => {
  if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({ [owner]: value }))
}, [RESULT_VIEW_KEY, viewOwnerTag(token), view])

test('a phone starts on cards whatever this viewer stored', async ({ page }) => {
  await storeView(page, 'mock-user-token', 'table')
  await openDesk(page, VIEWPORTS[1])
  await expect(cardsOf(page)).toHaveCount(deskRows.length)
  await expect(page.getByRole('table')).toHaveCount(0)
})

test('the view choice is the viewer’s own: the next account on the device does not inherit it', async ({ page }) => {
  // Reviewer's probe: scout A chooses Table, then scout B signs in on the same browser.
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  await signIn(page, 'token-a')
  await installApiMocks(page)
  await page.goto('/scout')
  const view = page.getByRole('group', { name: 'Show players as' })
  await view.getByRole('button', { name: 'Table' }).click()
  await expect(page.getByRole('table')).toBeVisible()

  await changeViewer(page, 'token-b')
  await expect(view.getByRole('button', { name: 'Cards' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('table')).toHaveCount(0)
  // Nothing of the credential is written to storage.
  const stored = await page.evaluate((key) => localStorage.getItem(key), RESULT_VIEW_KEY)
  expect(stored).not.toContain('token-a')
  expect(JSON.parse(stored)).toEqual({ [viewOwnerTag('token-a')]: 'table' })

  // A's own choice is still there when A comes back.
  await changeViewer(page, 'token-a')
  await expect(view.getByRole('button', { name: 'Table' })).toHaveAttribute('aria-pressed', 'true')
  await changeViewer(page, null)
  await expect(view.getByRole('button', { name: 'Cards' })).toHaveAttribute('aria-pressed', 'true')
})

for (const viewport of VIEWPORTS) {
  test(`${viewport.name}px: a filter set with the table tools stays visible and clearable in the cards view`, async ({ page }) => {
    // Reviewer's probe: Table -> Status "On loan" -> Cards used to filter out of sight.
    const { calls } = await openDesk(page, viewport)
    await expect(cardsOf(page)).toHaveCount(deskRows.length)
    const more = page.getByRole('button', { name: 'Sort and more filters' })
    await expect(page.getByRole('combobox', { name: 'Filter by pathway status' })).toHaveCount(0)
    expect((await more.boundingBox()).height).toBeGreaterThanOrEqual(44)
    // Sort and the pathway filter are reachable from the cards view (phones never see the table).
    await more.click()
    await page.getByRole('combobox', { name: 'Sort by' }).click()
    await page.getByRole('option', { name: 'Name' }).click()
    await expect.poll(() => lastPlayersQuery(calls)?.get('sort')).toBe('name')
    await page.getByRole('combobox', { name: 'Filter by pathway status' }).click()
    await page.getByRole('option', { name: 'On loan' }).click()
    await expect.poll(() => lastPlayersQuery(calls)?.get('status')).toBe('on_loan')

    // While it is on, the tools cannot be put away — in either view.
    await expect(page.getByRole('button', { name: 'More filters on' })).toBeDisabled()
    await expect(page.getByRole('combobox', { name: 'Filter by pathway status' })).toContainText('On loan')
    if (viewport.width >= 768) {
      const view = page.getByRole('group', { name: 'Show players as' })
      await view.getByRole('button', { name: 'Table' }).click()
      await view.getByRole('button', { name: 'Cards' }).click()
      await expect(page.getByRole('combobox', { name: 'Filter by pathway status' })).toContainText('On loan')
    }
    await shot(page, `09-cards-with-table-filter-on-${viewport.name}`)

    await page.getByRole('combobox', { name: 'Filter by pathway status' }).click()
    await page.getByRole('option', { name: 'All statuses' }).click()
    await expect.poll(() => lastPlayersQuery(calls)?.get('status') ?? null).toBe(null)
    await page.getByRole('button', { name: 'Fewer filters' }).click()
    await expect(page.getByRole('combobox', { name: 'Filter by pathway status' })).toHaveCount(0)
  })
}

test('asking from a card: afterwards the card shows the thread, not a second request', async ({ page }) => {
  const { state } = await openDesk(page, VIEWPORTS[0])
  const kofi = cardsOf(page).filter({ hasText: 'Kofi Asante-Reid' })
  await kofi.getByRole('button', { name: 'Introduce yourself to Kofi Asante-Reid' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Message to Kofi Asante-Reid' }).fill('I watched you against Skerraby.')
  await dialog.getByRole('button', { name: 'Send introduction' }).click()
  await expect(dialog.getByText('Sent. You will see the reply under your introductions.')).toBeVisible()
  expect(state.posts).toHaveLength(1)
  await dialog.getByRole('button', { name: 'Done' }).click()
  await expect(kofi.getByRole('link', { name: 'Open your introduction to Kofi Asante-Reid' })).toHaveAttribute('href', '/introductions?request=r-new')
  await expect(kofi.getByRole('button', { name: /Introduce yourself/ })).toHaveCount(0)
  await expect(kofi).toContainText('Introduction pending')
})

test('the table offers the same introduction control as the cards', async ({ page }) => {
  await storeView(page, 'mock-user-token', 'table')
  await openDesk(page, VIEWPORTS[0])
  const table = page.getByRole('table')
  await expect(table.getByRole('link', { name: 'Open your introduction to Tobi Olawale' })).toHaveAttribute('href', '/introductions?request=r-tobi')
  await expect(table.getByRole('button', { name: 'Introduce yourself to Kofi Asante-Reid' })).toBeVisible()
  await expect(table.getByRole('button', { name: /Introduce yourself to (Tobi Olawale|Nabil Ferhane|Maximilian|Emeka)/ })).toHaveCount(0)
})

test('frozen provider mode: nothing on the desk implies live provider stats', async ({ page }) => {
  await openDesk(page, VIEWPORTS[0], { frozen: true, boards: leaderboards(), rows: [] })
  await expect(page.getByText('No players match these filters.')).toBeVisible()
  // The worldwide (provider) search is not offered while provider data is frozen.
  await expect(page.getByRole('link', { name: 'Search worldwide' })).toHaveCount(0)
  await expect(page.getByTestId('scout-leaders')).toContainText('Public match data is not being updated.')
  for (const claim of [/\blive\b/i, /ranked across clubs and leagues/i, /Global talent discovery/i]) {
    await expect(page.locator('div.bg-night').first()).not.toContainText(claim)
  }
  await shot(page, '08-frozen-mode-1440')
})

test('a payload without the merged-lines fields prints no club- or player-entered figures', async ({ page }) => {
  // What /scout/players returns before the merged-lines rollup: these totals can
  // differ from the player's page, so the card prints neither them nor "no matches".
  const legacy = [
    { id: 1, player_id: -12, player_name: 'Kofi Asante-Reid', position: 'Right-back', age: 27, primary_team_name: 'Quillmere Athletic', appearances: 2, minutes_played: 164, provenance: CLUB, contactable: true },
    { id: 2, player_id: -14, player_name: 'Olu Adeyemi-Clarke', position: 'Winger', age: 22, appearances: 0, minutes_played: 0, provenance: SELF, contactable: false },
    { id: 3, player_id: 42, player_name: 'Test Prospect', position: 'Midfielder', age: 20, primary_team_name: 'Test Academy', appearances: 30, minutes_played: 2412, provenance: API, contactable: false },
  ]
  await openDesk(page, VIEWPORTS[0], { rows: legacy })
  const cards = cardsOf(page)
  await expect(cards).toHaveCount(3)
  for (const name of ['Kofi Asante-Reid', 'Olu Adeyemi-Clarke']) {
    const card = cards.filter({ hasText: name })
    await expect(card).not.toContainText(/\bapps?\b/)
    await expect(card).not.toContainText(/\bmin\b/)
    await expect(card).not.toContainText('No matches recorded yet')
    await expect(card.getByRole('img', { name: 'Club-confirmed' })).toHaveCount(0)
  }
  await expect(cards.filter({ hasText: 'Test Prospect' })).toContainText('30 apps')

  // The table of the same page prints dashes for those rows, and the provider's figures as before.
  await page.getByRole('group', { name: 'Show players as' }).getByRole('button', { name: 'Table' }).click()
  const kofiRow = page.getByRole('row').filter({ hasText: 'Kofi Asante-Reid' })
  await expect(kofiRow).not.toContainText('164')
  await expect(page.getByRole('row').filter({ hasText: 'Test Prospect' })).toContainText('2,412')
})

test('leaders leave out a row whose figure could differ from the player page', async ({ page }) => {
  const legacyClub = { id: 1, player_id: -12, player_name: 'Kofi Asante-Reid', primary_team_name: 'Quillmere Athletic', goals: 2, minutes_played: 164, provenance: CLUB }
  await openDesk(page, VIEWPORTS[0], { boards: { top_scorers: [byId(42), legacyClub], top_assists: [], most_minutes: [legacyClub], best_per90: [] } })
  const leaders = page.getByTestId('scout-leaders')
  await expect(leaders.getByRole('heading', { name: 'Top Scorers' })).toBeVisible()
  await expect(leaders).toContainText('Test Prospect')
  await expect(leaders).not.toContainText('Kofi Asante-Reid')
  // A board left with no printable row is not drawn.
  await expect(leaders.getByRole('heading', { name: 'Most Minutes' })).toHaveCount(0)
})

test('"Open to an introduction" and the introduce control exist only where introductions do', async ({ page }) => {
  const { calls } = await openDesk(page, VIEWPORTS[0], { contactRail: false })
  await expect(cardsOf(page)).toHaveCount(deskRows.length)
  await expect(page.getByRole('button', { name: 'Open to an introduction' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Introduce yourself/ })).toHaveCount(0)
  expect(calls.filter((call) => call.pathname === '/api/scout/players').every((call) => !call.params.has('contactable'))).toBe(true)
})

test('watchlist: asking opens the existing form; the row then shows the request the server reports', async ({ page }) => {
  const { state } = await openWatchlist(page, VIEWPORTS[0], { entries: watchlistEntries() })
  const row = page.getByTestId('watchlist-row').filter({ hasText: 'Kofi Asante-Reid' })
  await row.getByRole('button', { name: 'Ask: introduction to Kofi Asante-Reid' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Introduce yourself to Kofi Asante-Reid' })).toBeVisible()
  await dialog.getByRole('textbox', { name: 'Message to Kofi Asante-Reid' }).fill('I watched you against Skerraby.')
  await dialog.getByRole('button', { name: 'Send introduction' }).click()
  await expect(dialog.getByText('Sent. You will see the reply under your introductions.')).toBeVisible()
  expect(state.posts).toEqual([{ player_api_id: -12, message: 'I watched you against Skerraby.', permission_attestation: false }])
  await dialog.getByRole('button', { name: 'Done' }).click()
  await expect(row.getByTestId('watchlist-introduction')).toContainText('Pending')
  await expect(row.getByTestId('watchlist-introduction')).toContainText('Sent 3 Oct. Waiting on the player.')
  await expect(row.getByRole('link', { name: 'Open thread: Kofi Asante-Reid' })).toHaveAttribute('href', '/introductions?request=r-new')
})

test('watchlist: an unverified scout is sent to verification, not to the form', async ({ page }) => {
  await openWatchlist(page, VIEWPORTS[0], { entries: watchlistEntries(), verification: { status: 'pending' } })
  const row = page.getByTestId('watchlist-row').filter({ hasText: 'Kofi Asante-Reid' })
  await expect(row.getByRole('link', { name: 'Get verified to ask: Kofi Asante-Reid' })).toHaveAttribute('href', '/scout/verification')
  await expect(row.getByRole('button', { name: /^Ask/ })).toHaveCount(0)
  await shot(page, '14-watchlist-unverified-1440')
})

test('watchlist: with introductions switched off there is no introduction column', async ({ page }) => {
  await openWatchlist(page, VIEWPORTS[0], { entries: watchlistEntries(), contactRail: false })
  await expect(page.getByTestId('watchlist-row')).toHaveCount(10)
  await expect(page.getByText('Introduction', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /Open thread/ })).toHaveCount(0)
  await expect(page.getByText('Your notes first. Numbers when there are numbers.')).toBeVisible()
})

test('watchlist: digest toggle, CSV export and Find players keep working', async ({ page }) => {
  const { calls } = await openWatchlist(page, VIEWPORTS[0], { entries: watchlistEntries().slice(0, 2) })
  await expect(page.getByTestId('watchlist-row')).toHaveCount(2)
  const digest = page.getByRole('checkbox', { name: 'Weekly digest email' })
  await expect(digest).toBeChecked()
  await digest.click()
  await expect.poll(() => calls.find((call) => call.pathname === '/api/scout/watchlist/settings')?.body).toBe(JSON.stringify({ digest_opt_in: false }))
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  expect((await download).suggestedFilename()).toBe('academy-watch-scout-export.csv')
  expect(calls.find((call) => call.pathname === '/api/scout/export.csv').params.get('ids')).toBe('-21,-15')
  await expect(page.getByRole('link', { name: 'Find players' })).toHaveAttribute('href', '/scout')
})

test('watchlist: one scout’s notes never appear for the next account on the same device', async ({ page }) => {
  let release
  const held = new Promise((resolve) => { release = resolve })
  await page.clock.setFixedTime(TODAY)
  await signIn(page, 'token-a')
  await installApiMocks(page, { entries: watchlistEntries() })
  await page.route('**/api/scout/watchlist', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    if (route.request().headers().authorization === 'Bearer token-b') {
      await held
      return route.fulfill({ json: { entries: [entry(-24, 'B’s own note.')], digest_opt_in: true } })
    }
    return route.fallback()
  })
  await page.goto('/scout/watchlist')
  const rows = page.getByTestId('watchlist-row')
  await expect(rows).toHaveCount(10)
  const draftRow = rows.filter({ hasText: 'Kofi Asante-Reid' })
  await draftRow.getByRole('button', { name: 'Add a note for Kofi Asante-Reid' }).click()
  await draftRow.getByRole('textbox', { name: 'Note for Kofi Asante-Reid' }).fill('A’s unsaved draft')

  await changeViewer(page, 'token-b')
  // B's list is still loading: nothing of A's is on screen, not even the draft.
  await expect(rows).toHaveCount(0, { timeout: 2000 })
  await expect(page.getByText(NOTE_400)).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: /Note for/ })).toHaveCount(0)
  release()
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('B’s own note.')

  await changeViewer(page, null)
  await expect(page.getByRole('heading', { name: 'Sign in to build your watchlist' })).toBeVisible()
  await expect(page.getByText('B’s own note.')).toHaveCount(0)
})

test('"Open thread" lands on that thread in Introductions', async ({ page }) => {
  await page.clock.setFixedTime(TODAY)
  await signIn(page)
  const request = (id, name) => ({ id, player_api_id: -21, message: `Hello ${name}`, status: 'pending', routing_mode: 'direct', messaging_open: false, created_at: '2026-09-30T09:00:00', participants: { scout: { display_name: 'Corinne' }, player: { display_name: name } } })
  await installApiMocks(page, { sent: [request('r-other', 'Reuben Castellane'), request('r-tobi', 'Tobi Olawale')] })
  await page.goto('/introductions?request=r-tobi')
  const selected = page.locator('button[aria-current="true"]')
  await expect(selected).toHaveCount(1)
  await expect(selected).toContainText('Tobi Olawale')

  // Reviewer's probe: the requested id changes without a reload (a link, Back / Forward).
  await page.evaluate(() => { window.history.pushState({}, '', '/introductions?request=r-other'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await expect(selected).toContainText('Reuben Castellane')
  await page.goBack()
  await expect(selected).toContainText('Tobi Olawale')
  // An id that is not one of the caller's own requests selects nothing new.
  await page.evaluate(() => { window.history.pushState({}, '', '/introductions?request=r-someone-elses'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await expect(selected).toContainText('Tobi Olawale')
})
