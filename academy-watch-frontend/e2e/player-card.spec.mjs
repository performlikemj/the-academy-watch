/* global document, window, getComputedStyle, Image, MutationObserver */
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { test, expect } from '@playwright/test'

// Every person, club and league below is fictional (the staging story's world).
// Screenshots are written only when PC_SHOTS_DIR is set.
const SHOTS = process.env.PC_SHOTS_DIR || null
const VIEWPORTS = [
  { name: '1440', width: 1440, height: 900 },
  { name: '390', width: 390, height: 844 },
]
const LEAGUE = 'Wendle & District Senior League, Premier Division'

const seasonsDirectory = {
  current_season: 2026,
  display_season: 2026,
  bounds: { min: 2024, max: 2026 },
  seasons: [
    { season: 2026, label: '2026/27', has_rollup: true, is_current: true },
    { season: 2025, label: '2025/26', has_rollup: true, is_current: false },
  ],
}

function silhouette(background, figure) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 768"><rect width="600" height="768" fill="${background}"/><circle cx="300" cy="300" r="150" fill="${figure}"/><path d="M10 768 C24 580 150 500 300 500 C450 500 576 580 590 768 Z" fill="${figure}"/></svg>`
}
const PHOTOS = {
  '/fixture-photos/portrait.svg': silhouette('#C8C2B3', '#A9A293'),
  '/fixture-photos/second.svg': silhouette('#B7C0B4', '#8FA08C'),
  '/fixture-photos/third.svg': silhouette('#C9B8A6', '#A58E78'),
  '/fixture-photos/white.svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 768"><rect width="600" height="768" fill="#FFFFFF"/></svg>',
}

function photo(id, url, extra = {}) {
  return { id, kind: 'photo', status: 'approved', public_url: url, is_primary: false, sort_order: id, ...extra }
}

function line(matchDate, opponent, overrides = {}) {
  return {
    key: `${matchDate}|${opponent.toLowerCase()}`,
    season: 2026,
    match_date: matchDate,
    opponent,
    competition: LEAGUE,
    home_away: 'home',
    result_for: 3,
    result_against: 1,
    minutes: 90,
    goals: 0,
    assists: 0,
    yellows: 0,
    reds: 0,
    saves: null,
    goals_conceded: null,
    confirmation: 'club_confirmed',
    self_report: 'matches',
    shared_slot: false,
    ...overrides,
  }
}

// Same arithmetic as the server's season_totals(): the fixture can never state
// totals that its own lines do not add up to.
function totalsOf(lines) {
  const sum = (key) => lines.reduce((total, entry) => total + (entry[key] || 0), 0)
  const known = (key) => (lines.some((entry) => entry[key] != null) ? sum(key) : null)
  const confirmed = lines.filter((entry) => entry.confirmation === 'club_confirmed')
  return {
    matches: lines.length,
    appearances: lines.filter((entry) => entry.minutes > 0).length,
    full_matches: lines.filter((entry) => entry.minutes >= 90).length,
    minutes: sum('minutes'),
    goals: sum('goals'),
    assists: sum('assists'),
    yellows: known('yellows'),
    reds: known('reds'),
    cards_known: lines.length > 0 && lines.every((entry) => entry.yellows != null && entry.reds != null),
    saves: known('saves'),
    goals_conceded: known('goals_conceded'),
    keeper_matches: lines.filter((entry) => entry.saves != null || entry.goals_conceded != null).length,
    club_confirmed: confirmed.length,
    self_reported_only: lines.length - confirmed.length,
    differing: confirmed.filter((entry) => entry.self_report === 'differs').length,
  }
}

function seasonsOf(lines) {
  const bySeason = new Map()
  for (const entry of lines) bySeason.set(entry.season, [...(bySeason.get(entry.season) || []), entry])
  return [...bySeason.entries()]
    .sort(([a], [b]) => b - a)
    .map(([season, seasonLines]) => ({ season, lines: seasonLines, totals: totalsOf(seasonLines) }))
}

const kofiProfile = {
  bio: 'Right-back at Quillmere Athletic. Five seasons in the first team. I like defending properly and I will overlap all day if someone covers me.',
  positions: 'RB, RWB',
  preferred_foot: 'right',
  height_cm: 178,
  contract_status: 'under_contract',
  availability: 'not_looking',
  languages: 'English, Twi',
}
const quillmere = { id: 1, club_name: 'Quillmere Athletic', status: 'club_confirmed', season: '2026/27' }

const OPPONENTS = [
  'Skerraby United', 'Durnsea Juniors', 'Pellowick Town', 'Thrandby Wrens', 'Greaveholme Town', 'Marlowe Quay',
  'Fennick Rovers', 'Ostley Vale', 'Brackwater', 'Holm St Agnes', 'Wexcombe', 'Saltern Athletic',
]

// A believable season: 22 matches, 15 confirmed by the club, 7 only reported
// by the player, a few goals, assists and cards, one unused-substitute day and
// one match where the two reports differ.
function fullSeason() {
  const lines = []
  for (let index = 0; index < 22; index += 1) {
    const date = new Date(Date.UTC(2026, 7, 8 + index * 7))
    const matchDate = date.toISOString().slice(0, 10)
    const clubConfirmed = index % 3 !== 2 || index === 20
    lines.push(line(matchDate, OPPONENTS[index % OPPONENTS.length], {
      home_away: index % 2 ? 'away' : 'home',
      competition: index % 6 === 5 ? 'Wendleshire Senior Cup' : LEAGUE,
      result_for: [2, 1, 0, 3, 1, 2][index % 6],
      result_against: [0, 1, 2, 1, 1, 3][index % 6],
      minutes: index === 9 ? 0 : index % 5 === 3 ? 64 : index % 7 === 6 ? 78 : 90,
      goals: index === 4 || index === 15 ? 1 : 0,
      assists: [2, 6, 11, 13, 18].includes(index) ? 1 : 0,
      yellows: [3, 8, 12, 19].includes(index) ? 1 : 0,
      reds: 0,
      confirmation: clubConfirmed ? 'club_confirmed' : 'self_reported',
      self_report: !clubConfirmed ? null : index === 12 ? 'differs' : index % 2 ? 'matches' : null,
    }))
  }
  return lines.reverse()
}

