import { expect, test } from '@playwright/test'

const seasons = {
  current_season: 2026,
  bounds: { min: 2025, max: 2026 },
  seasons: [
    { season: 2026, label: '2026/27', has_rollup: true, is_current: true },
    { season: 2025, label: '2025/26', has_rollup: true, is_current: false },
  ],
}

const selfProvenance = {
  source_category: 'self',
  source_label: 'Self-reported',
  primary_source: 'user',
}

const clubProvenance = {
  source_category: 'club',
  source_label: 'Club-confirmed',
  primary_source: 'club',
}

const emptyShowcase = {
  claim_status: 'claimed',
  reel: [],
  photos: [],
  affiliations: [],
  verified_footage: [],
  profile: null,
}

function json404(route) {
  return route.fulfill({
    status: 404,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'Not found' }),
  })
}

test('approved player owner adds, edits, and deletes a self-reported game', async ({ page }) => {
  const createBodies = []
  const updateBodies = []
  const deletePaths = []
  let savedMatch = null

  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-player-owner-token')
    localStorage.setItem('academy_watch_display_name', 'Ava Forward')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.pathname === '/api/seasons') return route.fulfill({ json: seasons })
    if (url.pathname === '/api/players/42/profile') {
      return route.fulfill({ json: { name: 'Ava Forward', position: 'Forward', age: 20, nationality: 'England' } })
    }
    if (url.pathname === '/api/players/42/stats') {
      return route.fulfill({
        json: {
          matches: [],
          summary: { season: 2026 },
          provenance: selfProvenance,
        },
      })
    }
    if (url.pathname === '/api/players/42/season-stats') {
      return route.fulfill({
        json: {
          season: '2026/2027',
          appearances: savedMatch ? 1 : 0,
          minutes: savedMatch?.minutes || 0,
          goals: savedMatch?.goals || 0,
          assists: savedMatch?.assists || 0,
          provenance: selfProvenance,
        },
      })
    }
    if (url.pathname === '/api/players/42/journey/map') {
      return route.fulfill({ json: { entries: [], nodes: [], edges: [] } })
    }
    if (url.pathname === '/api/players/42/showcase') return route.fulfill({ json: emptyShowcase })
    if (url.pathname === '/api/me/claims') {
      return route.fulfill({
        json: {
          claims: [{ id: 71, player_api_id: 42, relationship_type: 'player', status: 'approved' }],
        },
      })
    }
    if (url.pathname === '/api/players/42/matches' && request.method() === 'GET') {
      return route.fulfill({ json: { matches: savedMatch ? [savedMatch] : [], total: savedMatch ? 1 : 0, page: 1, per_page: 50 } })
    }
    if (url.pathname === '/api/players/42/matches' && request.method() === 'POST') {
      const body = request.postDataJSON()
      createBodies.push(body)
      savedMatch = {
        id: 901,
        player_api_id: 42,
        season: 2026,
        ...body,
        source: 'self',
        status: 'self_reported',
        editable: true,
        provenance: selfProvenance,
      }
      return route.fulfill({
        json: {
          match: savedMatch,
          season_stats: { season: 2026, appearances: 1, minutes: body.minutes, goals: body.goals, assists: body.assists, provenance: selfProvenance },
        },
      })
    }
    if (url.pathname === '/api/players/42/matches/901' && request.method() === 'PATCH') {
      const body = request.postDataJSON()
      updateBodies.push(body)
      savedMatch = { ...savedMatch, ...body }
      return route.fulfill({
        json: {
          match: savedMatch,
          season_stats: { season: 2026, appearances: 1, minutes: body.minutes, goals: body.goals, assists: body.assists, provenance: selfProvenance },
        },
      })
    }
    if (url.pathname === '/api/players/42/matches/901' && request.method() === 'DELETE') {
      deletePaths.push(url.pathname)
      savedMatch = null
      return route.fulfill({ json: { deleted: true, season: 2026, rollup_refreshed: true } })
    }

    return route.fulfill({ json: {} })
  })

  await page.goto('/players/42')
  await page.getByRole('button', { name: 'Add a game', exact: true }).click()

  let dialog = page.getByRole('dialog')
  await dialog.getByLabel('Match date').fill('2026-08-30')
  await dialog.getByLabel('Competition').fill('National Academy League')
  await dialog.getByLabel('Opponent').fill('North City')
  await dialog.getByLabel('Score for').fill('2')
  await dialog.getByLabel('Score against').fill('1')
  await dialog.getByLabel('Minutes').fill('90')
  await dialog.getByLabel('Goals').fill('1')
  await dialog.getByLabel('Assists').fill('1')
  await dialog.getByLabel('Yellow cards').fill('0')
  await dialog.getByLabel('Red cards').fill('0')
  await dialog.getByLabel('Note (optional)').fill('Strong run behind the back line.')
  await dialog.getByRole('button', { name: 'Add game', exact: true }).click()

  await expect.poll(() => createBodies.length).toBe(1)
  const gameRow = page.locator('article[role="listitem"]').filter({ hasText: 'North City' })
  await expect(gameRow).toBeVisible()
  await expect(gameRow.getByText('Self-reported')).toBeVisible()

  await page.getByRole('button', { name: 'Edit game against North City' }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByLabel('Goals').fill('2')
  await dialog.getByRole('button', { name: 'Save changes' }).click()
  await expect.poll(() => updateBodies.length).toBe(1)
  await expect(gameRow.getByText('2', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Delete game against North City' }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Delete game', exact: true }).click()
  await expect.poll(() => deletePaths).toEqual(['/api/players/42/matches/901'])
  await expect(gameRow).toHaveCount(0)

  const expectedCreate = {
    match_date: '2026-08-30',
    competition: 'National Academy League',
    opponent: 'North City',
    home_away: 'home',
    result_for: 2,
    result_against: 1,
    minutes: 90,
    goals: 1,
    assists: 1,
    yellows: 0,
    reds: 0,
    saves: null,
    goals_conceded: null,
    note: 'Strong run behind the back line.',
  }
  expect(createBodies[0]).toEqual(expectedCreate)
  expect(updateBodies[0]).toEqual({ ...expectedCreate, goals: 2 })
})

