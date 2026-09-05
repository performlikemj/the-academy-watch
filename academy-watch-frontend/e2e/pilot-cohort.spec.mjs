import { expect, test } from '@playwright/test'

const REGISTER = {
  schema_version: 1, cohort_id: 'one-club-pilot', declared_at: '2026-09-05T00:00:00Z', program_id: 7,
  window: { start: '2026-09-05T00:00:00Z', end: '2026-10-05T00:00:00Z' },
  participants: [{ person_key: 'p01', primary_role: 'player', user_account_ids: [101], player_api_ids: [-42], own_account_verified: true, excluded: false }],
  excluded_user_account_ids: [], observations: [], continuation: { decision: 'not_discussed', occurred_at: null, evidence_ref: null },
}
const REPORT = {
  schema_version: 1, register_sha256: 'a'.repeat(64), generated_at: '2026-09-12T00:00:00Z',
  capabilities: { relationships: false, feedback: false, stable_results: false },
  summary: { qualifying_people: 0, by_role: { staff: 0, player: 0, scout: 0, supporter: 0 }, repeat_people: 0, repeat_staff: 0, repeat_players: 0, repeat_target_met: false },
  participants: [{ person_key: 'p01', primary_role: 'player', qualified: false, eligible_now: true, qualified_at: null, action_dates: [], repeat_dates: [], evidence: [], missing: ['accepted_relationship', 'feedback_unavailable'] }],
  cross_person_outcomes: [], continuation: { decision: 'not_discussed', evidence_basis: 'operator' }, warnings: ['relationships_not_installed'],
}

async function setup(page, { status = 200, pause = false, response = REPORT } = {}) {
  const unexpected = [], submissions = [], diagnostics = []
  let release
  const wait = pause ? new Promise(resolve => { release = resolve }) : Promise.resolve()
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-admin-token')
    localStorage.setItem('academy_watch_admin_key', 'mock-admin-key')
    localStorage.setItem('academy_watch_is_admin', 'true')
    localStorage.setItem('academy_watch_display_name', 'Pilot Admin')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (path === '/api/admin/pilot-cohort/report' && req.method() === 'POST') {
      submissions.push(req.postDataJSON())
      expect(req.headers().authorization).toBe('Bearer mock-admin-token')
      expect(req.headers()['x-api-key']).toBe('mock-admin-key')
      await wait
      return route.fulfill({ status, json: status === 200 ? response : { error: status === 403 ? 'Admin login required' : 'cohort_report_failed' } })
    }
    if (path === '/api/events' && req.method() === 'POST') {
      diagnostics.push(...req.postDataJSON().events.filter(e => e.name === 'pilot_ui'))
      return route.fulfill({ status: 202, json: { accepted: 1 } })
    }
    const fixtures = {
      '/api/auth/me': { email: 'admin@example.test', role: 'admin', account_role: 'admin', user_id: 1, display_name: 'Pilot Admin', display_name_confirmed: true },
      '/api/features': { contact_rail: false },
      '/api/admin/community-takes/stats': {}, '/api/admin/manual-players': [],
      '/api/admin/flags/stats': {}, '/api/admin/tracking-requests': [],
      '/api/admin/player-links/pending': [], '/api/admin/scout-verifications': { verifications: [] },
      '/api/admin/reports': { reports: [] }, '/api/admin/jobs/active': { jobs: [] },
      '/api/admin/auth-check': { authorized: true },
      '/api/sync-status': { running: false },
      '/api/admin/rebuild-configs': [],
      '/api/admin/api-football/status': { connected: false },
      '/api/journalists': [], '/api/sponsors': [], '/api/teams': [],
      '/api/subscriptions/me': [], '/api/me/claims': { claims: [] },
      '/api/billing/config': { enabled: false, products: [], packs: [] },
      '/api/user/all-subscriptions': { free_subscriptions: [], paid_subscriptions: [], journalist_follows: [] },
      '/api/user/email-preferences': { email_delivery_preference: 'individual' },
    }
    if (req.method() === 'GET' && Object.hasOwn(fixtures, path)) return route.fulfill({ json: fixtures[path] })
    unexpected.push(`${req.method()} ${path}`)
    await route.abort()
  })
  await page.goto('/admin/tools')
  await expect(page.getByText('Upload the register declared before the pilot.')).toBeVisible()
  return { unexpected, submissions, diagnostics, release }
}

async function upload(page, value = REGISTER) {
  await page.getByLabel('Declared register (JSON, up to 256 KiB)').setInputFiles({ name: 'register.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(value)) })
}

async function downloaded(page, name) {
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name, exact: true }).click()
  const file = await pending
  const stream = await file.createReadStream()
  const chunks = []
  for await (const chunk of stream) chunks.push(chunk)
  return JSON.parse(Buffer.concat(chunks).toString())
}

