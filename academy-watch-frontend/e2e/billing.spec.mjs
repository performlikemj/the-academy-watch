// Run: pnpm dev --host 127.0.0.1 --port 5194 --strictPort
// Then: E2E_BASE_URL=http://127.0.0.1:5194 pnpm exec playwright test e2e/billing.spec.mjs
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
  scout_pro: { enabled: true, tier: 'pro', features: { gol_chat: true } },
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

async function installApi(page, handler, { signedIn = false, account = ACCOUNT } = {}) {
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
    if (url.pathname === '/api/auth/me' && signedIn) return route.fulfill({ json: account })
    if (url.pathname === '/api/features') return route.fulfill({ json: { contact_rail: false } })
    if (url.pathname === '/api/sync-status') return route.fulfill({ json: { running: false } })
    if (url.pathname === '/api/journalists') return route.fulfill({ json: [] })
    if (url.pathname === '/api/sponsors') return route.fulfill({ json: [] })
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

test('pricing shows a retryable outage state for a non-dark config failure', async ({ page }) => {
  let recovered = false
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/billing/config') {
      await route.fulfill(recovered
        ? { json: BILLING_CONFIG }
        : { status: 500, json: { error: 'temporary_failure' } })
      return true
    }
    return false
  })
  await page.goto('/pricing')
  await expect(page.getByRole('heading', { name: 'Pricing is temporarily unavailable' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
  await expect(page.getByText('Free during beta', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Subscribe', exact: true })).toHaveCount(0)
  recovered = true
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByText('$9.00', { exact: true })).toBeVisible()
})

test('legal paid-feature copy stays off without the build-time flag', async ({ page }) => {
  let billingConfigGets = 0
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/billing/config') {
      billingConfigGets += 1
      await route.fulfill({ json: BILLING_CONFIG })
      return true
    }
    return false
  })

  await page.goto('/terms')
  await expect(page.getByRole('heading', { name: /Paid subscriptions/ })).toHaveCount(0)
  await page.goto('/privacy')
  await expect(page.getByText(/When you buy an optional paid feature/)).toHaveCount(0)
  expect(billingConfigGets).toBe(0)
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
      await route.fulfill({ json: { entitlements: { billing_enabled: true, tier: 'pro', source: 'subscription', subscription_status: 'active', current_period_end: '2026-10-03T00:00:00', cancel_at_period_end: false, grandfathered_until: null, features: { gol_chat: true } } } })
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
  await page.addInitScript(() => {
    sessionStorage.setItem('academyWatch.checkout.scout_pro.monthly', 'completed-client-key')
    sessionStorage.setItem('unrelated-session-key', 'keep')
  })
  await page.route('**/portal-stub', (route) => route.fulfill({ contentType: 'text/html', body: '<h1>Billing portal stub</h1>' }))

  const privateSession = 'checkout-session-private-value'
  await page.goto(`/account/billing?checkout=success&session_id=${privateSession}`)
  await expect(page.getByText(/Checkout complete/)).toBeVisible()
  await expect(page.getByText('GOL chatbot unlocked', { exact: true })).toBeVisible()
  await expect(page).toHaveURL('/account/billing')
  expect(await page.evaluate(() => sessionStorage.getItem('academyWatch.checkout.scout_pro.monthly'))).toBeNull()
  expect(await page.evaluate(() => sessionStorage.getItem('unrelated-session-key'))).toBe('keep')
  await page.waitForTimeout(5500)
  const events = eventBatches.flatMap((batch) => batch.events || [])
  expect(events.filter((event) => event.name === 'checkout_completed')).toHaveLength(1)
  for (const event of events) expect(JSON.stringify({ path: event.path, referrer: event.referrer, props: event.props })).not.toContain(privateSession)

  await page.getByRole('button', { name: 'Manage billing' }).click()
  await expect(page.getByRole('heading', { name: 'Billing portal stub' })).toBeVisible()
  expect(portalPosts).toBe(1)
})