test('approved local player uses the reserved negative id for totals and games', async ({ page }) => {
  const signedRequests = []

  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-local-owner-token')
    localStorage.setItem('academy_watch_display_name', 'Local Seven')
  })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.includes('/players/-7/')) signedRequests.push(url)

    if (url.pathname === '/api/local-players/7') {
      return route.fulfill({
        json: {
          player: {
            id: 7,
            api_player_id: -7,
            display_name: 'Local Seven',
            status: 'approved',
            position: 'Midfielder',
            birth_year: 2005,
            club_name: 'Harbour Academy',
          },
        },
      })
    }
    if (url.pathname === '/api/local-players/7/showcase') return route.fulfill({ json: emptyShowcase })
    if (url.pathname === '/api/me/claims') {
      return route.fulfill({ json: { claims: [{ id: 72, local_player_id: 7, relationship_type: 'player', status: 'approved' }] } })
    }
    if (url.pathname === '/api/players/-7/season-stats') {
      return route.fulfill({
        json: { season: '2026/2027', appearances: 1, minutes: 80, goals: 1, assists: 0, provenance: selfProvenance },
      })
    }
    if (url.pathname === '/api/players/-7/matches') {
      return route.fulfill({
        json: {
          matches: [{
            id: 77,
            player_api_id: -7,
            season: 2026,
            match_date: '2026-08-20',
            competition: 'Kanto Academy League',
            opponent: 'Eastside',
            home_away: 'away',
            result_for: 1,
            result_against: 0,
            minutes: 80,
            goals: 1,
            assists: 0,
            yellows: 0,
            reds: 0,
            saves: null,
            goals_conceded: null,
            note: null,
            source: 'self',
            status: 'self_reported',
            editable: true,
            provenance: selfProvenance,
          }],
          total: 1,
          page: 1,
          per_page: 50,
        },
      })
    }

    return route.fulfill({ json: {} })
  })

  await page.goto('/local-players/7')
  await expect(page.getByRole('heading', { name: 'Local Seven', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '2026/27 Totals' })).toBeVisible()
  await expect(page.getByText('vs Eastside')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add a game', exact: true })).toBeVisible()
  await expect(page.locator('[data-provenance-source="self"]').first()).toBeVisible()
  await expect.poll(() => signedRequests.some((url) => (
    url.pathname === '/api/players/-7/matches' && !url.searchParams.has('season')
  ))).toBe(true)
  expect(signedRequests.some((url) => url.pathname === '/api/players/-7/season-stats')).toBe(true)
})