for (const width of [1280, 390]) {
  test(`upload, capability gaps, downloads, no persistence at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const state = await setup(page, { pause: true })
    const storageBefore = await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }))
    await expect(page.getByRole('button', { name: 'Generate report' })).toBeDisabled()
    await upload(page)
    expect(await downloaded(page, 'Download register')).toEqual(REGISTER)
    await page.getByRole('button', { name: 'Generate report' }).click()
    await expect(page.getByText('Checking registered actions…')).toBeVisible()
    state.release()
    await expect(page.getByText(/Relationship\/feedback evidence is not available yet/)).toBeVisible()
    for (const title of ['Qualifying people', 'Later-week use', 'Cross-person outcomes', 'Paid continuation']) {
      await expect(page.getByText(title, { exact: true })).toBeVisible()
    }
    await expect(page.getByText(/Named return use cannot be reconstructed/)).toBeVisible()
    await expect(page.getByText('This report contains account references. Store it privately.')).toBeVisible()
    expect(await downloaded(page, 'Download report')).toEqual(REPORT)
    expect(state.submissions).toEqual([REGISTER])
    expect(await page.locator('html').evaluate(el => el.scrollWidth)).toBeLessThanOrEqual(width)
    expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }))).toEqual(storageBefore)
    await page.screenshot({ path: testInfo.outputPath(`pilot-${width}.png`), fullPage: true })
    await expect.poll(() => state.diagnostics.map(e => e.props.action)).toEqual(expect.arrayContaining(['report_requested', 'report_completed']))
    await page.reload()
    await expect(page.getByRole('button', { name: 'Generate report' })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Download report' })).toHaveCount(0)
    expect(state.unexpected).toEqual([])
    expect(state.diagnostics.map(e => e.props.action)).toEqual(expect.arrayContaining(['report_requested', 'report_completed']))
    for (const event of state.diagnostics) expect(Object.keys(event.props).sort()).toEqual(['action', 'outcome', 'package'])
  })
}

test('invalid uploads are rejected before posting', async ({ page }) => {
  const state = await setup(page)
  await upload(page, [])
  await expect(page.getByRole('alert')).toContainText('Choose a valid schema version 1 JSON register.')
  await expect(page.getByRole('button', { name: 'Generate report' })).toBeDisabled()
  await page.getByLabel('Declared register (JSON, up to 256 KiB)').setInputFiles({ name: 'large.json', mimeType: 'application/json', buffer: Buffer.alloc(256 * 1024 + 1) })
  await expect(page.getByRole('alert')).toContainText('smaller than 256 KiB')
  expect(state.submissions).toEqual([])
  expect(state.unexpected).toEqual([])
})

for (const status of [400, 403, 500]) {
  test(`report handles HTTP ${status} and clears stale output`, async ({ page }) => {
    const state = await setup(page, { status })
    await upload(page)
    await page.getByRole('button', { name: 'Generate report' }).click()
    await expect(page.getByRole('alert')).toContainText(status === 403 ? 'Admin access required.' : 'The report could not be generated. Your register has not been saved.')
    await expect(page.getByRole('button', { name: 'Download report' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Download register' })).toBeEnabled()
    expect(state.unexpected).toEqual([])
  })
}


test('future references show explicit capability gaps', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 })
  const recordId = '00000000-0000-4000-8000-000000000003'
  const futureRegister = { ...REGISTER, observations: [{ id: 'obs01', person_key: 'p01',
    kind: 'self_operated_action', occurred_at: '2026-09-12T00:00:00Z',
    record_type: 'player_feedback', record_id: recordId, evidence_ref: 'cycle-02' }] }
  const state = await setup(page)
  await upload(page, futureRegister)
  await page.getByRole('button', { name: 'Generate report' }).click()
  await expect(page.getByText(/Missing:.*feedback unavailable/)).toBeVisible()
  expect(state.submissions).toEqual([futureRegister])
  expect(state.unexpected).toEqual([])
})

test('installed feedback and stable result evidence renders on mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 })
  const recordId = '00000000-0000-4000-8000-000000000003'
  const result = { ...REPORT,
    capabilities: { relationships: true, feedback: true, stable_results: true },
    summary: { ...REPORT.summary, qualifying_people: 1 },
    participants: [{ ...REPORT.participants[0], qualified: true, missing: [], action_dates: ['2026-09-12'],
      evidence: [{ kind: 'feedback_published', record_type: 'player_feedback', record_id: recordId,
        occurred_at: '2026-09-12T00:00:00Z', basis: 'operator_correlated' },
      { kind: 'self_operated_action', record_type: 'club_result', record_id: recordId,
        occurred_at: '2026-09-12T00:00:00Z', basis: 'operator_correlated' }] }],
    cross_person_outcomes: [{ kind: 'cross_person_outcome', stage: 'feedback_acknowledged', record_type: 'player_feedback',
      record_id: recordId, occurred_at: '2026-09-12T01:00:00Z', basis: 'database' }],
  }
  const state = await setup(page, { response: result })
  await upload(page)
  await page.getByRole('button', { name: 'Generate report' }).click()
  await expect(page.getByText(/feedback published.*Observed outside the app/)).toBeVisible()
  await expect(page.getByText(/self operated action.*club_result/)).toBeVisible()
  await expect(page.getByText(/feedback acknowledged.*player_feedback/)).toBeVisible()
  await expect(page.getByText(/Relationship\/feedback evidence is not available yet/)).toHaveCount(0)
  expect(await page.locator('html').evaluate(el => el.scrollWidth)).toBeLessThanOrEqual(390)
  expect(state.unexpected).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('pilot-installed-mobile.png'), fullPage: true })
})
