import { expect, test } from '@playwright/test'

const SYNTHETIC_BRIEF = 'Maintain wide support before receiving\nRecover inside after possession changes.'
const SYNTHETIC_BRIEF_HASH = '93c166d205e6ea0b4e1984af522912598458a6329bf60be454b0d5c93d4cb53a'

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
    brief: {
      body: SYNTHETIC_BRIEF,
      updated_at: '2026-09-03T09:15:00Z',
      hash: SYNTHETIC_BRIEF_HASH,
    },
    created_at: '2026-08-20T10:00:00Z',
  }],
  count: 1,
  system_brief: { body: 'Synthetic compact possession structure.', updated_at: '2026-09-03T09:10:00Z', hash: 'system-hash' },
}

const qwenAnalysis = {
  match_summary: 'Harbour build through midfield in the sampled windows.',
  team_analysis: [],
  player_notes: [{
    kit_color: 'teal',
    jersey_number: 8,
    observations: ['Offers a passing option.', 'Turns into the open channel.'],
    evidence: [
      { t: 21.25, box: [180, 90, 310, 430], iou: 0.72 },
      { t: 31.5, box: [210, 100, 340, 440], iou: 0.66 },
    ],
    read_model: 'qwen3-vl:8b',
    brief_checks: [{
      expectation_index: 1,
      brief_hash: SYNTHETIC_BRIEF_HASH,
      verdict: 'evidence_found',
      t: 21.25,
      box: [180, 90, 310, 430],
      iou: 0.72,
    }, {
      expectation_index: 2,
      brief_hash: SYNTHETIC_BRIEF_HASH,
      verdict: 'no_evidence',
    }],
  }],
  window_captions: [{
    roster_entry_id: 61,
    tracklet_id: 91,
    start_s: 20,
    end_s: 24,
    caption: 'Checks into space before receiving.',
    player_visible: true,
    action_type: 'off_ball_move',
    visible_pitch_zone: 'central',
    grounded: true,
    box_t: 21.25,
    box: [180, 90, 310, 430],
    evidence_iou: 0.72,
    caption_model: 'qwen3-vl:8b',
  }, {
    roster_entry_id: 61,
    tracklet_id: 92,
    start_s: 30,
    end_s: 34,
    caption: 'Unsupported claim that must be withheld.',
    player_visible: false,
    action_type: null,
    visible_pitch_zone: null,
    grounded: false,
    box_t: null,
    box: null,
    evidence_iou: null,
    caption_model: 'qwen3-vl:8b',
  }],
  honest_limits: ['Sampled frames cannot establish what happened between samples.'],
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
    capture_meta: { qwen_analysis: qwenAnalysis },
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
    tracklet_ids: [91, 92],
    chains: [
      { tracklet_id: 91, confidence: 'high', contaminated: false },
      { tracklet_id: 92, confidence: 'high', contaminated: false },
    ],
    number_mismatch: false,
    total_visible_s: 12,
    confidence: 'high',
    windows: [
      { start_s: 20, end_s: 24, tracklet_id: 91, rank: 1 },
      { start_s: 30, end_s: 34, tracklet_id: 92, rank: 2 },
    ],
  }],
  unassigned: { count: 3, visible_s: 19 },
  team_overview: {
    clusters: [{ cluster: 0, is_ours: true, players: [61], total_visible_s: 12 }],
    qwen_analysis_present: true,
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
        : route.fulfill({ json: { token: null, expires_in: 1800 } })
    }
    if (url.pathname.startsWith('/api/admin/video/')) {
      adminMediaHeaders.push(request.headers())
      if (url.pathname.endsWith('/crops')) return route.fulfill({ json: { crops: [] } })
      if (url.pathname.endsWith('/bbox-track')) return route.fulfill({ json: { boxes: [[20, 180, 90, 310, 430]], available: true } })
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

async function installAdminMocks(page) {
  const matchPayloads = []
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-admin-token')
    localStorage.setItem('academy_watch_is_admin', 'true')
    localStorage.setItem('academy_watch_admin_key', 'mock-admin-key')
    localStorage.setItem('academy_watch_display_name', 'Admin Reviewer')
  })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/admin/auth-check') return route.fulfill({ json: { ok: true } })
    if (url.pathname === '/api/admin/video/matches/41') {
      const payload = matchPayload()
      matchPayloads.push(payload)
      return route.fulfill({ json: payload })
    }
    if (url.pathname === '/api/admin/video/matches/41/tracklets') return route.fulfill({ json: { tracklets: [] } })
    if (url.pathname === '/api/admin/video/matches/41/reel') return route.fulfill({ json: reel })
    if (url.pathname === '/api/admin/video/matches/41/report') return route.fulfill({ json: { reports: [] } })
    if (url.pathname === '/api/admin/video/matches/41/accuracy') {
      return route.fulfill({
        json: {
          accuracy: {
            reviewed: 0,
            chains_total: 0,
            auto_tag_precision: null,
            number_read_accuracy: null,
            confirmed: 0,
            reassigned: 0,
            dismissed: 0,
            splits: 0,
            unreviewed: 0,
          },
          recalibration: { suggestions: [] },
        },
      })
    }
    if (url.pathname === '/api/admin/video/matches/41/media-token') return route.fulfill({ json: { token: null, expires_in: 1800 } })
    if (url.pathname.endsWith('/crops')) return route.fulfill({ json: { crops: [] } })
    if (url.pathname.endsWith('/bbox-track')) return route.fulfill({ json: { boxes: [[20, 180, 90, 310, 430]], available: true } })
    return route.fulfill({ json: {} })
  })
  return { matchPayloads }
}

