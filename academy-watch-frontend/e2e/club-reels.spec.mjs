import { expect, test } from '@playwright/test'

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
  members: [{
    id: 51,
    program_id: 7,
    available: true,
    subject_type: 'tracked',
    player_api_id: 7001,
    local_player_id: null,
    display_name: 'Mina Sato',
    position: 'Midfielder',
    is_minor: false,
    role: null,
    note: null,
    created_at: '2026-08-20T10:00:00Z',
  }],
  count: 1,
}

function matchPayload(id = 41) {
  return {
    id,
    club_program_id: 7,
    opponent_name: 'Riverside Juniors',
    match_date: '2026-08-24',
    competition: 'Kanto Academy League',
    our_kit_color: '#0e7490',
    opponent_kit_color: '#e11d48',
    capture_meta: {},
    duration_s: 5400,
    kickoff_s: 12,
    halftime_s: 2712,
    second_half_kickoff_s: 2800,
    our_team_cluster: 0,
    status: 'finalized',
    processing_request_status: 'requested',
    job: { status: 'completed', stage: 'complete', progress: 100 },
    roster: [{
      id: 61,
      video_match_id: id,
      player_name: 'Mina Sato',
      jersey_number: 8,
      position: 'Midfielder',
      tracked_player_id: 1,
      club_roster_member_id: 51,
    }],
  }
}

const reel = {
  players: [{
    roster_entry_id: 61,
    player_name: 'Mina Sato',
    jersey_number: 8,
    position: 'Midfielder',
    team_cluster: 0,
    tracklet_ids: [91],
    chains: [{ tracklet_id: 91, confidence: 'high', contaminated: false }],
    number_mismatch: false,
    total_visible_s: 12,
    confidence: 'high',
    windows: [{ start_s: 20, end_s: 32, tracklet_id: 91, rank: 1 }],
  }],
  unassigned: { count: 3, visible_s: 19 },
  team_overview: {
    clusters: [{ cluster: 0, is_ours: true, players: [61], total_visible_s: 12 }],
    qwen_analysis_present: false,
  },
}

async function installClubMocks(page, { denyReel = false, reelResponses = [reel] } = {}) {
  const adminMediaHeaders = []
  let reelRequestCount = 0
  let tokenRequestCount = 0
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
      const { roster: _matchRoster, ...summary } = matchPayload()
      return route.fulfill({ json: { matches: [summary], total: 1 } })
    }
    if (url.pathname === '/api/club/7/matches/41') return route.fulfill({ json: matchPayload() })
    if (url.pathname === '/api/club/7/matches/41/reel') {
      const response = reelResponses[Math.min(reelRequestCount, reelResponses.length - 1)]
      reelRequestCount += 1
      return denyReel
        ? route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'Match not found' }) })
        : route.fulfill({ json: response })
    }
    if (url.pathname === '/api/club/7/matches/41/media-token') {
      tokenRequestCount += 1
      return denyReel
        ? route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'Match not found' }) })
        : route.fulfill({ json: { token: 'scoped-club-media-token', expires_in: 1800 } })
    }
    if (url.pathname.startsWith('/api/admin/video/')) {
      adminMediaHeaders.push(request.headers())
      if (url.pathname.endsWith('/crops')) return route.fulfill({ json: { crops: [] } })
      if (url.pathname.endsWith('/bbox-track')) return route.fulfill({ json: { boxes: [], available: false } })
      return route.fulfill({ status: 404, body: '' })
    }
    return route.fulfill({ json: {} })
  })
  return {
    adminMediaHeaders,
    reelRequestCount: () => reelRequestCount,
    tokenRequestCount: () => tokenRequestCount,
  }
}

test('club manager opens a read-only player reel without admin credentials', async ({ page }) => {
  const requests = await installClubMocks(page, {
    reelResponses: [reel, { ...reel, players: [] }],
  })
  await page.goto('/my-club')
  await page.getByRole('tab', { name: 'Matches & reports' }).click()
  await page.getByRole('button', { name: 'View player reels' }).click()

  await expect(page.getByRole('heading', { name: 'Player reels' }).last()).toBeVisible()
  await expect(page.getByText('#8 Mina Sato')).toBeVisible()
  await expect(page.getByRole('button', { name: /Verify identity/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Unbind/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Not a player/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Run AI analysis/i })).toHaveCount(0)
  await expect.poll(() => requests.adminMediaHeaders.length).toBeGreaterThan(0)
  expect(requests.adminMediaHeaders.every((headers) => !headers['x-api-key'] && !headers['x-admin-key'])).toBe(true)

  await page.screenshot({ path: 'test-results/club-reels-allowed.png', fullPage: true })

  await page.getByRole('button', { name: 'Hide player reels' }).click()
  await page.getByRole('button', { name: 'View player reels' }).click()
  await expect.poll(requests.reelRequestCount).toBe(2)
  await expect.poll(requests.tokenRequestCount).toBe(2)
  await expect(page.getByText('No player reels yet — bind identities in Tag review below.')).toBeVisible()
  await expect(page.getByText('#8 Mina Sato')).toHaveCount(0)
})

test('foreign reel denial renders the same neutral unavailable state', async ({ page }) => {
  await installClubMocks(page, { denyReel: true })
  await page.goto('/my-club')
  await page.getByRole('tab', { name: 'Matches & reports' }).click()
  await page.getByRole('button', { name: 'View player reels' }).click()

  await expect(page.getByText('Player reels are not available for this match.')).toBeVisible()
  await expect(page.getByText('Match not found')).toHaveCount(0)
  await page.screenshot({ path: 'test-results/club-reels-denied.png', fullPage: true })
})
