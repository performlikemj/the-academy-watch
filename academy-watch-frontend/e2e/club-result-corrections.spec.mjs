/* global window, document */
import { expect, test } from '@playwright/test'

test.setTimeout(45000)

const resultId = '8b453a4c-6224-4df6-b55d-7040797be82f'
const roster = [
  { id: 51, player_api_id: 7001, display_name: 'Player One', available: true, position: 'Forward' },
  { id: 52, player_api_id: 7002, display_name: 'Player Two', available: true, position: 'Defender' },
]

function result(version = 1, overrides = {}) {
  return {
    result: {
      id: resultId,
      program_id: 7,
      version,
      season: 2026,
      match_date: '2026-09-05',
      opponent: 'Riverside',
      competition: 'League',
      home_away: 'home',
      result_for: 2,
      result_against: 1,
      video_match_id: null,
      video_available: false,
      updated_at: '2026-09-05T12:00:00Z',
      ...overrides,
    },
    matches: [
      { id: 101, club_result_id: resultId, club_roster_member_id: 51, player_api_id: 7001, player_name: 'Player One', minutes: 80, goals: 1, assists: 0, yellows: 0, reds: 0, saves: null, goals_conceded: null, note: null },
      { id: 102, club_result_id: resultId, club_roster_member_id: 52, player_api_id: 7002, player_name: 'Player Two', minutes: 90, goals: 0, assists: 0, yellows: 0, reds: 0, saves: null, goals_conceded: null, note: null },
    ],
    removed_entry_ids: [],
    refreshed_scopes: [],
    season_stats_by_player: {},
  }
}

