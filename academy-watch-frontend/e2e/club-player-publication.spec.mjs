/* global window, document */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const row = { id: 1, program_id: 7, local_player_id: 23, player_name: 'Synthetic C1 adult · test fixture', claimed: true, consented: false, association_confirmed: true, moderation_status: 'pending', withdrawn: false, club_revoked: false, version: 2, consent_version: 'public-profile-v1', consent_text: 'I am this adult player. I agree to make my approved profile public, including scout discovery, watchlists and sharing. Introductions go to my club first, then I choose. I can withdraw at any time.', public: false }
async function fixture(page, { on = true, admin = false, anonymous = false, published = false, consented = false, invite = false, selfInvite = false, longValues = false, featureRequests = [] } = {}) {
  if (!anonymous) await page.addInitScript(({ admin }) => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-c1-browser-token')
    localStorage.setItem('academy_watch_display_name', 'Synthetic C1 fixture')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (admin) { localStorage.setItem('academy_watch_admin_key', 'synthetic-c1-key'); localStorage.setItem('academy_watch_is_admin', 'true') }
  }, { admin })
  let current = { ...row, claimed: !invite, consented: published || consented, moderation_status: published ? 'approved' : 'pending', public: published,
    player_name: longValues ? 'X'.repeat(200) : row.player_name,
    moderation_evidence: admin ? { club_name: longValues ? 'C'.repeat(60) : 'Synthetic C1 club', squads: ['Adult first team'], adult: true, adult_evidence_source: 'club_birth_date', invited_email_masked: longValues ? `f***@${'d'.repeat(60)}.example` : 'f***@c1.example', claimant_email_masked: 'f***@c1.example', inviter_email_masked: 'm***@c1.example', same_account: selfInvite, same_email: selfInvite, self_invitation: selfInvite, invited_at: '2026-09-28T12:00:00', claimed_at: '2026-09-29T12:00:00', consented_at: '2026-09-30T12:00:00', review_history: [{ decision: 'rejected', reason: 'Previous authenticity rejection', reviewed_at: '2026-09-30T11:00:00' }] } : undefined }
  const writes = []
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), p = url.pathname
    const reply = json => route.fulfill({ json })
    if (p === '/api/features') { featureRequests.push(p); return reply({ club_player_publication: on }) }
    if (p === '/api/auth/me') return reply({ email: 'fixture@c1.example', role: admin ? 'admin' : 'user', display_name: 'Synthetic C1 fixture', display_name_confirmed: true })
    if (p === '/api/admin/dashboard-stats') return reply({ players: { total: 0, academy: 0, on_loan: 0, first_team: 0, released: 0 }, teams: { tracked: 0 }, newsletters: { total: 0, published: 0, drafts: 0 } })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: true })
    if (p === '/api/me/player-publication-invites/preview') return reply({ publication: current })
    if (p === '/api/me/player-publications' || p === '/api/club/7/player-publications' || p === '/api/admin/player-publications') return reply({ publications: [current] })
    if (p === '/api/club/7/publication-candidates') return reply({ players: [{ id: 23, name: row.player_name }] })
    if (p === '/api/club/7/players/23/publication-invite') { writes.push(request.postDataJSON()); return route.fulfill({ status: 201, json: { publication: current, token: 'synthetic-test-token-private-only' } }) }
    if (/player-publications\/1\/(consent|withdraw|review|revoke)$/.test(p)) {
      writes.push(request.postDataJSON())
      if (p.endsWith('/consent')) current = { ...current, consented: true, moderation_status: 'pending', version: 3 }
      if (p.endsWith('/withdraw')) current = { ...current, withdrawn: true, consented: false, public: false, version: 5 }
      return reply({ publication: current })
    }
    return reply({})
  })
  return writes
}
async function shot(page, name, viewport) {
  const folder = process.env.C1_SCREENSHOT_DIR || path.join(process.env.HOME, 'codex-runs/aw-redesign/shots/C1F2')
  await fs.mkdir(folder, { recursive: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.addStyleTag({ content: '[data-agentation-toolbar], [class*=styles-module__toolbar], [class*=styles-module__panel] { display: none !important; }' })
  const dialog = page.getByRole('alertdialog')
  const confirming = await dialog.isVisible()
  if (confirming) await dialog.evaluate(el => Promise.all(el.getAnimations({ subtree: true }).map(animation => animation.finished.catch(() => {}))))
  await page.screenshot({ path: path.join(folder, `${name}-${viewport}.png`), fullPage: !confirming })
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
    await expect(page.getByRole('alertdialog')).toBeVisible()
    await page.getByRole('button', { name: 'Confirm withdrawal' }).click()
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
    await expect(page.getByText('Synthetic C1 club', { exact: true })).toBeVisible()
    await expect(page.getByText('Previous authenticity rejection', { exact: true })).toBeVisible()
    await expect(page.getByText('2026-09-30T12:00:00', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Adult first team', { exact: true })).toBeVisible()
    await expect(page.getByText('Yes · Full birth date on club record', { exact: true })).toBeVisible()
    await expect(page.getByText('f***@c1.example', { exact: true })).toHaveCount(2)
    await shot(page, 'admin-review-test-fixture', viewport)
    await page.getByRole('button', { name: 'Approve profile and self-claim' }).click()
    expect(writes[0]).toMatchObject({ action: 'approve', reason: 'Independent adult identity and consent checked' })
  })
  test(`self-invitation is visibly flagged and approval blocked ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    const writes = await fixture(page, { admin: true, consented: true, selfInvite: true })
    await page.goto('/admin/player-publications')
    await page.getByLabel('Review reason').fill('The manager invited their own address')
    await expect(page.getByRole('alert')).toContainText('The inviter and claimant match')
    await expect(page.getByRole('button', { name: 'Approve profile and self-claim' })).toBeDisabled()
    await shot(page, 'admin-self-invite-blocked-test-fixture', viewport)
    expect(writes).toEqual([])
    await page.getByRole('button', { name: 'Keep private' }).click()
    expect(writes[0].action).toBe('reject')
  })
  test(`approved publication can withdraw ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    await fixture(page, { published: true })
    await page.goto('/player-publications')
    await expect(page.getByRole('link', { name: 'View public profile' })).toBeVisible()
    await shot(page, 'public-test-fixture', viewport)
    await page.getByRole('button', { name: 'Withdraw public consent' }).click()
    await expect(page.getByRole('alertdialog')).toBeVisible()
    await page.getByRole('button', { name: 'Confirm withdrawal' }).click()
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
for (const route of ['/player-publications', '/player-publication-invite', '/club-publications/7', '/admin/player-publications']) {
  for (const anonymous of [false, true]) {
    test(`flag off ${route} uses ordinary unknown-route result anonymous=${anonymous}`, async ({ page }) => {
      const requests = []
      page.on('request', req => { if (/\/api\/(me\/player-publication|club\/7\/(player-publications|publication-candidates)|admin\/player-publications)/.test(req.url())) requests.push(req.url()) })
      await fixture(page, { on: false, anonymous, admin: !anonymous })
      const unknown = route.startsWith('/admin/') ? '/admin/unknown-c1-fixture' : '/unknown-c1-fixture'
      await page.goto(unknown)
      await page.waitForURL(route.startsWith('/admin/') && !anonymous ? '**/admin/dashboard' : '**/')
      const ordinaryURL = page.url()
      await page.goto(route)
      await expect(page).toHaveURL(ordinaryURL)
      await expect(page.getByText('Page unavailable.')).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Sign in to review' })).toHaveCount(0)
      expect(requests).toEqual([])
    })
  }
}

test('admin can remove a legacy provider link from a club identity', async ({ page }) => {
  await fixture(page, { admin: true })
  await page.route('**/api/admin/local-players*', route => route.fulfill({ json: { players: [{ id: 23, display_name: 'Synthetic bridged club adult', status: 'approved', provenance: 'club', api_player_id: 7001 }] } }))
  const writes = []
  await page.route('**/api/admin/local-players/23/link-api', route => {
    writes.push(route.request().postDataJSON())
    return route.fulfill({ json: { player: { id: 23, api_player_id: -23, status: 'pending' } } })
  })
  await page.goto('/admin/showcase')
  await page.getByRole('tab', { name: 'Local players' }).click()
  await page.getByRole('button', { name: 'Edit API link' }).click()
  await page.getByRole('button', { name: 'Remove provider link' }).click()
  expect(writes).toEqual([{ player_api_id: null }])
})

for (const mode of ['player', 'club', 'admin', 'invite']) {
  test(`long values fit at 390px with one main landmark: ${mode}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    const featureRequests = []
    await fixture(page, { admin: mode === 'admin', invite: mode === 'invite', consented: mode === 'admin', longValues: true, featureRequests })
    await page.goto({ player: '/player-publications', club: '/club-publications/7', admin: '/admin/player-publications', invite: '/player-publication-invite#token=synthetic-test-token-private-only' }[mode])
    await expect(page.getByRole('heading', { name: 'X'.repeat(200) })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await expect(page.getByRole('main')).toHaveCount(1)
    expect(featureRequests).toHaveLength(1)
    if (mode === 'invite') {
      const width = await page.getByRole('checkbox', { name: /^I am this adult player/ }).evaluate(el => el.getBoundingClientRect().width)
      expect(width).toBeGreaterThanOrEqual(20)
    }
    await shot(page, `long-values-${mode}-test-fixture`, 'mobile')
  })
}
for (const [viewport, size] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
  test(`club revocation confirms consequences and cancellation preserves permission ${viewport}`, async ({ page }) => {
    await page.setViewportSize(size)
    const writes = await fixture(page, { published: true })
    await page.goto('/club-publications/7')
    await page.getByRole('button', { name: 'Revoke club association' }).click()
    await expect(page.getByRole('alertdialog')).toContainText('permanently closes existing introductions')
    expect(writes).toHaveLength(0)
    await shot(page, 'revocation-confirmation-test-fixture', viewport)
    await page.getByRole('button', { name: 'Keep current permission' }).click()
    expect(writes).toHaveLength(0)
    await page.getByRole('button', { name: 'Revoke club association' }).click()
    await page.getByRole('button', { name: 'Confirm revocation' }).click()
    await expect.poll(() => writes.length).toBe(1)
  })
}
for (const on of [true, false]) {
  test(`feature reads are shared during navigation enabled=${on}`, async ({ page }) => {
    const featureRequests = []
    await fixture(page, { on, featureRequests })
    await page.goto('/player-publications')
    if (on) await expect(page.getByRole('heading', { name: 'Your public profile' })).toBeVisible()
    else await expect(page).toHaveURL(/\/$/)
    expect(featureRequests).toHaveLength(1)
    await page.evaluate(() => { window.history.pushState({}, '', '/club-publications/7'); window.dispatchEvent(new window.PopStateEvent('popstate')) })
    if (on) await expect(page.getByRole('heading', { name: 'Invite an adult player' })).toBeVisible()
    else await expect(page).toHaveURL(/\/$/)
    expect(featureRequests).toHaveLength(1)
  })
}

test('unavailable invite explains recovery', async ({ page }) => {
  await fixture(page, { invite: true })
  await page.route('**/api/me/player-publication-invites/preview', route => route.fulfill({status:404,json:{error:'invite_unavailable'}}))
  await page.goto('/player-publication-invite#token=synthetic-test-token-private-only')
  await expect(page.getByRole('alert')).toContainText('ask your club for a new invitation')
  console.log('O6_ALERT', await page.getByRole('alert').innerText())
})

test('transient feature failure preserves draft; explicit OFF redirects', async ({ page }) => {
  await page.clock.install()
  await fixture(page)
  let failed=false, attempts=0
  await page.route('**/api/features', route => {
    attempts++
    return failed ? route.fulfill({status:503,json:{error:'temporary_failure'}}) : route.fulfill({json:{club_player_publication:true}})
  })
  await page.goto('/club-publications/7')
  await page.getByRole('combobox').selectOption('23')
  await page.getByLabel('Player’s email').fill('rc1v2-x-unsaved@example.test')
  await expect(page.getByLabel('Player’s email')).toHaveValue('rc1v2-x-unsaved@example.test')
  failed=true
  await page.clock.fastForward(16000)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect.poll(() => attempts).toBeGreaterThan(1)
  await expect(page).toHaveURL(/club-publications\/7$/)
  await expect(page.getByLabel('Player’s email')).toHaveValue('rc1v2-x-unsaved@example.test')
  await shot(page, 'transient-failure-draft', 'desktop')
  await page.route('**/api/features', route => route.fulfill({json:{club_player_publication:false}}))
  await page.clock.fastForward(16000)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/\/$/)
  console.log('O7_REDIRECT',page.url(),'feature attempts',attempts,'draft removed')
})

test('rejected consented player can request a fresh private review', async ({ page }) => {
  await page.setViewportSize({width:390,height:844})
  const writes=await fixture(page, { consented:true })
  await page.route('**/api/me/player-publications', route => route.fulfill({json:{publications:[{...row,consented:true,moderation_status:'rejected',review_history:[{decision:'rejected',reason:'Earlier rejection'}]}]}}))
  await page.goto('/player-publications')
  await expect(page.getByText('Not approved · private')).toBeVisible()
  await expect(page.getByRole('button',{name:'Withdraw public consent'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Give public profile consent'})).toBeDisabled()
  await expect(page.getByRole('checkbox',{name:/^I am this adult player/})).toBeVisible()
  await shot(page,'rejected-fresh-consent','mobile')
  await page.getByRole('checkbox',{name:/^I am this adult player/}).check()
  await page.getByRole('button',{name:'Give public profile consent'}).click()
  await expect(page.getByText('Waiting for moderation · private')).toBeVisible()
  expect(writes[0]).toMatchObject({public_profile_consent:true})
  await expect(page.getByRole('link',{name:'View public profile'})).toHaveCount(0)
  console.log('O8_REJECTED_PAGE',await page.locator('main').innerText())
})


test('stored birth conflict is visible and blocks moderator approval',async ({page})=>{
  await page.setViewportSize({width:390,height:844})
  await fixture(page,{admin:true,consented:true})
  await page.route('**/api/admin/player-publications',route=>route.fulfill({json:{publications:[{...row,consented:true,moderation_evidence:{adult:false,birth_evidence_conflict:true,adult_evidence_source:'club_birth_date'}}]}}))
  await page.goto('/admin/player-publications')
  await page.getByLabel('Review reason').fill('Conflicting evidence must remain private')
  await expect(page.getByRole('alert')).toContainText('Stored birth evidence conflicts with adulthood')
  await expect(page.getByRole('button',{name:'Approve profile and self-claim'})).toBeDisabled()
  await shot(page,'birth-conflict-review','mobile')
})
