/* global document, innerWidth */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const oid = '00000000-0000-4000-8000-000000000041'
const rid = '00000000-0000-4000-8000-000000000042'
const post = { id: oid, program_id: 7, title: 'C4 TEST ONLY adult trial', club_name: 'C4 TEST ONLY Club', club_slug: 'c4-test-only', type: 'trial', starts_at: '2026-10-17T10:00:00Z', timezone: 'Europe/London', venue: 'Test ground', birth_year_max: 2005, status: 'published', distance_km: null }
const request = { id: rid, opportunity_id: oid, program_id: 7, title: post.title, note: 'Test only observation request.', status: 'pending', version: 1, scout: { name: 'C4 TEST ONLY Scout', organization: 'Test only organization', role_title: 'Scout', verified: true } }

async function fixture(page, { enabled = true, verified = true, attendance = null, empty = false, conflict = false, coach = false, second = null, introductionsMore = false, editorDates = {} } = {}) {
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem('academy_watch_user_token', 'c4-test-only-token')
    localStorage.setItem('academy_watch_display_name', 'C4 TEST ONLY User')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  let current = attendance ? structuredClone(attendance) : null
  let requestCount = 1
  const writes = []
  const program = { id: 7, name: post.club_name, slug: post.club_slug, platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
  const scopes = coach ? ['players.view', 'players.manage', 'matches.view', 'matches.upload', 'feedback'] : ['players.view', 'recruiting', 'contact', 'matches.view', 'matches.upload', 'players.manage', 'branding', 'staff.directory', 'access.view']
  await page.route('**/api/**', route => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname
    const reply = json => route.fulfill({ json })
    if (p === '/api/scout-attendance/features') return reply({ scout_attend: enabled })
    if (p === '/api/auth/me') return reply({ email: 'c4-test@example.test', display_name: 'C4 TEST ONLY User', display_name_confirmed: true, role: 'user', is_verified_scout: verified })
    if (p === '/api/features') return reply({ club_directory: true, club_staff_access: coach, contact_rail: true, opportunities: true, applications: true })
    if (p === '/api/me/scout-attendance') return reply({ attendance: current ? [current] : [], next_cursor: null })
    if (p === '/api/opportunities/search') { const body = req.postDataJSON(); writes.push({ path: p, body, url: req.url() }); return reply({ opportunities: empty ? [] : [{ ...post, distance_km: body.lat ? 3.2 : null }], has_more: false }) }
    if (p === '/api/club-directory/search') { writes.push({ path: p, body: req.postDataJSON(), url: req.url() }); return reply({ clubs: empty ? [] : [{ id: 7, slug: post.club_slug, name: post.club_name, city: 'Test city', distance_km: null, open_opportunities: 1 }], has_more: false }) }
    if (p === `/api/opportunities/${oid}/attendance`) { writes.push({ path: p, body: req.postDataJSON() }); if (current?.status === 'withdrawn') requestCount++
      current = { ...request, version: current ? current.version + 1 : 1, note: req.postDataJSON().note, can_request_again: false };  return route.fulfill({ status: 201, json: { attendance: current } }) }
    if (p === `/api/me/scout-attendance/${rid}/withdraw`) { writes.push({ path: p, body: req.postDataJSON() }); current = { ...current, status: 'withdrawn', version: current.version + 1, arrival_instructions: undefined, can_request_again: requestCount < 2 }; return reply({ attendance: current }) }
    if (p === '/api/club/7/today') return reply({ program_id: 7, introductions_has_more: introductionsMore, queues: { ...(coach ? {} : { applications: [{ opportunity_id: oid, title: post.title, new: 2, total: 4 }], introductions: Array.from({ length: introductionsMore ? 30 : 1 }, (_, i) => ({ id: `test-introduction-${i}` })), attendance: [...(current?.status === 'pending' ? [current] : []), ...(second ? [second] : [])], accepted_attendance: current?.status === 'accepted' ? [{ id: current.id, opportunity_id: oid, title: current.title, status: current.status, version: current.version, scout: { name: current.scout.name, organization: current.scout.organization, verified: true } }] : [] }), team_sheet: [{ id: 40, opponent_name: 'C4 TEST ONLY opponent' }], analysing: [{ id: 41, opponent_name: 'C4 TEST ONLY analysing match', status: 'processing' }] } })
    if (p === `/api/club/7/attendance/${rid}/decision`) { writes.push({ path: p, body: req.postDataJSON() }); if (conflict) return route.fulfill({ status: 409, json: { error: 'version_conflict' } }); current = { ...current, status: req.postDataJSON().decision, arrival_instructions: req.postDataJSON().decision === 'accepted' ? req.postDataJSON().arrival_instructions : undefined, version: current.version + 1 }; return reply({ attendance: current }) }
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (p === '/api/scout/players') return reply({ players: [], total: 0, page: 1, pages: 1 })
    if (p === '/api/scout/leaderboards') return reply({})
    if (p === '/api/opportunities/features') return reply({ opportunities: true, applications: true })
    if (p === '/api/opportunities') return reply({ opportunities: [post], has_more: false })
    if (p === '/api/funding/claims/me') return reply({ claims: [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] })
    if (p === '/api/me/club-claims') return reply({ claims: [] })
    if (p === '/api/me/club') return reply({ clubs: [] })
    if (p === '/api/me/club-access') return reply({ programs: [] })
    if (p === '/api/club/7/access/me') return reply({ role: 'coach', whole_club: false, all_squads: true, squad_ids: [], capabilities: scopes })
    if (p === '/api/club/7/roster') return reply({ program, members: [], count: 0 })
    if (p === '/api/club/7/map') return reply({ program, squads: [], staff: [], unassigned_count: 0 })
    if (p === '/api/club/7/opportunities') return reply({ opportunities: [{ ...post, description: 'TEST ONLY description', instructions: '', position_requirements: 'All positions', gender_program: 'all', address: '', ends_at: '2026-10-17T12:00:00Z', closes_at: '2026-10-10T10:00:00Z', version: 1, application_count: 0, live_attendance: Boolean(current), ...editorDates }], has_more: false })
    if (p === `/api/club/7/opportunities/${oid}/applications`) return reply({ applications: [], has_more: false })
    if (p === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    return reply({})
  })
  return writes
}

async function shot(page, name) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (!process.env.C4_SCREENSHOTS) return
  await fs.mkdir(process.env.C4_SCREENSHOTS, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.addStyleTag({ content: '[data-agentation-theme] { display:none !important }' })
  await page.screenshot({ path: path.join(process.env.C4_SCREENSHOTS, `${name}.png`), fullPage: true, animations: 'disabled' })
}

for (const width of [1440, 390]) {
  const size = width === 390 ? 'mobile' : 'desktop'
  test(`verified scout asks once, sees accepted instructions and withdraws ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    const errors = []; page.on('pageerror', error => errors.push(error.message))
    const writes = await fixture(page)
    await page.goto('/scout?desk=clubs')
    await expect(page.getByRole('heading', { name: 'Trials & sessions' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Ask to attend' })).toBeEnabled()
    await shot(page, `scout-clubs-trials-testonly-${size}`)
    await page.getByRole('button', { name: 'Ask to attend' }).click()
    await expect(page.getByRole('button', { name: 'Send attendance request' })).toBeDisabled()
    await page.getByLabel('A note to the club').fill('Test only: I would like to observe.')
    await page.getByRole('checkbox').check()
    await shot(page, `ask-to-attend-testonly-${size}`)
    await page.getByRole('button', { name: 'Send attendance request' }).click()
    await expect(page.getByText('Request sent · waiting on the club')).toBeVisible()
    await shot(page, `request-sent-testonly-${size}`)
    const submit = writes.find(r => r.path.endsWith('/attendance'))
    expect(submit.body).toEqual({ note: 'Test only: I would like to observe.', no_approach_confirmed: true })
    await page.getByRole('button', { name: 'Withdraw request' }).click()
    await expect(page.getByText('Attendance withdrawn')).toBeVisible()
    expect(errors).toEqual([])
  })
  test(`club Today accepts attendance and includes scoped queues ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    const writes = await fixture(page, { attendance: request })
    await page.goto('/my-club?program=7&view=today')
    await expect(page.getByRole('heading', { name: 'Attendance requests' })).toBeVisible()
    await expect(page.getByText('C4 TEST ONLY Scout · Test only organization')).toBeVisible()
    await page.getByLabel('Where to stand and who to report to').fill('Test only: report to reception.')
    await shot(page, `club-today-testonly-${size}`)
    await page.getByRole('button', { name: 'Accept attendance' }).click()
    await expect(page.getByText('No attendance requests waiting for your decision.')).toBeVisible()
    expect(writes.find(r => r.path.endsWith('/decision')).body).toEqual({ decision: 'accepted', expected_version: 1, arrival_instructions: 'Test only: report to reception.' })
    await page.goto('/scout?desk=clubs')
    await expect(page.getByText('Attendance accepted')).toBeVisible()
    await expect(page.getByText('Test only: report to reception.')).toBeVisible()
    await shot(page, `attendance-accepted-testonly-${size}`)
  })
  test(`trial distance uses POST and forgets position when switched off ${size}`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await context.grantPermissions(['geolocation']); await context.setGeolocation({ latitude: 35, longitude: 139 })
    const writes = await fixture(page)
    await page.goto('/opportunities')
    await page.getByRole('button', { name: 'Use my location' }).click()
    await expect(page.getByText('3.2 km from you')).toBeVisible()
    await shot(page, `trial-distance-testonly-${size}`)
    const search = writes.find(r => r.path === '/api/opportunities/search')
    expect(search.body).toMatchObject({ lat: 35, lng: 139, radius_km: 50 })
    expect(search.url).not.toContain('lat='); expect(search.url).not.toContain('lng=')
    expect(page.url()).not.toContain('35')
    await page.getByRole('button', { name: 'Turn location off' }).click()
    await expect(page.getByText('Distance unavailable', { exact: true })).toHaveCount(0)
  })
}