async function harness(page, options = {}) {
  const unexpected = []
  const events = []
  const requests = []
  const state = {
    saved: options.saved || null,
    conflict: options.conflict || false,
  }
  await page.route('**/__pilot-p4', (route) => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => (type) => type; window.__vite_plugin_react_preamble_installed__ = true;
    await import('/@vite/client');
    const React = (await import('/node_modules/.vite/deps/react.js')).default;
    const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
    const {APIService} = await import('/src/lib/api.js');
    const {RecordResultDialog, ResultHistory} = await import('/src/pages/MyClubConsole.jsx');
    await import('/src/App.css'); APIService.userToken = 'manager';
    const root = createRoot(document.getElementById('root'));
    const members = ${JSON.stringify(options.members || roster)};
    let renderCount = 0;
    const close = () => {};
    window.renderCreate = () => root.render(React.createElement(RecordResultDialog, {key:'create-' + (++renderCount), programId:7, videoMatch:null, members, savedResult:null, onSaved:(value)=>window.lastSaved=value, onClose:close, onAccessDenied:close}));
    window.renderEdit = async () => { const savedResult = await APIService.request('/club/7/results/${resultId}'); root.render(React.createElement(RecordResultDialog, {key:'edit-' + (++renderCount), programId:7, videoMatch:null, members, savedResult, onSaved:(value)=>window.lastSaved=value, onClose:close, onAccessDenied:close})); };
    window.renderHistory = () => root.render(React.createElement(ResultHistory, {programId:7, refreshToken:0, onEdit:(id)=>window.edited=id, onAccessDenied:close}));
    window.renderCreate();
  </script></body></html>` }))
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (path === '/api/events') {
      events.push(...(request.postDataJSON()?.events || []))
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/club/7/results' && request.method() === 'POST') {
      const body = request.postDataJSON()
      requests.push({ method: 'POST', body })
      expect(body.client_request_id).toMatch(/^[0-9a-f-]{36}$/)
      state.saved = result(1, { match_date: body.match_date, opponent: body.opponent, video_match_id: body.video_match_id })
      return route.fulfill({ status: 201, json: state.saved })
    }
    if (path === `/api/club/7/results/${resultId}` && request.method() === 'GET') {
      requests.push({ method: 'GET' })
      return route.fulfill({ json: state.saved })
    }
    if (path === `/api/club/7/results/${resultId}` && request.method() === 'PUT') {
      const body = request.postDataJSON()
      requests.push({ method: 'PUT', body })
      if (state.conflict) return route.fulfill({ status: 409, json: { error: 'result_version_conflict' } })
      expect(body.expected_version).toBe(state.saved.result.version)
      expect(body.entries.every((line) => Object.keys(line).includes('entry_id'))).toBe(true)
      const kept = new Set(body.entries.map((line) => line.entry_id))
      state.saved = {
        ...state.saved,
        result: { ...state.saved.result, version: state.saved.result.version + 1, match_date: body.match_date, opponent: body.opponent },
        matches: state.saved.matches.filter((line) => kept.has(line.id)),
      }
      return route.fulfill({ json: state.saved })
    }
    if (path === `/api/club/7/results/${resultId}` && request.method() === 'DELETE') {
      requests.push({ method: 'DELETE', body: request.postDataJSON() })
      state.saved = null
      return route.fulfill({ json: { id: resultId, deleted: true, version: 3 } })
    }
    if (path === '/api/club/7/results' && request.method() === 'GET') {
      return route.fulfill({ json: { results: state.saved ? [state.saved] : [], total: state.saved ? 1 : 0, next_before: null } })
    }
    unexpected.push(`${request.method()} ${path}`)
    return route.fulfill({ status: 500, json: { error: 'unexpected_api_call' } })
  })
  await page.goto('/__pilot-p4')
  await page.waitForTimeout(1000)
  if (!await page.evaluate(() => Boolean(window.renderEdit))) {
    throw new Error(`P4 harness failed to initialize: ${unexpected.join('; ')}`)
  }
  return { events, requests, state, unexpected }
}

async function fillCreate(page) {
  await page.getByLabel('Match date').fill('2026-09-05')
  await page.getByLabel('Opponent').fill('Riverside')
  await page.getByLabel('Competition').fill('League')
  await page.getByLabel('Our score').fill('2')
  await page.getByLabel('Their score').fill('1')
  await page.getByLabel('Include Player One in result').check()
  await page.getByLabel('Include Player Two in result').check()
}

test('create without video, reload, correct date/opponent, remove player and delete', async ({ page }) => {
  const fixture = await harness(page)
  await fillCreate(page)
  await page.getByRole('button', { name: 'Save result' }).click()
  await expect(page.getByText('Result saved for 2 players.')).toBeVisible()
  await page.evaluate(() => window.renderEdit())
  await expect(page.getByRole('heading', { name: 'Edit result vs Riverside' })).toBeVisible()
  await page.getByLabel('Match date').fill('2026-09-06')
  await page.getByLabel('Opponent').fill('Riverside City')
  await page.getByRole('button', { name: 'Remove Player Two from this result' }).click()
  await expect(page.getByText('1 player will be removed when you save.')).toBeVisible()
  await page.getByRole('button', { name: 'Save correction' }).click()
  expect(fixture.requests.at(-1).body.entries.map((line) => line.entry_id)).toEqual([101])
  await page.evaluate(() => window.renderEdit())
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete result' }).click()
  expect(fixture.requests.at(-1)).toEqual({ method: 'DELETE', body: { expected_version: 2 } })
  expect(fixture.unexpected).toEqual([])
})

test('associated video reload and stale correction conflict', async ({ page }) => {
  const saved = result(4, { video_match_id: 41, video_available: false })
  const fixture = await harness(page, { saved, conflict: true })
  await page.evaluate(() => window.renderHistory())
  await expect(page.getByText('Video unavailable')).toBeVisible()
  await page.evaluate(() => window.renderEdit())
  await page.getByLabel('Our score').fill('3')
  await page.getByRole('button', { name: 'Save correction' }).click()
  await expect(page.getByText('Someone changed this result. Reload the latest version before saving.')).toBeVisible()
  expect(fixture.requests.at(-1).body.video_match_id).toBe(41)
})

test('departed player remains editable and mobile form does not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const saved = result(2)
  saved.matches[0].club_roster_member_id = null
  saved.matches[0].player_name = 'Departed Player'
  await harness(page, { saved, members: roster.slice(1) })
  await page.evaluate(() => window.renderEdit())
  await expect(page.getByText('Departed Player')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove Departed Player from this result' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
