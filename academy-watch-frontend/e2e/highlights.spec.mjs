/* global document, innerWidth */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

// Synthetic workflow fixtures, clearly labelled; production has no fallback data.
const id = '00000000-0000-4000-8000-000000000001'
const clip = { id, title: 'Synthetic reviewed moment', club_name: 'Synthetic C2 Club', duration_s: 20, player_id: -7, version: 1, player_decision: 'pending', status_label: 'Waiting for you', render_status: 'ready', can_approve: true, revoked: false, preview_url: null, clip_url: null }
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
    if (p.startsWith(`/api/me/highlight-requests/${id}/`)) {
      writes.push({ path: p, body: req.postDataJSON() })
      if (conflict) return route.fulfill({ status: 409, json: { error: 'version_conflict' } })
      current = { ...current, version: current.version + 1, player_decision: p.endsWith('/revoke') ? 'private' : req.postDataJSON().decision, revoked: p.endsWith('/revoke') }
      current.status_label = current.revoked ? 'Taken back' : current.player_decision === 'approve' ? 'Public on your page' : 'Kept private'
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
    await page.getByRole('button', { name: 'Make public', exact: true }).click()
    await expect(page.getByText('Public on your page', { exact: true })).toBeVisible()
    await shot(page, `approved-${width}`)
    await page.getByRole('button', { name: 'Take it back', exact: true }).click()
    await expect(page.getByText('Taken back', { exact: true })).toBeVisible()
    await shot(page, `revoked-${width}`)
    expect(writes.map(x => x.body.decision)).toEqual(['private', 'approve', undefined])
    expect(writes[1].body.version).toBe(2)
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
  await expect(page.getByText('Highlights are not available yet.')).toBeVisible()
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
    let reviewed = false, picked = false
    const candidate = { roster_entry_id: 1, tracklet_id: 2, start_s: 10, end_s: 30, player_name: 'Synthetic Adult' }
    await page.route('**/api/club/7/matches/41/**', route => {
      const req = route.request(), p = new URL(req.url()).pathname
      if (p.endsWith('/highlight-review')) { expect(req.postDataJSON().all_visible_people_adults).toBe(true); reviewed = true }
      else if (req.method() === 'POST') { expect(req.postDataJSON().start_s).toBe(10); expect(req.postDataJSON().end_s).toBe(30); picked = true }
      else if (req.method() === 'DELETE') picked = false
      return route.fulfill({ json: { adult_recording: reviewed, can_review: true, candidates: reviewed ? [candidate] : [], highlights: picked ? [{ ...clip, ...candidate }] : [] } })
    })
    await page.goto('/highlight-approvals')
    await page.evaluate(async () => {
      const React = await import('/node_modules/.vite/deps/react.js')
      const { createRoot } = await import('/node_modules/.vite/deps/react-dom_client.js')
      const { ClubHighlightPicker } = await import('/src/components/highlights/ClubHighlightPicker.jsx')
      const host = document.createElement('div'); host.className = 'floodlight-container'; document.body.replaceChildren(host)
      createRoot(host).render(React.createElement(ClubHighlightPicker, { programId: 7, matchId: 41 }))
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
    await page.getByRole('button', { name: 'Remove pick' }).click()
    await expect(page.getByRole('button', { name: 'Pick moment' })).toBeVisible()
    await page.route('**/api/players/-7/highlights', route => route.fulfill({ json: { highlights: [{ ...clip, clip_url: `/highlights/${id}/clip` }] } }))
    await page.evaluate(async () => {
      const React = await import('/node_modules/.vite/deps/react.js')
      const { createRoot } = await import('/node_modules/.vite/deps/react-dom_client.js')
      const { PublicHighlights } = await import('/src/components/highlights/PublicHighlights.jsx')
      const host = document.createElement('div'); host.className = 'floodlight-container'; document.body.replaceChildren(host)
      createRoot(host).render(React.createElement(PublicHighlights, { playerId: -7 }))
    })
    await expect(page.getByRole('heading', { name: 'Highlights', exact: true })).toBeVisible()
    await expect(page.locator('video')).toHaveAttribute('src', `/api/highlights/${id}/clip`)
    await expect(page.locator('video')).toHaveAttribute('preload', 'none')
    await shot(page, `public-clip-${width}`)
  })
}