test('unverified scout has no attendance write or applicant reads', async ({ page }) => {
  const writes = await fixture(page, { verified: false })
  const privateReads = []; page.on('request', req => { if (/^\/api\/.*(?:applications|scout-attendance$)/.test(new URL(req.url()).pathname)) privateReads.push(req.url()) })
  await page.goto('/scout?desk=clubs')
  await expect(page.getByRole('button', { name: 'Ask to attend' })).toBeDisabled()
  await expect(page.getByText(/Attendance requests are for verified scouts/)).toBeVisible()
  expect(privateReads).toEqual([])
  expect(writes.some(r => r.path.endsWith('/attendance'))).toBe(false)
})

test('flag off preserves existing Scout Desk and club Today controls', async ({ page }) => {
  await fixture(page, { enabled: false })
  await page.goto('/scout')
  await expect(page.getByRole('heading', { name: /Who are you/ })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Clubs & trials' })).toHaveCount(0)
  await page.goto('/my-club?program=7&view=today')
  await expect(page.getByRole('heading', { name: 'The club, today.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Club inbox' })).toHaveCount(0)
})

test('stale club decision keeps the draft and shows a refresh instruction', async ({ page }) => {
  await fixture(page, { attendance: request, conflict: true })
  await page.goto('/my-club?program=7&view=today')
  await page.getByLabel('Where to stand and who to report to').fill('Preserve this draft.')
  await page.getByRole('button', { name: 'Accept attendance' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'This request changed.' })).toBeVisible()
  await expect(page.getByLabel('Where to stand and who to report to')).toHaveValue('Preserve this draft.')
})


