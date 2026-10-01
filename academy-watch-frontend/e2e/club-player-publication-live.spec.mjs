/* global window, document */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

test('isolated PostgreSQL HTTP claim → consent → club-first introduction → withdrawal', async ({ browser, request }) => {
  test.skip(!process.env.C1_HTTP_AUTH_FILE, 'Opt-in own aw_p2_c1 fixture; no live production writes')
  const ids = JSON.parse(await fs.readFile(process.env.C1_HTTP_AUTH_FILE, 'utf8'))
  const api = process.env.E2E_API_URL
  async function call(endpoint, headers, data) {
    const response = data === undefined ? await request.get(`${api}${endpoint}`, { headers }) : await request.post(`${api}${endpoint}`, { headers, data })
    return { status: response.status(), body: await response.json() }
  }
  async function visible() {
    const response = await call('/scout/players?search=C1&per_page=100', ids.scout_headers)
    expect(response.status).toBe(200)
    return response.body.players.some(row => row.player_id === -ids.local)
  }
  async function shots(name) {
    for (const [viewport, size] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
      const context = await browser.newContext({ viewport: size })
      await context.addInitScript(({ token }) => {
        localStorage.setItem('academy_watch_user_token', token)
        localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
      }, { token: ids.player_headers.Authorization.slice(7) })
      const page = await context.newPage()
      await page.goto('/player-publications')
      await expect(page.getByRole('heading', { name: 'Your public profile' })).toBeVisible()
      await expect(page.getByText('Loading profiles…')).toHaveCount(0)
      await expect(page.getByRole('alert')).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.addStyleTag({ content: '[data-agentation-toolbar], [class*=styles-module__toolbar], [class*=styles-module__panel] { display: none !important; }' })
      await page.screenshot({ path: path.join(process.env.HOME, 'codex-runs/aw-redesign/shots/C1', `http-postgres-${name}-test-fixture-${viewport}.png`), fullPage: true })
      await context.close()
    }
  }
  expect(await visible()).toBe(false)
  const invited = await call(`/club/${ids.program}/players/${ids.local}/publication-invite`, ids.club_headers, { recipient_email: ids.email })
  expect(invited.status).toBe(201)
  const token = invited.body.token
  expect((await call('/me/player-publication-invites/accept', ids.scout_headers, { token, self_claim: true })).status).toBe(404)
  const claimed = await call('/me/player-publication-invites/accept', ids.player_headers, { token, self_claim: true })
  expect(claimed.status).toBe(200)
  let row = claimed.body.publication
  expect(await visible()).toBe(false)
  await shots('consent')
  const consented = await call(`/me/player-publications/${row.id}/consent`, ids.player_headers, { expected_version: row.version, public_profile_consent: true, consent_version: row.consent_version })
  expect(consented.status).toBe(200)
  row = consented.body.publication
  expect(await visible()).toBe(false)
  const approved = await call(`/admin/player-publications/${row.id}/review`, ids.admin_headers, { expected_version: row.version, action: 'approve', reason: 'Explicitly synthetic local HTTP adult workflow fixture' })
  expect(approved.status).toBe(200)
  row = approved.body.publication
  expect(row.public).toBe(true)
  expect(await visible()).toBe(true)
  await shots('public')
  const introduction = await call('/contact/requests', ids.scout_headers, { player_api_id: -ids.local, message: 'Synthetic local HTTP introduction fixture' })
  expect(introduction.status).toBe(201)
  const contact = introduction.body.contact_request
  expect(contact.club_first).toBe(true)
  expect((await call('/contact/requests?box=inbox', ids.player_headers)).body.requests).toEqual([])
  expect((await call(`/contact/requests/${contact.id}/accept`, ids.player_headers, {})).status).toBe(404)
  expect((await call(`/contact/requests/${contact.id}/club-consent`, ids.club_headers, { action: 'grant' })).status).toBe(200)
  expect((await call(`/contact/requests/${contact.id}/messages`, ids.scout_headers, { body: 'Premature fixture' })).status).toBe(409)
  expect((await call(`/contact/requests/${contact.id}/accept`, ids.player_headers, {})).status).toBe(200)
  expect((await call(`/contact/requests/${contact.id}/messages`, ids.scout_headers, { body: 'Both permissions fixture' })).status).toBe(201)
  expect((await call(`/me/player-publications/${row.id}/withdraw`, ids.player_headers, { expected_version: row.version })).status).toBe(200)
  expect(await visible()).toBe(false)
  expect((await call(`/contact/requests/${contact.id}/messages`, ids.scout_headers, { body: 'Revoked fixture' })).status).toBe(404)
  await shots('withdrawn')
})