const players = {
  // The approved mockup, exactly: one club-confirmed match that matches the player's own report.
  '-12': {
    name: 'Kofi Asante-Reid', position: 'Right-back', age: 25,
    showcase: { profile: kofiProfile, photos: [photo(1, '/fixture-photos/portrait.svg', { is_primary: true })], affiliations: [quillmere], claim_status: 'claimed', contactable: true },
    lines: [line('2026-09-20', 'Skerraby United')],
  },
  // State D: no approved photo.
  '-13': {
    name: 'Kofi Asante-Reid', position: 'Right-back', age: 25,
    showcase: { profile: kofiProfile, photos: [], affiliations: [quillmere], claim_status: 'claimed', contactable: true },
    lines: [line('2026-09-20', 'Skerraby United')],
  },
  // No matches yet, no photo, unclaimed and unconfirmed.
  '-14': {
    name: 'Olu Adeyemi-Clarke', position: 'Winger', age: 22,
    showcase: { profile: { positions: 'LW, RW', preferred_foot: 'left' }, photos: [], affiliations: [], claim_status: 'unclaimed', contactable: false },
    lines: [],
  },
  // A full season with mixed sources.
  '-15': {
    name: 'Reuben Castellane', position: 'Midfielder', age: 23,
    showcase: {
      profile: { ...kofiProfile, positions: 'CM, DM', bio: 'Central midfielder. Signed from the summer open trial.', height_cm: 181, languages: 'English' },
      photos: [photo(1, '/fixture-photos/portrait.svg', { is_primary: true })], affiliations: [quillmere], claim_status: 'claimed', contactable: true,
    },
    lines: fullSeason(),
  },
  // The two reports of one match differ; another is only self-reported.
  '-16': {
    name: 'Kofi Asante-Reid', position: 'Right-back', age: 25,
    showcase: { profile: kofiProfile, photos: [photo(1, '/fixture-photos/portrait.svg', { is_primary: true })], affiliations: [quillmere], claim_status: 'claimed', contactable: true },
    lines: [
      line('2026-09-27', 'Durnsea Juniors', { home_away: 'away', result_for: 1, result_against: 1, minutes: 74, yellows: 1, self_report: 'differs' }),
      line('2026-09-20', 'Skerraby United'),
      line('2026-09-13', 'Pellowick Town', { home_away: 'away', result_for: 0, result_against: 2, minutes: 90, assists: 1, confirmation: 'self_reported', self_report: null }),
    ],
  },
  // Very long name and a long competition name.
  '-17': {
    name: 'Maximilian-Alexander Oluwaseun Featherstonehaugh-Abernathy', position: 'Attacking midfielder', age: 24,
    showcase: {
      profile: { ...kofiProfile, positions: 'Attacking midfielder, Second striker, Left winger', languages: 'English, Yoruba, French, Portuguese', nationality_secondary: 'Nigeria', bio: 'Plays between the lines.' },
      photos: [photo(1, '/fixture-photos/portrait.svg', { is_primary: true })],
      affiliations: [{ ...quillmere, club_name: 'Quillmere Athletic & Wendleshire Community Sports Association' }],
      claim_status: 'claimed', contactable: true,
    },
    lines: [
      line('2026-09-20', 'Greaveholme-under-Lyne Wanderers Reserves & Development', {
        competition: 'Wendleshire & District Football Association Senior Challenge Invitation Cup, Preliminary Qualifying Round (Northern Section)',
        home_away: 'neutral', goals: 2, assists: 1, yellows: 1, reds: 1,
      }),
      line('2026-09-13', 'Skerraby United', { competition: null, result_for: null, result_against: null, confirmation: 'self_reported', self_report: null }),
    ],
  },
  // Several approved photos.
  '-18': {
    name: 'Kofi Asante-Reid', position: 'Right-back', age: 25,
    showcase: {
      profile: kofiProfile,
      photos: [
        photo(1, '/fixture-photos/portrait.svg', { is_primary: true }), photo(2, '/fixture-photos/second.svg'), photo(3, '/fixture-photos/third.svg'),
        { id: 4, kind: 'photo', status: 'pending', public_url: null }, { id: 5, kind: 'photo', status: 'approved', public_url: null },
      ],
      affiliations: [quillmere], claim_status: 'claimed', contactable: true,
    },
    lines: [line('2026-09-20', 'Skerraby United')],
  },
  // A goalkeeper: keeper figures replace goals + assists.
  '-19': {
    name: 'Tamsin Holloway', position: 'Goalkeeper', age: 27,
    showcase: {
      profile: { positions: 'GK', preferred_foot: 'right', height_cm: 191, contract_status: 'under_contract', languages: 'English' },
      photos: [photo(1, '/fixture-photos/portrait.svg', { is_primary: true })], affiliations: [quillmere], claim_status: 'claimed', contactable: true,
    },
    lines: [
      line('2026-09-27', 'Durnsea Juniors', { home_away: 'away', result_for: 0, result_against: 2, saves: 6, goals_conceded: 2, self_report: null }),
      line('2026-09-20', 'Skerraby United', { saves: 4, goals_conceded: 1 }),
      line('2026-09-13', 'Pellowick Town', { result_for: 1, result_against: 0, saves: 3, goals_conceded: 0, yellows: 1, self_report: null }),
      line('2026-09-06', 'Thrandby Wrens', { result_for: 2, result_against: 2, confirmation: 'self_reported', self_report: null }),
    ],
  },
  // White test photo: text over the hero photo must stay readable.
  '-20': {
    name: 'Kofi Asante-Reid', position: 'Right-back', age: 25,
    showcase: { profile: kofiProfile, photos: [photo(1, '/fixture-photos/white.svg', { is_primary: true })], affiliations: [quillmere], claim_status: 'claimed', contactable: true },
    lines: [line('2026-09-20', 'Skerraby United')],
  },
  // Two seasons of own entries.
  '-21': {
    name: 'Jago Penrose', position: 'Winger', age: 24,
    showcase: { profile: { positions: 'LW' }, photos: [], affiliations: [], claim_status: 'claimed', contactable: true },
    lines: [
      line('2026-09-13', 'Pellowick Town', { confirmation: 'self_reported', self_report: null, minutes: 61 }),
      line('2025-10-04', 'Marrowby Colts', { season: 2025, confirmation: 'self_reported', self_report: null, minutes: 30 }),
    ],
  },
  // A community profile linked to the provider identity 4242 below.
  '-22': {
    name: 'Linked Prospect', position: 'Midfielder', age: 22, linkedTo: 4242,
    showcase: { profile: null, photos: [], affiliations: [], claim_status: 'unclaimed', contactable: false },
    lines: [],
  },
  // Only an older season, and a profile claimed by a guardian (not the player).
  '-23': {
    name: 'Nabil Ferhane', position: 'Attacking midfield', age: 21,
    showcase: { profile: { positions: 'AM' }, photos: [], affiliations: [], claim_status: 'claimed', contactable: false },
    lines: [line('2024-10-05', 'Marrowby Colts', { season: 2024, confirmation: 'self_reported', self_report: null })],
  },
  // A double-header: two club results on one date against one opponent, and
  // two own entries on another. Nothing is paired, nothing is dropped.
  '-24': {
    name: 'Emeka Nwosu-Clarke', position: 'Centre-back', age: 20,
    showcase: { profile: { positions: 'CB' }, photos: [], affiliations: [quillmere], claim_status: 'claimed', contactable: true },
    lines: [
      line('2026-09-27', 'Hallowfen Rovers', { key: '2026-09-27|hallowfen rovers|club-1', minutes: 45, result_for: 1, result_against: 0, self_report: null, shared_slot: true }),
      line('2026-09-27', 'Hallowfen Rovers', { key: '2026-09-27|hallowfen rovers|club-2', minutes: 60, result_for: 0, result_against: 2, self_report: null, shared_slot: true }),
      line('2026-09-20', 'Skerraby United', { key: '2026-09-20|skerraby united|own-1', minutes: 45, confirmation: 'self_reported', self_report: null, shared_slot: true }),
      line('2026-09-20', 'Skerraby United', { key: '2026-09-20|skerraby united|own-2', minutes: 45, confirmation: 'self_reported', self_report: null, shared_slot: true }),
    ],
  },
  // Provider identity with totals this season only, and one own entry the season before.
  4242: {
    name: 'Linked Prospect', position: 'Midfielder', age: 22, provider: true, providerSeasons: [2026],
    showcase: { profile: null, photos: [], affiliations: [], claim_status: 'unclaimed', contactable: false },
    lines: [line('2025-10-04', 'Marrowby Colts', { season: 2025, confirmation: 'self_reported', self_report: null, minutes: 30 })],
  },
  // Provider-tracked player: provider totals stay, the club's own lines are listed, never added.
  42: {
    name: 'Test Prospect', position: 'Midfielder', age: 19, provider: true,
    showcase: { profile: null, photos: [], affiliations: [], claim_status: 'unclaimed', contactable: false },
    lines: [line('2026-09-20', 'Skerraby United', { self_report: null })],
  },
}

