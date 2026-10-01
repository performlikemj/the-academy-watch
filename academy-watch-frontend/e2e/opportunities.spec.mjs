/* global document, innerWidth */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

// Clearly synthetic browser fixtures; the app has no fixture/fallback data path.
const oid = '00000000-0000-4000-8000-000000000001'
const aid = '00000000-0000-4000-8000-000000000002'
const opportunity = { id: oid, program_id: 7, club_name: 'Synthetic B2 Club', club_slug: 'synthetic-b2', type: 'trial', title: 'Adult development trial', description: 'A synthetic opportunity used only to check the application workflow.', instructions: 'Bring boots, shin pads and water.', venue: 'Test training ground', address: 'Test pitch', timezone: 'Europe/London', starts_at: '2026-10-20T10:00:00Z', ends_at: '2026-10-20T12:00:00Z', closes_at: '2026-10-18T12:00:00Z', birth_year_min: 1998, birth_year_max: 2008, gender_program: 'all', position_requirements: 'All positions', status: 'published', version: 1, coach: 'Club coaching team', application_count: 1 }
const application = { id: aid, opportunity_id: oid, program_id: 7, opportunity_title: opportunity.title, club_name: opportunity.club_name, timezone: 'Europe/London', claim_id: 3, signed_player_id: 7001, applicant_name: 'Synthetic Adult Applicant', position: 'Midfielder', current_club: '', profile_available: true, status: 'new', status_label: 'Applied', submitted_at: '2026-10-01T10:00:00Z', retention_expires_at: '2027-01-18T10:00:00Z', version: 1, reservation_state: 'none', transitions: ['rejected', 'shortlisted'], notes: [], events: [{ version: 1, created_at: '2026-10-01T10:00:00Z', reason_code: 'submitted' }] }

async function fixture(page, { on = true, apps = true, empty = false, invited = false, deniedClaims = false, conflict = false, unavailableAction = null, unavailableStatus = 404, held = false } = {}) {
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'b2-synthetic-browser-token')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    localStorage.setItem('academy_watch_display_name', 'Synthetic B2 User')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
  })
  let current = structuredClone(application)
  if (invited) current = { ...current, status: 'invited', status_label: 'Invited to trial', reservation_state: 'pending', trial_at: '2026-10-20T10:00:00Z', trial_venue: 'Test training ground', trial_instructions: 'Bring your boots.', transitions: ['attended', 'rejected'], version: 3 }
  let unavailable = false
  const requests = []
  const program = { id: 7, name: opportunity.club_name, slug: opportunity.club_slug, platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname
    const reply = json => route.fulfill({ json })
    if (p === '/api/opportunities/features') return on ? reply({ opportunities: on, applications: on && apps }) : route.fulfill({ status: 404, json: { error: 'Not found' } })
    if (p === '/api/opportunities') return reply({ opportunities: empty ? [] : [opportunity], has_more: false })
    if (p === `/api/opportunities/${oid}`) return reply({ opportunity })
    if (p === '/api/me/application-claims') return reply({ claims: deniedClaims ? [] : [{ claim_id: 3, signed_player_id: 7001, name: 'Synthetic Adult Applicant' }] })
    if (p === `/api/opportunities/${oid}/applications`) { requests.push(req.postDataJSON()); return route.fulfill({ status: 201, json: { application: current } }) }
    if (p === '/api/me/applications') return reply({ applications: empty ? [] : [current] })
    if (p === `/api/club/7/applications/${aid}`) return reply({ application: current })
    if (p === `/api/me/applications/${aid}/withdraw`) { requests.push(req.postDataJSON()); current = { ...current, status: 'withdrawn', status_label: 'Withdrawn', version: current.version + 1, reservation_state: 'released' }; return reply({ application: current }) }
    if (p === `/api/me/applications/${aid}/trial-response`) { if (held) return route.fulfill({ status: 403, json: { error: 'temporarily_unavailable' } }); requests.push(req.postDataJSON()); current = { ...current, reservation_state: 'confirmed', version: current.version + 1 }; return reply({ application: current }) }
    if (p === '/api/club/7/opportunities' && req.method() === 'POST') { requests.push(req.postDataJSON()); return route.fulfill({ status: 201, json: { opportunity } }) }
    if (p === '/api/club/7/opportunities') return reply({ opportunities: empty ? [] : [{ ...opportunity, ...(held ? { capacity: 1, places_left: 0, temporarily_unavailable_reservations: 1 } : {}) }] })
    if (p === `/api/club/7/opportunities/${oid}/applications`) return reply({ applications: empty || unavailable || held ? [] : [current] })
    if (p === `/api/club/7/applications/${aid}/transition`) {
      if (unavailableAction === 'transition') { unavailable = true; return route.fulfill({ status: unavailableStatus, json: { error: 'Not found' } }) }
      const body = req.postDataJSON(); requests.push(body)
      current = { ...current, status: body.status, status_label: 'With the club', version: current.version + 1, transitions: ['invited', 'rejected'] }
      if (body.status === 'invited') current = { ...current, ...body, reservation_state: 'pending', transitions: ['attended', 'rejected'] }
      if (conflict) return route.fulfill({ status: 409, json: { error: 'version_conflict' } })
      return reply({ application: current })
    }
    if (p === `/api/club/7/applications/${aid}/notes`) { if (unavailableAction === 'notes') { unavailable = true; return route.fulfill({ status: unavailableStatus, json: { error: 'Not found' } }) } const body = req.postDataJSON(); requests.push(body); current.notes.push({ id: 'note', body: body.body, created_at: '2026-10-01T10:00:00Z' }); return route.fulfill({ status: 201, json: { note: current.notes[0] } }) }
    if (p === `/api/club/7/opportunities/${oid}/close`) { requests.push(req.postDataJSON()); return reply({ opportunity: { ...opportunity, status: 'closed', version: 2 } }) }
    if (p === '/api/funding/claims/me') return reply({ claims: [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] })
    if (p === '/api/me/club-claims') return reply({ claims: [] })
    if (p === '/api/me/club') return reply({ clubs: [] })
    if (p === '/api/club/7/roster') return reply({ program, members: [], count: 0 })
    if (p === '/api/club/7/map') return reply({ program, squads: [], staff: [], unassigned_count: 0 })
    if (p === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (p === '/api/auth/me') return reply({ email: 'b2-test@example.test', display_name: 'Synthetic B2 User', display_name_confirmed: true, role: 'user' })
    return reply({})
  })
  return requests
}

