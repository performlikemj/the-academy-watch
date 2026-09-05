/* global window, document */
import { expect, test } from '@playwright/test'
test.setTimeout(45000)

// Render the production panels in a Vite harness; every API request is mocked.
const id = 'a26c4314-78a0-4784-aa7b-642ea7e02b93'
const initial = () => ({ id, program_id: 7, program_name: 'Synthetic Harbour Club', player_api_id: -42, claim_id: 123, status: 'pending', created_at: '2026-09-05T10:00:00Z', expires_at: '2099-09-12T10:00:00Z', responded_at: null, roster_member_id: null })

async function harness(page, options = {}) {
  const unexpected = []
  page.on('pageerror', (error) => { unexpected.push(error.message); console.error(error.message) })
  const events = []
  const state = { rows: options.invited ? [initial()] : [], profile: null, decisionError: options.decisionError }
  await page.route('**/__pilot-p2', (route) => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root" style="max-width:800px;margin:16px auto;padding:12px"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => (type) => type; window.__vite_plugin_react_preamble_installed__ = true;
    await import('/@vite/client');
    const React = (await import('/node_modules/.vite/deps/react.js')).default;
    const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
    const {APIService} = await import('/src/lib/api.js');
    const {ClubInvitationPanel} = await import('/src/pages/MyClubConsole.jsx');
    const {ClaimantClubRelationships} = await import('/src/components/ShowcaseSection.jsx');
    await import('/src/App.css');
    const root = createRoot(document.getElementById('root'));
    window.renderP2 = (mode, props = {}) => { APIService.userToken = props.token || 'claimant'; root.render(React.createElement(mode === 'manager' ? ClubInvitationPanel : ClaimantClubRelationships, { programId: 7, signedId: -42, local: true, token: APIService.userToken, key: mode + ':' + APIService.userToken + ':' + (props.signedId || -42) + ':' + (props.programId || 7), ...props })); };
    window.renderP2('manager', {token:'manager'});
  </script></body></html>` }))
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const auth = req.headers().authorization
    const path = url.pathname
    if (path === '/api/events') {
      events.push(...(req.postDataJSON()?.events || []))
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/players/-42/profile') return route.fulfill({ json: { player_id: -42, name: 'Synthetic Local Player' } })
    if (path === '/api/scout/players') return route.fulfill({ json: { players: [{ player_api_id: -42, player_name: 'Synthetic Local Player' }] } })
    if (path === '/api/club/8/invitations') return route.fulfill({ json: { invitations: [], next_before: null } })
    if (path === '/api/club/7/invitations') {
      if (options.denied) return route.fulfill({ status: 403, json: { error: 'Club manager access denied' } })
      if (options.disabled) return route.fulfill({ status: 404, json: { error: 'not_found' } })
      if (req.method() === 'POST') {
        if (options.deferCreate) await options.deferCreate()
        expect(Object.keys(req.postDataJSON()).sort()).toEqual(['client_request_id', 'player_api_id'])
        expect(req.postDataJSON().player_api_id).toBe(-42)
        state.rows = [initial()]
        return route.fulfill({ status: 201, json: { invitation: state.rows[0], share_path: `/players/-42#club-invitation=${id}` } })
      }
      return route.fulfill({ json: { invitations: state.rows, next_before: null } })
    }
    if (path === '/api/me/club-invitations') {
      if (options.deferList) await options.deferList(auth, url)
      return route.fulfill({ json: { invitations: auth === 'Bearer claimant' && url.searchParams.get('player_api_id') === '-42' ? state.rows : [], next_before: null } })
    }
    if (path.startsWith(`/api/me/club-invitations/${id}/`) || path === `/api/club/7/invitations/${id}/revoke`) {
      expect(req.postDataJSON()).toEqual({})
      if (auth !== 'Bearer claimant' && auth !== 'Bearer manager') return route.fulfill({ status: 404, json: { error: 'invitation_not_found' } })
      if (options.deferDecision) await options.deferDecision()
      if (state.decisionError) return route.fulfill({ status: 409, json: { error: state.decisionError } })
      const action = path.split('/').at(-1)
      state.rows[0] = { ...state.rows[0], status: { accept: 'accepted', decline: 'declined', revoke: 'revoked' }[action] }
      return route.fulfill({ json: { invitation: state.rows[0] } })
    }
    if (path === '/api/local-players/42/showcase/profile' && req.method() === 'PUT') {
      expect(req.postDataJSON()).toEqual({ contract_status: 'contracted', club_program_id: 7 })
      state.profile = { ...req.postDataJSON(), contract_attestation_review_status: 'pending' }
      return route.fulfill({ json: { profile: state.profile } })
    }
    unexpected.push(`${req.method()} ${path}`)
    return route.fulfill({ status: 500, json: { error: 'unexpected_api_call' } })
  })
  await page.goto('/__pilot-p2')
  await page.waitForFunction(() => Boolean(window.renderP2), null, { timeout: 15000 })
  return { state, unexpected, events }
}