// What /scout/players returns today. For club- or player-entered seasons the
// rollup counts the club's rows only, so these figures can differ from the
// player's page (Reuben: 15 club rows here, 22 matches on his page) — which is
// why the card must not print them. Provider-sourced rows keep their counters.
const scoutRows = [
  { id: 1, player_id: -12, player_name: 'Kofi Asante-Reid', position: 'Right-back', primary_team_name: 'Quillmere Athletic', appearances: 1, minutes_played: 90, provenance: { source: 'club' }, player_photo: null },
  { id: 2, player_id: -15, player_name: 'Reuben Castellane', position: 'Midfielder', primary_team_name: 'Quillmere Athletic', appearances: 15, minutes_played: 1238, provenance: { source: 'club' }, player_photo: '/fixture-photos/portrait.svg' },
  { id: 3, player_id: -14, player_name: 'Olu Adeyemi-Clarke', position: 'Winger', primary_team_name: null, appearances: 0, minutes_played: 0, provenance: { source: 'self' }, player_photo: null, contactable: false },
  { id: 4, player_id: -17, player_name: 'Maximilian-Alexander Oluwaseun Featherstonehaugh-Abernathy', position: 'Attacking midfielder', primary_team_name: 'Quillmere Athletic & Wendleshire Community Sports Association', appearances: 2, minutes_played: 180, provenance: { source: 'self' }, player_photo: null },
  { id: 5, player_id: -19, player_name: 'Tamsin Holloway', position: 'Goalkeeper', primary_team_name: 'Quillmere Athletic', appearances: 3, minutes_played: 270, provenance: { source: 'club' }, player_photo: null },
  { id: 6, player_id: 42, player_name: 'Test Prospect', position: 'Midfielder', primary_team_name: 'Test Academy', appearances: 30, minutes_played: 2412, provenance: { primary_source: 'journey' }, player_photo: null, contactable: false },
].map((row) => ({ nationality: 'England', age: 24, status: null, recent_form: [], goals: 0, assists: 0, contactable: true, ...row }))

async function installApiMocks(page, { frozen = false, contactRail = true, watched = [], linesStatus = () => 200, seasonStatsStatus = () => 200, verification = null, claims = [], rawMatches = [], gate = null } = {}) {
  const calls = []
  await page.route('**/fixture-photos/*', (route) => {
    const body = PHOTOS[new URL(route.request().url()).pathname]
    return body ? route.fulfill({ contentType: 'image/svg+xml', body }) : route.fulfill({ status: 404, body: '' })
  })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname
    calls.push(`${route.request().method()} ${pathname}${url.search}`)
    if (pathname === '/api/seasons') return route.fulfill({ json: seasonsDirectory })
    if (pathname === '/api/features') return route.fulfill({ json: { contact_rail: contactRail } })
    if (pathname === '/api/meta/data-mode') return route.fulfill({ json: { api_football_frozen: frozen, newsletters_frozen: frozen } })
    if (pathname === '/api/scout/watchlist/ids') return route.fulfill({ json: { player_ids: watched } })
    if (pathname === '/api/scout/verification') return route.fulfill({ json: { verification } })
    if (pathname === '/api/me/claims') return route.fulfill({ json: { claims } })
    if (pathname === '/api/scout/players') return route.fulfill({ json: { season: 2026, players: scoutRows, total: scoutRows.length, total_pages: 1 } })
    if (pathname === '/api/scout/leaderboards') return route.fulfill({ json: { season: 2026, leaderboards: {} } })

    const local = /^\/api\/local-players\/(\d+)(\/.*)?$/.exec(pathname)
    if (local) {
      const player = players[`-${local[1]}`]
      if (!player) return route.fulfill({ status: 404, json: { error: 'local player not found' } })
      if (!local[2]) {
        return route.fulfill({ json: { player: { id: Number(local[1]), display_name: player.name, position: player.position, birth_year: 2001, city: 'Quillmere', country: 'England', club_name: 'Quillmere Athletic', status: 'approved', api_player_id: player.linkedTo ?? null } } })
      }
      if (local[2] === '/showcase') return route.fulfill({ json: { local_player_id: Number(local[1]), reel: [], verified_footage: [], ...player.showcase } })
    }

    const match = /^\/api\/players\/(-?\d+)\/(.+)$/.exec(pathname)
    if (match) {
      const player = players[match[1]]
      if (!player) return route.fulfill({ status: 404, json: { error: 'Player not found' } })
      const [, id, resource] = match
      if (resource === 'profile') return route.fulfill({ json: { name: player.name, position: player.position, age: player.age, nationality: 'England' } })
      if (resource === 'showcase') return route.fulfill({ json: { player_api_id: Number(id), reel: [], verified_footage: [], ...player.showcase } })
      if (resource === 'followers/count') return route.fulfill({ json: { fans: 6, following: false, share_url: `https://example.test/players/${id}` } })
      if (resource === 'matches') {
        if (url.searchParams.get('view') === 'lines') {
          const status = linesStatus()
          if (status !== 200) return route.fulfill({ status, json: { error: 'Failed to load player matches' } })
          return route.fulfill({ json: { view: 'lines', seasons: seasonsOf(player.lines), truncated: false } })
        }
        return route.fulfill({ json: { matches: rawMatches, total: rawMatches.length, page: 1, per_page: 100 } })
      }
      if (resource === 'stats') {
        return route.fulfill({ json: player.provider
          ? { matches: [{ fixture_date: '2026-09-01', opponent: 'Test United', position: 'M', minutes: 90, goals: 1, assists: 0, rating: '7.4' }], summary: { season: 2026 } }
          : { matches: [], summary: { season: 2026 } } })
      }
      if (resource === 'season-stats') {
        const provider = { appearances: 30, minutes: 2412, goals: 6, assists: 4, yellows: 3, reds: 0, avg_rating: 7.12 }
        const grain = totalsOf(player.lines.filter((entry) => entry.confirmation === 'club_confirmed'))
        const asked = Number(url.searchParams.get('season') || 2026)
        if (gate) await gate(asked)
        const seasonStatus = seasonStatsStatus()
        if (seasonStatus !== 200) return route.fulfill({ status: seasonStatus, json: { error: 'Failed to load season stats' } })
        const providerHasSeason = player.provider && (!player.providerSeasons || player.providerSeasons.includes(asked))
        const base = providerHasSeason
          ? { ...provider, source: 'season-rollup', provenance: { primary_source: 'journey', reconcile_flag: null } }
          // What the rollup says today for a community player: the club's rows only.
          : { appearances: grain.appearances, minutes: grain.minutes, goals: grain.goals, assists: grain.assists, source: 'season-rollup', provenance: { primary_source: 'club' } }
        const separated = frozen ? {
          public_match_data: providerHasSeason
            ? { available: true, as_of: '2026-09-28T09:00:00+00:00', totals: provider }
            : { available: true, as_of: null, totals: { appearances: 0, minutes: 0, goals: 0, assists: 0 } },
          club_verified: { available: grain.matches > 0, totals: grain },
        } : {}
        return route.fulfill({ json: { player_id: Number(id), season: `${asked}/${asked + 1}`, clubs: [], ...base, ...separated } })
      }
    }
    return route.fulfill({ json: {} })
  })
  return calls
}