async function shot(page, name) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (!process.env.B2_SCREENSHOTS) return
  await fs.mkdir(process.env.B2_SCREENSHOTS, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: path.join(process.env.B2_SCREENSHOTS, `${name}.png`), fullPage: true, animations: 'disabled' })
}

for (const width of [1440, 390]) {
  const size = width === 390 ? 'mobile' : 'desktop'
  for (const entry of ['list', 'detail']) {
    test(`anonymous visitor on opportunity ${entry} makes zero authenticated requests or 401s at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await page.addInitScript(() => localStorage.clear())
      const authenticatedRequests = []
      const unauthorizedResponses = []
      const publicRequests = []
      page.on('response', response => { if (response.status() === 401) unauthorizedResponses.push(response.url()) })
      // Deny everything except the public reads needed by these pages and the shell.
      await page.route('**/api/**', route => {
        const req = route.request(), p = new URL(req.url()).pathname
        const publicReplies = {
          '/api/meta/data-mode': { api_football_frozen: false },
          '/api/sync-status': { syncing: false },
          '/api/features': {},
          '/api/opportunities/features': { opportunities: true, applications: true },
          '/api/opportunities': { opportunities: [opportunity], has_more: false },
          [`/api/opportunities/${oid}`]: { opportunity },
        }
        if (req.method() !== 'GET' || req.headers().authorization || !Object.hasOwn(publicReplies, p)) {
          authenticatedRequests.push(`${req.method()} ${p}`)
          return route.fulfill({ status: 401, json: { error: 'Sign in required' } })
        }
        publicRequests.push(p)
        return route.fulfill({ json: publicReplies[p] })
      })
      if (entry === 'list') {
        await page.goto('/opportunities')
        await expect(page.getByRole('heading', { name: 'Open opportunities' })).toBeVisible()
        await expect(page.getByRole('link', { name: /Synthetic B2 Club.*Adult development trial/ })).toBeVisible()
        await page.waitForLoadState('networkidle')
        expect(authenticatedRequests).toEqual([])
        expect(unauthorizedResponses).toEqual([])
        expect(publicRequests).toContain('/api/opportunities')
        await page.getByRole('link', { name: /Synthetic B2 Club.*Adult development trial/ }).click()
      } else {
        await page.goto(`/opportunities/${oid}`)
      }
      await expect(page.getByRole('heading', { name: 'Take the next step.' })).toBeVisible()
      await expect(page.getByText('Sign in and claim your adult player profile to apply.')).toBeVisible()
      await expect(page.getByRole('link', { name: 'Find my profile' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
      await expect(page.getByText('Checking your profiles…')).toHaveCount(0)
      await expect(page.getByRole('alert')).toHaveCount(0)
      await page.waitForLoadState('networkidle')
      expect(publicRequests).toContain(`/api/opportunities/${oid}`)
      expect(authenticatedRequests).toEqual([])
      expect(unauthorizedResponses).toEqual([])
    })
  }
  test(`public opportunities and adult submission at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    const requests = await fixture(page)
    await page.goto('/opportunities')
    await expect(page.getByRole('heading', { name: 'Open opportunities' })).toBeVisible()
    await shot(page, `opportunities-${size}`)
    await page.getByRole('link', { name: /Synthetic B2 Club.*Adult development trial/ }).click()
    await expect(page.getByRole('heading', { name: 'Take the next step.' })).toBeVisible()
    await expect(page.getByText('A path for younger players.')).toBeVisible()
    await expect(page.getByText(/places available/)).toHaveCount(0)
    await page.getByLabel('Position', { exact: true }).fill('Midfielder')
    await page.getByRole('checkbox', { name: /I agree/ }).check()
    await shot(page, `opportunity-detail-${size}`)
    await page.getByRole('button', { name: 'Send application', exact: true }).click()
    await expect(page.getByText('Application sent.', { exact: true })).toBeVisible()
    expect(requests[0]).toMatchObject({ claim_id: 3, contact_consent: true, position: 'Midfielder' })
    expect(requests[0]).not.toHaveProperty('child_name')
  })
  test(`player invitation confirmation and withdrawal at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await fixture(page, { invited: true })
    await page.goto('/onboarding/player')
    await expect(page.getByRole('heading', { name: 'My applications' })).toBeVisible()
    await shot(page, `player-home-${size}`)
    await page.getByRole('button', { name: 'Confirm trial' }).click()
    await expect(page.getByText('Your place is confirmed.')).toBeVisible()
    await page.getByRole('button', { name: 'Withdraw application' }).click()
    await expect(page.getByText('Withdrawn', { exact: true })).toBeVisible()
  })
  test(`recruiting stage, private note, invitation, editor at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    const requests = await fixture(page)
    await page.goto('/my-club?view=recruiting')
    await expect(page.getByRole('heading', { name: 'Adult development trial', exact: true })).toBeVisible()
    await shot(page, `recruiting-${size}`)
    await page.getByRole('button', { name: 'Synthetic Adult Applicant' }).click()
    await page.getByLabel('Private note', { exact: true }).fill('Synthetic private review')
    await page.getByRole('button', { name: 'Add note', exact: true }).click()
    await expect(page.getByText('Synthetic private review', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: /Shortlist →/ }).click()
    await page.getByRole('button', { name: 'Invite to trial →' }).click()
    await page.getByLabel('Trial (Europe/London)', { exact: true }).fill('2026-10-20T10:00')
    await page.getByLabel('Trial venue', { exact: true }).fill('Test ground')
    await page.getByRole('button', { name: 'Send trial invitation' }).click()
    await expect(page.getByRole('button', { name: 'Reschedule trial' })).toBeVisible()
    await page.getByRole('button', { name: '+ New opportunity' }).click()
    await expect(page.getByRole('dialog', { name: 'New opportunity' })).toBeVisible()
    await page.getByLabel('Title', { exact: true }).fill('Synthetic new vacancy')
    await page.getByLabel('Opportunity type', { exact: true }).selectOption('position')
    await page.getByLabel('About this opportunity', { exact: true }).fill('A synthetic test vacancy only.')
    await page.getByLabel('Venue', { exact: true }).fill('Test ground')
    await page.getByLabel(/Applications close \(/).fill('2026-10-18T12:00')
    await shot(page, `opportunity-editor-${size}`)
    await page.getByRole('dialog').evaluate(dialog => { dialog.scrollTop = 0 })
    await shot(page, `opportunity-editor-top-${size}`)
    await page.getByRole('button', { name: 'Save opportunity', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(requests.some(r => r.status === 'shortlisted' && r.expected_version === 1)).toBe(true)
    expect(requests.some(r => r.status === 'invited' && r.trial_venue === 'Test ground')).toBe(true)
    expect(requests.some(r => r.type === 'position' && r.title === 'Synthetic new vacancy')).toBe(true)
  })
  test(`empty public opportunities at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await fixture(page, { empty: true })
    await page.goto('/opportunities')
    await expect(page.getByText('No open opportunities at the moment. Check back for your next step.')).toBeVisible()
    await shot(page, `opportunities-empty-${size}`)
  })
}

test('dark launch preserves all three teasers', async ({ page }) => {
  await fixture(page, { on: false })
  await page.goto('/opportunities')
  await expect(page.getByRole('heading', { name: 'Hear first' })).toBeVisible()
  await page.goto('/onboarding/player')
  await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toBeVisible()
  await page.goto('/my-club?view=recruiting')
  await expect(page.getByRole('heading', { name: 'The next player. The right place.' })).toBeVisible()
  await expect(page.getByRole('button', { name: '+ New opportunity' })).toHaveCount(0)
})

test('applications independently dark and no eligible claim stays a signup', async ({ page }) => {
  await fixture(page, { apps: false })
  await page.goto(`/opportunities/${oid}`)
  await expect(page.getByRole('heading', { name: 'Applications are coming.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
})

test('missing adult claim offers the existing claim flow', async ({ page }) => {
  await fixture(page, { deniedClaims: true })
  await page.goto(`/opportunities/${oid}`)
  await expect(page.getByRole('link', { name: 'Find my profile' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
})

test('concurrent decision refreshes pipeline after version conflict', async ({ page }) => {
  await fixture(page, { conflict: true })
  await page.goto('/my-club?view=recruiting')
  await page.getByRole('button', { name: /Shortlist →/ }).click()
  await expect(page.getByRole('button', { name: 'Invite to trial →' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Shortlist →/ })).toHaveCount(0)
})

test('legacy unsupported zones cannot crash list, detail, applicant home or club pipeline', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await fixture(page, { invited: true })
  const bad = { ...opportunity, timezone: 'Factory' }
  const badApplication = { ...application, timezone: 'posixrules', status: 'invited', reservation_state: 'pending', trial_at: '2026-10-10T17:00:00Z', trial_venue: 'Ground' }
  await page.route('**/api/opportunities?*', route => route.fulfill({ json: { opportunities: [bad], has_more: false } }))
  await page.route(`**/api/opportunities/${oid}`, route => route.fulfill({ json: { opportunity: bad } }))
  await page.route('**/api/me/applications?*', route => route.fulfill({ json: { applications: [badApplication], has_more: false } }))
  await page.route('**/api/club/7/opportunities?*', route => route.fulfill({ json: { opportunities: [bad], has_more: false } }))
  await page.route(`**/api/club/7/opportunities/${oid}/applications?*`, route => route.fulfill({ json: { applications: [badApplication], has_more: false } }))
  await page.goto('/opportunities')
  await expect(page.getByRole('heading', { name: 'Open opportunities' })).toBeVisible()
  await expect(page.getByText(/20 Oct 2026, 10:00 UTC \(UTC\)/)).toBeVisible()
  await page.goto(`/opportunities/${oid}`)
  await expect(page.getByRole('heading', { name: 'Take the next step.' })).toBeVisible()
  await expect(page.getByText(/Applications close.*UTC \(UTC\)/)).toBeVisible()
  await page.goto('/onboarding/player')
  await expect(page.getByText(/Trial.*10 Oct 2026, 17:00 UTC \(UTC\)/)).toBeVisible()
  await page.goto('/my-club?view=recruiting')
  await expect(page.getByRole('button', { name: 'Synthetic Adult Applicant' })).toBeVisible()
  await expect(page.getByText(/10 Oct 2026, 17:00 UTC \(UTC\)/)).toBeVisible()
  expect(errors).toEqual([])
  await shot(page, 'legacy-timezone-fallback-desktop')
})

test('opportunities render error boundary keeps app navigation and offers reload', async ({ page }) => {
  await fixture(page)
  await page.route('**/api/opportunities?*', route => route.fulfill({ json: { opportunities: [{ ...opportunity, type: null }], has_more: false } }))
  await page.goto('/opportunities')
  await expect(page.getByRole('alert').filter({ hasText: 'We could not display this opportunity.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reload', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Academy Watch/i }).first()).toBeVisible()
})

test('pipeline pagination and detail-only history remain usable', async ({ page }) => {
  await fixture(page)
  await page.route(`**/api/club/7/opportunities/${oid}/applications?*`, async route => {
    const second = new URL(route.request().url()).searchParams.get('page') === '2'
    const row = second ? { ...application, id: '00000000-0000-4000-8000-000000000003', applicant_name: 'Synthetic second page' } : application
    const { notes: _notes, events: _events, ...boardRow } = row
    return route.fulfill({ json: { applications: [boardRow], has_more: !second } })
  })
  await page.goto('/my-club?view=recruiting')
  await page.getByRole('button', { name: 'Synthetic Adult Applicant' }).click()
  await expect(page.getByText('submitted', { exact: false }).last()).toBeVisible()
  await page.getByRole('button', { name: 'Next applications', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Synthetic second page' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Synthetic Adult Applicant' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Previous applications', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Synthetic Adult Applicant' })).toBeVisible()
})

test('every accepted canonical IANA zone is supported by real Chromium Intl', async ({ page }) => {
  const zones = JSON.parse(await fs.readFile(new URL('../../academy-watch-backend/src/data/opportunity_timezones.json', import.meta.url), 'utf8'))
  expect(await page.evaluate(zones => zones.filter(timeZone => {
    try { new Intl.DateTimeFormat('en-GB', { timeZone }).format(new Date()); return false } catch { return true }
  }), zones)).toEqual([])
})

for (const status of [403, 404]) {
  for (const action of ['transition', 'notes']) {
    test(`unavailable candidate disappears after ${action} ${status} without reload`, async ({ page }) => {
      await fixture(page, { unavailableAction: action, unavailableStatus: status })
      await page.goto('/my-club?view=recruiting')
      await expect(page.getByRole('button', { name: 'Synthetic Adult Applicant' })).toBeVisible()
      if (action === 'transition') await page.getByRole('button', { name: /Shortlist →/ }).click()
      else {
        await page.getByRole('button', { name: 'Synthetic Adult Applicant' }).click()
        await page.getByLabel('Private note', { exact: true }).fill('Synthetic private review')
        await page.getByRole('button', { name: 'Add note', exact: true }).click()
      }
      await expect(page.getByRole('button', { name: 'Synthetic Adult Applicant' })).toHaveCount(0)
      await expect(page.getByRole('heading', { name: 'Adult development trial', exact: true })).toBeVisible()
    })
  }
}

for (const width of [1440, 390]) {
  test(`held applicant receives a neutral temporary message at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await fixture(page, { invited: true, held: true })
    await page.goto('/onboarding/player')
    await page.getByRole('button', { name: 'Confirm trial' }).click()
    await expect(page.getByRole('alert')).toHaveText('Temporarily unavailable. Please try again later.')
    await expect(page.getByText('An approved adult player claim and current access are required.')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Withdraw application' })).toBeEnabled()
  })

  test(`held reservation is explained to staff without identity at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await fixture(page, { invited: true, held: true })
    await page.goto('/my-club?view=recruiting')
    await expect(page.getByText('1 place reserved — applicant temporarily unavailable', { exact: true })).toBeVisible()
    await expect(page.getByText('0 of 1 trial places available')).toBeVisible()
    await expect(page.getByText('Synthetic Adult Applicant')).toHaveCount(0)
  })
}

test('all Chromium device-default zone spellings resolve, format and round-trip via committed aliases', async ({ page }) => {
  const zones = JSON.parse(await fs.readFile(new URL('../src/lib/opportunity-timezones.json', import.meta.url), 'utf8'))
  await fixture(page)
  await page.goto('/opportunities')
  const failures = await page.evaluate(async zones => {
    const { canonicalTimezone, when, localInput, fromLocalInput } = await import('/src/lib/opportunity-time.js')
    const failures = []
    const instant = '2026-10-10T17:00:00.000Z'
    for (const zone of zones) {
      const deviceDefault = new Intl.DateTimeFormat('en-GB', { timeZone: zone }).resolvedOptions().timeZone
      if (!zones.includes(deviceDefault)) { failures.push(deviceDefault); continue }
      const canonical = canonicalTimezone(deviceDefault)
      if (!when(instant, deviceDefault).endsWith(`(${canonical})`)) failures.push(`${deviceDefault}: format`)
      if (fromLocalInput(localInput(instant, deviceDefault), deviceDefault) !== instant) failures.push(`${deviceDefault}: round-trip`)
    }
    return failures
  }, zones)
  expect(failures).toEqual([])
})

for (const [legacy, canonical] of [['Asia/Calcutta', 'Asia/Kolkata'], ['Europe/Kiev', 'Europe/Kyiv'], ['America/Indianapolis', 'America/Indiana/Indianapolis']]) {
  test(`editor canonicalizes Chromium device default ${legacy}`, async ({ browser }) => {
    const context = await browser.newContext({ timezoneId: legacy })
    try {
      const page = await context.newPage()
      await fixture(page)
      await page.goto('/my-club?view=recruiting')
      await page.getByRole('button', { name: 'New opportunity' }).click()
      await expect(page.getByLabel('Time zone (for example Europe/London)')).toHaveValue(canonical)
    } finally { await context.close() }
  })
}