test('public minor receives only the neutral missing state', async ({ page }) => {
  const matchRequests = []

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/local-players/8') return json404(route)
    if (url.pathname === '/api/players/-8/season-stats') return json404(route)
    if (url.pathname === '/api/players/-8/matches') {
      matchRequests.push(url.pathname)
      return json404(route)
    }
    return route.fulfill({ json: {} })
  })

  await page.goto('/local-players/8')
  await expect(page.getByRole('heading', { name: "This profile doesn't exist or isn't public yet" })).toBeVisible()
  await expect(page.getByText('Games', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Add a game', exact: true })).toHaveCount(0)
  expect(matchRequests).toEqual([])
})

test('Scout source filter reaches browse, boards, signed compare, and CSV while rendering chips', async ({ page }) => {
  const playerUrls = []
  const boardUrls = []
  const compareUrls = []
  const csvUrls = []
  const scoutPlayers = [
    {
      id: -7,
      player_id: -7,
      player_name: 'Local Seven',
      nationality: 'Japan',
      age: 21,
      position: 'Midfielder',
      status: 'academy',
      primary_team_name: 'Harbour Academy',
      appearances: 4,
      minutes_played: 320,
      goals: 2,
      assists: 3,
      avg_rating: 7.4,
      contributions_per90: 1.41,
      recent_form: [],
      provenance: clubProvenance,
    },
    {
      id: 42,
      player_id: 42,
      player_name: 'Ava Forward',
      nationality: 'England',
      age: 20,
      position: 'Attacker',
      status: 'on_loan',
      primary_team_name: 'North Academy',
      loan_team_name: 'Riverside FC',
      appearances: 5,
      minutes_played: 400,
      goals: 4,
      assists: 1,
      avg_rating: 7.6,
      contributions_per90: 1.13,
      recent_form: [],
      provenance: clubProvenance,
    },
  ]

  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-scout-token')
    localStorage.setItem('academy_watch_display_name', 'Mock Scout')
  })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/seasons') return route.fulfill({ json: seasons })
    if (url.pathname === '/api/scout/watchlist/ids') return route.fulfill({ json: { player_ids: [] } })
    if (url.pathname === '/api/scout/players') {
      playerUrls.push(url)
      return route.fulfill({ json: { season: 2026, players: scoutPlayers, total: 2, total_pages: 1 } })
    }
    if (url.pathname === '/api/scout/leaderboards') {
      boardUrls.push(url)
      return route.fulfill({
        json: {
          season: 2026,
          leaderboards: {
            top_scorers: [scoutPlayers[1]],
            top_assists: [scoutPlayers[0]],
            most_minutes: [scoutPlayers[1]],
            best_per90: [scoutPlayers[0]],
          },
        },
      })
    }
    if (url.pathname === '/api/scout/compare') {
      compareUrls.push(url)
      return route.fulfill({
        json: {
          season: 2026,
          players: scoutPlayers.map((player) => ({
            profile: {
              player_id: player.player_id,
              player_name: player.player_name,
              position: player.position,
              age: player.age,
              status: player.status,
              primary_team_name: player.primary_team_name,
              loan_team_name: player.loan_team_name,
            },
            totals: {
              appearances: player.appearances,
              minutes_played: player.minutes_played,
              goals: player.goals,
              assists: player.assists,
              avg_rating: player.avg_rating,
            },
            per90: { goal_contributions: player.contributions_per90 },
            career: {},
            availability: {},
            provenance: player.provenance,
          })),
        },
      })
    }
    if (url.pathname === '/api/scout/export.csv') {
      csvUrls.push(url)
      return route.fulfill({ status: 200, contentType: 'text/csv', body: 'player,source\nLocal Seven,club\n' })
    }
    return route.fulfill({ json: {} })
  })

  await page.goto('/scout')
  await page.getByRole('combobox', { name: 'Filter by stats source' }).click()
  await page.getByRole('option', { name: 'Club-confirmed' }).click()

  await expect(page).toHaveURL(/(?:\?|&)source=club(?:&|$)/)
  await expect.poll(() => playerUrls.some((url) => url.searchParams.get('source') === 'club')).toBe(true)
  await expect.poll(() => boardUrls.some((url) => url.searchParams.get('source') === 'club')).toBe(true)
  await expect(page.locator('[data-provenance-source="club"]').first()).toBeVisible()

  await page.getByLabel('Compare Local Seven').click()
  await page.getByLabel('Compare Ava Forward').click()
  await page.getByRole('button', { name: 'Compare', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Player Comparison/ })).toBeVisible()
  await expect.poll(() => compareUrls.some((url) => (
    url.searchParams.get('source') === 'club' && url.searchParams.get('ids') === '-7,42'
  ))).toBe(true)

  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  await expect.poll(() => csvUrls.some((url) => url.searchParams.get('source') === 'club')).toBe(true)
})