async function shot(page, name) {
  if (!SHOTS) return
  fs.mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

async function signIn(page) {
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-user-token')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
}

// "This season" is worded from today's date; pin it so the fixtures stay current.
const TODAY = new Date('2026-10-03T12:00:00Z')

async function openPlayer(page, id, viewport, options) {
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize({ width: viewport.width, height: viewport.height })
  const calls = await installApiMocks(page, options)
  await page.goto(`/players/${id}`)
  await expect(page.getByTestId('player-hero')).toBeVisible()
  await expect(page.getByTestId('player-season')).toHaveAttribute('aria-labelledby', 'pc-season-title')
  await expect(page.getByTestId('season-empty').getByText('Loading the season…')).toHaveCount(0)
  await page.evaluate(() => document.fonts.ready)
  return calls
}

async function expectNoSidewaysScroll(page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
}

for (const viewport of VIEWPORTS) {
  const phone = viewport.width < 900
  const rows = (page) => page.getByTestId(phone ? 'match-card' : 'match-line')

  test.describe(`${viewport.name}px`, () => {
    test('the mockup state: one match, shown once, with totals that add up', async ({ page }) => {
      const calls = await openPlayer(page, -12, viewport)

      await expect(page.getByRole('heading', { level: 1, name: 'Kofi Asante-Reid' })).toBeVisible()
      await expect(page.getByTestId('player-hero-photo')).toHaveAttribute('alt', 'Kofi Asante-Reid')
      await expect(page.getByTestId('player-hero-copy').getByText('Confirmed by Quillmere Athletic')).toBeVisible()
      await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
      await expect(rows(page)).toHaveCount(1)
      await expect(rows(page).getByText('Skerraby United')).toBeVisible()
      await expect(rows(page).getByText('Club-confirmed')).toBeVisible()
      await expect(rows(page).getByText("Matches the player's own report")).toBeVisible()
      await expect(page.getByTestId('season-tile-minutes')).toContainText('90')
      await expect(page.getByTestId('season-tile-minutes')).toContainText('Every minute of the 1 match recorded')
      await expect(page.getByTestId('season-tile-appearances')).toContainText('1')
      await expect(page.getByTestId('season-tile-discipline')).toContainText('Clean')
      await expect(page.getByTestId('season-source')).toHaveText('Built from 1 match. 1 confirmed by the club, 0 only reported by the player.')
      // What was wrong before: zero totals above a 90-minute row, and zeros listed as facts.
      await expect(page.getByText('Public match data')).toHaveCount(0)
      await expect(page.getByText(/0 goals|0 assists|0 yellow|0 red/)).toHaveCount(0)
      await expect(page.getByTestId('player-facts').locator('dt')).toHaveText(['Positions', 'Foot', 'Height', 'Contract', 'Availability', 'Languages'])
      expect(calls.some((call) => call.includes('/api/players/-12/matches?view=lines'))).toBe(true)
      await expectNoSidewaysScroll(page)
      await shot(page, `01-photo-one-match-${viewport.name}`)
    })

    test('no photo: initials in the club colours replace the old ring', async ({ page }) => {
      await openPlayer(page, -13, viewport)

      await expect(page.getByTestId('player-hero')).toHaveAttribute('data-photo', 'no')
      await expect(page.getByRole('img', { name: 'Kofi Asante-Reid — no photo yet' })).toBeVisible()
      await expect(page.getByTestId('player-hero').getByText('KA', { exact: true })).toBeVisible()
      await expectNoSidewaysScroll(page)
      await shot(page, `02-no-photo-${viewport.name}`)
    })

    test('no matches yet: an honest empty state, no zero tiles', async ({ page }) => {
      await openPlayer(page, -14, viewport)

      await expect(page.getByTestId('season-empty')).toContainText('No matches recorded yet')
      await expect(page.locator('[data-testid^="season-tile-"]')).toHaveCount(0)
      await expect(page.getByTestId('match-lines')).toHaveCount(0)
      await expect(page.getByTestId('player-facts').locator('dt')).toHaveText(['Positions', 'Foot'])
      await expect(page.getByTestId('player-hero-copy').getByText(/Confirmed by/)).toHaveCount(0)
      await expectNoSidewaysScroll(page)
      await shot(page, `03-no-matches-${viewport.name}`)
    })

    test('a full season: latest ten first, Show all, and totals equal to the lines', async ({ page }) => {
      await openPlayer(page, -15, viewport)
      const lines = players['-15'].lines
      const totals = totalsOf(lines)

      await expect(rows(page)).toHaveCount(10)
      await expect(page.getByTestId('season-tile-minutes')).toContainText(totals.minutes.toLocaleString('en-GB'))
      await expect(page.getByTestId('season-tile-appearances')).toContainText(String(totals.appearances))
      await expect(page.getByTestId('season-tile-contribution')).toContainText(String(totals.goals + totals.assists))
      await expect(page.getByTestId('season-source')).toContainText(`Built from 22 matches. ${totals.club_confirmed} confirmed by the club, ${totals.self_reported_only} only reported by the player.`)
      await shot(page, `04-full-season-${viewport.name}`)

      await page.getByRole('button', { name: 'Show all 22 matches' }).click()
      await expect(rows(page)).toHaveCount(22)
      // Each match appears once: no two rows share a date and opponent.
      const keys = lines.map((entry) => entry.key)
      expect(new Set(keys).size).toBe(22)
      await expectNoSidewaysScroll(page)
      await shot(page, `04-full-season-all-${viewport.name}`)
    })

    test('a mismatch is stated neutrally and the club figures are the ones shown', async ({ page }) => {
      await openPlayer(page, -16, viewport)

      const differing = rows(page).filter({ hasText: 'Durnsea Juniors' })
      await expect(differing.getByText('Club-confirmed')).toBeVisible()
      await expect(differing).toContainText('Club figures shown')
      await expect(differing).toContainText("Differs from the player's report")
      const selfOnly = rows(page).filter({ hasText: 'Pellowick Town' })
      await expect(selfOnly.getByText('Self-reported')).toBeVisible()
      await expect(selfOnly.getByText('Club-confirmed')).toHaveCount(0)
      await expect(page.getByTestId('season-source')).toContainText("Where the two reports differ, the club's figures are used.")
      await expect(page.getByTestId('season-tile-minutes')).toContainText('254')
      await expect(page.getByText(/wrong|false|incorrect|disputed/i)).toHaveCount(0)
      await expectNoSidewaysScroll(page)
      await shot(page, `05-mismatch-${viewport.name}`)
    })

    test('a very long name and competition do not overflow', async ({ page }) => {
      await openPlayer(page, -17, viewport)

      await expect(page.getByRole('heading', { level: 1 })).toContainText('Featherstonehaugh-Abernathy')
      await expect(rows(page).first()).toContainText('Senior Challenge Invitation Cup')
      await expectNoSidewaysScroll(page)
      const clipped = await page.getByRole('heading', { level: 1 }).evaluate((node) => node.scrollWidth > node.clientWidth + 1)
      expect(clipped).toBe(false)
      await shot(page, `06-long-names-${viewport.name}`)
    })

    test('several approved photos can be looked through; unapproved ones never appear', async ({ page }) => {
      await openPlayer(page, -18, viewport)

      const thumbs = page.getByRole('button', { name: /^Show photo \d of 3$/ }).filter({ visible: true })
      await expect(thumbs).toHaveCount(3)
      await expect(page.getByTestId('player-hero-photo')).toHaveAttribute('src', '/fixture-photos/portrait.svg')
      await thumbs.nth(1).click()
      await expect(page.getByTestId('player-hero-photo')).toHaveAttribute('src', '/fixture-photos/second.svg')
      await expect(thumbs.nth(1)).toHaveAttribute('aria-pressed', 'true')
      const box = await thumbs.first().boundingBox()
      expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44)
      await expectNoSidewaysScroll(page)
      await shot(page, `07-several-photos-${viewport.name}`)
    })

    test('a goalkeeper sees keeper figures instead of goals and assists', async ({ page }) => {
      await openPlayer(page, -19, viewport)

      await expect(page.getByTestId('season-tile-keeper')).toContainText('13')
      await expect(page.getByTestId('season-tile-contribution')).toHaveCount(0)
      if (!phone) {
        await expect(page.getByTestId('season-tile-keeper')).toContainText('3 conceded in 3 matches')
        await expect(page.getByRole('columnheader', { name: 'SV' })).toBeVisible()
        await expect(page.getByRole('columnheader', { name: 'GC' })).toBeVisible()
      } else {
        await expect(rows(page).filter({ hasText: 'Pellowick Town' })).toContainText('3 saves · none conceded · 1 yellow')
      }
      await expectNoSidewaysScroll(page)
      await shot(page, `08-keeper-${viewport.name}`)
    })

    test('a provider-tracked player keeps provider totals and lists club lines separately', async ({ page }) => {
      await openPlayer(page, 42, viewport, { frozen: true })

      await expect(page.getByTestId('player-season')).toHaveAttribute('data-source', 'provider')
      await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')
      await expect(page.getByTestId('season-source')).toContainText('Public match data — last updated 2026-09-28.')
      await expect(page.getByTestId('season-source')).toContainText('not added to these totals')
      await expect(rows(page)).toHaveCount(1)
      await expectNoSidewaysScroll(page)
      await shot(page, `09-provider-player-${viewport.name}`)
    })

    test('targets are at least 44px and are real buttons or links', async ({ page }) => {
      await openPlayer(page, -15, viewport)

      const targets = [
        page.getByRole('button', { name: 'Add to watchlist' }),
        page.getByRole('button', { name: /introduction/i }),
        page.getByRole('button', { name: 'Show all 22 matches' }),
        page.getByRole('button', { name: 'Follow', exact: true }),
      ]
      targets.push(page.getByRole('button', { name: 'Share', exact: true }))
      for (const target of targets) {
        await expect(target).toBeVisible()
        expect((await target.boundingBox()).height).toBeGreaterThanOrEqual(44)
      }
    })

    test('the community player page uses the same read view', async ({ page }) => {
      await page.clock.setFixedTime(TODAY)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await installApiMocks(page)
      await page.goto('/local-players/16')

      await expect(page.getByRole('heading', { level: 1, name: 'Kofi Asante-Reid' })).toBeVisible()
      await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
      await expect(rows(page)).toHaveCount(3)
      await expect(page.getByText('Community profile — self-reported.')).toBeVisible()
      await expect(page.getByTestId('season-tile-minutes')).toContainText('254')
      await expectNoSidewaysScroll(page)
      await shot(page, `10-community-page-${viewport.name}`)
    })

    test('the scout desk can show players as cards (photo and no-photo states)', async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await signIn(page)
      await installApiMocks(page, { watched: [-15] })
      await page.goto('/scout')
      const view = page.getByRole('group', { name: 'Show players as' })
      await expect(view.getByRole('button', { name: phone ? 'Cards' : 'Table' })).toHaveAttribute('aria-pressed', 'true')
      if (!phone) {
        await expect(page.getByRole('table')).toBeVisible()
        await view.getByRole('button', { name: 'Cards' }).click()
      }

      for (const name of ['Cards', 'Table']) {
        expect((await view.getByRole('button', { name }).boundingBox()).height).toBeGreaterThanOrEqual(44)
      }
      const cards = page.getByTestId('player-card')
      await expect(cards).toHaveCount(scoutRows.length)
      const kofi = cards.filter({ hasText: 'Kofi Asante-Reid' })
      await expect(kofi.getByRole('link', { name: 'Kofi Asante-Reid' })).toHaveAttribute('href', '/players/-12')
      await expect(kofi).toContainText('Right-back at Quillmere Athletic.')
      // Club- and player-entered seasons: no apps/minutes on the card (the desk's
      // figures and the player's page are counted differently until they share one source).
      for (const name of ['Kofi Asante-Reid', 'Reuben Castellane', 'Tamsin Holloway', 'Olu Adeyemi-Clarke']) {
        const card = cards.filter({ hasText: name })
        await expect(card).not.toContainText(/\bapps?\b/)
        await expect(card).not.toContainText(/\bmin\b/)
        await expect(card.getByRole('img', { name: 'Club-confirmed' })).toHaveCount(0)
      }
      // Provider-sourced figures are the same totals the player's page shows.
      const provider = cards.filter({ hasText: 'Test Prospect' })
      await expect(provider).toContainText('30 apps')
      await expect(provider).toContainText('2,412 min')
      await expect(cards.filter({ hasText: 'Reuben Castellane' }).getByRole('button', { name: 'Unwatch Reuben Castellane' })).toHaveAttribute('aria-pressed', 'true')
      const watch = kofi.getByRole('button', { name: 'Watch Kofi Asante-Reid' })
      expect((await watch.boundingBox()).height).toBeGreaterThanOrEqual(44)
      // The table's compare and introduce actions are on the card too.
      const compare = kofi.getByRole('button', { name: 'Compare Kofi Asante-Reid' })
      const introduce = kofi.getByRole('link', { name: 'Get verified to introduce yourself' })
      for (const control of [compare, introduce]) {
        const box = await control.boundingBox()
        expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44)
      }
      await expect(introduce).toHaveAttribute('href', '/scout/verification')
      await expect(cards.filter({ hasText: 'Olu Adeyemi-Clarke' }).getByRole('link', { name: /introduce/i })).toHaveCount(0)
      await compare.click()
      await expect(compare).toHaveAttribute('aria-pressed', 'true')
      await expect(page.getByText('1 of 4 selected')).toBeVisible()
      await expectNoSidewaysScroll(page)
      await page.evaluate(() => document.fonts.ready)
      await shot(page, `11-scout-desk-cards-${viewport.name}`)
    })
  })
}

