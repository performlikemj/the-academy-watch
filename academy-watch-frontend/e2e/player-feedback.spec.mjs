/* global window, document */
import { expect, test } from '@playwright/test'
test.setTimeout(45000)
const invitationId = 'a26c4314-78a0-4784-aa7b-642ea7e02b93'
const threadId = 'c26c4314-78a0-4784-aa7b-642ea7e02b93'
const idFor = (n) => `b26c4314-78a0-4784-aa7b-${String(n).padStart(12, '0')}`

async function harness(page, options = {}) {
  const state = { revisions: [], withdrawn: false, revoked: false }
  const unexpected = [], events = [], responses = []
  page.on('pageerror', (error) => unexpected.push(error.message))
  const playerRow = (row) => ({ id: row.id, thread_id: threadId, revision: row.revision, program: { id: 7, name: 'Synthetic Harbour Club' }, player_api_id: -42, title: row.title, body: row.body, observation_refs: row.observation_refs, author: { display_name: 'Synthetic Coach' }, published_at: row.published_at, acknowledged_at: row.acknowledged_at, can_acknowledge: !row.acknowledged_at && row.revision === state.revisions.length })
  const summary = (row) => { const result = playerRow(row); delete result.body; delete result.observation_refs; return result }
  await page.route('**/__pilot-p3', (route) => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root" style="max-width:800px;margin:16px auto;padding:12px"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => (type) => type; window.__vite_plugin_react_preamble_installed__ = true;
    await import('/@vite/client');
    const React = (await import('/node_modules/.vite/deps/react.js')).default;
    const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
    const {APIService} = await import('/src/lib/api.js');
    const {PlayerFeedbackPanel} = await import('/src/pages/MyClubConsole.jsx');
    const {default: PlayerFeedbackInbox} = await import('/src/components/showcase/PlayerFeedbackInbox.jsx');
    await import('/src/App.css');
    const root = createRoot(document.getElementById('root'));
    window.renderP3 = (mode, props = {}) => { APIService.userToken = Object.hasOwn(props, 'token') ? props.token : mode === 'manager' ? 'manager' : 'claimant'; root.render(React.createElement(mode === 'manager' ? PlayerFeedbackPanel : PlayerFeedbackInbox, { programId: 7, invitationId: '${invitationId}', playerName: 'Synthetic Player', signedId: -42, token: APIService.userToken, ...props })); };
    window.renderP3('manager');
  </script></body></html>` }))
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, auth = req.headers().authorization
    const reply = (json, status = 200) => { responses.push(JSON.stringify(json)); return route.fulfill({ json, status, headers: { 'Cache-Control': 'private, no-store' } }) }
    if (path === '/api/events') { events.push(...(req.postDataJSON()?.events || [])); return route.fulfill({ status: 204 }) }
    if (path === '/api/club/7/player-feedback' || path === `/api/club/7/player-feedback/${threadId}/revisions`) {
      if (req.method() === 'POST') {
        if (options.deferPublish) await options.deferPublish()
        if (options.publishError) return reply({ error: options.publishError }, 500)
        const data = req.postDataJSON(), revision = state.revisions.length + 1
        expect(Object.keys(data).sort()).toEqual(['body', 'client_request_id', path.endsWith('/revisions') ? 'expected_revision' : 'invitation_id', 'observation_refs', 'title', 'video_match_id'].sort())
        if (revision > 1) expect(data.expected_revision).toBe(revision - 1)
        state.revisions.push({ id: idFor(revision), revision, title: data.title, body: data.body, observation_refs: data.observation_refs, published_at: `2026-09-05T10:00:0${revision}Z`, acknowledged_at: null })
        return reply({ feedback: playerRow(state.revisions.at(-1)) }, 201)
      }
      if (state.revoked) return reply({ error: 'Club manager access denied' }, 403)
      const row = state.revisions.at(-1)
      return reply({ feedback: row ? [state.withdrawn ? { id: row.id, thread_id: threadId, revision: row.revision, unavailable: true } : { ...summary(row), revision_history: state.revisions.map((r) => ({ id: r.id, revision: r.revision, acknowledged_at: r.acknowledged_at })) }] : [], next_before: null })
    }
    if (path === `/api/club/7/player-feedback/${threadId}/withdraw`) {
      expect(req.postDataJSON()).toEqual({ expected_revision: state.revisions.length })
      state.withdrawn = true
      return reply({ feedback: { thread_id: threadId, revision: state.revisions.length, withdrawn_at: '2026-09-05T12:00:00Z' } })
    }
    if (path === '/api/me/player-feedback') {
      if (options.deferList) await options.deferList()
      if (state.revoked) return reply({ error: 'feedback_not_found' }, 404)
      return reply({ feedback: auth === 'Bearer claimant' && url.searchParams.get('player_api_id') === '-42' && state.revisions.length && !state.withdrawn ? [summary(state.revisions.at(-1))] : [], next_before: null })
    }
    if (path.startsWith('/api/me/player-feedback/')) {
      if (options.deferDetail) await options.deferDetail()
      if (auth !== 'Bearer claimant' || state.withdrawn || state.revoked) return reply({ error: 'feedback_not_found' }, 404)
      const row = state.revisions.find((r) => r.id === path.split('/')[4])
      if (!row) return reply({ error: 'feedback_not_found' }, 404)
      if (req.method() === 'POST') { expect(req.postDataJSON()).toEqual({}); row.acknowledged_at ||= '2026-09-05T11:00:00Z' }
      return reply({ feedback: playerRow(row) })
    }
    unexpected.push(`${req.method()} ${path}`)
    return reply({ error: 'unexpected_api_call' }, 500)
  })
  await page.goto('/__pilot-p3')
  await page.waitForFunction(() => Boolean(window.renderP3))
  return { state, events, unexpected, responses }
}
const render = (page, mode, props = {}) => page.evaluate(({ mode, props }) => window.renderP3(mode, props), { mode, props })
async function publish(page, title = 'Receiving under pressure', body = 'Coach-authored feedback.') {
  await page.getByLabel('Feedback title', { exact: true }).fill(title)
  await page.getByLabel('Feedback text', { exact: true }).fill(body)
  await page.getByRole('button', { name: 'Preview publication', exact: true }).click()
  await expect(page.getByLabel('Publication preview')).toContainText(body)
  await page.getByRole('button', { name: 'Confirm and publish' }).click()
  await expect(page.getByRole('status')).toHaveText('Feedback published.')
}
for (const width of [1280, 390]) {
  test(`publish, exact inbox, acknowledge, correction and withdrawal at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const fixture = await harness(page)
    await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
    await expect(page.getByLabel('Feedback text', { exact: true })).toHaveValue('')
    await publish(page)
    await render(page, 'player')
    await page.getByRole('button', { name: /Receiving under pressure/ }).click()
    await expect(page.getByLabel('Feedback detail')).toContainText('Acknowledging confirms you read this revision; it does not mean you agree.')
    await page.getByRole('button', { name: 'I’ve read this feedback' }).click()
    await expect(page.getByLabel('Feedback detail').getByRole('status')).toHaveText('Acknowledged')
    await page.screenshot({ path: testInfo.outputPath(`acknowledged-${width}.png`), fullPage: true })
    await render(page, 'manager')
    await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
    await page.getByRole('button', { name: 'Publish correction' }).click()
    await expect(page.getByLabel('Feedback text', { exact: true })).toHaveValue('')
    await publish(page, 'Receiving correction', 'Take a look before receiving.')
    await render(page, 'player')
    await page.getByRole('button', { name: /Receiving correction/ }).click()
    await expect(page.getByLabel('Feedback detail')).toContainText('Updated feedback — please read again')
    await page.getByRole('button', { name: 'I’ve read this feedback' }).click()
    await expect(page.getByLabel('Feedback detail').getByRole('status')).toHaveText('Acknowledged')
    expect(fixture.state.revisions.every((row) => row.acknowledged_at)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(await page.locator('body').innerText()).not.toContain('PRIVATE_ANALYSIS_SENTINEL')
    expect(fixture.responses.join('')).not.toContain('PRIVATE_ANALYSIS_SENTINEL')
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('Take a look before receiving.')
    await page.screenshot({ path: testInfo.outputPath(`correction-${width}.png`), fullPage: true })
    await render(page, 'manager')
    await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
    await page.getByRole('button', { name: 'Withdraw feedback', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm withdrawal' }).click()
    await expect(page.getByRole('status')).toHaveText('Feedback withdrawn.')
    await render(page, 'player')
    await page.evaluate((id) => { window.location.hash = `player-feedback=${id}` }, idFor(2))
    await expect(page.getByRole('alert')).toHaveText('This feedback is no longer available.')
    await page.waitForTimeout(5200)
    expect(fixture.events.filter((e) => e.name === 'pilot_ui').map((e) => e.props.action)).toEqual(['feedback_published', 'feedback_opened', 'feedback_acknowledged', 'feedback_published', 'feedback_opened', 'feedback_acknowledged', 'feedback_withdrawn'])
    for (const event of fixture.events.filter((e) => e.name === 'pilot_ui')) expect(Object.keys(event.props).sort()).toEqual(['action', 'outcome', 'package'])
    expect(fixture.unexpected).toEqual([])
  })
}
for (const denied of ['revoked', 'wrong-account']) {
  test(`${denied} direct detail stays unavailable`, async ({ page }) => {
    const fixture = await harness(page)
    await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
    await publish(page)
    fixture.state.revoked = denied === 'revoked'
    await render(page, 'player', denied === 'wrong-account' ? { token: 'other' } : {})
    await page.evaluate((id) => { window.location.hash = `player-feedback=${id}` }, idFor(1))
    await expect(page.getByRole('alert')).toHaveText('This feedback is no longer available.')
    await expect(page.getByText('Coach-authored feedback.')).toHaveCount(0)
    expect(fixture.unexpected).toEqual([])
  })
}
for (const change of ['logout', 'subject']) {
  test(`${change} discards delayed private detail`, async ({ page }) => {
    let release, requested = false
    const pending = new Promise((resolve) => { release = resolve })
    const fixture = await harness(page, { deferDetail: () => { requested = true; return pending } })
    await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
    await publish(page)
    await render(page, 'player')
    await page.getByRole('button', { name: /Receiving under pressure/ }).click()
    await expect.poll(() => requested).toBe(true)
    await render(page, 'player', change === 'logout' ? { token: null } : { signedId: -43 })
    release()
    await expect(page.getByText('Coach-authored feedback.')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'I’ve read this feedback' })).toHaveCount(0)
    expect(fixture.unexpected).toEqual([])
  })
}
test('draft survives retryable failure only in mounted memory', async ({ page }) => {
  const fixture = await harness(page, { publishError: 'feedback_operation_failed' })
  await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
  await page.getByLabel('Feedback title', { exact: true }).fill('Private title')
  await page.getByLabel('Feedback text', { exact: true }).fill('Private draft text')
  await page.getByRole('button', { name: 'Preview publication' }).click()
  await page.getByRole('button', { name: 'Confirm and publish' }).click()
  await expect(page.getByRole('alert')).toContainText('Your draft is still here')
  await page.getByRole('button', { name: 'Back to draft' }).click()
  await expect(page.getByLabel('Feedback text', { exact: true })).toHaveValue('Private draft text')
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('Private draft text')
  await render(page, 'manager', { token: null })
  await expect(page.getByLabel('Feedback text', { exact: true })).toHaveCount(0)
  await render(page, 'manager')
  await page.getByRole('button', { name: 'Publish feedback', exact: true }).click()
  await expect(page.getByLabel('Feedback text', { exact: true })).toHaveValue('')
  expect(fixture.unexpected).toEqual([])
})