for (const width of [1440, 390]) {
  const size = width === 390 ? 'mobile' : 'desktop'
  test(`RC4 club sees accepted scouts and rescinds permission ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    const writes = await fixture(page, { attendance: { ...request, status: 'accepted', version: 2, arrival_instructions: 'TEST ONLY arrival instructions' } })
    await page.goto('/my-club?program=7&view=today')
    await expect(page.getByRole('heading', { name: 'Accepted scouts per session' })).toBeVisible()
    await expect(page.getByText('C4 TEST ONLY Scout · Test only organization')).toBeVisible()
    await expect(page.getByText('Accepted attendance · verified scout')).toBeVisible()
    await expect(page.getByLabel('Where to stand and who to report to')).toHaveCount(0)
    await shot(page, `club-accepted-scouts-testonly-${size}`)
    await page.getByRole('button', { name: 'Rescind attendance' }).click()
    const dialog = page.getByRole('dialog', { name: 'Rescind attendance?' })
    await expect(dialog).toBeVisible()
    expect(writes.filter(r => r.path.endsWith('/decision'))).toHaveLength(0)
    await shot(page, `club-rescind-confirm-testonly-${size}`)
    await dialog.getByRole('button', { name: 'Keep attendance' }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Rescind attendance', exact: true })).toBeFocused()
    expect(writes.filter(r => r.path.endsWith('/decision'))).toHaveLength(0)
    await page.getByRole('button', { name: 'Rescind attendance', exact: true }).click()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Rescind attendance', exact: true })).toBeFocused()
    expect(writes.filter(r => r.path.endsWith('/decision'))).toHaveLength(0)
    await page.getByRole('button', { name: 'Rescind attendance', exact: true }).click()
    await dialog.getByRole('button', { name: 'Confirm rescind' }).click()
    await expect(page.getByText('No accepted scouts for upcoming or ongoing sessions.')).toBeVisible()
    expect(writes.find(r => r.path.endsWith('/decision')).body).toEqual({ decision: 'declined', expected_version: 2, arrival_instructions: '' })
    await page.goto('/scout?desk=clubs')
    await expect(page.getByText('Attendance declined')).toBeVisible()
    await expect(page.getByText('TEST ONLY arrival instructions')).toHaveCount(0)
    await shot(page, `attendance-rescinded-testonly-${size}`)
  })
  test(`RC4 withdrawn scout can ask again once ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await fixture(page, { attendance: { ...request, status: 'withdrawn', version: 2, can_request_again: true } })
    await page.goto('/scout?desk=clubs')
    await expect(page.getByText(/After withdrawing, you may ask again once/)).toBeVisible()
    await page.getByRole('button', { name: 'Ask again' }).click()
    await page.getByLabel('A note to the club').fill('TEST ONLY renewed request')
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: 'Send attendance request' }).click()
    await expect(page.getByText('Request sent · waiting on the club')).toBeVisible()
    await page.getByRole('button', { name: 'Withdraw request' }).click()
    await expect(page.getByText('Attendance withdrawn')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Ask again' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Ask to attend', exact: true })).toHaveCount(0)
    await shot(page, `attendance-retry-used-testonly-${size}`)
  })
}

