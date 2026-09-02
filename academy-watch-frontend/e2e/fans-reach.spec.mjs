// Run with an independently started Vite server (5180+):
// E2E_BASE_URL=http://127.0.0.1:5180 E2E_API_URL=http://127.0.0.1:5180 \
//   pnpm exec playwright test e2e/fans-reach.spec.mjs
import { expect, test } from '@playwright/test'

const TRACKED_ID = 42
const LOCAL_URL_ID = 7
const LOCAL_SIGNED_ID = -7
const SHARE_URL = `https://api.theacademywatch.test/p/${TRACKED_ID}`

const seasons = {
  current_season: 2026,
  bounds: { min: 2025, max: 2026 },
  seasons: [
    { season: 2026, label: '2026/27', has_rollup: true, is_current: true },
    { season: 2025, label: '2025/26', has_rollup: true, is_current: false },
  ],
}

const provenance = {
  source_category: 'self',
  source_label: 'Self-reported',
  primary_source: 'user',
}

const emptyShowcase = {
  claim_status: 'claimed',
  reel: [],
  photos: [],
  affiliations: [],
  verified_footage: [],
  profile: null,
}

function parseJsonBody(request) {
  const rawBody = request.postData()
  if (!rawBody) return null
  try {
    return JSON.parse(rawBody)
  } catch {
    return null
  }
}

function profileViewEvents(state) {
  return state.analyticsEvents.filter((event) => event?.name === 'profile_view')
}

function requestsFor(state, pathname, method) {
  return state.requests.filter((request) => (
    request.pathname === pathname && (!method || request.method === method)
  ))
}

async function settleEffects(page) {
  await page.evaluate(() => new Promise((resolve) => {
    globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(resolve))
  }))
}

async function flushAnalytics(page, state) {
  const previousRequestCount = state.analyticsRequests
  await page.evaluate(() => globalThis.dispatchEvent(new globalThis.Event('pagehide')))
  await expect.poll(() => state.analyticsRequests).toBeGreaterThan(previousRequestCount)
}