test('hero C: text over a pure white photo keeps at least 4.5:1 through the scrim', async ({ page }) => {
  await openPlayer(page, -20, VIEWPORTS[1])
  await expect(page.getByTestId('player-hero-photo')).toBeVisible()
  await page.waitForFunction(() => {
    const image = document.querySelector('[data-testid="player-hero-photo"]')
    return image && image.complete && image.naturalWidth > 0
  })
  await shot(page, '12-white-photo-contrast-390')

  // Hide the text itself, then read the pixels that sit behind each text box.
  const copy = page.getByTestId('player-hero-copy')
  const targets = await copy.evaluate((node) => {
    const picked = []
    for (const element of node.querySelectorAll('.pc-hero-confirmed span, .pc-hero-eyebrow, .pc-hero-name, .pc-hero-line')) {
      const rect = element.getBoundingClientRect()
      if (!rect.width || !rect.height) continue
      picked.push({ label: element.className || element.parentElement.className, color: getComputedStyle(element).color, x: rect.x, y: rect.y, width: rect.width, height: rect.height })
    }
    node.style.color = 'transparent'
    for (const element of node.querySelectorAll('*')) element.style.color = 'transparent'
    for (const element of node.querySelectorAll('svg, button, a')) element.style.visibility = 'hidden'
    return picked
  })
  expect(targets.length).toBeGreaterThanOrEqual(3)
  const backdrop = await page.screenshot({ fullPage: true })
  const results = await page.evaluate(async ({ png, targets: boxes, scrollY }) => {
    const image = new Image()
    image.src = `data:image/png;base64,${png}`
    await image.decode()
    const scale = image.width / document.documentElement.clientWidth
    const canvas = Object.assign(document.createElement('canvas'), { width: image.width, height: image.height })
    const context = canvas.getContext('2d')
    context.drawImage(image, 0, 0)
    const channel = (value) => { const c = value / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
    const luminance = ([r, g, b]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return boxes.map((box) => {
      const text = luminance(box.color.match(/[\d.]+/g).slice(0, 3).map(Number))
      const data = context.getImageData(Math.floor(box.x * scale), Math.floor((box.y + scrollY) * scale), Math.ceil(box.width * scale), Math.ceil(box.height * scale)).data
      let worst = Infinity
      for (let index = 0; index < data.length; index += 4) {
        const background = luminance([data[index], data[index + 1], data[index + 2]])
        const ratio = (Math.max(text, background) + 0.05) / (Math.min(text, background) + 0.05)
        if (ratio < worst) worst = ratio
      }
      return { label: box.label, color: box.color, worst: Math.round(worst * 100) / 100 }
    })
  }, { png: backdrop.toString('base64'), targets, scrollY: await page.evaluate(() => window.scrollY) })

  if (SHOTS) fs.writeFileSync(path.join(SHOTS, '12-white-photo-contrast.json'), `${JSON.stringify(results, null, 2)}\n`)
  for (const result of results) expect(result.worst, `${result.label} over a white photo`).toBeGreaterThanOrEqual(4.5)
})

test('Compare from a player page fills the scout desk tray with that player', async ({ page }) => {
  await openPlayer(page, -12, VIEWPORTS[0])
  await page.getByRole('link', { name: 'Compare' }).click()

  await expect(page).toHaveURL(/\/scout\?compare=-12$/)
  await expect(page.getByText('1 of 4 selected')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('asking for an introduction: only the player\'s own claim, and only verified scouts reach the form', async ({ page }) => {
  // Unclaimed, and claimed only by a guardian: no invitation at all.
  for (const id of [-14, -23]) {
    await openPlayer(page, id, VIEWPORTS[0])
    await expect(page.getByRole('button', { name: /introduction/i })).toHaveCount(0)
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  }
  await openPlayer(page, -12, VIEWPORTS[0], { contactRail: false })
  await expect(page.getByRole('button', { name: /introduction/i })).toHaveCount(0)

  await page.unrouteAll({ behavior: 'ignoreErrors' })
  await openPlayer(page, -12, VIEWPORTS[0])
  await page.getByRole('button', { name: 'Ask for an introduction' }).click()
  // Signed out: the existing sign-in prompt, never the message form.
  await expect(page.getByRole('heading', { name: 'Sign in to The Academy Watch' })).toBeVisible()
})

test('a signed-in visitor who is not a verified scout is sent to verification', async ({ page }) => {
  await signIn(page)
  const calls = await openPlayer(page, -12, VIEWPORTS[0], { verification: { status: 'pending' } })
  // Verification is only asked for when the button is used, not on every page view.
  expect(calls.filter((call) => call.includes('/api/scout/verification'))).toEqual([])
  await page.getByRole('button', { name: 'Ask for an introduction' }).click()

  await expect(page).toHaveURL(/\/scout\/verification$/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('a verified scout gets the introduction form', async ({ page }) => {
  await signIn(page)
  await openPlayer(page, -12, VIEWPORTS[0], { verification: { status: 'approved' } })
  await page.getByRole('button', { name: 'Ask for an introduction' }).click()

  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Introduce yourself to Kofi Asante-Reid' })).toBeVisible()
})

test('a failed match read is an error with a retry, never an empty season', async ({ page }) => {
  let status = 500
  await openPlayer(page, -16, VIEWPORTS[0], { linesStatus: () => status })

  const error = page.getByTestId('season-error')
  await expect(error).toContainText('The matches could not be loaded.')
  await expect(page.getByTestId('player-season')).toHaveAttribute('data-source', 'error')
  await expect(page.getByText('No matches recorded yet')).toHaveCount(0)
  await expect(page.getByText(/Nothing has been entered/)).toHaveCount(0)
  await expect(page.locator('[data-testid^="season-tile-"]')).toHaveCount(0)
  await shot(page, '14-read-failed-1440')

  status = 200
  await error.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByTestId('match-line')).toHaveCount(3)
  await expect(page.getByTestId('season-error')).toHaveCount(0)
  await expect(page.getByTestId('season-tile-minutes')).toContainText('254')
})

test('a provider-tracked player whose club lines fail to load keeps the provider totals and says so', async ({ page }) => {
  await openPlayer(page, 42, VIEWPORTS[0], { linesStatus: () => 503 })

  await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')
  await expect(page.getByTestId('season-error')).toContainText('The matches entered by the club or the player could not be loaded.')
})

test('a double-header and two own entries are all listed and all counted', async ({ page }) => {
  for (const viewport of VIEWPORTS) {
    await page.unrouteAll({ behavior: 'ignoreErrors' })
    await openPlayer(page, -24, viewport)
    const rows = page.getByTestId(viewport.width < 900 ? 'match-card' : 'match-line')

    await expect(rows).toHaveCount(4)
    await expect(rows.filter({ hasText: 'Hallowfen Rovers' })).toHaveCount(2)
    await expect(rows.filter({ hasText: 'Skerraby United' })).toHaveCount(2)
    await expect(rows.filter({ hasText: 'One of several entries for this date and opponent' })).toHaveCount(4)
    await expect(page.getByTestId('season-tile-minutes')).toContainText('195')
    await expect(page.getByTestId('season-tile-appearances')).toContainText('4')
    await expect(page.getByTestId('season-source')).toContainText('Built from 4 matches. 2 confirmed by the club, 2 only reported by the player.')
    await expect(page.getByTestId('season-source')).toContainText('Entries that share a date and opponent are listed separately and each is counted.')
    await expectNoSidewaysScroll(page)
    await shot(page, `13-double-header-${viewport.name}`)
  }
})

test('the community page picker: one picked season drives the URL, the request, the heading and the totals', async ({ page }) => {
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  const calls = await installApiMocks(page)
  await page.goto('/local-players/21')
  await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
  await expect(page.getByTestId('player-season')).toContainText('This season')
  await expect(page.getByTestId('season-tile-minutes')).toContainText('61')

  await page.locator('.pc-season-pick select').selectOption('2025')

  await expect(page).toHaveURL(/\/local-players\/21\?season=2025$/)
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toBeVisible()
  await expect(page.getByTestId('season-tile-minutes')).toContainText('30')
  await expect(page.getByTestId('match-line')).toHaveCount(1)
  await expect(page.getByTestId('match-line')).toContainText('Marrowby Colts')
  await expect(page.getByTestId('player-season')).not.toContainText('This season')
  expect(calls.some((call) => call.includes('/api/players/-21/season-stats?season=2025'))).toBe(true)

  // A shared link opens on the same season.
  await page.reload()
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toBeVisible()
  await expect(page.locator('.pc-season-pick select')).toHaveValue('2025')
})

test('provider totals of another season are never shown under the picked season', async ({ page }) => {
  // Reviewer's probe: provider-linked profile, current season 2,412 minutes, one 30-minute entry in 2025/26.
  let release
  const held = new Promise((resolve) => { release = resolve })
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  await installApiMocks(page, { gate: (season) => (season === 2025 ? held : null) })
  await page.goto('/local-players/22')
  await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
  await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')

  await page.locator('.pc-season-pick select').selectOption('2025')

  // While the totals for 2025/26 are still on their way, the 2026/27 figure is not relabelled.
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toBeVisible()
  await expect(page.getByText('2,412')).toHaveCount(0)
  release()
  await expect(page.getByTestId('season-tile-minutes')).toContainText('30')
  await expect(page.getByTestId('player-season')).toHaveAttribute('data-source', 'grain')
  await expect(page.getByText('2,412')).toHaveCount(0)
})

test('an older season is not headed "This season"; self-reported facts say so', async ({ page }) => {
  await openPlayer(page, -23, VIEWPORTS[0])

  await expect(page.getByRole('heading', { name: '2024/25 Totals' })).toBeVisible()
  await expect(page.getByTestId('player-season').locator('.pc-kicker')).toHaveText('Season')
  await expect(page.getByTestId('player-facts-note')).toHaveText('Self-reported by the player')
})

test('phones show the explanation under the match cards', async ({ page }) => {
  await openPlayer(page, -12, VIEWPORTS[1])

  await expect(page.getByText("One card per match. Where the club has confirmed, the club's figures are shown.")).toBeVisible()
})

test('season tiles keep their figures inside the tile between 900 and 1100 px', async ({ page }) => {
  for (const width of [900, 960, 1024, 1099, 1100]) {
    await page.unrouteAll({ behavior: 'ignoreErrors' })
    await openPlayer(page, -15, { width, height: 900 })
    const overflow = await page.locator('[data-testid^="season-tile-"]').evaluateAll((tiles) => tiles.map((tile) => {
      const style = getComputedStyle(tile)
      const inner = tile.getBoundingClientRect().right - parseFloat(style.paddingRight) - parseFloat(style.borderRightWidth)
      const value = tile.querySelector('.pc-tile-value')
      const range = document.createRange()
      range.selectNodeContents(value)
      return Math.round(range.getBoundingClientRect().right - inner)
    }))
    expect(Math.max(...overflow), `tile text past the padding at ${width}px`).toBeLessThanOrEqual(0)
    await expectNoSidewaysScroll(page)
  }
})

// One showcase read per page, and the raw match rows only for the owner (the
// only viewer who still sees them). Vite dev runs React StrictMode, which
// mounts every effect twice, so "once" is 2 here; exact production counts are
// in logs/PCF1.request-counts.md.
for (const [label, path, id, claim] of [
  ['PlayerPage', '/players/-16', '-16', { player_api_id: -16 }],
  ['LocalPlayerPage', '/local-players/16', '-16', { local_player_id: 16 }],
]) {
  for (const viewer of ['anonymous', 'scout', 'owner']) {
    test(`${label} request cost — ${viewer}`, async ({ page }) => {
      if (viewer !== 'anonymous') await signIn(page)
      await page.clock.setFixedTime(TODAY)
      await page.setViewportSize(VIEWPORTS[0])
      const calls = await installApiMocks(page, {
        verification: { status: 'approved' },
        claims: viewer === 'owner' ? [{ id: 9, status: 'approved', relationship_type: 'player', ...claim }] : [],
      })
      await page.goto(path)
      await expect(page.getByTestId('match-line')).toHaveCount(3)
      if (viewer === 'owner') await expect(page.getByRole('button', { name: 'Add a game', exact: true })).toBeEnabled()
      await page.waitForLoadState('networkidle')

      const count = (test) => calls.filter(test).length
      const showcase = count((call) => /\/showcase$/.test(call))
      const lines = count((call) => call.includes(`/api/players/${id}/matches?view=lines`))
      const raw = count((call) => call.includes(`/api/players/${id}/matches?`) && !call.includes('view=lines'))
      expect(showcase).toBeGreaterThanOrEqual(1)
      expect(showcase).toBeLessThanOrEqual(2)
      expect(lines).toBeLessThanOrEqual(2)
      if (viewer === 'owner') expect(raw).toBeGreaterThanOrEqual(1)
      else expect(raw).toBe(0)
      expect(count((call) => call.includes('/api/scout/verification'))).toBe(0)
    })
  }
}

// ---- PCF2: nothing of one viewer is shown to the next ---------------------

const PRIVATE_EMAIL = 'private-agent@example.test'
const bearer = (route) => (route.request().headers().authorization || '').replace(/^Bearer\s+/i, '') || null

// The server adds the agent's email only for signed-in readers. `hold` delays
// the answer for one viewer so the transition can be inspected while it is pending.
async function viewerShowcase(page, id, { hold = {}, emails = {} } = {}) {
  await page.route(`**/api/players/${id}/showcase`, async (route) => {
    const token = bearer(route)
    if (hold[token ?? 'public']) await hold[token ?? 'public']
    const email = token ? (emails[token] ?? PRIVATE_EMAIL) : null
    return route.fulfill({ json: {
      player_api_id: Number(id), reel: [], verified_footage: [], ...players[id].showcase,
      profile: { ...kofiProfile, agent_name: 'Fixture Agent', ...(email ? { agent_contact_email: email } : {}) },
    } })
  })
}

// Records every moment `text` is present in the page from now on, and whether
// it was ever present AFTER it had first gone (a late answer painting it back).
async function watchForText(page, text) {
  await page.evaluate((needle) => {
    const state = { present: document.body.textContent.includes(needle), goneOnce: false, returned: false }
    window.__pcWatch = state
    new MutationObserver(() => {
      const present = document.body.textContent.includes(needle)
      if (!present) state.goneOnce = true
      else if (state.goneOnce) state.returned = true
      state.present = present
    }).observe(document.body, { childList: true, subtree: true, characterData: true })
  }, text)
}

async function changeViewer(page, token) {
  await page.evaluate(async (next) => {
    const { APIService } = await import('/src/lib/api.js')
    if (next) APIService.setUserToken(next)
    else APIService.logout()
  }, token)
}

test('logout: the signed-in-only agent email leaves the page at once, before the anonymous read answers', async ({ page }) => {
  // The reviewer's probe, reversed.
  let release
  const held = new Promise((resolve) => { release = resolve })
  await signIn(page)
  await installApiMocks(page)
  await viewerShowcase(page, '-12', { hold: { public: held } })
  await page.clock.setFixedTime(TODAY)
  await page.goto('/players/-12')
  await expect(page.getByTestId('player-facts')).toContainText(PRIVATE_EMAIL)
  await watchForText(page, PRIVATE_EMAIL)

  await changeViewer(page, null)

  // The anonymous showcase is still pending: nothing of the signed-in viewer is left.
  await expect(page.getByText(PRIVATE_EMAIL)).toHaveCount(0, { timeout: 2000 })
  await expect(page.getByTestId('player-facts')).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: 'Kofi Asante-Reid' })).toBeVisible()
  release()
  await expect(page.getByTestId('player-facts')).toContainText('Fixture Agent')
  await expect(page.getByText(PRIVATE_EMAIL)).toHaveCount(0)
  // Not at any point after it first went: no late answer painted it back.
  expect(await page.evaluate(() => window.__pcWatch)).toMatchObject({ present: false, goneOnce: true, returned: false })
})

test('a late answer for the signed-in viewer is ignored after logout', async ({ page }) => {
  // The signed-in read itself is the slow one: it answers only after the logout.
  let release
  const held = new Promise((resolve) => { release = resolve })
  await signIn(page)
  await installApiMocks(page)
  await viewerShowcase(page, '-12', { hold: { 'mock-user-token': held } })
  await page.clock.setFixedTime(TODAY)
  await page.goto('/players/-12')
  await expect(page.getByRole('heading', { level: 1, name: 'Kofi Asante-Reid' })).toBeVisible()
  await watchForText(page, PRIVATE_EMAIL)

  await changeViewer(page, null)
  await expect(page.getByTestId('player-facts')).toContainText('Fixture Agent')
  release()
  await page.waitForTimeout(500)

  await expect(page.getByText(PRIVATE_EMAIL)).toHaveCount(0)
  expect((await page.evaluate(() => window.__pcWatch)).present).toBe(false)
})

test('account switch: viewer A\'s showcase, watchlist state and open dialog never reach viewer B', async ({ page }) => {
  let release
  const held = new Promise((resolve) => { release = resolve })
  await signIn(page)
  await installApiMocks(page, { verification: { status: 'approved' } })
  await viewerShowcase(page, '-12', { hold: { 'token-b': held }, emails: { 'mock-user-token': 'agent-for-a@example.test', 'token-b': 'agent-for-b@example.test' } })
  await page.route('**/api/scout/watchlist/ids', async (route) => {
    if (bearer(route) === 'token-b') { await held; return route.fulfill({ json: { player_ids: [] } }) }
    return route.fulfill({ json: { player_ids: [-12] } })
  })
  await page.clock.setFixedTime(TODAY)
  await page.goto('/players/-12')
  await expect(page.getByTestId('player-facts')).toContainText('agent-for-a@example.test')
  await expect(page.getByRole('button', { name: 'On your watchlist' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Ask for an introduction' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await watchForText(page, 'agent-for-a@example.test')

  await changeViewer(page, 'token-b')

  // B's reads are still pending: nothing of A is on screen.
  await expect(page.getByText('agent-for-a@example.test')).toHaveCount(0, { timeout: 2000 })
  await expect(page.getByRole('button', { name: 'On your watchlist' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add to watchlist' })).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  release()
  await expect(page.getByTestId('player-facts')).toContainText('agent-for-b@example.test')
  await expect(page.getByRole('button', { name: 'Add to watchlist' })).toHaveAttribute('aria-pressed', 'false')
  expect(await page.evaluate(() => window.__pcWatch)).toMatchObject({ present: false, returned: false })
})

test('the community page drops the signed-in viewer\'s showcase on logout', async ({ page }) => {
  let release
  const held = new Promise((resolve) => { release = resolve })
  await signIn(page)
  await installApiMocks(page)
  await page.route('**/api/local-players/16/showcase', async (route) => {
    const token = bearer(route)
    if (!token) await held
    return route.fulfill({ json: {
      local_player_id: 16, reel: [], verified_footage: [], ...players['-16'].showcase,
      profile: { ...kofiProfile, agent_name: 'Fixture Agent', ...(token ? { agent_contact_email: PRIVATE_EMAIL } : {}) },
    } })
  })
  await page.clock.setFixedTime(TODAY)
  await page.goto('/local-players/16')
  await expect(page.getByTestId('player-facts')).toContainText(PRIVATE_EMAIL)
  await watchForText(page, PRIVATE_EMAIL)

  await changeViewer(page, null)

  await expect(page.getByText(PRIVATE_EMAIL)).toHaveCount(0, { timeout: 2000 })
  release()
  await expect(page.getByTestId('player-facts')).toContainText('Fixture Agent')
  expect(await page.evaluate(() => window.__pcWatch)).toMatchObject({ present: false, returned: false })
})

test('scout desk cards: watch state and an open introduction do not survive logout or an account switch', async ({ page }) => {
  let release
  const held = new Promise((resolve) => { release = resolve })
  await signIn(page)
  await page.setViewportSize(VIEWPORTS[1])
  await installApiMocks(page, { verification: { status: 'approved' } })
  await page.route('**/api/scout/watchlist/ids', async (route) => {
    if (bearer(route) === 'token-b') { await held; return route.fulfill({ json: { player_ids: [-19] } }) }
    return route.fulfill({ json: { player_ids: [-15] } })
  })
  await page.goto('/scout')
  const cards = page.getByTestId('player-card')
  const reuben = cards.filter({ hasText: 'Reuben Castellane' })
  await expect(reuben.getByRole('button', { name: 'Unwatch Reuben Castellane' })).toHaveAttribute('aria-pressed', 'true')
  await reuben.getByRole('button', { name: 'Introduce yourself to Reuben Castellane' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  // Switch to another account whose watchlist is still loading.
  await changeViewer(page, 'token-b')
  await expect(reuben.getByRole('button', { name: 'Watch Reuben Castellane' })).toHaveAttribute('aria-pressed', 'false', { timeout: 2000 })
  await expect(page.getByRole('button', { name: /^Unwatch / })).toHaveCount(0)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  release()
  await expect(cards.filter({ hasText: 'Tamsin Holloway' }).getByRole('button', { name: 'Unwatch Tamsin Holloway' })).toHaveAttribute('aria-pressed', 'true')
  await expect(reuben.getByRole('button', { name: 'Watch Reuben Castellane' })).toHaveAttribute('aria-pressed', 'false')

  // Scout -> logout: nothing is marked as watched, the header count is gone.
  await changeViewer(page, null)
  await expect(page.getByRole('button', { name: /^Unwatch / })).toHaveCount(0, { timeout: 2000 })
  await expect(cards.filter({ hasText: 'Tamsin Holloway' }).getByRole('button', { name: 'Watch Tamsin Holloway' })).toHaveAttribute('aria-pressed', 'false')
})

// ---- PCF2: a failed season-totals read is not an empty season --------------

test('provider totals fail on first load: an error with a retry, totals built from the match log, never "No matches"', async ({ page }) => {
  // The reviewer's probe, reversed: season-stats 500, per-match rows fine, no club/self entries.
  let status = 500
  await installApiMocks(page, { seasonStatsStatus: () => status })
  await page.route('**/api/players/42/matches?view=lines', (route) => route.fulfill({ json: { view: 'lines', seasons: [], truncated: false } }))
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  await page.goto('/players/42')
  await expect(page.getByTestId('player-hero')).toBeVisible()

  const error = page.getByTestId('season-error')
  await expect(error).toContainText('The season totals could not be loaded.')
  await expect(page.getByText('No matches recorded yet')).toHaveCount(0)
  await expect(page.getByText(/Nothing has been entered/)).toHaveCount(0)
  // The successful per-match read still gives the season its figures, as on main.
  await expect(page.getByTestId('season-tile-minutes')).toContainText('90')
  await expect(page.getByTestId('season-source')).toContainText('Totals are built from the 1 match in the public match log.')
  await expect(page.getByRole('tab', { name: 'Match Log' })).toBeVisible()
  await shot(page, '15-totals-read-failed-1440')

  status = 200
  await error.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')
  await expect(page.getByTestId('season-error')).toHaveCount(0)
})

test('provider matches beside an empty grain and empty totals: the season is not called empty', async ({ page }) => {
  await installApiMocks(page)
  await page.route('**/api/players/42/season-stats**', (route) => route.fulfill({ json: { season: '2026/2027', appearances: 0, minutes: 0, goals: 0, assists: 0, source: 'none', clubs: [] } }))
  await page.route('**/api/players/42/matches?view=lines', (route) => route.fulfill({ json: { view: 'lines', seasons: [], truncated: false } }))
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  await page.goto('/players/42')

  await expect(page.getByTestId('player-season')).toHaveAttribute('data-source', 'provider')
  await expect(page.getByTestId('season-tile-minutes')).toContainText('90')
  await expect(page.getByTestId('season-empty')).toHaveCount(0)
  await expect(page.getByTestId('season-error')).toHaveCount(0)
})

test('provider totals fail on a refresh: the last good totals stay, with a retry', async ({ page }) => {
  let status = 200
  await signIn(page)
  await installApiMocks(page, {
    seasonStatsStatus: () => status,
    claims: [{ id: 9, status: 'approved', relationship_type: 'player', player_api_id: 42 }],
  })
  await page.route('**/api/players/42/matches', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    return route.fulfill({ json: { match: { id: 123, ...route.request().postDataJSON(), season: 2026, source: 'self', status: 'self_reported' } } })
  })
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  await page.goto('/players/42')
  await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')

  // An owner's change refreshes the totals; that refresh fails.
  await page.getByRole('button', { name: 'Add a game', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Match date').fill('2026-09-28')
  await dialog.getByLabel('Opponent', { exact: true }).fill('Fixture Town')
  status = 500
  await dialog.getByRole('button', { name: 'Add game', exact: true }).click()

  await expect(page.getByTestId('season-error')).toContainText('The latest figures could not be loaded. Showing what was loaded before.')
  await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')
  await expect(page.getByText('No matches recorded yet')).toHaveCount(0)

  status = 200
  await page.getByTestId('season-error').getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByTestId('season-error')).toHaveCount(0)
  await expect(page.getByTestId('season-tile-minutes')).toContainText('2,412')
})

test('the community page: a failed totals read with nothing else to show is an error, not an empty season', async ({ page }) => {
  let status = 500
  await installApiMocks(page, { seasonStatsStatus: () => status })
  await page.clock.setFixedTime(TODAY)
  await page.setViewportSize(VIEWPORTS[0])
  await page.goto('/local-players/14')
  await expect(page.getByRole('heading', { level: 1, name: 'Olu Adeyemi-Clarke' })).toBeVisible()

  await expect(page.getByTestId('season-error')).toContainText('The season could not be loaded.')
  await expect(page.getByTestId('player-season')).toHaveAttribute('data-source', 'error')
  await expect(page.getByText('No matches recorded yet')).toHaveCount(0)

  status = 200
  await page.getByTestId('season-error').getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByTestId('season-empty')).toContainText('No matches recorded yet')
  await expect(page.getByTestId('season-error')).toHaveCount(0)
})

// Before/after proof: replays responses captured read-only from staging for one
// player, with the match lines produced by the real server merge function.
// Runs only when PC_REPLAY_FILE points at such a capture.
test.describe('replay of a captured staging player', () => {
  test.skip(!process.env.PC_REPLAY_FILE, 'no capture supplied')
  test.use({ ignoreHTTPSErrors: true })

  for (const viewport of VIEWPORTS) {
    test(`after — ${viewport.name}px`, async ({ page }) => {
      const replay = JSON.parse(fs.readFileSync(process.env.PC_REPLAY_FILE, 'utf8'))
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.route('**/api/**', (route) => {
        const url = new URL(route.request().url())
        if (url.pathname.startsWith('/api/media/')) return route.continue({ url: `${replay.origin}${url.pathname}` })
        const hit = replay.captured[url.pathname + url.search] || replay.captured[url.pathname]
        return hit ? route.fulfill({ status: hit.status, json: hit.body }) : route.fulfill({ json: {} })
      })
      await page.goto(replay.kofiPath)
      await expect(page.getByTestId('player-hero')).toBeVisible()
      await expect(page.getByTestId('match-lines')).toBeVisible()
      await expect(page.getByTestId(viewport.width < 900 ? 'match-card' : 'match-line')).toHaveCount(replay.expectedLines)
      await page.evaluate(() => document.fonts.ready)
      await page.waitForLoadState('networkidle')
      await shot(page, `after-staging-data-kofi-${viewport.name}`)
    })
  }
})