test('RC4 de-verified scout never renders previously accepted instructions', async ({ page }) => {
  await fixture(page, { verified: false, attendance: { ...request, status: 'accepted', arrival_instructions: 'TEST ONLY secret instructions' } })
  await page.goto('/scout?desk=clubs')
  await expect(page.getByText(/Attendance requests are for verified scouts/)).toBeVisible()
  await expect(page.getByText('TEST ONLY secret instructions')).toHaveCount(0)
})

for (const width of [1440, 390]) {
  test(`C4F2 public distance copy and radius empty recovery ${width}`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await context.grantPermissions(['geolocation'])
    await context.setGeolocation({ latitude: 35, longitude: 139 })
    await fixture(page, { empty: true })
    await page.goto('/opportunities')
    await expect(page.getByRole('heading', { name: post.title })).toBeVisible()
    await expect(page.getByText('Distance unavailable', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Use my location' }).click()
    await expect(page.getByText('No open opportunities with a published location within 50 km.')).toBeVisible()
    await expect(page.getByText('No open opportunities at the moment.', { exact: false })).toHaveCount(0)
    await shot(page, `trial-radius-empty-testonly-${width}`)
    await page.getByRole('button', { name: 'Browse without location' }).click()
    await expect(page.getByRole('heading', { name: post.title })).toBeVisible()
    await expect(page.getByText('Distance unavailable', { exact: true })).toHaveCount(0)
    await shot(page, `trial-location-off-testonly-${width}`)
  })
}

for (const width of [1440, 390]) {
  test(`C4F3 unrelated advert edit keeps live session terms fixed ${width}`, async ({ page }) => {
    if (process.env.C4_E2E_BACKEND_PYTHON) test.setTimeout(60 * 60 * 1000)
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await fixture(page, { attendance: request })
    let saved = null
    await page.route(`**/api/club/7/opportunities/${oid}`, route => {
      saved = route.request().postDataJSON()
      if (process.env.C4_E2E_BACKEND_PYTHON) {
        execFileSync(process.env.C4_E2E_BACKEND_PYTHON, ['-m', 'pytest', '-q', 'tests/test_scout_attendance_editor.py', '-k', 'browser_editor_payload'], {
          cwd: path.resolve('..', 'academy-watch-backend'), timeout: 60 * 60 * 1000,
          env: { ...process.env, C4_BROWSER_EDITOR_PAYLOAD: JSON.stringify(saved), SKIP_API_HANDSHAKE: '1', API_USE_STUB_DATA: 'true', TEST_ONLY_MANU: 'false', OPENAI_API_KEY: 'test-not-a-real-key' },
        })
      }
      return route.fulfill({ json: { opportunity: { ...post, ...saved } } })
    })
    await page.goto('/my-club?program=7&view=recruiting')
    await page.getByRole('button', { name: 'Edit opportunity' }).click()
    const dialog = page.getByRole('dialog')
    for (const label of ['Opportunity type', 'Venue', 'Address', 'Time zone', 'Starts', 'Ends']) {
      await expect(dialog.getByLabel(label, { exact: false }).first()).toBeDisabled()
    }
    await expect(dialog.getByText(/Scout attendance is pending or accepted/)).toBeVisible()
    await dialog.getByLabel('About this opportunity').fill('Corrected TEST ONLY description')
    await shot(page, `live-attendance-editor-testonly-${width}`)
    await dialog.getByText(/Scout attendance is pending or accepted/).scrollIntoViewIfNeeded()
    await shot(page, `live-attendance-editor-lock-testonly-${width}`)
    await dialog.getByRole('button', { name: 'Save opportunity' }).click()
    await expect(dialog).toHaveCount(0)
    expect(saved.description).toBe('Corrected TEST ONLY description')
    expect(saved).toMatchObject({ type: 'trial', venue: 'Test ground', address: '', timezone: 'Europe/London', starts_at: '2026-10-17T10:00:00Z', ends_at: '2026-10-17T12:00:00Z' })
  })
  test(`C4F3 live term conflict has a distinct explanation ${width}`, async ({ page }) => {
    await fixture(page)
    await page.route(`**/api/club/7/opportunities/${oid}`, route => route.fulfill({ status: 409, json: { error: 'advertised_terms_locked' } }))
    await page.goto('/my-club?program=7&view=recruiting')
    await page.getByRole('button', { name: 'Edit opportunity' }).click()
    await page.getByRole('dialog').getByLabel('Venue', { exact: true }).fill('Changed ground')
    await page.getByRole('button', { name: 'Save opportunity' }).click()
    await expect(page.getByRole('alert')).toHaveText(/Advertised details are fixed/)
    await expect(page.getByRole('alert')).not.toHaveText(/changed while you were working/)
  })
  for (const accepted of [false, true]) {
    test(`C4F3 ${accepted ? 'rescind' : 'accept'} preserves another scout draft and useful focus ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await fixture(page, { attendance: { ...request, status: accepted ? 'accepted' : 'pending' }, second: { ...request, id: 'second-request', scout: { ...request.scout, name: 'Second TEST ONLY Scout' } } })
      await page.goto('/my-club?program=7&view=today')
      const second = page.locator('article').filter({ hasText: 'Second TEST ONLY Scout' })
      await second.getByRole('textbox').fill('TEST ONLY unsaved second instructions')
      if (accepted) {
        await page.getByRole('button', { name: 'Rescind attendance', exact: true }).click()
        await page.getByRole('button', { name: 'Confirm rescind' }).click()
      } else {
        await page.getByLabel('Where to stand and who to report to').first().fill('TEST ONLY first instructions')
        await page.getByRole('button', { name: 'Accept attendance' }).first().click()
      }
      await expect(second.getByRole('textbox')).toHaveValue('TEST ONLY unsaved second instructions')
      await expect(second.getByRole('textbox')).toBeFocused()
      await shot(page, `today-preserved-draft-${accepted ? 'rescind' : 'accept'}-testonly-${width}`)
    })
  }
  test(`C4F3 failed rescind announces its error once ${width}`, async ({ page }) => {
    await fixture(page, { attendance: { ...request, status: 'accepted' }, conflict: true })
    await page.goto('/my-club?program=7&view=today')
    await page.getByRole('button', { name: 'Rescind attendance', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm rescind' }).click()
    await expect(page.getByRole('alert', { includeHidden: true })).toHaveCount(1)
    await expect(page.getByRole('dialog').getByRole('alert')).toHaveText(/This request changed/)
    await page.getByRole('button', { name: 'Keep attendance' }).click()
    await expect(page.getByRole('alert', { includeHidden: true })).toHaveCount(1)
  })
  test(`C4F3 scout tab distance off on off keeps club metadata ${width}`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await context.grantPermissions(['geolocation']); await context.setGeolocation({ latitude: 35, longitude: 139 })
    await fixture(page)
    await page.goto('/scout?desk=clubs')
    await expect(page.getByRole('heading', { name: 'Trials & sessions' })).toBeVisible()
    await expect(page.getByText('Distance unavailable', { exact: false })).toHaveCount(0)
    await expect(page.getByText('1 open opportunities', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Use my location' }).click()
    await expect(page.getByText('3.2 km from you')).toBeVisible()
    await expect(page.getByText('Distance unavailable', { exact: false })).toHaveCount(1)
    await shot(page, `scout-shared-location-testonly-${width}`)
    await page.getByRole('button', { name: 'Turn location off' }).click()
    await expect(page.getByText('Distance unavailable', { exact: false })).toHaveCount(0)
    await expect(page.getByText('3.2 km from you')).toHaveCount(0)
    await expect(page.getByText('1 open opportunities', { exact: true })).toBeVisible()
    await shot(page, `scout-location-off-testonly-${width}`)
  })
  test(`C4F3 capped introductions count and exact count ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await fixture(page, { introductionsMore: true })
    await page.goto('/my-club?program=7&view=today')
    const button = page.getByRole('button', { name: /Introductions awaiting your consent/ })
    await expect(button.locator('.ch-task-number')).toHaveText('30+')
    await shot(page, `today-introductions-capped-testonly-${width}`)
    await button.click()
    await expect(page).toHaveURL(/view=introductions/)
    await page.route('**/api/club/7/today', route => route.fulfill({ json: { queues: { introductions: [{ id: 'one' }] }, introductions_has_more: false } }))
    await page.goto('/my-club?program=7&view=today')
    await expect(page.getByRole('button', { name: /Introductions awaiting your consent/ }).locator('.ch-task-number')).toHaveText('1')
  })
}

test('C4F3 last decision focuses inbox heading', async ({ page }) => {
  await fixture(page, { attendance: request })
  await page.goto('/my-club?program=7&view=today')
  await page.getByRole('button', { name: 'Decline attendance' }).click()
  await expect(page.getByRole('heading', { name: 'Club inbox', exact: true })).toBeFocused()
})

test('C4F3 failed read clears private rows and drafts', async ({ page }) => {
  await fixture(page, { attendance: request })
  await page.goto('/my-club?program=7&view=today')
  await page.getByLabel('Where to stand and who to report to').fill('TEST ONLY private draft')
  await page.route('**/api/club/7/today', route => route.fulfill({ status: 403, json: { error: 'forbidden' } }))
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(page.getByText('C4 TEST ONLY Scout · Test only organization')).toHaveCount(0)
  await expect(page.getByLabel('Where to stand and who to report to')).toHaveCount(0)
  await expect(page.getByRole('alert')).toBeVisible()
})


test('C4F3 unchanged locked dates preserve the exact instant in a repeated DST hour', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const dates = { starts_at: '2026-10-25T00:30:37.123Z', ends_at: '2026-10-25T02:30:41.456Z' }
  await fixture(page, { attendance: request, editorDates: dates })
  let saved = null
  await page.route(`**/api/club/7/opportunities/${oid}`, route => {
    saved = route.request().postDataJSON()
    return route.fulfill({ json: { opportunity: { ...post, ...saved } } })
  })
  await page.goto('/my-club?program=7&view=recruiting')
  await page.getByRole('button', { name: 'Edit opportunity' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('About this opportunity').fill('Corrected TEST ONLY description in repeated hour')
  await dialog.getByText(/Scout attendance is pending or accepted/).scrollIntoViewIfNeeded()
  await shot(page, 'live-attendance-dst-testonly-390')
  await dialog.getByRole('button', { name: 'Save opportunity' }).click()
  await expect(dialog.getByRole('alert')).toHaveCount(0)
  await expect(dialog).toHaveCount(0)
  expect(saved).toMatchObject({ ...dates, description: 'Corrected TEST ONLY description in repeated hour' })
})


test('attendance started by A and answered after switching to B leaves B untouched', async ({ page }) => {
  await fixture(page, { attendance: { ...request, status: 'accepted', arrival_instructions: 'A only instructions' } })
  const sent = []
  page.on('request', req => { if (new URL(req.url()).pathname.startsWith('/api/')) sent.push({ path: new URL(req.url()).pathname, token: req.headers().authorization }) })
  await page.route('**/api/me/scout-attendance', route => route.request().headers().authorization === 'Bearer c4-account-b'
    ? route.fulfill({ json: { attendance: [], next_cursor: null } }) : route.fallback())
  let release
  const held = new Promise(resolve => { release = resolve })
  let started = false
  await page.route(`**/api/me/scout-attendance/${rid}/withdraw`, async route => {
    started = true
    await held
    await route.fulfill({ json: { attendance: { ...request, status: 'withdrawn', version: 2 } } })
  })
  await page.goto('/scout?desk=clubs')
  await expect(page.getByText('A only instructions')).toBeVisible()
  await page.getByRole('button', { name: 'Withdraw request' }).click()
  await expect.poll(() => started).toBe(true)
  await page.evaluate(async () => {
    const { APIService } = await import('/src/lib/api.js')
    APIService.setUserToken('c4-account-b')
  })
  await expect(page.getByText('A only instructions')).toHaveCount(0)
  await page.getByRole('button', { name: 'Ask to attend', exact: true }).click()
  const draft = page.getByRole('textbox', { name: 'A note to the club' })
  await draft.fill('B private draft remains')
  const count = sent.length
  const answer = page.waitForResponse(response => response.url().endsWith(`/me/scout-attendance/${rid}/withdraw`))
  release()
  await answer
  await page.waitForTimeout(300)
  expect(sent.slice(count)).toEqual([])
  await expect(draft).toHaveValue('B private draft remains')
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('academy_watch_user_token'))).toBe('c4-account-b')
})