async function mockApi(page, customHandler, {
  signedIn = false,
  ownerSubject = null,
  includeLocalApiId = true,
  localApiId = LOCAL_SIGNED_ID,
} = {}) {
  const state = {
    requests: [],
    analyticsEvents: [],
    analyticsRequests: 0,
  }

  await page.addInitScript(({ hasSession }) => {
    for (const key of [
      'academy_watch_user_token',
      'academy_watch_display_name',
      'academy_watch_display_name_confirmed',
      'academy_watch_is_admin',
      'academy_watch_is_journalist',
      'academy_watch_is_curator',
      'academy_watch_admin_key',
      'academy_watch_curator_key',
      'aw_analytics_optout',
    ]) {
      localStorage.removeItem(key)
    }
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (hasSession) {
      localStorage.setItem('academy_watch_user_token', 'mock-user-token')
      localStorage.setItem('academy_watch_display_name', 'Alex Supporter')
      localStorage.setItem('academy_watch_display_name_confirmed', 'true')
      localStorage.setItem('academy_watch_is_admin', 'false')
      localStorage.setItem('academy_watch_is_journalist', 'false')
      localStorage.setItem('academy_watch_is_curator', 'false')
    }

    globalThis.__copiedShareUrls = []
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: undefined,
    })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => {
          globalThis.__copiedShareUrls.push(value)
        },
      },
    })
  }, { hasSession: signedIn })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const recordedRequest = {
      method: request.method(),
      pathname: url.pathname,
      search: url.search,
      authorization: request.headers().authorization || null,
      body: parseJsonBody(request),
    }
    state.requests.push(recordedRequest)

    if (url.pathname === '/api/events') {
      const events = Array.isArray(recordedRequest.body?.events)
        ? recordedRequest.body.events
        : []
      state.analyticsEvents.push(...events)
      state.analyticsRequests += 1
      return route.fulfill({ status: 202, json: { accepted: events.length } })
    }

    if (customHandler && await customHandler({ route, request, url, recordedRequest, state })) return

    if (url.pathname === '/api/auth/me') {
      if (!signedIn) {
        return route.fulfill({ status: 401, json: { error: 'authentication required' } })
      }
      return route.fulfill({
        json: {
          email: 'alex.supporter@example.com',
          role: 'user',
          account_role: 'user',
          user_id: 17,
          display_name: 'Alex Supporter',
          display_name_confirmed: true,
          is_journalist: false,
          is_curator: false,
          is_verified_scout: false,
        },
      })
    }
    if (url.pathname === '/api/features') return route.fulfill({ json: { contact_rail: false } })
    if (url.pathname === '/api/seasons') return route.fulfill({ json: seasons })
    if (url.pathname === '/api/subscriptions/me') return route.fulfill({ json: [] })
    if (url.pathname === '/api/user/all-subscriptions') {
      return route.fulfill({ json: { free_subscriptions: [], paid_subscriptions: [], journalist_follows: [] } })
    }
    if (url.pathname === '/api/scout/watchlist/ids') {
      return route.fulfill({ json: { player_ids: [] } })
    }
    if (url.pathname === '/api/scout/watchlist') {
      return route.fulfill({ status: request.method() === 'POST' ? 201 : 200, json: { entries: [] } })
    }
    if (url.pathname === '/api/me/claims') {
      const trackedClaim = {
        id: 71,
        player_api_id: TRACKED_ID,
        relationship_type: 'player',
        status: 'approved',
      }
      const localClaim = {
        id: 72,
        local_player_id: LOCAL_URL_ID,
        relationship_type: 'player',
        status: 'approved',
      }
      const claims = ownerSubject === 'tracked'
        ? [trackedClaim]
        : ownerSubject === 'local' ? [localClaim] : []
      return route.fulfill({ json: { claims } })
    }
    if (url.pathname === '/api/showcase/mine/interest-signals') {
      return route.fulfill({ json: { week_start: '2026-08-31T00:00:00', interest_signals: [] } })
    }
    if (url.pathname === '/api/user/email-preferences') {
      return route.fulfill({
        json: {
          user_id: 17,
          email_delivery_preference: 'individual',
          profile_activity_email_opt_in: recordedRequest.body?.profile_activity_email_opt_in ?? false,
        },
      })
    }

    if (url.pathname === `/api/players/${TRACKED_ID}/profile`) {
      return route.fulfill({
        json: {
          player_id: TRACKED_ID,
          name: 'Test Prospect',
          position: 'Midfielder',
          age: 20,
          nationality: 'England',
        },
      })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/stats`) {
      const season = Number(url.searchParams.get('season') || 2026)
      return route.fulfill({
        json: { matches: [], summary: { season }, provenance },
      })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/season-stats`) {
      const season = Number(url.searchParams.get('season') || 2026)
      return route.fulfill({
        json: {
          season: `${season}/${season + 1}`,
          appearances: 0,
          minutes: 0,
          goals: 0,
          assists: 0,
          provenance,
        },
      })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/commentaries`) {
      return route.fulfill({ json: { commentaries: [], authors: [], total_count: 0 } })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/academy-stats`) {
      return route.fulfill({ json: null })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/journey/map`) {
      return route.fulfill({ json: { entries: [], nodes: [], edges: [] } })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/showcase`) {
      return route.fulfill({ json: emptyShowcase })
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/matches`) {
      return route.fulfill({ json: { matches: [], total: 0, page: 1, per_page: 100 } })
    }

    if (url.pathname === `/api/local-players/${LOCAL_URL_ID}`) {
      return route.fulfill({
        json: {
          player: {
            id: LOCAL_URL_ID,
            ...(includeLocalApiId ? { api_player_id: localApiId } : {}),
            display_name: 'Local Seven',
            status: 'approved',
            position: 'Midfielder',
            birth_year: 2005,
            club_name: 'Harbour Academy',
          },
        },
      })
    }
    if (url.pathname === `/api/local-players/${LOCAL_URL_ID}/showcase`) {
      return route.fulfill({ json: emptyShowcase })
    }
    if (url.pathname === `/api/players/${LOCAL_SIGNED_ID}/season-stats`) {
      return route.fulfill({
        json: {
          season: '2026/2027',
          appearances: 0,
          minutes: 0,
          goals: 0,
          assists: 0,
          provenance,
        },
      })
    }
    if (url.pathname === `/api/players/${LOCAL_SIGNED_ID}/matches`) {
      return route.fulfill({ json: { matches: [], total: 0, page: 1, per_page: 100 } })
    }

    // Every API request is fulfilled here; no test can leak to a real backend.
    return route.fulfill({ json: {} })
  })

  return state
}

test('anonymous tracked-player fans can share and Follow opens sign-in', async ({ page }) => {
  const state = await mockApi(page, async ({ route, url }) => {
    if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: TRACKED_ID,
          fans: 6,
          following: null,
          share_url: SHARE_URL,
        },
      })
      return true
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/follow`) {
      await route.fulfill({ status: 401, json: { error: 'authentication required' } })
      return true
    }
    return false
  })

  await page.goto(`/players/${TRACKED_ID}`)
  await expect(page.getByRole('heading', { name: 'Test Prospect', exact: true })).toBeVisible()
  const controls = page.getByTestId('player-reach-controls')
  await expect(controls).toBeVisible()
  await expect(controls.getByText('6 fans', { exact: true })).toBeVisible()

  await controls.getByRole('button', { name: 'Share', exact: true }).click()
  await expect.poll(() => page.evaluate(() => globalThis.__copiedShareUrls)).toEqual([SHARE_URL])
  await expect(controls.getByText('Link copied', { exact: true })).toBeVisible()

  await controls.getByRole('button', { name: 'Follow', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to The Academy Watch' })).toBeVisible()

  const countRequests = requestsFor(
    state,
    `/api/players/${TRACKED_ID}/followers/count`,
    'GET',
  )
  expect(countRequests.length).toBeGreaterThan(0)
  expect(countRequests.every((request) => request.authorization === null)).toBe(true)
  expect(requestsFor(state, `/api/players/${TRACKED_ID}/follow`, 'POST')).toHaveLength(0)
})