test('club manager records both video-linked and no-video results with roster stats', async ({ page }) => {
  const resultBodies = []
  const programClaim = {
    id: 301,
    status: 'approved',
    relationship_type: 'club_official',
    program: {
      id: 7,
      name: 'Harbour Academy',
      slug: 'harbour-academy',
      platform_status: 'approved',
      country: 'Japan',
      region: 'Kanto',
    },
  }
  const roster = {
    members: [
      {
        id: 51,
        program_id: 7,
        available: true,
        subject_type: 'tracked',
        player_api_id: 7001,
        local_player_id: null,
        display_name: 'Mina Sato',
        position: 'Midfielder',
        is_minor: false,
      },
      {
        id: 52,
        program_id: 7,
        available: true,
        subject_type: 'local',
        player_api_id: -11,
        local_player_id: 11,
        display_name: 'Kai Mori',
        position: 'Goalkeeper',
        is_minor: false,
      },
    ],
    count: 2,
  }
  const fullMatch = {
    id: 41,
    club_program_id: 7,
    opponent_name: 'Riverside Juniors',
    match_date: '2026-08-24',
    competition: 'Kanto Academy League',
    home_away: 'away',
    status: 'created',
    processing_request_status: null,
    roster: [
      { id: 61, club_roster_member_id: 51, player_name: 'Mina Sato', jersey_number: 8, position: 'Midfielder' },
      { id: 62, club_roster_member_id: 52, player_name: 'Kai Mori', jersey_number: 1, position: 'Goalkeeper' },
    ],
  }

  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-club-manager-token')
    localStorage.setItem('academy_watch_display_name', 'Club Manager')
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname === '/api/me/club-claims') return route.fulfill({ json: { claims: [] } })
    if (url.pathname === '/api/me/club') return route.fulfill({ json: { clubs: [] } })
    if (url.pathname === '/api/funding/claims/me') return route.fulfill({ json: { claims: [programClaim] } })
    if (url.pathname === '/api/club/7/roster') return route.fulfill({ json: roster })
    if (url.pathname === '/api/club/7/matches') {
      const { roster: _roster, ...summary } = fullMatch
      return route.fulfill({ json: { matches: [summary], total: 1 } })
    }
    if (url.pathname === '/api/club/7/matches/41') return route.fulfill({ json: fullMatch })
    if (url.pathname === '/api/club/7/results' && request.method() === 'POST') {
      const body = request.postDataJSON()
      resultBodies.push(body)
      return route.fulfill({
        json: {
          result: {
            video_match_id: body.video_match_id,
            match_date: body.match_date,
            opponent: body.opponent,
            competition: body.competition,
            home_away: body.home_away,
            result_for: body.result_for,
            result_against: body.result_against,
          },
          matches: body.entries.map((entry, index) => ({
            id: 1000 + index,
            player_api_id: entry.club_roster_member_id === 51 ? 7001 : -11,
            ...entry,
            source: 'club',
            status: 'club_confirmed',
          })),
          season_stats_by_player: {
            7001: { season: 2026, appearances: 4, minutes: 320, goals: 2, assists: 2, yellows: 1, reds: 0 },
            '-11': { season: 2026, appearances: 4, minutes: 320, goals: 0, assists: 0, yellows: 0, reds: 0, saves: 12, goals_conceded: 3 },
          },
        },
      })
    }
    return route.fulfill({ json: {} })
  })

  await page.goto('/my-club')
  await page.getByRole('tab', { name: 'Matches & reports' }).click()
  await page.getByRole('button', { name: 'Record result for Riverside Juniors' }).click()

  let dialog = page.getByRole('dialog')
  await dialog.getByLabel('Our score').fill('2')
  await dialog.getByLabel('Their score').fill('1')
  const mina = dialog.locator('article').filter({ hasText: 'Mina Sato' })
  await mina.getByLabel('Minutes').fill('90')
  await mina.getByLabel('Goals').fill('1')
  await mina.getByLabel('Assists').fill('1')
  await mina.getByLabel('Yellows').fill('1')
  await mina.getByLabel('Note').fill("Captain's goal")
  const kai = dialog.locator('article').filter({ hasText: 'Kai Mori' })
  await kai.getByLabel('Minutes').fill('90')
  await kai.getByLabel('Saves').fill('4')
  await kai.getByLabel('Goals conceded').fill('1')
  await dialog.getByRole('button', { name: 'Save result' }).click()

  await expect.poll(() => resultBodies.length).toBe(1)
  await expect(dialog.getByRole('heading', { name: 'Season totals updated' })).toBeVisible()
  const minaTotals = dialog.locator('article').filter({ hasText: 'Mina Sato' })
  const kaiTotals = dialog.locator('article').filter({ hasText: 'Kai Mori' })
  await expect(minaTotals.getByText('320', { exact: true })).toBeVisible()
  await expect(minaTotals.getByText('2', { exact: true }).first()).toBeVisible()
  await expect(kaiTotals.getByText('12', { exact: true })).toBeVisible()
  await expect(kaiTotals.getByText('3', { exact: true })).toBeVisible()
  await dialog.locator('[data-slot="dialog-footer"]').getByRole('button', { name: 'Close' }).click()

  await page.getByRole('button', { name: 'Record result for Riverside Juniors' }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Our score')).toHaveValue('2')
  await expect(dialog.locator('article').filter({ hasText: 'Mina Sato' }).getByLabel('Goals')).toHaveValue('1')
  await expect(dialog.locator('article').filter({ hasText: 'Kai Mori' }).getByLabel('Saves')).toHaveValue('4')
  await dialog.getByRole('button', { name: 'Cancel' }).click()

  await page.getByRole('button', { name: 'Record result without video' }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByLabel('Match date').fill('2026-08-31')
  await dialog.getByLabel('Opponent').fill('Bay United')
  await dialog.getByLabel('Competition').fill('Harbour Cup')
  await dialog.getByLabel('Our score').fill('3')
  await dialog.getByLabel('Their score').fill('0')
  await dialog.getByLabel('Include Mina Sato in result').check()
  await dialog.getByLabel('Include Kai Mori in result').check()
  await dialog.getByRole('button', { name: 'Save result' }).click()
  await expect.poll(() => resultBodies.length).toBe(2)

  expect(resultBodies[0]).toEqual({
    video_match_id: 41,
    match_date: '2026-08-24',
    opponent: 'Riverside Juniors',
    competition: 'Kanto Academy League',
    home_away: 'away',
    result_for: 2,
    result_against: 1,
    entries: [
      { club_roster_member_id: 51, minutes: 90, goals: 1, assists: 1, yellows: 1, reds: 0, saves: null, goals_conceded: null, note: "Captain's goal" },
      { club_roster_member_id: 52, minutes: 90, goals: 0, assists: 0, yellows: 0, reds: 0, saves: 4, goals_conceded: 1, note: null },
    ],
  })
  expect(resultBodies[1]).toEqual({
    video_match_id: null,
    match_date: '2026-08-31',
    opponent: 'Bay United',
    competition: 'Harbour Cup',
    home_away: 'home',
    result_for: 3,
    result_against: 0,
    entries: [
      { club_roster_member_id: 51, minutes: 0, goals: 0, assists: 0, yellows: 0, reds: 0, saves: null, goals_conceded: null, note: null },
      { club_roster_member_id: 52, minutes: 0, goals: 0, assists: 0, yellows: 0, reds: 0, saves: null, goals_conceded: null, note: null },
    ],
  })
})
