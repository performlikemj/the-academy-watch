/* global window, document */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const row = { id: 1, program_id: 7, local_player_id: 23, player_name: 'Synthetic C1 adult · test fixture', claimed: true, consented: false, association_confirmed: true, moderation_status: 'pending', withdrawn: false, club_revoked: false, version: 2, consent_version: 'public-profile-v1', consent_text: 'I am this adult player. I agree to make my approved profile public, including scout discovery, watchlists and sharing. Introductions go to my club first, then I choose. I can withdraw at any time.', public: false }
async function fixture(page, { on = true, admin = false, anonymous = false, published = false, consented = false, invite = false } = {}) {
  if (!anonymous) await page.addInitScript(({ admin }) => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-c1-browser-token')
    localStorage.setItem('academy_watch_display_name', 'Synthetic C1 fixture')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (admin) { localStorage.setItem('academy_watch_admin_key', 'synthetic-c1-key'); localStorage.setItem('academy_watch_is_admin', 'true') }
  }, { admin })
  let current = { ...row, claimed: !invite, consented: published || consented, moderation_status: published ? 'approved' : 'pending', public: published }
  const writes = []
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), p = url.pathname
    const reply = json => route.fulfill({ json })
    if (p === '/api/features') return reply({ club_player_publication: on })
    if (p === '/api/auth/me') return reply({ email: 'fixture@c1.example', role: admin ? 'admin' : 'user', display_name: 'Synthetic C1 fixture', display_name_confirmed: true })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: true })
    if (p === '/api/me/player-publication-invites/preview') return reply({ publication: current })
    if (p === '/api/me/player-publications' || p === '/api/club/7/player-publications' || p === '/api/admin/player-publications') return reply({ publications: [current] })
    if (p === '/api/club/7/publication-candidates') return reply({ players: [{ id: 23, name: row.player_name }] })
    if (p === '/api/club/7/players/23/publication-invite') { writes.push(request.postDataJSON()); return route.fulfill({ status: 201, json: { publication: current, token: 'synthetic-test-token-private-only' } }) }
    if (/player-publications\/1\/(consent|withdraw|review|revoke)$/.test(p)) {
      writes.push(request.postDataJSON())
      if (p.endsWith('/consent')) current = { ...current, consented: true, version: 3 }
      if (p.endsWith('/withdraw')) current = { ...current, withdrawn: true, consented: false, public: false, version: 5 }
      return reply({ publication: current })
    }
    return reply({})
  })
  return writes
}
async function shot(page, name, viewport) {
  const folder = path.join(process.env.HOME, 'codex-runs/aw-redesign/shots/C1')
  await fs.mkdir(folder, { recursive: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.addStyleTag({ content: '[data-agentation-toolbar], [class*=styles-module__toolbar], [class*=styles-module__panel] { display: none !important; }' })
  await page.screenshot({ path: path.join(folder, `${name}-${viewport}.png`), fullPage: true })
}
for (const [viewport, size] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
  test(`explicit consent, moderation wait and withdrawal ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    const writes = await fixture(page)
    await page.goto('/player-publications')
    const send = page.getByRole('button', { name: 'Give public profile consent' })
    await expect(send).toBeDisabled()
    await shot(page, 'consent-test-fixture', viewport)
    await page.getByRole('checkbox', { name: /^I am this adult player/ }).check()
    await send.click()
    await expect(page.getByText('Waiting for moderation · private')).toBeVisible()
    expect(writes[0]).toMatchObject({ public_profile_consent: true, consent_version: 'public-profile-v1', expected_version: 2 })
    await shot(page, 'moderation-wait-test-fixture', viewport)
    await page.getByRole('button', { name: 'Withdraw public consent' }).click()
    await expect(page.getByText('Consent withdrawn · private')).toBeVisible()
    await shot(page, 'withdrawn-test-fixture', viewport)
  })
  test(`private club invitation ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    const writes = await fixture(page)
    await page.goto('/club-publications/7')
    await page.getByRole('combobox').selectOption('23')
    await page.getByLabel('Player’s email').fill('fixture@c1.example')
    await page.getByRole('button', { name: 'Create private invite' }).click()
    await expect(page.getByLabel('Private invite link')).toHaveValue(/#token=/)
    expect(writes[0].recipient_email).toBe('fixture@c1.example')
    await shot(page, 'club-invite-test-fixture', viewport)
  })
  test(`authenticated private claim and public profile ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    await fixture(page, { invite: true })
    await page.goto('/player-publication-invite#token=synthetic-test-token-private-only')
    await expect(page.getByRole('button', { name: 'Claim my private profile' })).toBeDisabled()
    await expect(page).not.toHaveURL(/#token=/)
    await shot(page, 'claim-test-fixture', viewport)
  })
  test(`admin moderation needs a reason ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    const writes = await fixture(page, { admin: true, consented: true })
    await page.goto('/admin/player-publications')
    await expect(page.getByRole('button', { name: 'Approve profile and self-claim' })).toBeDisabled()
    await page.getByLabel('Review reason').fill('Independent adult identity and consent checked')
    await shot(page, 'admin-review-test-fixture', viewport)
    await page.getByRole('button', { name: 'Approve profile and self-claim' }).click()
    expect(writes[0]).toMatchObject({ action: 'approve', reason: 'Independent adult identity and consent checked' })
  })
  test(`approved publication can withdraw ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    await fixture(page, { published: true })
    await page.goto('/player-publications')
    await expect(page.getByRole('link', { name: 'View public profile' })).toBeVisible()
    await shot(page, 'public-test-fixture', viewport)
    await page.getByRole('button', { name: 'Withdraw public consent' }).click()
    await expect(page.getByRole('link', { name: 'View public profile' })).toHaveCount(0)
  })
}
test('anonymous invite preserves sign-in handoff without private API calls', async ({ page }) => {
  const requests = []
  page.on('request', req => { if (req.url().includes('player-publication-invites')) requests.push(req.url()) })
  await fixture(page, { anonymous: true })
  await page.goto('/player-publication-invite#token=synthetic-test-token-private-only')
  await expect(page.getByRole('button', { name: 'Sign in to review' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign in to review' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(requests).toEqual([])
})
test('flag off hides new UI and private requests', async ({ page }) => {
  const requests = []
  page.on('request', req => { if (req.url().includes('/me/player-publications')) requests.push(req.url()) })
  await fixture(page, { on: false })
  await page.goto('/player-publications')
  await expect(page.getByText('Page unavailable.')).toBeVisible()
  expect(requests).toEqual([])
})
