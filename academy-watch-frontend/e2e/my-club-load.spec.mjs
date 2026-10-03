/* global document, MutationObserver, window */
import path from 'node:path'
import { expect, test } from '@playwright/test'

// Fictional Ruth persona; real routed component, synthetic API data only.
const program = { id: 7, name: 'Ruth Calloway Test Club', slug: 'ruth-test-club', platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
const squads = [{ id: 12, name: 'Under-18s', member_count: 0 }]
const all = ['players.view', 'players.manage', 'matches.view', 'matches.upload', 'feedback', 'recruiting', 'contact', 'results', 'player_invitations', 'branding', 'staff.directory', 'access.view', 'access.manage', 'billing']
const capabilities = {
  owner: all,
  manager: all.filter(c => !['contact', 'results', 'player_invitations', 'access.manage', 'billing'].includes(c)),
  coach: ['players.view', 'matches.view', 'matches.upload', 'feedback'],
  analyst: ['players.view', 'matches.view', 'matches.upload'],
  viewer: ['players.view', 'matches.view'],
  'staff-only': ['players.view', 'matches.view'],
}
const endpoints = {
  claims: '/api/funding/claims/me',
  eligibility: '/api/club/7/roster',
  staff: '/api/me/club-access',
  features: '/api/features',
  legacy: '/api/me/club-claims',
  clubs: '/api/me/club',
}
function barrier() {
  let release
  const promise = new Promise(resolve => { release = resolve })
  return { promise, release }
}
async function mock(page, { role = 'owner', flag = true, legacy = false, programs = [program] } = {}) {
  const state = { calls: [], hold: null, failure: null, failures: new Set(), denied: null, affiliations: [] }
  const access = { program_id: 7, role: role === 'staff-only' ? 'viewer' : role, verified: role === 'owner', whole_club: ['owner', 'manager'].includes(role), squad_ids: [12], capabilities: capabilities[role] || [] }
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-ruth')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    window.clubEmptyFlashed = false
    new MutationObserver(records => {
      if (records.some(record => [...record.addedNodes].some(node => node.textContent?.includes('Represent a club?')))) window.clubEmptyFlashed = true
    }).observe(document, { childList: true, subtree: true })
  })
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const p = url.pathname
    state.calls.push(p)
    const reply = json => route.fulfill({ json })
    const held = state.hold?.endpoint === p ? state.hold : null
    if (held) {
      await held.promise
      if (held.json) return reply(held.json)
    }
    if (state.denied === p) return route.fulfill({ status: 403, json: { error: 'Synthetic denied' } })
    if (state.failure === p || state.failures.has(p)) return route.fulfill({ status: 503, json: { error: 'Synthetic unavailable' } })
    if (p === '/api/me/club/affiliations/41/confirm') {
      state.failure = endpoints.clubs
      return reply({})
    }
    if (p === '/api/auth/me') return reply({ email: 'ruth@example.test', display_name: 'Ruth Calloway', display_name_confirmed: true, role: 'user', scout_pro: { enabled: false } })
    if (p === endpoints.features) return reply({ club_staff_access: flag, contact_rail: false })
    if (p === endpoints.claims) return reply({ claims: ['owner', 'manager'].includes(role) && !legacy ? programs.map(p => ({ id: p.id, status: 'approved', relationship_type: 'club_official', program: p })) : [] })
    if (p === endpoints.staff) return reply({ programs: !['owner', 'manager', 'none'].includes(role) ? programs.map(p => ({ program: p, access })) : [] })
    if (p === endpoints.legacy) return reply({ claims: legacy ? [{ id: 31, status: 'approved', club_name: program.name, role_title: 'Owner' }] : [] })
    if (p === endpoints.clubs) return reply({ clubs: legacy ? [{ claim: { id: 31 }, club_name: program.name, pending_affiliations: state.affiliations, vouchable_player_claims: [] }] : [] })
    if (/^\/api\/club\/\d+\/access\/me$/.test(p)) return reply({ access })
    if (/^\/api\/club\/\d+\/roster$/.test(p)) return reply({ program: programs.find(row => row.id === Number(p.split('/')[3])), members: [], count: 0 })
    if (/^\/api\/club\/\d+\/map$/.test(p)) return reply({ program: programs.find(row => row.id === Number(p.split('/')[3])), squads, staff: [], unassigned_count: 0 })
    if (p === '/api/club/7/roster/8/profile') return reply({ identity: { id: 8, available: true, display_name: 'Synthetic U18 Player', is_minor: true, squad_id: 12, squad: squads[0] }, scout_interest: { locked: true }, pathway: [] })
    if (p === '/api/club/7/access') return reply({ me: access, people: [], invites: [], activity: [], matrix: { rows: [] } })
    if (p === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    if (p === '/api/club/7/results') return reply({ results: [] })
    if (p === '/api/club/7/profile') return reply({ program, approved: null, pending: null, updates: [] })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    return reply({})
  })
  return state
}
async function expectConsole(page, heading = 'Matches & reports') {
  await expect(page.locator('.club-home')).toBeVisible()
  const title = ['Private roster', 'Edit program profile'].includes(heading)
    ? page.getByText(heading, { exact: true })
    : page.getByRole('heading', { name: heading, exact: true })
  await expect(title.first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
  expect(await page.evaluate(() => window.clubEmptyFlashed)).toBe(false)
}

for (const width of [390, 1440]) test(`Matches reload evidence at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 })
  const state = await mock(page)
  await page.goto('/my-club?program=7&view=matches')
  await expect(page.getByRole('heading', { name: 'Matches & reports' })).toBeVisible()
  const hold = barrier()
  state.hold = { endpoint: endpoints.claims, ...hold }
  await page.reload()
  await expect.poll(() => state.calls.filter(p => p === endpoints.claims).length).toBe(2)
  const before = process.env.MYC1_BEFORE === '1'
  if (before) await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
  else {
    await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
  }
  if (process.env.MYC1_SHOTS_DIR) await page.screenshot({ path: path.join(process.env.MYC1_SHOTS_DIR, `${before ? 'before' : 'after'}/matches-reload-${width}.png`), fullPage: true })
  hold.release()
  await expect(page.getByRole('heading', { name: 'Matches & reports' })).toBeVisible()
  if (!before) {
    await expectConsole(page)
    if (process.env.MYC1_SHOTS_DIR) await page.screenshot({ path: path.join(process.env.MYC1_SHOTS_DIR, `after/matches-settled-${width}.png`), fullPage: true })
  }
})

const views = [
  ['today', 'The club, today.'], ['map', 'Club map'], ['squad', 'Unassigned'], ['matches', 'Matches & reports'],
  ['recruiting', 'The next player. The right place.'], ['introductions', null], ['branding', 'Make it your club'], ['squads', 'Squads & age groups'],
  ['staff', 'Staff directory'], ['roster', 'Private roster'], ['profile', 'Edit program profile'], ['affiliations', null], ['player', 'Synthetic U18 Player'],
]
for (const role of [...Object.keys(capabilities), 'none']) test(`${role}: reload every console page retains URL and permitted view`, async ({ page }) => {
  await mock(page, { role })
  for (const [view, heading] of views) {
    const url = view === 'player' ? '/my-club?program=7&player=8' : `/my-club?program=7&view=${view}`
    await page.goto(url)
    if (role === 'none') await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
    else await expect(page.locator('.club-home')).toBeVisible()
    await page.reload()
    if (role === 'none') await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
    else {
      const allowed = ['today', 'map', 'squad', 'matches', 'player'].includes(view) || ['owner', 'manager'].includes(role) && (role === 'owner' || !['introductions', 'affiliations'].includes(view))
      if (!allowed) await expectConsole(page, 'Club map')
      else if (heading) await expectConsole(page, heading)
      else {
        await expect(page.locator('.club-home')).toBeVisible()
        expect(await page.evaluate(() => window.clubEmptyFlashed)).toBe(false)
        await expect(page.locator('.ch-settings-nav button[aria-current="page"], .ch-rail button[aria-current="page"]')).not.toHaveCount(0)
      }
    }
    expect(new URL(page.url()).search).toBe(new URL(url, page.url()).search)
  }
})

for (const source of ['claims', 'eligibility', 'staff', 'features', 'legacy', 'clubs']) test(`slow ${source}: loader persists until club-granting reads settle`, async ({ page }) => {
  const state = await mock(page, { role: source === 'staff' ? 'staff-only' : 'owner' })
  const hold = barrier()
  state.hold = { endpoint: endpoints[source], ...hold }
  await page.goto('/my-club?program=7&view=matches')
  await expect.poll(() => state.calls.includes(endpoints[source])).toBe(true)
  await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
  if (source === 'features') expect(state.calls.filter(p => p === endpoints.staff)).toHaveLength(0)
  hold.release()
  await expectConsole(page)
})

for (const source of ['claims', 'eligibility', 'staff', 'features', 'legacy', 'clubs']) for (const role of ['owner', 'staff-only', 'none']) {
  if (source === 'eligibility' && role === 'none') continue
  test(`${role} failed ${source}: Retry replaces empty state and recovers same page`, async ({ page }) => {
    const state = await mock(page, { role })
    state.failure = endpoints[source]
    await page.goto('/my-club?program=7&view=matches')
    await expect(page.getByText("We couldn't load your club. Try again.")).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
    const previous = state.calls.filter(p => p === endpoints[source]).length
    state.failure = null
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    if (role === 'none') await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
    else await expectConsole(page)
    expect(state.calls.filter(p => p === endpoints[source]).length).toBeGreaterThan(previous)
    expect(new URL(page.url()).search).toBe('?program=7&view=matches')
  })
}

for (const source of ['claims', 'staff', 'features']) test(`no club: slow ${source} is not an empty answer`, async ({ page }) => {
  const state = await mock(page, { role: 'none' })
  const hold = barrier()
  state.hold = { endpoint: endpoints[source], ...hold }
  await page.goto('/my-club?view=matches')
  await expect.poll(() => state.calls.includes(endpoints[source])).toBe(true)
  await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
  hold.release()
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
})

test('legacy claims keep their moderation workspace; flag OFF makes no staff request', async ({ page }) => {
  const state = await mock(page, { legacy: true, flag: false })
  await page.goto('/my-club')
  await expect(page.getByText('Your club claims')).toBeVisible()
  await expect(page.getByRole('heading', { name: program.name, level: 2 })).toBeVisible()
  expect(await page.evaluate(() => window.clubEmptyFlashed)).toBe(false)
  expect(state.calls.filter(p => p === endpoints.staff)).toHaveLength(0)
})

test('first load reads each granting source once and honors a non-first URL program', async ({ page }) => {
  const other = { ...program, id: 9, name: 'Other Test Club' }
  const state = await mock(page, { programs: [program, other] })
  await page.goto('/my-club?program=9&view=matches')
  await expectConsole(page)
  await expect(page.getByRole('heading', { name: other.name, exact: true })).toBeVisible()
  for (const source of ['features', 'claims', 'staff', 'legacy', 'clubs']) expect(state.calls.filter(p => p === endpoints[source])).toHaveLength(1)
  for (const id of [7, 9]) expect(state.calls.filter(p => p === `/api/club/${id}/roster`)).toHaveLength(1)
})


test('known owner also waits for slow staff discovery without duplicate eligibility reads', async ({ page }) => {
  const state = await mock(page)
  const hold = barrier()
  state.hold = { endpoint: endpoints.staff, ...hold }
  await page.goto('/my-club?program=7&view=matches')
  await expect.poll(() => state.calls.includes(endpoints.staff) && state.calls.includes(endpoints.claims)).toBe(true)
  await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
  expect(state.calls.filter(p => p === endpoints.eligibility)).toHaveLength(0)
  hold.release()
  await expectConsole(page)
  expect(state.calls.filter(p => p === endpoints.eligibility)).toHaveLength(1)
})

test('legacy failure waits for its still-pending companion before showing Retry', async ({ page }) => {
  const state = await mock(page, { role: 'none' })
  const hold = barrier()
  state.failure = endpoints.legacy
  state.hold = { endpoint: endpoints.clubs, ...hold }
  await page.goto('/my-club?view=matches')
  await expect.poll(() => state.calls.includes(endpoints.clubs)).toBe(true)
  await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
  hold.release()
  await expect(page.getByText("We couldn't load your club. Try again.")).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
})


for (const selected of [7, 9]) test(`one failed program leaves the working club open (URL ${selected}); Retry only checks that program`, async ({ page }) => {
  const other = { ...program, id: 9, name: 'Other Test Club' }
  const state = await mock(page, { programs: [program, other] })
  state.failure = '/api/club/9/roster'
  await page.goto(`/my-club?program=${selected}&view=matches`)
  await expectConsole(page)
  await expect(page.getByRole('alert')).toContainText('1 clubs could not be checked.')
  if (selected === 7 && process.env.MYC1_SHOTS_DIR) for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await page.screenshot({ path: path.join(process.env.MYC1_SHOTS_DIR, `working-club-${width}.png`), fullPage: true })
  }
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeEnabled()
  await expectConsole(page)
  expect(new URL(page.url()).search).toBe(`?program=${selected}&view=matches`)
  expect(state.calls.filter(p => p === '/api/club/7/roster')).toHaveLength(1)
  expect(state.calls.filter(p => p === '/api/club/9/roster')).toHaveLength(2)
  state.failure = null
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.calls.filter(p => p === '/api/club/7/roster')).toHaveLength(1)
  expect(state.calls.filter(p => p === '/api/club/9/roster')).toHaveLength(3)
  expect(state.calls.filter(p => p === endpoints.claims)).toHaveLength(1)
  await expect(page.getByRole('heading', { name: selected === 9 ? other.name : program.name, exact: true })).toBeVisible()
})

for (const consoleOwner of [false, true]) test(`silent refresh failure preserves ${consoleOwner ? 'console' : 'legacy workspace'} after successful mutation`, async ({ page }) => {
  const state = await mock(page, { legacy: true })
  state.affiliations = [{ id: 41, player_api_id: 8, status: 'pending' }, { id: 42, player_api_id: 9, status: 'pending' }]
  // Legacy evidence and a program claim can coexist for an established owner.
  if (consoleOwner) await page.route('**/api/funding/claims/me', route => route.fulfill({ json: { claims: [{ id: 7, status: 'approved', program }] } }))
  await page.goto(consoleOwner ? '/my-club?program=7&view=affiliations' : '/my-club')
  const note = page.getByRole('textbox', { name: 'Rejection note for player 8' })
  await note.fill('Acted-on note')
  const untouchedNote = page.getByRole('textbox', { name: 'Rejection note for player 9' })
  await untouchedNote.fill('Keep this unsaved draft')
  await page.evaluate(() => { window.workspaceBeforeMutation = document.querySelector('.club-home') || document.querySelector('.fl-club-entry') })
  await page.getByRole('button', { name: 'Confirm', exact: true }).first().click()
  await expect(page.getByRole('alert')).toContainText('Synthetic unavailable')
  await expect(page.getByText("We couldn't load your club. Try again.")).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => window.workspaceBeforeMutation === (document.querySelector('.club-home') || document.querySelector('.fl-club-entry')))).toBe(true)
  await expect(note).toBeVisible()
  await expect(untouchedNote).toHaveValue('Keep this unsaved draft')
  if (consoleOwner) await expect(page.locator('.club-home')).toBeVisible()
  else await expect(page.getByText('Your club claims')).toBeVisible()
  expect(new URL(page.url()).search).toBe(consoleOwner ? '?program=7&view=affiliations' : '')
})

for (const source of Object.keys(endpoints)) test(`deadline ${source}: unanswered source offers Retry; late response cannot undo recovery`, async ({ page }) => {
  const state = await mock(page, { role: source === 'staff' ? 'staff-only' : 'owner' })
  // Simulate a transport that ignores abort, so the generation protection must
  // also work when the expired promise eventually resolves after a fresh read.
  await page.addInitScript(endpoint => {
    const fetch = window.fetch
    let first = true
    window.fetch = (input, options) => {
      if (first && String(input).endsWith(endpoint)) {
        first = false
        const { signal: _signal, ...rest } = options || {}
        return fetch(input, rest)
      }
      return fetch(input, options)
    }
  }, endpoints[source])
  const hold = barrier()
  state.hold = { endpoint: endpoints[source], ...hold, json: source === 'features' ? { club_staff_access: false } : { claims: [], clubs: [], programs: [], members: [], program: { ...program, name: 'Expired stale club' } } }
  await page.clock.install()
  await page.goto('/my-club?program=7&view=matches')
  await expect.poll(() => state.calls.includes(endpoints[source])).toBe(true)
  await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
  await page.waitForTimeout(150)
  await page.clock.fastForward(15001)
  await expect(page.getByText("We couldn't load your club. Try again.")).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toHaveCount(0)
  state.hold = null
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expectConsole(page)
  hold.release()
  await page.waitForTimeout(100)
  await expectConsole(page)
  await expect(page.getByRole('heading', { name: 'Expired stale club' })).toHaveCount(0)
  expect(new URL(page.url()).search).toBe('?program=7&view=matches')
  expect(state.calls.filter(p => p === endpoints[source])).toHaveLength(2)
})

for (const source of ['claims', 'features']) test(`deadline ${source} body: headers arriving cannot leave body consumption pending`, async ({ page }) => {
  await mock(page)
  await page.addInitScript(endpoint => {
    const fetch = window.fetch
    let first = true
    window.fetch = async (input, options) => {
      const response = await fetch(input, options)
      if (first && String(input).endsWith(endpoint)) {
        first = false
        // Do not attach the stream to the request's abort signal.
        return new Response(new ReadableStream({ start() {} }), { headers: { 'Content-Type': 'application/json' } })
      }
      return response
    }
  }, endpoints[source])
  await page.clock.install()
  await page.goto('/my-club?program=7&view=matches')
  await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
  await page.waitForTimeout(150)
  await page.clock.fastForward(15001)
  await expect(page.getByText("We couldn't load your club. Try again.")).toBeVisible()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expectConsole(page)
  expect(new URL(page.url()).search).toBe('?program=7&view=matches')
})

test('combined discovery and eligibility failures share Retry without duplicate roster reads', async ({ page }) => {
  const state = await mock(page)
  state.failures = new Set([endpoints.staff, endpoints.eligibility])
  await page.goto('/my-club?program=7&view=matches')
  await expect(page.getByText("We couldn't load your club. Try again.")).toBeVisible()
  state.failures.clear()
  await page.getByRole('button', { name: 'Retry', exact: true }).dblclick()
  await expectConsole(page)
  expect(state.calls.filter(p => p === endpoints.staff)).toHaveLength(2)
  expect(state.calls.filter(p => p === endpoints.eligibility)).toHaveLength(2)
})

test('retry discovery retains successful roster grants for unchanged claims', async ({ page }) => {
  const state = await mock(page)
  state.failure = endpoints.staff
  await page.goto('/my-club?program=7&view=matches')
  await expect(page.getByText("We couldn't load your club. Try again.")).toBeVisible()
  expect(state.calls.filter(p => p === endpoints.eligibility)).toHaveLength(1)
  state.failure = null
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expectConsole(page)
  expect(state.calls.filter(p => p === endpoints.eligibility)).toHaveLength(1)
})

for (const width of [390, 1440]) test(`Retry presentation ${width}px: one neutral alert and comfortable button`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 })
  const state = await mock(page, { role: 'none' })
  state.failure = endpoints.legacy
  await page.goto('/my-club?view=matches')
  await expect(page.getByRole('alert')).toHaveCount(1)
  await expect(page.getByRole('alert')).toContainText("We couldn't load your club. Try again.")
  const button = page.getByRole('button', { name: 'Retry', exact: true })
  const box = await button.boundingBox()
  expect(box.height).toBeGreaterThanOrEqual(44)
  expect(box.width).toBeGreaterThanOrEqual(80)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
  await button.focus()
  await expect(button).toBeFocused()
  if (process.env.MYC1_SHOTS_DIR) await page.screenshot({ path: path.join(process.env.MYC1_SHOTS_DIR, `retry-${width}.png`), fullPage: true })
  state.failure = null
  await button.press('Enter')
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
})

test('live console denial removes the revoked club without restoring a cached grant', async ({ page }) => {
  const state = await mock(page)
  await page.goto('/my-club?program=7&view=map')
  await expectConsole(page, 'Club map')
  state.denied = '/api/club/7/matches'
  await page.getByRole('button', { name: /Matches/ }).first().click()
  await expect.poll(() => state.calls.includes(state.denied)).toBe(true)
  await expect(page.locator('.club-home')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Represent a club?' })).toBeVisible()
})