test('account billing failure hides partial subscription and entitlement data', async ({ page }) => {
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/billing/config') return route.fulfill({ json: BILLING_CONFIG }).then(() => true)
    if (url.pathname === '/api/billing/me') return route.fulfill({ status: 500, json: { error: 'temporary_failure' } }).then(() => true)
    if (url.pathname === '/api/scout/entitlements') {
      await route.fulfill({ json: { entitlements: { billing_enabled: true, tier: 'pro', source: 'subscription', subscription_status: 'active', current_period_end: '2026-10-03T00:00:00', cancel_at_period_end: false, grandfathered_until: null, features: { gol_chat: true } } } })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto('/account/billing')
  await expect(page.getByRole('heading', { name: "We couldn't load your billing details." })).toBeVisible()
  await expect(page.getByText('Try again.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
  await expect(page.getByText('Free', { exact: true })).toHaveCount(0)
  await expect(page.getByText('No paid subscriptions yet.', { exact: true })).toHaveCount(0)
})

test('admin revenue renders mixed-currency MRR without invalid placeholders', async ({ page }) => {
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/auth/me') return route.fulfill({ json: { ...ACCOUNT, role: 'admin', account_role: 'admin' } }).then(() => true)
    if (url.pathname === '/api/admin/auth-check') return route.fulfill({ json: { ok: true } }).then(() => true)
    if (url.pathname === '/api/admin/dashboard-stats') return route.fulfill({ json: { players: { total: 3, academy: 1, on_loan: 1, first_team: 1, released: 0 }, teams: { tracked: 2 }, newsletters: { total: 4, published: 3, drafts: 1 } } }).then(() => true)
    if (url.pathname === '/api/admin/billing/summary') return route.fulfill({ json: { active_subscriptions: 3, by_product: { scout_pro: 3 }, mrr_cents: null, currency: null, mrr_by_currency: { usd: 1700, gbp: 800 }, past_due: 0, canceled_last_30d: 0, webhook_events_last_24h: 4, webhook_failed_last_24h: 0, checkout_sessions_open: 0 } }).then(() => true)
    if (url.pathname === '/api/admin/jobs/active') return route.fulfill({ json: { jobs: [] } }).then(() => true)
    if (url.pathname === '/api/admin/ops/overview') return route.fulfill({ json: { tracked: { active: 3, placeholder_names: 0, owning_club_active: 0 }, jobs: { active: 0 } } }).then(() => true)
    if (url.pathname === '/api/admin/analytics/summary') return route.fulfill({ json: { totals: {}, daily: [], distinct_sessions: 0 } }).then(() => true)
    if (url.pathname === '/api/admin/community-takes/stats') return route.fulfill({ json: { takes: { pending: 0 }, submissions: { pending: 0 } } }).then(() => true)
    if (url.pathname === '/api/admin/manual-players') return route.fulfill({ json: [] }).then(() => true)
    if (url.pathname === '/api/admin/flags/stats') return route.fulfill({ json: { by_status: { pending: 0 } } }).then(() => true)
    if (url.pathname === '/api/admin/tracking-requests') return route.fulfill({ json: [] }).then(() => true)
    if (url.pathname === '/api/admin/player-links/pending') return route.fulfill({ json: [] }).then(() => true)
    if (url.pathname === '/api/admin/scout-verifications') return route.fulfill({ json: { total: 0, items: [] } }).then(() => true)
    if (url.pathname === '/api/admin/reports') return route.fulfill({ json: { total: 0, items: [] } }).then(() => true)
    return false
  }, { signedIn: true })
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_is_admin', 'true')
    localStorage.setItem('academy_watch_admin_key', 'admin-test-placeholder')
  })

  await page.goto('/admin/dashboard')
  const revenue = page.getByTestId('revenue-summary')
  await expect(revenue).toContainText('USD · $17.00')
  await expect(revenue).toContainText('GBP · £8.00')
  await expect(revenue).not.toContainText('NaN')
  await expect(revenue).not.toContainText('null')
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
  let profileGets = 0
  const program = { id: 7, slug: 'northbank', name: 'Northbank Juniors', platform_status: 'approved', country: 'England', league: { name: 'Northern Youth League', age_bands: ['U12', 'U14'], data_tier: 'self_reported' }, provenance: { label: 'Self-reported' } }
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/me/club-claims') return route.fulfill({ json: { claims: [] } }).then(() => true)
    if (url.pathname === '/api/me/club') return route.fulfill({ json: { clubs: [] } }).then(() => true)
    if (url.pathname === '/api/funding/claims/me') return route.fulfill({ json: { claims: [{ id: 12, status: 'approved', program }] } }).then(() => true)
    if (url.pathname === '/api/club/7/roster') return route.fulfill({ json: { members: [], system_brief: { body: null, updated_at: null, hash: null } } }).then(() => true)
    if (url.pathname === '/api/club/7/matches') return route.fulfill({ json: { matches: [] } }).then(() => true)
    if (url.pathname === '/api/club/7/profile' && request.method() === 'GET') {
      profileGets += 1
      await route.fulfill({ json: { program: { id: 7, slug: 'northbank', name: 'Northbank Juniors' }, approved: { id: 20, status: 'approved', summary: 'Existing approved profile.', age_groups: ['U12'], activities: ['Training'], funding_purpose: 'Pitch hire.', official_url: 'https://northbank.example.org', safeguarding_url: 'https://northbank.example.org/safeguarding', media_urls: ['https://northbank.example.org/team.jpg'], external_support: { provider: 'patreon', url: 'https://patreon.com/northbankjuniors' }, review_reason: 'Verified.', reviewed_at: '2026-09-02T00:00:00', created_at: '2026-09-01T00:00:00' }, pending: null, limits: { summary_max: 2000, funding_purpose_max: 1000, list_items_max: 12, list_item_max: 40, media_urls_max: 6, updates_pending_max: 5 } } })
      return true
    }
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
  const summary = page.getByLabel('Summary')
  await expect.poll(() => profileGets).toBe(1)
  await expect(page.getByLabel('External support URL')).toHaveValue('https://patreon.com/northbankjuniors')
  await summary.fill('Unsaved manager draft')
  await page.evaluate(() => globalThis.dispatchEvent(new Event('storage')))
  await page.waitForTimeout(200)
  await expect(summary).toHaveValue('Unsaved manager draft')
  expect(profileGets).toBe(1)
  await summary.fill('A volunteer-led academy serving north Leeds.')
  await page.getByLabel('Age groups (comma separated)').fill('U12, U14')
  await page.getByLabel('Activities (comma separated)').fill('Training, League matches')
  await page.getByLabel('Funding purpose').fill('Cover pitch hire and equipment.')
  await page.getByLabel('Official URL').fill('https://northbank.example.org')
  await page.getByLabel('Safeguarding URL').fill('https://northbank.example.org/safeguarding')
  await page.getByLabel('Media URLs (one per line)').fill('https://northbank.example.org/team.jpg')
  await page.getByLabel('External support provider').click()
  await page.getByRole('option', { name: 'None' }).click()
  await expect(page.getByLabel('External support URL')).toHaveValue('')
  await page.getByRole('button', { name: 'Save for review' }).click()
  await expect.poll(() => profilePuts.length).toBe(1)
  expect(profilePuts[0]).toEqual({ summary: 'A volunteer-led academy serving north Leeds.', age_groups: ['U12', 'U14'], activities: ['Training', 'League matches'], funding_purpose: 'Cover pitch hire and equipment.', official_url: 'https://northbank.example.org', safeguarding_url: 'https://northbank.example.org/safeguarding', media_urls: ['https://northbank.example.org/team.jpg'], external_support: null })

  await page.getByLabel('Title').fill('New Thursday session')
  await page.getByLabel('Body').fill('We are opening a new weekly training session for local players.')
  await page.getByLabel('Impact (optional)').fill('Twenty more training places.')
  await page.getByRole('button', { name: 'Submit update' }).click()
  await expect.poll(() => updatePosts).toEqual([{ title: 'New Thursday session', body: 'We are opening a new weekly training session for local players.', impact: 'Twenty more training places.' }])
})