test('signed-in non-scout follows and unfollows independently of the scout watchlist star', async ({ page }) => {
  const fanMutations = []
  const state = await mockApi(page, async ({ route, request, url, recordedRequest }) => {
    if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: TRACKED_ID,
          fans: 1,
          following: false,
          share_url: SHARE_URL,
        },
      })
      return true
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/follow`) {
      fanMutations.push(recordedRequest)
      if (request.method() === 'POST') {
        await route.fulfill({
          status: 201,
          json: {
            player_api_id: TRACKED_ID,
            following: true,
            fans: 2,
            created: true,
          },
        })
      } else {
        await route.fulfill({
          json: { player_api_id: TRACKED_ID, following: false, deleted: true },
        })
      }
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto(`/players/${TRACKED_ID}`)
  const controls = page.getByTestId('player-reach-controls')
  await expect(controls.getByText('1 fan', { exact: true })).toBeVisible()

  await controls.getByRole('button', { name: 'Follow', exact: true }).click()
  await expect.poll(() => fanMutations.length).toBe(1)
  await expect(controls.getByRole('button', { name: 'Following', exact: true })).toBeEnabled()
  await expect(controls.getByText('2 fans', { exact: true })).toBeVisible()

  await controls.getByRole('button', { name: 'Following', exact: true }).click()
  await expect.poll(() => fanMutations.length).toBe(2)
  await expect(controls.getByRole('button', { name: 'Follow', exact: true })).toBeEnabled()
  await expect(controls.getByText('1 fan', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Watch this player' }).click()
  await expect.poll(() => requestsFor(state, '/api/scout/watchlist', 'POST').length).toBe(1)

  expect(fanMutations.map((request) => request.method)).toEqual(['POST', 'DELETE'])
  expect(fanMutations.every((request) => request.authorization === 'Bearer mock-user-token')).toBe(true)
  expect(requestsFor(state, '/api/scout/watchlist', 'POST')).toEqual([
    expect.objectContaining({
      body: { player_api_id: TRACKED_ID },
      authorization: 'Bearer mock-user-token',
    }),
  ])
  expect(requestsFor(state, `/api/players/${TRACKED_ID}/follow`)).toHaveLength(2)
})

test('profile_view emits once when a tracked player season changes', async ({ page }) => {
  const state = await mockApi(page, async ({ route, url }) => {
    if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: TRACKED_ID,
          fans: 4,
          following: null,
          share_url: SHARE_URL,
        },
      })
      return true
    }
    return false
  })

  await page.goto(`/players/${TRACKED_ID}?season=2026`)
  await expect(page.getByTestId('player-reach-controls')).toBeVisible()
  await flushAnalytics(page, state)

  expect(profileViewEvents(state)).toHaveLength(1)
  expect(profileViewEvents(state)[0].props).toEqual({ player_api_id: TRACKED_ID })

  await page.getByRole('combobox', { name: 'Select season' }).click()
  await page.getByRole('option', { name: /2025\/26/ }).click()
  await expect(page).toHaveURL(/season=2025/)
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toBeVisible()
  await expect(page.getByTestId('player-reach-controls').getByText('4 fans', { exact: true })).toBeVisible()
  await flushAnalytics(page, state)

  expect(profileViewEvents(state)).toHaveLength(1)
  expect(profileViewEvents(state)[0].props).toEqual({ player_api_id: TRACKED_ID })
})

test('neutral fan-count 404 hides reach controls and suppresses profile_view', async ({ page }) => {
  const state = await mockApi(page, async ({ route, url }) => {
    if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
      await route.fulfill({ status: 404, json: { error: 'Player not found' } })
      return true
    }
    return false
  })

  const countResponse = page.waitForResponse((response) => (
    new URL(response.url()).pathname === `/api/players/${TRACKED_ID}/followers/count`
    && response.status() === 404
  ))
  await page.goto(`/players/${TRACKED_ID}`)
  await expect(page.getByRole('heading', { name: 'Test Prospect', exact: true })).toBeVisible()
  await countResponse
  await settleEffects(page)
  await expect(page.getByTestId('player-reach-controls')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Follow', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Share', exact: true })).toHaveCount(0)

  await flushAnalytics(page, state)
  expect(profileViewEvents(state)).toHaveLength(0)
})

test('local reach requests and profile_view use the negative payload identity', async ({ page }) => {
  const state = await mockApi(page, async ({ route, request, url }) => {
    if (url.pathname === `/api/players/${LOCAL_SIGNED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: LOCAL_SIGNED_ID,
          fans: 2,
          following: false,
          share_url: `https://api.theacademywatch.test/p/${LOCAL_SIGNED_ID}`,
        },
      })
      return true
    }
    if (url.pathname === `/api/players/${LOCAL_SIGNED_ID}/follow` && request.method() === 'POST') {
      await route.fulfill({
        status: 201,
        json: {
          player_api_id: LOCAL_SIGNED_ID,
          following: true,
          fans: 3,
          created: true,
        },
      })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto(`/local-players/${LOCAL_URL_ID}`)
  await expect(page.getByRole('heading', { name: 'Local Seven', exact: true })).toBeVisible()
  const controls = page.getByTestId('player-reach-controls')
  await expect(controls.getByText('2 fans', { exact: true })).toBeVisible()
  await flushAnalytics(page, state)

  await controls.getByRole('button', { name: 'Follow', exact: true }).click()
  await expect(controls.getByRole('button', { name: 'Following', exact: true })).toBeEnabled()
  await expect(controls.getByText('3 fans', { exact: true })).toBeVisible()

  const countRequests = requestsFor(
    state,
    `/api/players/${LOCAL_SIGNED_ID}/followers/count`,
    'GET',
  )
  const followRequests = requestsFor(
    state,
    `/api/players/${LOCAL_SIGNED_ID}/follow`,
    'POST',
  )
  expect(countRequests.length).toBeGreaterThan(0)
  expect(followRequests).toHaveLength(1)
  expect(followRequests[0].authorization).toBe('Bearer mock-user-token')
  expect(requestsFor(state, `/api/players/${LOCAL_URL_ID}/followers/count`)).toHaveLength(0)
  expect(requestsFor(state, `/api/players/${LOCAL_URL_ID}/follow`)).toHaveLength(0)
  expect(profileViewEvents(state).map((event) => event.props?.player_api_id)).toEqual([
    LOCAL_SIGNED_ID,
  ])
})

