// Run: pnpm dev --host 127.0.0.1 --port 5181 --strictPort
// Then: E2E_BASE_URL=http://127.0.0.1:5181 pnpm exec playwright test e2e/billing.spec.mjs
import { expect, test } from '@playwright/test'

const ACCOUNT = {
  email: 'alex.scout@example.com',
  role: 'user',
  account_role: 'scout',
  user_id: 42,
  display_name: 'Alex Scout',
  display_name_confirmed: true,
  is_journalist: false,
  is_curator: false,
  is_verified_scout: true,
  scout_tier: 'free',
  scout_pro: { enabled: true, tier: 'free', features: { csv_export: false, custom_lists: false, custom_lists_max: 3 } },
}

const BILLING_CONFIG = {
  enabled: true,
  products: [{
    code: 'scout_pro',
    name: 'Scout Pro',
    scope_type: 'user',
    prices: [{ price_code: 'monthly', interval: 'month', unit_amount: 900, currency: 'usd' }],
  }],
}

async function installApi(page, handler, { signedIn = false } = {}) {
  await page.addInitScript(({ authenticated }) => {
    localStorage.clear()
    sessionStorage.clear()
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (authenticated) {
      localStorage.setItem('academy_watch_user_token', 'mock-user-token')
      localStorage.setItem('academy_watch_display_name', 'Alex Scout')
      localStorage.setItem('academy_watch_is_admin', 'false')
      localStorage.setItem('academy_watch_is_journalist', 'false')
      localStorage.setItem('academy_watch_is_curator', 'false')
    }
  }, { authenticated: signedIn })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (handler && await handler({ route, request, url })) return
    if (url.pathname === '/api/auth/me' && signedIn) return route.fulfill({ json: ACCOUNT })
    if (url.pathname === '/api/features') return route.fulfill({ json: { contact_rail: false } })
    if (url.pathname === '/api/sync-status') return route.fulfill({ json: { running: false } })
    if (url.pathname === '/api/journalists') return route.fulfill({ json: [] })
    if (url.pathname === '/api/events' && request.method() === 'POST') return route.fulfill({ json: { accepted: true } })
    throw new Error(`Unmocked API request: ${request.method()} ${url.pathname}${url.search}`)
  })
}

test('pricing stays in beta mode while billing is dark', async ({ page }) => {
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/billing/config') {
      await route.fulfill({ status: 404, body: 'Not Found' })
      return true
    }
    return false
  })
  await page.goto('/pricing')
  await expect(page.getByText('Free during beta', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Subscribe', exact: true })).toHaveCount(0)
})

test('lit pricing posts only product, price, and reusable client key before checkout navigation', async ({ page }) => {
  const checkoutBodies = []
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/billing/config') {
      await route.fulfill({ json: BILLING_CONFIG })
      return true
    }
    if (url.pathname === '/api/billing/checkout' && request.method() === 'POST') {
      checkoutBodies.push(request.postDataJSON())
      await route.fulfill({ json: { checkout_url: `${url.origin}/checkout-stub`, session_id: 'checkout-session' } })
      return true
    }
    return false
  }, { signedIn: true })
  await page.route('**/checkout-stub', (route) => route.fulfill({ contentType: 'text/html', body: '<h1>Hosted checkout stub</h1>' }))

  await page.goto('/pricing')
  await expect(page.getByText('$9.00', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Subscribe', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Hosted checkout stub' })).toBeVisible()
  expect(checkoutBodies).toHaveLength(1)
  expect(Object.keys(checkoutBodies[0]).sort()).toEqual(['client_key', 'price_code', 'product_code'])
  expect(checkoutBodies[0]).toMatchObject({ product_code: 'scout_pro', price_code: 'monthly' })
  expect(checkoutBodies[0].client_key).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
})