async function expectVerifiedAndWithheldReel(page, screenshotPaths) {
  await page.getByRole('button', { name: /#8 Mina Sato/ }).click()

  await expect(page.getByText('Checks into space before receiving.')).toBeVisible()
  await expect(page.getByText('verified on player').last()).toBeVisible()
  await expect(page.getByLabel('checked against tracking at t=21.25s (overlap 0.72)').last()).toBeVisible()
  await expect(page.getByText('box follows this player (1 detections)')).toBeVisible()
  await expect(page.locator('canvas[aria-hidden="true"]').last()).toBeVisible()

  await page.getByText('AI match read (qualitative)', { exact: true }).click()
  await expect(page.getByText('2 of 2 observations verified')).toBeVisible()
  await expect(page.getByText('Offers a passing option.')).toBeVisible()
  await expect(page.getByLabel('checked against tracking at t=31.5s (overlap 0.66)')).toBeVisible()
  await page.screenshot({ path: `test-results/${screenshotPaths.verified}`, fullPage: true })

  await page.getByRole('button', { name: /02 · 0:30/ }).click()
  await expect(page.getByText('No verified note for this clip')).toBeVisible()
  await expect(page.getByText('Checks into space before receiving.')).toHaveCount(0)
  await expect(page.getByText('Unsupported claim that must be withheld.')).toHaveCount(0)
  await page.screenshot({ path: `test-results/${screenshotPaths.withheld}`, fullPage: true })
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

  await expectVerifiedAndWithheldReel(page, {
    verified: 'club-reels-allowed.png',
    withheld: 'club-reels-withheld.png',
  })
  await expect(page.getByText("Coach's brief", { exact: true })).toBeVisible()
  await expect(page.getByText('Maintain wide support before receiving')).toBeVisible()
  await expect(page.getByText('Evidence at 0:21')).toBeVisible()
  await expect(page.getByText('No evidence in sampled frames')).toBeVisible()
  await expect(page.getByText("An evidence frame verifies the player's identity and location, not the behaviour itself.")).toBeVisible()
  await expect(page.getByText('What this read cannot tell you')).toBeVisible()

  await page.getByRole('button', { name: 'Hide player reels' }).click()
  await page.getByRole('button', { name: 'View player reels' }).click()
  await expect.poll(requests.reelRequestCount).toBe(2)
  await expect.poll(requests.tokenRequestCount).toBe(2)
  await expect(page.getByText('No player reels yet — bind identities in Tag review below.')).toBeVisible()
  await expect(page.getByText('#8 Mina Sato')).toHaveCount(0)
})

test('admin reel shows verified notes and honestly withholds ungrounded prose', async ({ page }) => {
  const { matchPayloads } = await installAdminMocks(page)
  await page.goto('/admin/video/41')

  await expect(page.getByRole('heading', { name: 'Player reels' })).toBeVisible()
  await expectVerifiedAndWithheldReel(page, {
    verified: 'admin-reels-verified.png',
    withheld: 'admin-reels-withheld.png',
  })
  await expect(page.getByText('Expectation 1 — evidence at 0:21')).toBeVisible()
  await expect(page.getByText('Expectation 2 — no evidence in sampled frames')).toBeVisible()
  expect(JSON.stringify(matchPayloads)).not.toContain(SYNTHETIC_BRIEF)
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