test('local payload without api_player_id mounts no reach controls or owner card', async ({ page }) => {
  const state = await mockApi(page, null, {
    signedIn: true,
    ownerSubject: 'local',
    includeLocalApiId: false,
  })

  await page.goto(`/local-players/${LOCAL_URL_ID}`)
  await expect(page.getByRole('heading', { name: 'Local Seven', exact: true })).toBeVisible()
  // Waiting for an owner-only action proves Showcase has resolved the local claim.
  await expect(page.getByRole('button', { name: 'Add a game', exact: true })).toBeVisible()
  await settleEffects(page)

  await expect(page.getByTestId('player-reach-controls')).toHaveCount(0)
  await expect(page.getByTestId('watching-me-card')).toHaveCount(0)
  expect(state.requests.filter((request) => (
    request.pathname.endsWith('/followers/count') || request.pathname.endsWith('/follow')
  ))).toHaveLength(0)
  expect(requestsFor(state, '/api/showcase/mine/interest-signals')).toHaveLength(0)

  await flushAnalytics(page, state)
  expect(profileViewEvents(state)).toHaveLength(0)
})

test('local player owner card matches the negative payload identity', async ({ page }) => {
  const state = await mockApi(page, async ({ route, url }) => {
    if (url.pathname === `/api/players/${LOCAL_SIGNED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: LOCAL_SIGNED_ID,
          fans: 6,
          following: false,
          share_url: `https://api.theacademywatch.test/p/${LOCAL_SIGNED_ID}`,
        },
      })
      return true
    }
    if (url.pathname === '/api/showcase/mine/interest-signals') {
      await route.fulfill({
        json: {
          week_start: '2026-08-31T00:00:00',
          interest_signals: [
            {
              player_api_id: LOCAL_URL_ID,
              watchlists: { total: 99, added_this_week: 99 },
              fans: { total: 99, added_this_week: 99 },
              profile_views: { last_7_days: 99, last_30_days: 99 },
            },
            {
              player_api_id: LOCAL_SIGNED_ID,
              watchlists: { total: 14, added_this_week: 3 },
              fans: { total: 6, added_this_week: 2 },
              profile_views: { last_7_days: 32, last_30_days: 80 },
            },
          ],
        },
      })
      return true
    }
    return false
  }, { signedIn: true, ownerSubject: 'local' })

  await page.goto(`/local-players/${LOCAL_URL_ID}`)
  const card = page.getByTestId('watching-me-card')
  await expect(card).toBeVisible()
  await expect(card.getByText('14', { exact: true })).toBeVisible()
  await expect(card.getByText('6', { exact: true })).toBeVisible()
  await expect(card.getByText('32', { exact: true })).toBeVisible()
  await expect(card.getByText('80', { exact: true })).toBeVisible()
  await expect(card.getByText('99', { exact: true })).toHaveCount(0)

  const signalRequests = requestsFor(state, '/api/showcase/mine/interest-signals', 'GET')
  expect(signalRequests.length).toBeGreaterThan(0)
  expect(signalRequests.every((request) => request.authorization === 'Bearer mock-user-token')).toBe(true)
})