test('club profile falls back to the former read-only record when either editing route is unavailable', async ({ page }) => {
  const program = { id: 7, slug: 'northbank', name: 'Northbank Juniors', city: 'Leeds', platform_status: 'approved', country: 'England', league: { name: 'Northern Youth League', age_bands: ['U12', 'U14'], data_tier: 'self_reported' }, provenance: { label: 'Self-reported' } }
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/me/club-claims') return route.fulfill({ json: { claims: [] } }).then(() => true)
    if (url.pathname === '/api/me/club') return route.fulfill({ json: { clubs: [] } }).then(() => true)
    if (url.pathname === '/api/funding/claims/me') return route.fulfill({ json: { claims: [{ id: 12, status: 'approved', program }] } }).then(() => true)
    if (url.pathname === '/api/club/7/roster') return route.fulfill({ json: { members: [], system_brief: { body: null, updated_at: null, hash: null } } }).then(() => true)
    if (url.pathname === '/api/club/7/matches') return route.fulfill({ json: { matches: [] } }).then(() => true)
    if (url.pathname === '/api/club/7/profile') return route.fulfill({ json: { program: { id: 7, slug: 'northbank', name: 'Northbank Juniors' }, approved: null, pending: null, limits: { summary_max: 2000, funding_purpose_max: 1000, list_items_max: 12, list_item_max: 40, media_urls_max: 6, updates_pending_max: 5 } } }).then(() => true)
    if (url.pathname === '/api/club/7/updates') return route.fulfill({ status: 404, body: 'Not Found' }).then(() => true)
    return false
  }, { signedIn: true })

  await page.goto('/my-club')
  await page.getByRole('tab', { name: 'Club profile' }).click()
  await expect(page.getByText('Read-only verified program record', { exact: true })).toBeVisible()
  await expect(page.getByText('Northern Youth League', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save for review' })).toHaveCount(0)
})