async function render(page, mode, props) {
  await page.evaluate(({ mode, props }) => window.renderP2(mode, props), { mode, props })
}

for (const width of [1280, 390]) {
  test(`manager invite, claimant acceptance, moderated attestation and withdrawal at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
    const fixture = await harness(page)
    await page.getByLabel('Find a public player').fill('Synthetic')
    await page.getByRole('button', { name: 'Synthetic Local Player · Local player' }).click()
    await page.getByRole('button', { name: 'Create invitation' }).click()
    await expect(page.getByText('Awaiting player', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Copy invitation link' }).click()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(`/players/-42#club-invitation=${id}`)
    await render(page, 'claimant', { token: 'claimant' })
    await expect(page.getByText('Contract status and introductions require separate choices.', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'Accept club relationship', exact: true }).click()
    await expect(page.getByText('Accepted', { exact: true })).toBeVisible()
    await page.getByLabel('Contract status for contact routing').selectOption('contracted')
    await page.getByLabel('Accepted club').selectOption('7')
    await page.getByRole('button', { name: 'Submit contract status for review' }).click()
    await expect(page.getByText('Pending review', { exact: true })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath(`pending-${width}.png`), fullPage: true })
    await render(page, 'claimant', { token: 'claimant', profile: { ...fixture.state.profile, contract_attestation_review_status: 'approved' } })
    await expect(page.getByText('Pending review', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Leave club relationship' }).click()
    await expect(page.getByText('Revoked', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`withdrawn-${width}.png`), fullPage: true })
    // Flush analytics without putting any invitation/claim/program/player identifier in props.
    await page.waitForTimeout(5200)
    const pilotEvents = fixture.events.filter((event) => event.name === 'pilot_ui')
    expect(pilotEvents.map((event) => event.props.action)).toEqual(['invite_created', 'invite_accepted', 'attestation_submitted', 'relationship_revoked'])
    for (const event of pilotEvents) {
      expect(Object.keys(event.props).sort()).toEqual(['action', 'outcome', 'package'])
      expect(JSON.stringify(event)).not.toContain(id)
    }
    expect(fixture.unexpected).toEqual([])
  })
}

test('wrong account has no invitation capability and manager denial is explicit', async ({ page }) => {
  const fixture = await harness(page, { invited: true, denied: true })
  await expect(page.getByRole('alert')).toHaveText('Club manager access denied.')
  await render(page, 'claimant', { token: 'other-account' })
  await expect(page.getByText('No club invitations yet.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Accept club relationship' })).toHaveCount(0)
  expect(fixture.unexpected).toEqual([])
})