test('approved player owner sees aggregate interest and can enable weekly email', async ({ page }) => {
  const preferencePatches = []
  const ownFollowRequests = []
  const state = await mockApi(page, async ({ route, request, url, recordedRequest }) => {
    if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: TRACKED_ID,
          fans: 9,
          following: false,
          share_url: SHARE_URL,
        },
      })
      return true
    }
    if (url.pathname === `/api/players/${TRACKED_ID}/follow` && request.method() === 'POST') {
      ownFollowRequests.push(recordedRequest)
      await route.fulfill({
        status: 400,
        json: { error: 'You cannot follow your own profile' },
      })
      return true
    }
    if (url.pathname === '/api/showcase/mine/interest-signals') {
      await route.fulfill({
        json: {
          week_start: '2026-08-31T00:00:00',
          interest_signals: [{
            player_api_id: TRACKED_ID,
            watchlists: { total: 12, added_this_week: 2 },
            follows: { total: 4, added_this_week: 1 },
            fans: { total: 8, added_this_week: 3 },
            profile_views: { last_7_days: 21, last_30_days: 64 },
          }],
        },
      })
      return true
    }
    if (url.pathname === '/api/user/email-preferences' && request.method() === 'GET') {
      await route.fulfill({
        json: {
          user_id: 17,
          email_delivery_preference: 'individual',
          profile_activity_email_opt_in: false,
        },
      })
      return true
    }
    if (url.pathname === '/api/user/email-preferences' && request.method() === 'PATCH') {
      preferencePatches.push(recordedRequest)
      await route.fulfill({
        json: {
          user_id: 17,
          email_delivery_preference: 'individual',
          profile_activity_email_opt_in: true,
        },
      })
      return true
    }
    return false
  }, { signedIn: true, ownerSubject: 'tracked' })

  await page.goto(`/players/${TRACKED_ID}`)
  const card = page.getByTestId('watching-me-card')
  await expect(card).toBeVisible()
  await expect(card.getByRole('heading', { name: "Who's watching me" })).toBeVisible()
  await expect(card.getByText('Counts only — we never show who.', { exact: true })).toBeVisible()

  const watchlistsMetric = card.getByRole('heading', { name: 'Watchlists' }).locator('..').locator('..')
  await expect(watchlistsMetric.getByText('12', { exact: true })).toBeVisible()
  await expect(watchlistsMetric.getByText('+2 this week', { exact: true })).toBeVisible()
  const fansMetric = card.getByRole('heading', { name: 'Fans' }).locator('..').locator('..')
  await expect(fansMetric.getByText('8', { exact: true })).toBeVisible()
  await expect(fansMetric.getByText('+3 this week', { exact: true })).toBeVisible()
  const viewsMetric = card.getByRole('heading', { name: 'Profile views' }).locator('..').locator('..')
  await expect(viewsMetric.getByText('21', { exact: true })).toBeVisible()
  await expect(viewsMetric.getByText('7 days', { exact: true })).toBeVisible()
  await expect(viewsMetric.getByText('64', { exact: true })).toBeVisible()
  await expect(viewsMetric.getByText('30 days', { exact: true })).toBeVisible()

  const emailToggle = card.getByRole('switch', { name: 'Email me a weekly activity summary' })
  await expect(emailToggle).not.toBeChecked()
  await emailToggle.click()
  await expect.poll(() => preferencePatches.length).toBe(1)
  await expect(emailToggle).toBeChecked()
  expect(preferencePatches[0]).toEqual(expect.objectContaining({
    authorization: 'Bearer mock-user-token',
    body: { profile_activity_email_opt_in: true },
  }))

  const controls = page.getByTestId('player-reach-controls')
  await expect(controls.getByText('9 fans', { exact: true })).toBeVisible()
  await controls.getByRole('button', { name: 'Follow', exact: true }).click()
  await expect(controls.getByText(/cannot follow your own profile/i)).toBeVisible()
  await expect(controls.getByText('9 fans', { exact: true })).toBeVisible()
  expect(ownFollowRequests).toHaveLength(1)
  expect(ownFollowRequests[0].authorization).toBe('Bearer mock-user-token')
  expect(requestsFor(state, '/api/showcase/mine/interest-signals').length).toBeGreaterThan(0)
})