test('account billing records one sanitized completion and opens the billing portal', async ({ page }) => {
  const eventBatches = []
  let portalPosts = 0
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/billing/config') return route.fulfill({ json: BILLING_CONFIG }).then(() => true)
    if (url.pathname === '/api/billing/me') {
      await route.fulfill({ json: { enabled: true, has_billing_account: true, subscriptions: [{ id: 1, scope_type: 'user', scope_id: 42, product_code: 'scout_pro', price_code: 'monthly', status: 'active', is_active: true, current_period_end: '2026-10-03T00:00:00', cancel_at_period_end: false, unit_amount: 900, currency: 'usd', interval: 'month' }] } })
      return true
    }
    if (url.pathname === '/api/scout/entitlements') {
      await route.fulfill({ json: { entitlements: { billing_enabled: true, tier: 'pro', source: 'subscription', subscription_status: 'active', current_period_end: '2026-10-03T00:00:00', cancel_at_period_end: false, grandfathered_until: null, features: { csv_export: true, custom_lists_max: 25 } } } })
      return true
    }
    if (url.pathname === '/api/billing/portal' && request.method() === 'POST') {
      portalPosts += 1
      await route.fulfill({ json: { portal_url: `${url.origin}/portal-stub` } })
      return true
    }
    if (url.pathname === '/api/events' && request.method() === 'POST') {
      eventBatches.push(request.postDataJSON())
      await route.fulfill({ json: { accepted: true } })
      return true
    }
    return false
  }, { signedIn: true })
  await page.route('**/portal-stub', (route) => route.fulfill({ contentType: 'text/html', body: '<h1>Billing portal stub</h1>' }))

  const privateSession = 'checkout-session-private-value'
  await page.goto(`/account/billing?checkout=success&session_id=${privateSession}`)
  await expect(page.getByText(/Checkout complete/)).toBeVisible()
  await expect(page).toHaveURL('/account/billing')
  await page.waitForTimeout(5500)
  const events = eventBatches.flatMap((batch) => batch.events || [])
  expect(events.filter((event) => event.name === 'checkout_completed')).toHaveLength(1)
  for (const event of events) expect(JSON.stringify({ path: event.path, referrer: event.referrer, props: event.props })).not.toContain(privateSession)

  await page.getByRole('button', { name: 'Manage billing' }).click()
  await expect(page.getByRole('heading', { name: 'Billing portal stub' })).toBeVisible()
  expect(portalPosts).toBe(1)
})

test('program page renders an external Patreon link and approved updates', async ({ page }) => {
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/programs/northbank') {
      await route.fulfill({ json: { program: { id: 7, slug: 'northbank', name: 'Northbank Juniors', city: 'Leeds', country: 'England', platform_status: 'approved', is_verified_program: true, is_fundable: false, provenance: { label: 'Self-reported' }, program_provided: { label: 'Program-provided', summary: 'A volunteer-led youth program.', age_groups: ['U12', 'U14'], activities: ['Training'], funding_purpose: 'Pitch hire.' }, roster_links: {}, external_support: { provider: 'patreon', label: 'Patreon', url: 'https://patreon.com/northbankjuniors' }, updates: [{ id: 2, title: 'New training night', body: 'We added a Thursday session.', impact: 'More places for players.', published_at: '2026-09-02T12:00:00' }, { id: 1, title: 'Summer tournament', body: 'The U14 group reached the final.', impact: null, published_at: '2026-08-20T12:00:00' }] } } })
      return true
    }
    return false
  })
  await page.goto('/programs/northbank')
  const support = page.getByRole('link', { name: 'Support on Patreon' })
  await expect(support).toBeVisible()
  await expect(support).toHaveAttribute('target', '_blank')
  const rel = await support.getAttribute('rel')
  expect(new Set(rel.split(/\s+/))).toEqual(new Set(['noopener', 'noreferrer']))
  await expect(page.getByText('Latest from the program', { exact: true })).toBeVisible()
  await expect(page.locator('article')).toHaveCount(2)
  await expect(page.getByText('Support is not live yet')).toHaveCount(0)
})

