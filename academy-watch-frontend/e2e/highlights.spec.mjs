/* global document, innerWidth */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

// Synthetic workflow fixtures, clearly labelled; production has no fallback data.
const id = '00000000-0000-4000-8000-000000000001'
const clip = { id, title: 'Synthetic reviewed moment', club_name: 'Synthetic C2 Club', duration_s: 20, player_id: -7, version: 1, player_decision: 'pending', status_label: 'Waiting for you', render_status: 'ready', can_approve: true, revoked: false, preview_url: `/api/me/highlight-requests/${id}/preview`, clip_url: null }
async function fixture(page, { enabled = true, empty = false, fail = false, conflict = false } = {}) {
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-c2-browser-token')
    localStorage.setItem('academy_watch_display_name', 'Synthetic C2 User')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  let current = structuredClone(clip)
  const writes = []
  await page.route('**/api/**', async route => {
    const req = route.request(), p = new URL(req.url()).pathname
    const reply = json => route.fulfill({ json })
    if (p === '/api/features') return reply(enabled ? { highlights: true } : {})
    if (p === '/api/auth/me') return reply({ email: 'c2@example.test', display_name: 'Synthetic C2 User', display_name_confirmed: true, role: 'user' })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (p === '/api/me/highlight-requests') return fail ? route.fulfill({ status: 503, json: { error: 'unavailable' } }) : reply({ highlights: empty ? [] : [current], has_more: false })
    if (p.endsWith(`/${id}/preview`)) return route.fulfill({ contentType: 'video/mp4', body: Buffer.from([0, 0, 0, 0]) })
    if (p.startsWith(`/api/me/highlight-requests/${id}/`)) {
      writes.push({ path: p, body: req.postDataJSON() })
      if (conflict) return route.fulfill({ status: 409, json: { error: 'version_conflict' } })
      current = { ...current, version: current.version + 1, player_decision: p.endsWith('/revoke') ? 'private' : req.postDataJSON().decision, revoked: p.endsWith('/revoke') }
      if (p.endsWith('/retry')) current = { ...current, player_decision: 'pending', render_status: 'ready', can_approve: true, can_retry: false, preview_url: clip.preview_url }
      else if (current.player_decision === 'private') current = { ...current, render_status: 'stale', can_approve: false, can_retry: !current.revoked, preview_url: null }
      current.status_label = current.revoked ? 'Taken back' : current.player_decision === 'approve' ? 'Public on your page' : current.player_decision === 'pending' ? 'Waiting for you' : 'Kept private'
      return reply(current)
    }
    return reply({})
  })
  return writes
}
async function shot(page, name) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (!process.env.C2_SCREENSHOTS) return
  await fs.mkdir(process.env.C2_SCREENSHOTS, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: path.join(process.env.C2_SCREENSHOTS, `${name}.png`), fullPage: true, animations: 'disabled' })
}
for (const width of [1440, 390]) {
  test(`adult decisions and revoke at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const writes = await fixture(page)
    await page.goto('/highlight-approvals')
    await expect(page.getByRole('heading', { name: 'Your moments, your call.' })).toBeVisible()
    await shot(page, `inbox-${width}`)
    await page.getByRole('button', { name: 'Keep private', exact: true }).click()
    await expect(page.getByText('Kept private', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Make public', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await page.getByRole('button', { name: 'Make public', exact: true }).click()
    await expect(page.getByText('Public on your page', { exact: true })).toBeVisible()
    await shot(page, `approved-${width}`)
    await page.getByRole('button', { name: 'Take it back', exact: true }).click()
    await expect(page.getByText('Taken back', { exact: true })).toBeVisible()
    await shot(page, `revoked-${width}`)
    expect(writes.map(x => x.body.decision)).toEqual(['private', undefined, 'approve', undefined])
    expect(writes[2].body.version).toBe(3)
  })
  test(`empty and error states at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await fixture(page, { empty: true })
    await page.goto('/highlight-approvals')
    await expect(page.getByText(/Nothing waiting for you/)).toBeVisible()
    await shot(page, `empty-${width}`)
  })
}
test('dark flag sends no inbox requests', async ({ page }) => {
  await fixture(page, { enabled: false })
  const reads = []
  page.on('request', req => { if (req.url().includes('/me/highlight-requests')) reads.push(req.url()) })
  await page.goto('/highlight-approvals')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Your moments, your call.' })).toHaveCount(0)
  expect(reads).toEqual([])
})
test('unavailable inbox has a retry and no approval actions', async ({ page }) => {
  await fixture(page, { fail: true })
  await page.goto('/highlight-approvals')
  await expect(page.getByRole('alert')).toContainText('could not load')
  await expect(page.getByRole('button', { name: 'Make public' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Refresh' })).toBeEnabled()
  await shot(page, 'error')
})
test('stale decision stays private and shows refresh guidance', async ({ page }) => {
  await fixture(page, { conflict: true })
  await page.goto('/highlight-approvals')
  await page.getByRole('button', { name: 'Make public' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText('Public on your page', { exact: true })).toHaveCount(0)
})

for (const width of [1440, 390]) {
  test(`club review pick remove and public clips at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await fixture(page)
    let reviewed = false, picked = false, approved = false
    const candidate = { roster_entry_id: 1, tracklet_id: 2, start_s: 10, end_s: 30, player_name: 'Synthetic Adult' }
    await page.route('**/api/club/7/matches/41/**', route => {
      const req = route.request(), p = new URL(req.url()).pathname
      if (p.endsWith('/highlight-review')) { if (req.postDataJSON().classification === 'private') { reviewed = false; picked = false } else { expect(req.postDataJSON().all_visible_people_adults).toBe(true); reviewed = true } }
      else if (req.method() === 'POST') { expect(req.postDataJSON().start_s).toBe(10); expect(req.postDataJSON().end_s).toBe(30); picked = true }
      else if (req.method() === 'DELETE') picked = false
      return route.fulfill({ json: { adult_recording: reviewed, review_classification: reviewed ? 'adult_only' : 'private', can_review: true, candidates: reviewed ? [candidate] : [], highlights: picked ? [{ ...clip, ...candidate, ...(approved ? { player_decision: 'approve', status_label: 'Public on your page' } : {}) }] : [] } })
    })
    await page.goto('/highlight-approvals')
    await page.evaluate(async () => {
      const { default: React } = await import('/node_modules/.vite/deps/react.js')
      const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js')
      const { ClubHighlightPicker } = await import('/src/components/highlights/ClubHighlightPicker.jsx')
      const host = document.createElement('div'); host.className = 'floodlight-container'; document.body.replaceChildren(host)
      ReactDOM.createRoot(host).render(React.createElement(ClubHighlightPicker, { programId: 7, matchId: 41 }))
    })
    await expect(page.getByRole('button', { name: 'Confirm adult-only recording' })).toBeDisabled()
    await shot(page, `club-review-${width}`)
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: 'Confirm adult-only recording' }).click()
    await expect(page.getByRole('heading', { name: 'Synthetic Adult' })).toBeVisible()
    await page.getByLabel('Clip title').fill('Synthetic reviewed moment')
    await page.getByRole('button', { name: 'Pick moment' }).click()
    await expect(page.getByText('Waiting for player', { exact: true })).toBeVisible()
    await shot(page, `club-picked-${width}`)
    approved = true
    await page.getByRole('button', { name: 'Refresh highlights' }).click()
    await expect(page.getByText('Public on player and club pages', { exact: true })).toBeVisible()
    await expect(page.getByText('Public on your page', { exact: true })).toHaveCount(0)
    await shot(page, `club-approved-${width}`)
    await page.getByRole('button', { name: 'Remove pick' }).click()
    await expect(page.getByRole('button', { name: 'Pick moment' })).toBeVisible()
    await page.route('**/api/players/-7/highlights', route => route.fulfill({ json: { highlights: [{ ...clip, clip_url: `/api/highlights/${id}/clip` }] } }))
    await page.evaluate(async () => {
      const { default: React } = await import('/node_modules/.vite/deps/react.js')
      const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js')
      const { PublicHighlights } = await import('/src/components/highlights/PublicHighlights.jsx')
      const host = document.createElement('div'); host.className = 'floodlight-container'; document.body.replaceChildren(host)
      ReactDOM.createRoot(host).render(React.createElement(PublicHighlights, { playerId: -7 }))
    })
    await expect(page.getByRole('heading', { name: 'Highlights', exact: true })).toBeVisible()
    await expect(page.locator('video')).toHaveAttribute('src', `/api/highlights/${id}/clip`)
    await expect(page.locator('video')).toHaveAttribute('preload', 'none')
    await shot(page, `public-clip-${width}`)
  })
}

test('recipient preview gets authenticated standalone URL only', async ({ page }) => {
  await fixture(page)
  await page.route('**/api/me/highlight-requests?*', route => route.fulfill({ json: { highlights: [{ ...clip, preview_url: `/api/me/highlight-requests/${id}/preview` }], has_more: false } }))
  let reads = 0
  await page.route(`**/api/me/highlight-requests/${id}/preview?transport=url`, route => {
    expect(route.request().headers().authorization).toBe('Bearer synthetic-c2-browser-token')
    reads += 1
    return route.fulfill({ json: { url: 'https://storage.example.test/highlights/standalone.mp4' } })
  })
  const fullMatchReads = []
  page.on('request', req => { if (/media-token|footage|sas/.test(req.url())) fullMatchReads.push(req.url()) })
  await page.goto('/highlight-approvals')
  await page.getByRole('button', { name: 'Preview short clip' }).click()
  await expect(page.locator('video')).toHaveAttribute('src', 'https://storage.example.test/highlights/standalone.mp4')
  expect(reads).toBe(1)
  await page.getByRole('button', { name: 'Make public' }).click()
  await expect(page.locator('video')).toHaveCount(0)
  expect(fullMatchReads).toEqual([])
})

async function mountPicker(page) {
  await page.evaluate(async () => {
    const { default: React } = await import('/node_modules/.vite/deps/react.js')
    const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js')
    const { ClubHighlightPicker } = await import('/src/components/highlights/ClubHighlightPicker.jsx')
    const host = document.createElement('div'); host.className = 'floodlight-container'; document.body.replaceChildren(host)
    ReactDOM.createRoot(host).render(React.createElement(ClubHighlightPicker, { programId: 7, matchId: 41 }))
  })
}
for (const width of [1440, 390]) {
  test(`expired raw recording retains remove and un-attest controls at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await fixture(page)
    let picked = true, reviewed = true
    await page.route('**/api/club/7/matches/41/**', route => {
      const request = route.request()
      if (request.method() === 'DELETE') picked = false
      if (new URL(request.url()).pathname.endsWith('/highlight-review')) {
        expect(request.postDataJSON().classification).toBe('private')
        reviewed = false; picked = false
      }
      return route.fulfill({ json: { adult_recording: false, recording_block_reason: 'source_unavailable', review_classification: reviewed ? 'adult_only' : 'private', can_review: false, candidates: [], highlights: picked ? [{ ...clip, player_decision: 'approve', status_label: 'Public on your page' }] : [] } })
    })
    await page.goto('/highlight-approvals')
    await mountPicker(page)
    await expect(page.getByRole('button', { name: 'Remove pick' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Mark recording private' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Confirm adult-only recording' })).toHaveCount(0)
    await shot(page, `expired-controls-${width}`)
    await page.getByRole('button', { name: 'Remove pick' }).click()
    await expect(page.getByRole('button', { name: 'Remove pick' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Mark recording private' }).click()
    await expect(page.getByRole('button', { name: 'Mark recording private' })).toHaveCount(0)
  })
}
test('queued preview cannot be approved and polling backs off from thirty seconds', async ({ page }) => {
  await fixture(page)
  await page.clock.install()
  let reads = 0
  await page.route('**/api/me/highlight-requests?*', route => {
    reads += 1
    return route.fulfill({ json: { highlights: [{ ...clip, render_status: 'queued', can_approve: false, preview_url: null }], has_more: false } })
  })
  await page.goto('/highlight-approvals')
  await expect(page.getByText('Waiting for you', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Make public' })).toHaveCount(0)
  await shot(page, 'preparing-no-approval')
  const initial = reads
  await page.clock.fastForward(29000)
  expect(reads).toBe(initial)
  await page.clock.fastForward(1000)
  await expect.poll(() => reads).toBe(initial + 1)
  await expect(page.getByText('Waiting for you', { exact: true })).toBeVisible()
  await page.clock.fastForward(59000)
  expect(reads).toBe(initial + 1)
  await page.clock.fastForward(1000)
  await expect.poll(() => reads).toBe(initial + 2)
})
test('admin can take down one clip without raw footage', async ({ page }) => {
  await fixture(page)
  const actions = []
  await page.route(`**/api/admin/highlights/${id}/takedown`, route => {
    actions.push(route.request().url())
    return route.fulfill({ json: { id, revoked: true } })
  })
  await page.goto('/highlight-approvals')
  await page.evaluate(async () => {
    const { default: React } = await import('/node_modules/.vite/deps/react.js')
    const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js')
    const { AdminHighlightTakedown } = await import('/src/components/highlights/AdminHighlightTakedown.jsx')
    const { APIService } = await import('/src/lib/api.js')
    APIService.setAdminKey('synthetic-c2-admin-key')
    const host = document.createElement('div'); host.className = 'floodlight-container dark'; document.body.replaceChildren(host)
    ReactDOM.createRoot(host).render(React.createElement(AdminHighlightTakedown))
  })
  await page.getByLabel('Highlight ID').fill(id)
  await page.getByRole('button', { name: 'Take down clip', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Clip taken down until an admin lifts it.')
  expect(actions).toHaveLength(1)
  await shot(page, 'admin-clip-takedown')
  await page.route(`**/api/admin/highlights/${id}/lift`, route => route.fulfill({json:{id,revoked:true}}))
  await page.getByRole('button',{name:'Lift takedown'}).click()
  await expect(page.getByRole('status')).toContainText('A fresh club pick and player approval are required')
  await shot(page,'admin-lift-requires-fresh-consent')
})

test('native preview plays across page, authenticated API and storage origins without storage CORS', async ({ page }) => {
  const { createServer } = await import('node:http')
  const { execFileSync } = await import('node:child_process')
  const { mkdtemp, readFile, rm } = await import('node:fs/promises')
  const { tmpdir } = await import('node:os')
  const dir = await mkdtemp(path.join(tmpdir(), 'c2-duel-media-'))
  const mp4Path = path.join(dir, 'clip.mp4')
  execFileSync('ffmpeg', ['-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=black:s=160x90:d=1','-an','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',mp4Path])
  const bytes = await readFile(mp4Path)
  const storageReads = [], apiReads = []
  const storage = createServer((req, res) => {
    storageReads.push(req.headers)
    // Azurite-style private blob endpoint: valid standalone capability, ranges,
    // and intentionally NO Access-Control-Allow-Origin response header.
    const range = req.headers.range?.match(/bytes=(\d+)-(\d*)/)
    const start = range ? Number(range[1]) : 0
    const end = range?.[2] ? Math.min(Number(range[2]), bytes.length-1) : bytes.length-1
    res.writeHead(range ? 206 : 200, { 'Content-Type':'video/mp4', 'Cache-Control':'private, no-store',
      'Accept-Ranges':'bytes', 'Content-Length':end-start+1, ...(range ? {'Content-Range':`bytes ${start}-${end}/${bytes.length}`} : {}) })
    res.end(bytes.subarray(start,end+1))
  })
  let storageOrigin
  const api = createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*')
    res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type')
    res.setHeader('Referrer-Policy','no-referrer')
    res.setHeader('Cache-Control','private, no-store')
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return }
    apiReads.push(req.headers)
    if (req.headers.authorization !== 'Bearer synthetic-c2-browser-token') { res.writeHead(401); res.end(); return }
    res.setHeader('Content-Type','application/json')
    res.end(JSON.stringify({url:storageOrigin+'/highlights/standalone.mp4?read=60'}))
  })
  const listen = server => new Promise(resolve => server.listen(0,'127.0.0.1',resolve))
  try {
    await listen(storage); await listen(api)
    storageOrigin = `http://127.0.0.1:${storage.address().port}`
    const apiOrigin = `http://127.0.0.1:${api.address().port}`
    await fixture(page)
    await page.route('**/src/lib/api.js*', async route => {
      const original = await route.fetch()
      const body = await original.text()
      expect(body).toMatch(/\|\| ['"]\/api['"]/)
      await route.fulfill({response:original,body:body.replace(/\|\| ['"]\/api['"]/, `|| '${apiOrigin}/api'`)})
    })
    await page.route(`**/api/me/highlight-requests/${id}/preview?transport=url`, route => route.continue())
    await page.goto('/highlight-approvals')
    await page.getByRole('button',{name:'Preview short clip'}).click()
    await expect(page.locator('video')).toHaveAttribute('src',storageOrigin+'/highlights/standalone.mp4?read=60')
    await expect.poll(() => page.locator('video').evaluate(video => video.readyState)).toBeGreaterThanOrEqual(1)
    expect(apiReads).toHaveLength(1)
    expect(apiReads[0].origin).toBe(new URL(page.url()).origin)
    expect(storageReads.length).toBeGreaterThan(0)
    for (const headers of storageReads) {
      expect(headers.origin).not.toBe('null')
      expect(headers.authorization).toBeUndefined()
      expect(headers.referer).toBeUndefined()
    }
    await shot(page,'three-origin-preview')
  } finally {
    await page.close()
    await Promise.all([api,storage].map(server => new Promise(resolve => { server.closeAllConnections(); server.close(resolve) })))
    await rm(dir,{recursive:true,force:true})
  }
})