test('approved non-player claimant never mounts the private watching card', async ({ page }) => {
  const state = await mockApi(page, async ({ route, url }) => {
    if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
      await route.fulfill({
        json: {
          player_api_id: TRACKED_ID,
          fans: 5,
          following: false,
          share_url: SHARE_URL,
        },
      })
      return true
    }
    if (url.pathname === '/api/me/claims') {
      await route.fulfill({
        json: {
          claims: [{
            id: 73,
            player_api_id: TRACKED_ID,
            relationship_type: 'agent',
            status: 'approved',
          }],
        },
      })
      return true
    }
    return false
  }, { signedIn: true })

  const ownerInputs = Promise.all([
    page.waitForResponse((response) => new URL(response.url()).pathname === '/api/me/claims'),
    page.waitForResponse((response) => (
      new URL(response.url()).pathname === `/api/players/${TRACKED_ID}/showcase`
    )),
  ])
  await page.goto(`/players/${TRACKED_ID}`)
  await expect(page.getByTestId('player-reach-controls')).toBeVisible()
  await ownerInputs
  await settleEffects(page)

  await expect(page.getByTestId('watching-me-card')).toHaveCount(0)
  expect(requestsFor(state, '/api/showcase/mine/interest-signals')).toHaveLength(0)
})

for (const signalResult of ['no matching entry', 'request failure']) {
  test(`owner watching card stays hidden on ${signalResult}`, async ({ page }) => {
    await mockApi(page, async ({ route, url }) => {
      if (url.pathname === `/api/players/${TRACKED_ID}/followers/count`) {
        await route.fulfill({
          json: {
            player_api_id: TRACKED_ID,
            fans: 3,
            following: false,
            share_url: SHARE_URL,
          },
        })
        return true
      }
      if (url.pathname === '/api/showcase/mine/interest-signals') {
        if (signalResult === 'request failure') {
          await route.fulfill({ status: 503, json: { error: 'temporarily unavailable' } })
        } else {
          await route.fulfill({
            json: {
              week_start: '2026-08-31T00:00:00',
              interest_signals: [{
                player_api_id: 999,
                watchlists: { total: 1, added_this_week: 0 },
                fans: { total: 1, added_this_week: 0 },
                profile_views: { last_7_days: 1, last_30_days: 1 },
              }],
            },
          })
        }
        return true
      }
      return false
    }, { signedIn: true, ownerSubject: 'tracked' })

    const signalsResponse = page.waitForResponse((response) => (
      new URL(response.url()).pathname === '/api/showcase/mine/interest-signals'
    ))
    await page.goto(`/players/${TRACKED_ID}`)
    await expect(page.getByRole('button', { name: 'Add a game', exact: true })).toBeVisible()
    await signalsResponse
    await settleEffects(page)

    await expect(page.getByTestId('watching-me-card')).toHaveCount(0)
  })
}