test('club console saves the moderated profile payload and submits an update', async ({ page }) => {
  const profilePuts = []
  const updatePosts = []
  const program = { id: 7, slug: 'northbank', name: 'Northbank Juniors', platform_status: 'approved', country: 'England', league: { name: 'Northern Youth League', age_bands: ['U12', 'U14'], data_tier: 'self_reported' }, provenance: { label: 'Self-reported' } }
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/me/club-claims') return route.fulfill({ json: { claims: [] } }).then(() => true)
    if (url.pathname === '/api/me/club') return route.fulfill({ json: { clubs: [] } }).then(() => true)
    if (url.pathname === '/api/funding/claims/me') return route.fulfill({ json: { claims: [{ id: 12, status: 'approved', program }] } }).then(() => true)
    if (url.pathname === '/api/club/7/roster') return route.fulfill({ json: { members: [], system_brief: { body: null, updated_at: null, hash: null } } }).then(() => true)
    if (url.pathname === '/api/club/7/matches') return route.fulfill({ json: { matches: [] } }).then(() => true)
    if (url.pathname === '/api/club/7/profile' && request.method() === 'GET') return route.fulfill({ json: { program: { id: 7, slug: 'northbank', name: 'Northbank Juniors' }, approved: null, pending: null, limits: { summary_max: 2000, funding_purpose_max: 1000, list_items_max: 12, list_item_max: 40, media_urls_max: 6, updates_pending_max: 5 } } }).then(() => true)
    if (url.pathname === '/api/club/7/profile' && request.method() === 'PUT') {
      profilePuts.push(request.postDataJSON())
      await route.fulfill({ json: { pending: { id: 21, status: 'pending', ...request.postDataJSON(), review_reason: null, reviewed_at: null, created_at: '2026-09-03T00:00:00' } } })
      return true
    }
    if (url.pathname === '/api/club/7/updates' && request.method() === 'GET') return route.fulfill({ json: { updates: [] } }).then(() => true)
    if (url.pathname === '/api/club/7/updates' && request.method() === 'POST') {
      updatePosts.push(request.postDataJSON())
      await route.fulfill({ status: 201, json: { update: { id: 31, status: 'pending', ...request.postDataJSON(), review_reason: null, created_at: '2026-09-03T00:00:00', published_at: null } } })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto('/my-club')
  await page.getByRole('tab', { name: 'Club profile' }).click()
  await page.getByLabel('Summary').fill('A volunteer-led academy serving north Leeds.')
  await page.getByLabel('Age groups (comma separated)').fill('U12, U14')
  await page.getByLabel('Activities (comma separated)').fill('Training, League matches')
  await page.getByLabel('Funding purpose').fill('Cover pitch hire and equipment.')
  await page.getByLabel('Official URL').fill('https://northbank.example.org')
  await page.getByLabel('Safeguarding URL').fill('https://northbank.example.org/safeguarding')
  await page.getByLabel('Media URLs (one per line)').fill('https://northbank.example.org/team.jpg')
  await page.getByLabel('External support provider').click()
  await page.getByRole('option', { name: 'Patreon' }).click()
  await page.getByLabel('External support URL').fill('https://patreon.com/northbankjuniors')
  await page.getByRole('button', { name: 'Save for review' }).click()
  await expect.poll(() => profilePuts.length).toBe(1)
  expect(profilePuts[0]).toEqual({ summary: 'A volunteer-led academy serving north Leeds.', age_groups: ['U12', 'U14'], activities: ['Training', 'League matches'], funding_purpose: 'Cover pitch hire and equipment.', official_url: 'https://northbank.example.org', safeguarding_url: 'https://northbank.example.org/safeguarding', media_urls: ['https://northbank.example.org/team.jpg'], external_support: { provider: 'patreon', url: 'https://patreon.com/northbankjuniors' } })

  await page.getByLabel('Title').fill('New Thursday session')
  await page.getByLabel('Body').fill('We are opening a new weekly training session for local players.')
  await page.getByLabel('Impact (optional)').fill('Twenty more training places.')
  await page.getByRole('button', { name: 'Submit update' }).click()
  await expect.poll(() => updatePosts).toEqual([{ title: 'New Thursday session', body: 'We are opening a new weekly training session for local players.', impact: 'Twenty more training places.' }])
})

test('CSV entitlement rejection surfaces an inline Scout Pro upgrade prompt', async ({ page }) => {
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/scout/watchlist' && request.method() === 'GET') {
      await route.fulfill({ json: { entries: [{ player_api_id: 101, note: null, player: { player_name: 'Jamie Prospect', position: 'Midfielder', status: 'academy' } }], digest_opt_in: true } })
      return true
    }
    if (url.pathname === '/api/scout/export.csv') {
      await route.fulfill({ status: 403, json: { error: 'scout_pro_required', feature: 'csv_export', upgrade_path: '/pricing' } })
      return true
    }
    return false
  }, { signedIn: true })
  await page.goto('/scout/watchlist')
  await page.getByRole('button', { name: /Export CSV/ }).click()
  await expect(page.getByText(/Scout Pro unlocks csv export/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'View Scout Pro' })).toHaveAttribute('href', '/pricing')
})