for (const [code, message] of [['invitation_already_resolved', 'This invitation has already been answered.'], ['invitation_expired', 'This invitation has expired.']]) {
  test(`decision handles ${code}`, async ({ page }) => {
    const fixture = await harness(page, { invited: true, decisionError: code })
    await render(page, 'claimant', { token: 'claimant' })
    await page.getByRole('button', { name: 'Accept club relationship' }).click()
    await expect(page.getByRole('alert')).toContainText(message)
    expect(fixture.unexpected).toEqual([])
  })
}

test('decline and manager revoke have separate outcomes', async ({ page }) => {
  const fixture = await harness(page, { invited: true })
  await render(page, 'claimant', { token: 'claimant' })
  await page.getByRole('button', { name: 'Decline', exact: true }).click()
  await expect(page.getByText('Declined', { exact: true })).toBeVisible()
  fixture.state.rows[0].status = 'accepted'
  await render(page, 'manager', { token: 'manager' })
  await page.getByRole('button', { name: 'Revoke relationship' }).click()
  await expect(page.getByText('Revoked', { exact: true })).toBeVisible()
  expect(fixture.unexpected).toEqual([])
})

for (const change of ['account', 'subject']) {
  test(`late decisions are discarded after ${change} change`, async ({ page }) => {
    let release
    const pending = new Promise((resolve) => { release = resolve })
    let requested = false
    const fixture = await harness(page, { invited: true, deferDecision: () => { requested = true; return pending } })
    await render(page, 'claimant', { token: 'claimant' })
    await page.getByRole('button', { name: 'Accept club relationship' }).click()
    await expect.poll(() => requested).toBe(true)
    await render(page, 'claimant', change === 'account' ? { token: 'other-account' } : { token: 'claimant', signedId: -43 })
    release()
    await expect(page.getByText('No club invitations yet.')).toBeVisible()
    await expect(page.getByText('Club relationship accepted.')).toHaveCount(0)
    expect(fixture.unexpected).toEqual([])
  })
}

for (const change of ['account', 'subject']) {
  test(`late invitation lists are discarded after ${change} change`, async ({ page }) => {
    let release
    const pending = new Promise((resolve) => { release = resolve })
    let requested = false
    const fixture = await harness(page, { invited: true, deferList: (auth, url) => {
      if (auth === 'Bearer claimant' && url.searchParams.get('player_api_id') === '-42') { requested = true; return pending }
    } })
    await render(page, 'claimant', { token: 'claimant' })
    await expect.poll(() => requested).toBe(true)
    await render(page, 'claimant', change === 'account' ? { token: 'other-account' } : { token: 'claimant', signedId: -43 })
    release()
    await expect(page.getByText('No club invitations yet.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Accept club relationship' })).toHaveCount(0)
    expect(fixture.unexpected).toEqual([])
  })
}

test('late manager creation is discarded after program change', async ({ page }) => {
  let release
  const pending = new Promise((resolve) => { release = resolve })
  let requested = false
  const fixture = await harness(page, { deferCreate: () => { requested = true; return pending } })
  await page.getByLabel('Find a public player').fill('Synthetic')
  await page.getByRole('button', { name: 'Synthetic Local Player · Local player' }).click()
  await page.getByRole('button', { name: 'Create invitation' }).click()
  await expect.poll(() => requested).toBe(true)
  await render(page, 'manager', { token: 'manager', programId: 8 })
  release()
  await expect(page.getByText('No club invitations yet.')).toBeVisible()
  await expect(page.getByText('Invitation ready to share.')).toHaveCount(0)
  expect(fixture.unexpected).toEqual([])
})


test('public signed identity selection works without local search discovery', async ({ page }) => {
  const fixture = await harness(page)
  await page.getByLabel('Find a public player').fill('-42')
  await page.getByRole('button', { name: 'Synthetic Local Player · Local player' }).click()
  await page.getByRole('button', { name: 'Create invitation' }).click()
  await expect(page.getByText('Awaiting player', { exact: true })).toBeVisible()
  expect(fixture.unexpected).toEqual([])
})
