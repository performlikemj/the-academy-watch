/* global window */
import { expect, test } from '@playwright/test'

test.setTimeout(45000)

test('real Flask results preserve main fixture identity, grouped totals and literal text', async ({ page, request }) => {
  test.skip(process.env.E2E_UXM2_REAL !== 'true', 'Requires foreground serve_uxm2_results.py and Vite proxy')
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const metadata = await (await request.get('/api/__uxm2-fixture')).json()
  // Only test HTML is supplied here; every API call reaches the real backend.
  await page.route('**/__uxm2-real', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type; window.__vite_plugin_react_preamble_installed__ = true;
    await import('/@vite/client');
    const React = (await import('/node_modules/.vite/deps/react.js')).default;
    const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
    const {APIService} = await import('/src/lib/api.js');
    const {RecordResultDialog, ResultHistory} = await import('/src/pages/MyClubConsole.jsx');
    await import('/src/App.css');
    APIService.userToken = ${JSON.stringify(metadata.token)};
    const root = createRoot(document.getElementById('root'));
    let counter = 0;
    window.createResult = () => root.render(React.createElement(RecordResultDialog, {key:++counter, programId:${metadata.program_id}, videoMatch:null, members:${JSON.stringify(metadata.members)}, savedResult:null, onSaved:value => {window.saved = value}, onClose:()=>{}, onAccessDenied:()=>{}}));
    window.showHistory = () => root.render(React.createElement(ResultHistory, {programId:${metadata.program_id}, refreshToken:counter, onEdit:()=>{}, onAccessDenied:()=>{}}));
    window.createResult();
  </script></body></html>` }))
  await page.goto('/__uxm2-real')
  await page.waitForFunction(() => typeof window.createResult === 'function')
  expect(errors).toEqual([])
  async function fill(date, opponent) {
    await page.getByLabel('Match date', { exact: true }).fill(date)
    await page.getByLabel('Opponent', { exact: true }).fill(opponent)
    await page.getByLabel('Competition', { exact: true }).fill('Wendle & District')
    await page.getByLabel('Our score', { exact: true }).fill('2')
    await page.getByLabel('Their score', { exact: true }).fill('1')
    await page.getByLabel('Include Known Academy Player in result').check()
    await page.getByLabel('Minutes', { exact: true }).fill('90')
    await page.getByLabel('Goals', { exact: true }).fill('1')
  }
  await fill('2025-09-01', 'Old & Rovers')
  const duplicate = page.waitForResponse(response => response.url().endsWith('/results') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save result', exact: true }).click()
  expect((await duplicate).status()).toBe(409)
  let after = await (await request.get('/api/__uxm2-fixture')).json()
  expect(after.results).toBe(1)
  expect(after.entries).toBe(2)
  await page.evaluate(() => window.createResult())
  await fill('2025-09-02', 'R&D &copy; FC &notin Town')
  const created = page.waitForResponse(response => response.url().endsWith('/results') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save result', exact: true }).click()
  expect((await created).status()).toBe(201)
  await expect(page.getByRole('alert').filter({ hasText: 'Result saved for 1 players.' })).toBeVisible()
  const saved = await page.evaluate(() => window.saved)
  expect(saved.result.opponent).toBe('R&D &copy; FC &notin Town')
  expect(saved.matches[0].opponent).toBe('R&D &copy; FC &notin Town')
  await page.evaluate(() => window.showHistory())
  await expect(page.getByText('2–1 vs R&D &copy; FC &notin Town', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Match date', { exact: true })).toBeVisible()
  await page.evaluate(() => window.showHistory())
  await expect(page.getByText('2–1 vs R&D &copy; FC &notin Town', { exact: true })).toBeVisible()
  after = await (await request.get('/api/__uxm2-fixture')).json()
  expect(after.results).toBe(2)
  expect(after.entries).toBe(3)
  for (const endpoint of ['season-stats', 'stats']) {
    const response = await request.get(`/api/players/7001/${endpoint}?season=2025`)
    expect(response.status()).toBe(200)
    const payload = await response.json()
    expect(payload.source_breakdown.club).toHaveLength(1)
    expect(payload.source_breakdown.club[0].competition_tier).toBe('Wendle & District')
    expect(payload.source_breakdown.club[0].detail.competition).toBe('Wendle & District')
    if (endpoint === 'season-stats') expect(payload.clubs[0].competition_tiers).toEqual(['Wendle & District'])
  }
  expect(after.stored_competitions).toEqual(['Wendle &amp; District'])
  expect(after.total).toMatchObject({ appearances: 3, minutes: 270, goals: 3 })
})