test('club profile blocks mutations after a failed load and retries both requests', async ({ page }) => {
  let profileGets = 0
  let updateGets = 0
  const program = { id: 7, slug: 'northbank', name: 'Northbank Juniors', city: 'Leeds', platform_status: 'approved', country: 'England', league: { name: 'Northern Youth League', age_bands: ['U12', 'U14'], data_tier: 'self_reported' }, provenance: { label: 'Self-reported' } }
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/me/club-claims') return route.fulfill({ json: { claims: [] } }).then(() => true)
    if (url.pathname === '/api/me/club') return route.fulfill({ json: { clubs: [] } }).then(() => true)
    if (url.pathname === '/api/funding/claims/me') return route.fulfill({ json: { claims: [{ id: 12, status: 'approved', program }] } }).then(() => true)
    if (url.pathname === '/api/club/7/roster') return route.fulfill({ json: { members: [], system_brief: { body: null, updated_at: null, hash: null } } }).then(() => true)
    if (url.pathname === '/api/club/7/matches') return route.fulfill({ json: { matches: [] } }).then(() => true)
    if (url.pathname === '/api/club/7/profile' && request.method() === 'GET') {
      profileGets += 1
      if (profileGets === 1) return route.fulfill({ status: 500, json: { error: 'temporary_failure' } }).then(() => true)
      await route.fulfill({ json: { program: { id: 7, slug: 'northbank', name: 'Northbank Juniors' }, approved: null, pending: null, limits: { summary_max: 2000, funding_purpose_max: 1000, list_items_max: 12, list_item_max: 40, media_urls_max: 6, updates_pending_max: 5 } } })
      return true
    }
    if (url.pathname === '/api/club/7/updates' && request.method() === 'GET') {
      updateGets += 1
      await route.fulfill({ json: { updates: [] } })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto('/my-club')
  await page.getByRole('tab', { name: 'Club profile' }).click()
  await expect(page.getByText("Club profile couldn't be loaded.", { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save for review' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('button', { name: 'Save for review' })).toBeVisible()
  expect(profileGets).toBe(2)
  expect(updateGets).toBe(2)
})

test('GOL asks signed-out visitors to sign in without showing a composer', async ({ page }) => {
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/gol/suggestions') return route.fulfill({ json: { suggestions: ['Compare two academy pathways'] } }).then(() => true)
    return false
  })

  await page.goto('/terms')
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await expect(page.getByText('Sign in to ask GOL', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  await expect(page.getByPlaceholder('Ask about any player or team…')).toHaveCount(0)
})

test('GOL shows the Scout Pro lock only for an explicit false entitlement', async ({ page }) => {
  const account = { ...ACCOUNT, scout_tier: 'free', scout_pro: { enabled: true, tier: 'free', features: { gol_chat: false } } }
  await installApi(page, async ({ route, url }) => {
    if (url.pathname === '/api/gol/suggestions') return route.fulfill({ json: { suggestions: ['Compare two academy pathways'] } }).then(() => true)
    return false
  }, { signedIn: true, account })

  await page.goto('/terms')
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await expect(page.getByText('Scout Pro unlocks GOL', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'View Scout Pro' })).toHaveAttribute('href', '/pricing')
  await expect(page.getByPlaceholder('Ask about any player or team…')).toBeDisabled()
})

test('GOL composer is usable with an explicit true entitlement', async ({ page }) => {
  const chatBodies = []
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/gol/suggestions') return route.fulfill({ json: { suggestions: ['Compare two academy pathways'] } }).then(() => true)
    if (url.pathname === '/api/gol/chat' && request.method() === 'POST') {
      chatBodies.push(request.postDataJSON())
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: token\ndata: {"content":"Academy answer"}\n\nevent: done\ndata: {}\n\n' })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto('/terms')
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  const composer = page.getByPlaceholder('Ask about any player or team…')
  await expect(composer).toBeEnabled()
  await composer.fill('Which academy has the strongest pathway?')
  await page.getByRole('button', { name: 'Send message' }).dispatchEvent('click')
  await expect.poll(() => chatBodies.length).toBe(1)
  expect(chatBodies[0].message).toBe('Which academy has the strongest pathway?')
})

test('GOL clears the prior identity transcript across sign-out and a different sign-in', async ({ page }) => {
  const accountB = {
    ...ACCOUNT,
    email: 'blair.scout@example.com',
    user_id: 84,
    display_name: 'Blair Scout',
  }
  let activeAccount = ACCOUNT

  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/auth/me') return route.fulfill({ json: activeAccount }).then(() => true)
    if (url.pathname === '/api/auth/request-code' && request.method() === 'POST') {
      await route.fulfill({ json: { ok: true } })
      return true
    }
    if (url.pathname === '/api/auth/verify-code' && request.method() === 'POST') {
      activeAccount = accountB
      await route.fulfill({ json: {
        ...accountB,
        token: 'mock-user-b-token',
        expires_in: 3600,
        display_name_confirmed: true,
      } })
      return true
    }
    if (url.pathname === '/api/gol/suggestions') return route.fulfill({ json: { suggestions: ['Compare two academy pathways'] } }).then(() => true)
    if (url.pathname === '/api/gol/chat' && request.method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: token\ndata: {"content":"Private answer for user A"}\n\nevent: done\ndata: {}\n\n' })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto('/terms')
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await page.getByPlaceholder('Ask about any player or team…').fill('Private question from user A')
  await page.getByRole('button', { name: 'Send message' }).dispatchEvent('click')
  await expect(page.getByText('Private answer for user A', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible()

  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Log Out', exact: true }).click()
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await expect(page.getByText('Sign in to ask GOL', { exact: true })).toBeVisible()
  await expect(page.getByText('Private answer for user A', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'PDF', exact: true })).toHaveCount(0)

  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByLabel('Email').fill(accountB.email)
  await page.getByRole('button', { name: 'Send login code' }).click()
  await page.getByLabel('Verification code').fill('test-code-1')
  await page.getByRole('button', { name: 'Verify & sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to The Academy Watch' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await expect(page.getByPlaceholder('Ask about any player or team…')).toBeEnabled()
  await expect(page.getByText('Private answer for user A', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0)
})

test('GOL switches to the locked state after a mid-session Scout Pro rejection', async ({ page }) => {
  let releaseEntitlement
  const entitlementReady = new Promise((resolve) => { releaseEntitlement = resolve })
  await installApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/auth/me') {
      await entitlementReady
      await route.fulfill({ json: ACCOUNT })
      return true
    }
    if (url.pathname === '/api/gol/suggestions') return route.fulfill({ json: { suggestions: ['Compare two academy pathways'] } }).then(() => true)
    if (url.pathname === '/api/gol/chat' && request.method() === 'POST') {
      await route.fulfill({ status: 403, json: { error: 'scout_pro_required', feature: 'gol_chat', upgrade_path: '/pricing' } })
      return true
    }
    return false
  }, { signedIn: true })

  await page.goto('/terms')
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).dispatchEvent('click')
  await page.getByPlaceholder('Ask about any player or team…').fill('Compare academy pathways')
  await page.getByRole('button', { name: 'Send message' }).dispatchEvent('click')
  await expect(page.getByText('Scout Pro unlocks GOL', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'View Scout Pro' })).toHaveAttribute('href', '/pricing')
  await expect(page.getByPlaceholder('Ask about any player or team…')).toBeDisabled()
  await expect(page.getByText('scout_pro_required', { exact: true })).toHaveCount(0)
  await expect(page.getByText(/something went wrong/i)).toHaveCount(0)

  releaseEntitlement()
  await expect(page.getByPlaceholder('Ask about any player or team…')).toBeEnabled()
})
