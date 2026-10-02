/* global document, innerWidth, getComputedStyle, history, dispatchEvent, PopStateEvent */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

// Other features can independently report a failed shared bootstrap.
const applicationAlerts = page => page.getByRole('alert').filter({ hasText: /Could not load opportunities|Could not check your profiles/ })

const oid = 'f9c683d7-2c0f-57ba-ae18-3a2544fa7c96'
const opportunity = { id: oid, program_id: 7, club_name: 'Synthetic UXBF1 Club', club_slug: 'synthetic-uxbf1', type: 'trial', title: 'Adult trial', description: 'Synthetic review regression opportunity.', instructions: 'Bring boots.', venue: 'Test pitch', timezone: 'UTC', starts_at: '2026-10-20T10:00:00Z', ends_at: '2026-10-20T12:00:00Z', closes_at: '2026-10-18T12:00:00Z', gender_program: 'all', position_requirements: 'All positions', status: 'published' }
const application = { id: '00000000-0000-4000-8000-000000000002', opportunity_id: oid, opportunity_title: opportunity.title, club_name: opportunity.club_name, status: 'new', status_label: 'New', timezone: 'UTC', version: 1, submitted_at: '2026-10-01T10:00:00Z' }
const claim = { claim_id: 3, signed_player_id: -9, name: 'Synthetic Adult', profile_path: '/local-players/9', application: null }
const program = { id: 7, name: opportunity.club_name, slug: opportunity.club_slug, brand: {}, platform_status: 'approved', provenance: { label: 'Self-reported' }, updates: [] }

async function fixture(page, { role = 'owner', on = true, eligible = true, claims = [claim], rows = [application], item = opportunity, conflict = false, featuresStatus = 200, claimsStatus = 200, retrySuccess = false, items, listStatus = 200, waitRetry, waitItems, waitFeatures, waitClaims } = {}) {
  if (role !== 'visitor') await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'uxbf1-synthetic-token')
    localStorage.setItem('academy_watch_display_name', 'Synthetic Viewer')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  const calls = [], errors = [], submissions = [], claimsReads = []
  let recovered = false
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('pageerror', error => errors.push(error.message))
  await page.context().route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname
    calls.push(p)
    const reply = json => route.fulfill({ json })
    if (p === '/api/opportunities/features') return route.fulfill({ status: on ? 200 : 404, json: on ? { opportunities: true, applications: true } : { error: 'Not found' } })
    if (p === '/api/features') {
      if (waitFeatures) await waitFeatures
      if (recovered && waitRetry) await waitRetry
      const status = retrySuccess && recovered ? 200 : featuresStatus
      return route.fulfill({ status, json: status === 200 ? (on ? { opportunities: true, applications: true } : {}) : { error: 'rate_limited' } })
    }
    if (p === '/api/auth/me') return reply({ email: 'uxbf1@example.test', display_name: 'Synthetic Viewer', display_name_confirmed: true, role: role === 'scout' ? 'scout' : 'user' })
    if (p === '/api/meta/data-mode') return reply({ api_football_frozen: true })
    if (p === '/api/programs/synthetic-uxbf1') return reply({ program })
    if (p === '/api/local-players/9') return reply({ player: { id: 9, api_player_id: -9, display_name: 'Synthetic Adult', birth_year: 2000, status: 'approved' } })
    if (p === '/api/local-players/9/showcase') return reply({ claim_status: 'claimed', profile: { bio: 'Synthetic profile' }, affiliations: [], reel: [], photos: [] })
    if (p === '/api/me/claims') return reply({ claims: role === 'owner' ? [{ id: 3, local_player_id: 9, player_api_id: -9, relationship_type: 'player', status: 'approved' }] : [] })
    if (p === '/api/me/application-claims') {
      claimsReads.push(req.url())
      if (waitClaims) await waitClaims
      if (recovered && waitRetry) await waitRetry
      const status = retrySuccess && recovered ? 200 : claimsStatus
      return route.fulfill({ status, json: status === 200 ? { claims: eligible ? claims : [] } : { error: 'unavailable' } })
    }
    if (p === '/api/funding/claims/me') return reply({ claims: role === 'club-owner' ? [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] : [] })
    if (p === '/api/me/club') return reply({ clubs: [] })
    if (p === '/api/me/club-claims') return reply({ claims: [] })
    if (p === '/api/me/applications') return reply({ applications: rows })
    if (p === '/api/opportunities') {
      if (waitItems) await waitItems
      return route.fulfill({ status: listStatus, json: listStatus === 200 ? { opportunities: items ?? [item], has_more: false } : { error: 'unavailable' } })
    }
    if (p.toLowerCase() === `/api/opportunities/${oid}`) return reply({ opportunity: item })
    if (p === `/api/opportunities/${oid}/applications`) {
      submissions.push(req.postDataJSON())
      return route.fulfill({ status: conflict ? 409 : 201, json: conflict ? { error: 'already_applied' } : { application } })
    }
    return reply({})
  })
  return { calls, errors, submissions, claimsReads, recover: () => { recovered = true } }
}
async function shot(page, name, size) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  if (!process.env.UXBF1_SCREENSHOTS) return
  await fs.mkdir(process.env.UXBF1_SCREENSHOTS, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: path.join(process.env.UXBF1_SCREENSHOTS, `${name}-${size}.png`), fullPage: true, style: '[data-agentation-root] { visibility: hidden !important; }' })
}
const businessCalls = calls => calls.filter(p => p.startsWith('/api/opportunities') || p.startsWith('/api/me/application'))
for (const [width, height, size] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
  test.describe(`UXBF1 ${size}`, () => {
    test.use({ viewport: { width, height } })
    test('dark bootstrap preserves club, home, onboarding and owner page with zero business calls/errors', async ({ page }) => {
      const evidence = await fixture(page, { on: false })
      for (const url of ['/programs/synthetic-uxbf1', '/', '/onboarding/player', '/local-players/9']) {
        await page.goto(url)
        await page.waitForLoadState('networkidle')
        if (url.includes('programs')) await expect(page.getByRole('heading', { name: 'Straight from the club, soon.' })).toBeVisible()
        if (url.includes('onboarding')) await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
        if (url.includes('local-players')) await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toBeVisible()
      }
      expect(businessCalls(evidence.calls)).toEqual([])
      expect(evidence.errors).toEqual([])
    })
    test('signed-out dark club adds zero business requests or console errors', async ({ page }) => {
      const evidence = await fixture(page, { role: 'visitor', on: false })
      await page.goto('/programs/synthetic-uxbf1')
      await expect(page.getByRole('heading', { name: 'Straight from the club, soon.' })).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(businessCalls(evidence.calls)).toEqual([])
      expect(evidence.errors).toEqual([])
    })
    test('all mounted consumers share one bootstrap request, including client navigation', async ({ page }) => {
      const evidence = await fixture(page)
      await page.goto('/onboarding/player')
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      await page.getByRole('link', { name: 'Synthetic Adult · My profile →' }).click()
      await expect(page.getByRole('heading', { name: 'Your applications', exact: true })).toBeVisible()
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(1)
      expect(evidence.calls).not.toContain('/api/opportunities/features')
    })
    test('applied profile selector stays available both ways and resets successful submission', async ({ page }) => {
      const evidence = await fixture(page, { claims: [{ ...claim, application }, { ...claim, claim_id: 4, signed_player_id: -10, profile_path: '/local-players/10', name: 'Second Adult' }] })
      await page.goto(`/opportunities/${oid}`)
      const select = page.getByLabel('Your player profile')
      await expect(page.getByText('You applied — New')).toBeVisible()
      await select.selectOption('4')
      await expect(page.getByRole('button', { name: 'Send application' })).toBeVisible()
      await select.selectOption('3')
      await expect(page.getByText('You applied — New')).toBeVisible()
      await select.selectOption('4')
      await page.getByLabel('Position', { exact: true }).fill('Midfielder')
      await page.getByRole('checkbox', { name: 'I agree that this club may contact me about my application.' }).check()
      await page.getByRole('button', { name: 'Send application' }).click()
      await expect(page.getByText('Application sent.')).toBeVisible()
      expect(evidence.submissions[0].claim_id).toBe(4)
      await select.selectOption('3')
      await expect(page.getByText('Application sent.')).toHaveCount(0)
      await expect(page.getByText('You applied — New')).toBeVisible()
      await select.selectOption('4')
      await expect(page.getByText('You applied — New')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
      await shot(page, 'multi-profile-applied', size)
    })
    test('age-band state offers another opportunity and no form', async ({ page }) => {
      await fixture(page, { claims: [{ ...claim, outside_age_band: true }] })
      await page.goto(`/opportunities/${oid}`)
      await expect(page.getByText('Your profile is outside the age range for this opportunity.')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
      await shot(page, 'age-band', size)
    })
    for (const role of ['owner', 'visitor', 'scout', 'other-player']) test(`${role} summary visibility and private request boundary`, async ({ page }) => {
      const evidence = await fixture(page, { role })
      await page.goto('/local-players/9')
      await expect(page.getByRole('heading', { name: 'Synthetic Adult', exact: true })).toBeVisible()
      await page.waitForLoadState('networkidle')
      const summary = page.getByRole('region', { name: 'Your applications', exact: true })
      if (role === 'owner') { await expect(summary).toBeVisible(); await expect(summary.getByText('Adult trial')).toBeVisible(); await shot(page, 'owner-summary', size) }
      else { await expect(summary).toHaveCount(0); expect(evidence.calls).not.toContain('/api/me/applications') }
    })
    test('ineligible owner keeps teaser and makes no applications read', async ({ page }) => {
      const evidence = await fixture(page, { eligible: false })
      await page.goto('/local-players/9')
      await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(evidence.calls).not.toContain('/api/me/applications')
    })
    test('valid long title and venue wrap on club and owner summary', async ({ page }) => {
      const title = 'X'.repeat(180), venue = 'V'.repeat(200)
      await fixture(page, { item: { ...opportunity, title, venue }, rows: [{ ...application, opportunity_title: title }] })
      await page.goto('/programs/synthetic-uxbf1')
      await expect(page.getByText(title, { exact: true })).toBeVisible()
      await expect(page.getByText(venue, { exact: false })).toBeVisible()
      await shot(page, 'long-club-title-venue', size)
      await page.goto('/local-players/9')
      await expect(page.getByRole('region', { name: 'Your applications', exact: true }).getByText(title)).toBeVisible()
      await shot(page, 'long-owner-title', size)
    })
    test('pending bootstrap never shows coming-soon teaser', async ({ page }) => {
      let resolve
      const waitFeatures = new Promise(r => { resolve = r })
      await fixture(page, { waitFeatures })
      await page.goto('/programs/synthetic-uxbf1')
      await expect(page.getByText('Loading opportunities…')).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Straight from the club, soon.' })).toHaveCount(0)
      resolve()
      await expect(page.getByText('Adult trial', { exact: true })).toBeVisible()
    })
    test('pending claims never show wrong audience and discovery stays below applications', async ({ page }) => {
      let resolve
      const waitClaims = new Promise(r => { resolve = r })
      await fixture(page, { waitClaims })
      await page.goto('/onboarding/player')
      await expect(page.getByText('Checking your profiles…', { exact: true })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toHaveCount(0)
      resolve()
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      await expect(page.getByText('Find your profile', { exact: true })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Create your profile', exact: true })).toBeVisible()
      const appY = await page.locator('#my-applications').evaluate(el => el.getBoundingClientRect().top)
      const discoveryY = await page.getByText('Find your profile', { exact: true }).evaluate(el => el.getBoundingClientRect().top)
      expect(discoveryY).toBeGreaterThan(appY)
      await shot(page, 'player-home-discovery', size)
    })
    test('bootstrap failure remains unavailable instead of declaring feature off', async ({ page }) => {
      await fixture(page, { featuresStatus: 429 })
      await page.goto('/programs/synthetic-uxbf1')
      await expect(applicationAlerts(page)).toContainText('Could not load opportunities')
      await expect(page.getByRole('heading', { name: 'Straight from the club, soon.' })).toHaveCount(0)
    })
    test('failed bootstrap never advertises recruiting as coming soon', async ({ page }) => {
      await fixture(page, { role: 'club-owner', featuresStatus: 429 })
      await page.goto('/my-club?view=recruiting')
      await expect(applicationAlerts(page)).toContainText('Could not load opportunities')
      await expect(page.getByRole('heading', { name: 'The next player. The right place.' })).toHaveCount(0)
    })
    test('expired retained duplicate hides form without expired details', async ({ page }) => {
      await fixture(page, { claims: [{ ...claim, application_unavailable: true }] })
      await page.goto(`/opportunities/${oid}`)
      await expect(page.getByText('You already applied. This application is no longer available.')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
      await shot(page, 'expired-retained-duplicate', size)
    })
    test('already_applied response replaces form with useful status copy', async ({ page }) => {
      await fixture(page, { conflict: true })
      await page.goto(`/opportunities/${oid}`)
      await page.getByLabel('Position', { exact: true }).fill('Midfielder')
      await page.getByRole('checkbox', { name: 'I agree that this club may contact me about my application.' }).check()
      await page.getByRole('button', { name: 'Send application' }).click()
      await expect(page.getByText('You already applied. View your applications and next steps on player home.')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send application' })).toHaveCount(0)
    })
    for (const role of ['visitor', 'owner']) for (const status of [500, 429]) {
      test(`UXBF2 failed bootstrap ${status} keeps discovery for ${role} and retries`, async ({ page }) => {
        const evidence = await fixture(page, { role, on: false, featuresStatus: status, retrySuccess: true })
        await page.goto('/onboarding/player')
        await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
        await expect(applicationAlerts(page)).toHaveCount(1)
        await expect(applicationAlerts(page)).toContainText('Could not load opportunities')
        await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toHaveCount(0)
        await expect(page.getByRole('link', { name: 'Create your profile', exact: true })).toBeVisible()
        await page.getByLabel('Player name').fill('Synthetic')
        await expect(page.getByText('No tracked player matches', { exact: false })).toBeVisible()
        expect(evidence.calls.some(p => p.startsWith('/api/scout/players'))).toBe(true)
        expect(businessCalls(evidence.calls)).toEqual([])
        await shot(page, `bootstrap-${status}-${role}-discovery`, size)
        evidence.recover()
        await page.getByRole('button', { name: 'Retry applications' }).click()
        await expect(applicationAlerts(page)).toHaveCount(0)
        await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toBeVisible()
        expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(2)
        expect(businessCalls(evidence.calls)).toEqual([])
      })
    }
    test('UXBF2 failed enabled bootstrap keeps discovery throughout retry', async ({ page }) => {
      let resolve
      const waitRetry = new Promise(r => { resolve = r })
      const evidence = await fixture(page, { featuresStatus: 500, retrySuccess: true, waitRetry })
      await page.goto('/onboarding/player')
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      await expect(applicationAlerts(page)).toHaveCount(1)
      await page.getByLabel('Player name').fill('Synthetic')
      evidence.recover()
      await page.getByRole('button', { name: 'Retry applications' }).click()
      await expect(page.getByRole('button', { name: 'Retry applications' })).toBeDisabled()
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      await expect(page.getByLabel('Player name')).toHaveValue('Synthetic')
      await expect(page.getByRole('link', { name: 'Create your profile', exact: true })).toBeVisible()
      resolve()
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      await expect(applicationAlerts(page)).toHaveCount(0)
      await expect(page.locator('#my-applications')).toBeVisible()
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(2)
    })
    test('UXBF2 failed claims keeps discovery with one contextual error and retry', async ({ page }) => {
      let resolve
      const waitRetry = new Promise(r => { resolve = r })
      const evidence = await fixture(page, { claimsStatus: 500, retrySuccess: true, waitRetry })
      await page.goto('/onboarding/player')
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      await expect(applicationAlerts(page)).toHaveCount(1)
      await expect(applicationAlerts(page)).toContainText('Could not check your profiles')
      await expect(page.getByRole('link', { name: 'Create your profile', exact: true })).toBeVisible()
      await page.getByLabel('Player name').fill('Synthetic')
      await expect(page.getByText('No tracked player matches', { exact: false })).toBeVisible()
      expect(evidence.calls).not.toContain('/api/me/applications')
      await shot(page, 'claims-error-discovery', size)
      const initialClaims = evidence.calls.filter(p => p === '/api/me/application-claims').length
      evidence.recover()
      await page.getByRole('button', { name: 'Retry applications' }).click()
      await expect(page.getByRole('button', { name: 'Retry applications' })).toBeDisabled()
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      await expect(page.getByLabel('Player name')).toHaveValue('Synthetic')
      resolve()
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      await expect(applicationAlerts(page)).toHaveCount(0)
      await expect(page.locator('#my-applications')).toBeVisible()
      expect(evidence.calls.filter(p => p === '/api/me/application-claims')).toHaveLength(initialClaims + 1)
    })
    test('UXBF2 parent anchor keeps email in view after delayed adult claims settle', async ({ page }) => {
      let resolve
      const waitClaims = new Promise(r => { resolve = r })
      await fixture(page, { waitClaims })
      await page.goto(`/opportunities/${oid}#parent-interest`)
      await expect(page.getByText('Checking your profiles…', { exact: true })).toBeVisible()
      resolve()
      await expect(page.getByLabel('Position', { exact: true })).toBeVisible()
      const block = page.locator('#parent-interest')
      await expect(block).toBeFocused()
      await expect(block.getByLabel('Email address')).toBeInViewport({ ratio: 1 })
      await shot(page, 'adult-parent-interest-settled', size)
      if (process.env.UXBF1_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.UXBF1_SCREENSHOTS, `adult-parent-interest-settled-${size}-viewport.png`), style: '[data-agentation-root] { visibility: hidden !important; }' })
      await page.getByLabel('Position', { exact: true }).fill('Midfielder')
      await expect(page.getByLabel('Position', { exact: true })).toBeFocused()
    })
    for (const surface of ['detail', 'home']) test(`UXBF2 maximum invitation text wraps on ${surface}`, async ({ page }) => {
      const invited = { ...application, status: 'invited', status_label: 'Invited', trial_at: '2026-10-20T10:00:00Z', trial_venue: 'V'.repeat(200), trial_instructions: 'I'.repeat(3000), reservation_state: 'pending' }
      await fixture(page, { claims: [{ ...claim, application: invited }], rows: [invited] })
      await page.goto(surface === 'detail' ? `/opportunities/${oid}` : '/onboarding/player')
      await expect(page.getByText(invited.trial_instructions, { exact: true })).toBeVisible()
      await shot(page, `maximum-invitation-${surface}`, size)
    })
    test('UXBF3 maximum claim name remains readable inside player home pill', async ({ page }) => {
      const name = 'X'.repeat(200)
      await fixture(page, { claims: [{ ...claim, name }] })
      await page.goto('/onboarding/player')
      const profile = page.getByRole('link', { name: `${name} · My profile →` })
      await expect(profile).toBeVisible()
      await expect(profile).toHaveAttribute('href', '/local-players/9')
      // Check glyph contrast at the curved edges, beyond the existing overflow check.
      expect(await profile.evaluate(link => {
        const pill = link.getBoundingClientRect()
        const radius = Math.min(parseFloat(getComputedStyle(link).borderTopLeftRadius), pill.width / 2, pill.height / 2)
        const text = link.querySelector('span').firstChild
        for (let i = 0; i < text.length; i++) {
          const range = document.createRange()
          range.setStart(text, i); range.setEnd(text, i + 1)
          const rect = range.getBoundingClientRect()
          const x = (rect.left + rect.right) / 2 - pill.left
          const y = (rect.top + rect.bottom) / 2 - pill.top
          const dx = Math.max(radius - x, x - (pill.width - radius), 0)
          const dy = Math.max(radius - y, y - (pill.height - radius), 0)
          if (dx * dx + dy * dy > radius * radius) return false
        }
        return true
      })).toBe(true)
      await shot(page, 'maximum-profile-name', size)
    })
    test('UXBF2 empty opportunity list never advertises Open now', async ({ page }) => {
      let resolve
      const waitItems = new Promise(r => { resolve = r })
      await fixture(page, { items: [], waitItems })
      await page.goto('/programs/synthetic-uxbf1')
      await expect(page.getByText('Loading opportunities…')).toBeVisible()
      await expect(page.getByText('Open now', { exact: true })).toHaveCount(0)
      resolve()
      await expect(page.getByText('No open opportunities at this club right now.')).toBeVisible()
      await expect(page.getByText('Open now', { exact: true })).toHaveCount(0)
      await shot(page, 'empty-club-opportunities', size)
    })
    test('UXBF2 failed opportunity list omits Open now', async ({ page }) => {
      await fixture(page, { listStatus: 500 })
      await page.goto('/programs/synthetic-uxbf1')
      await expect(applicationAlerts(page)).toBeVisible()
      await expect(page.getByText('Open now', { exact: true })).toHaveCount(0)
      await shot(page, 'failed-club-opportunities', size)
    })
    // Client-side route changes retain the shared provider and its cached state.
    const navigate = async (page, url) => {
      await page.evaluate(value => {
        const idx = (history.state?.idx ?? 0) + 1
        history.pushState({ usr: null, key: crypto.randomUUID(), idx }, '', value)
        dispatchEvent(new PopStateEvent('popstate'))
      }, url)
      await expect(page).toHaveURL(new RegExp(url + '$'))
    }
    const menu = async page => {
      await page.getByRole('button', { name: size === 'mobile' ? 'Toggle navigation menu' : 'Synthetic Viewer' }).click()
      return page.getByRole(size === 'mobile' ? 'dialog' : 'menu')
    }
    const destinations = ['/opportunities', `/opportunities/${oid}`, '/programs/synthetic-uxbf1', '/local-players/9']
    const normalContent = async (page, url, on) => {
      if (!on) {
        const title = url.includes('programs') ? 'Straight from the club, soon.' : url.includes('local-players') ? 'Your next chapter.' : 'Room for your next step.'
        await expect(page.getByRole('heading', { name: title })).toBeVisible()
      } else if (url === '/opportunities') await expect(page.getByRole('link', { name: /Adult trial/ }).first()).toBeVisible()
      else if (url.includes('programs')) await expect(page.getByRole('link', { name: /Adult trial/ })).toBeVisible()
      else if (url.includes('local-players')) await expect(page.getByRole('heading', { name: 'Your applications', exact: true })).toBeVisible()
      else await expect(page.getByRole('heading', { name: 'Adult trial', exact: true })).toBeVisible()
      await expect(applicationAlerts(page)).toHaveCount(0)
    }
    for (const on of [true, false]) for (const url of destinations.slice(0, 3)) for (const direction of ['back', 'forward']) test(`UXBF5 signed-out history ${direction} recovers ${url} flags ${on}`, async ({ page }) => {
      const evidence = await fixture(page, { role: 'visitor', on, featuresStatus: 500, retrySuccess: true })
      if (direction === 'forward') await page.addInitScript(value => {
        // Seed a real prior entry without mounting Home's independent feature reader.
        history.replaceState({ usr: null, key: 'uxbf5-home', idx: 0 }, '', '/')
        history.pushState({ usr: null, key: 'uxbf5-failed', idx: 1 }, '', value)
      }, url)
      await page.goto(url)
      await expect(applicationAlerts(page)).toHaveText('Could not load opportunities. Please try again later.')
      await page.waitForLoadState('networkidle')
      const initialReads = evidence.calls.filter(p => p === '/api/features').length
      expect(initialReads).toBeGreaterThan(0)
      const firstKey = await page.evaluate(() => history.state?.key ?? 'default')
      evidence.recover()
      if (direction === 'back') await page.getByRole('link', { name: 'The Academy Watch logo The Academy Watch' }).click()
      else await page.goBack()
      await expect(page).toHaveURL(/\/$/)
      await expect(page.getByRole('heading', { name: /Every player deserves to be/ })).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(await page.evaluate(() => history.state?.key ?? 'default')).not.toBe(firstKey)
      // Signed-out Home only moves the arrival marker; it must stay lazy.
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(initialReads)
      if (direction === 'back') await page.goBack()
      else await page.goForward()
      await expect(page).toHaveURL(new RegExp(url + '$'))
      expect(await page.evaluate(() => history.state?.key ?? 'default')).toBe(firstKey)
      await normalContent(page, url, on)
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(initialReads + 1)
      if (direction === 'back') await page.goForward()
      else await page.goBack()
      await expect(page).toHaveURL(/\/$/)
      await expect(page.getByRole('heading', { name: /Every player deserves to be/ })).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(initialReads + 1)
      if (direction === 'back') await page.goBack()
      else await page.goForward()
      await normalContent(page, url, on)
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(initialReads + 1)
      expect(evidence.calls.filter(p => p.startsWith('/api/me/'))).toEqual([])
      if (!on) expect(businessCalls(evidence.calls)).toEqual([])
      await shot(page, `history-${direction}-recovered-${url.includes('programs') ? 'club' : url === '/opportunities' ? 'list' : 'detail'}-${on ? 'on' : 'off'}`, size)
    })
    for (const on of [true, false]) for (const url of destinations) test(`UXBF4 startup failure recovers on navigation to ${url} flags ${on ? 'ON' : 'OFF'}`, async ({ page }) => {
      const evidence = await fixture(page, { on, featuresStatus: 500, retrySuccess: true })
      await page.goto('/')
      await expect.poll(() => evidence.calls.filter(p => p === '/api/features').length).toBe(1)
      await page.waitForLoadState('networkidle')
      evidence.recover()
      await navigate(page, url)
      await normalContent(page, url, on)
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(2)
      if (!on) expect(businessCalls(evidence.calls)).toEqual([])
      await shot(page, `navigation-recovered-${on ? 'on' : 'off'}-${destinations.indexOf(url)}`, size)
    })
    for (const on of [true, false]) test(`UXBF4 failed detail heals on another detail without remount flags ${on ? 'ON' : 'OFF'}`, async ({ page }) => {
      const evidence = await fixture(page, { on, featuresStatus: 500, retrySuccess: true })
      const otherId = '00000000-0000-4000-8000-000000000003'
      await page.route(`**/api/opportunities/${otherId}`, route => route.fulfill({ json: { opportunity: { ...opportunity, id: otherId } } }))
      await page.goto(`/opportunities/${oid}`)
      await expect(applicationAlerts(page)).toHaveCount(1)
      evidence.recover()
      await navigate(page, `/opportunities/${otherId}`)
      await normalContent(page, `/opportunities/${otherId}`, on)
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(2)
      if (!on) expect(businessCalls(evidence.calls)).toEqual([])
    })
    for (const on of [true, false]) test(`UXBF4 signed-out failure heals through site links flags ${on ? 'ON' : 'OFF'}`, async ({ page }) => {
      const evidence = await fixture(page, { role: 'visitor', on, featuresStatus: 500, retrySuccess: true })
      await page.goto('/opportunities')
      await expect(applicationAlerts(page)).toHaveCount(1)
      evidence.recover()
      await page.getByRole('link', { name: 'The Academy Watch logo The Academy Watch' }).click()
      await expect(page).toHaveURL(/\/$/)
      if (size === 'mobile') {
        await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
        await page.getByRole('dialog').getByRole('link', { name: 'Opportunities', exact: true }).click()
      } else await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
      await normalContent(page, '/opportunities', on)
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(2)
      expect(evidence.calls.filter(p => p.startsWith('/api/me/application'))).toEqual([])
      if (!on) expect(businessCalls(evidence.calls)).toEqual([])
    })
    for (const on of [true, false]) test(`UXBF4 recovered feature cache heals provider on navigation flags ${on ? 'ON' : 'OFF'}`, async ({ page }) => {
      const evidence = await fixture(page, { on, featuresStatus: 500, retrySuccess: true })
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      evidence.recover()
      // Clubs independently uses the shared feature cache.
      await navigate(page, '/clubs')
      await expect.poll(() => evidence.calls.filter(p => p === '/api/features').length).toBe(2)
      await page.waitForLoadState('networkidle')
      await navigate(page, '/opportunities')
      await normalContent(page, '/opportunities', on)
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(2)
      if (!on) expect(businessCalls(evidence.calls)).toEqual([])
    })
    for (const url of [...destinations, '/onboarding/player']) test(`UXBF4 failed claims recover on navigation to ${url}`, async ({ page }) => {
      const evidence = await fixture(page, { claimsStatus: 500, retrySuccess: true })
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === '/api/me/application-claims')).toHaveLength(1)
      let showOwner
      if (url.includes('local-players')) {
        const waiting = new Promise(resolve => { showOwner = resolve })
        await page.route('**/api/local-players/9/showcase', async route => { await waiting; await route.fallback() })
      }
      evidence.recover()
      await navigate(page, url)
      if (showOwner) {
        await expect.poll(() => evidence.claimsReads.filter(value => !new URL(value).search).length).toBe(2)
        // Opening the menu proves the recovery was published before summary mount.
        const recoveredMenu = await menu(page)
        await expect(recoveredMenu.getByText('My profile', { exact: true })).toBeVisible()
        await page.keyboard.press('Escape')
        showOwner()
      }
      if (url.includes('onboarding')) await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      else await normalContent(page, url, true)
      const opened = await menu(page)
      await expect(opened.getByText('My profile', { exact: true })).toBeVisible()
      await expect(opened.getByText('My applications', { exact: true })).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(evidence.claimsReads.filter(value => !new URL(value).search)).toHaveLength(2)
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(1)
    })
    for (const failure of ['bootstrap', 'claims']) test(`UXBF4 persistent ${failure} failure retries once per arrival without looping`, async ({ page }) => {
      const evidence = await fixture(page, { featuresStatus: failure === 'bootstrap' ? 500 : 200, claimsStatus: failure === 'claims' ? 500 : 200 })
      const endpoint = failure === 'bootstrap' ? '/api/features' : '/api/me/application-claims'
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      await navigate(page, '/onboarding/player')
      await expect(applicationAlerts(page)).toHaveCount(1)
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === endpoint)).toHaveLength(2)
      await page.getByLabel('Player name').fill('synthetic')
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === endpoint)).toHaveLength(2)
    })
    for (const url of ['/onboarding/player', '/local-players/9']) test(`UXBF4 approval and removal revalidate on navigation to ${url} with reload control`, async ({ page }) => {
      const evidence = await fixture(page, { claims: [] })
      let claims = [], release, waiting
      await page.route('**/api/me/application-claims', async route => {
        evidence.calls.push('/api/me/application-claims')
        const snapshot = claims
        if (waiting) await waiting
        await route.fulfill({ json: { claims: snapshot } })
      })
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      claims = [claim]
      await navigate(page, url)
      if (url.includes('onboarding')) await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      else await normalContent(page, url, true)
      expect(evidence.calls.filter(p => p === '/api/me/application-claims')).toHaveLength(2)
      let opened = await menu(page)
      await expect(opened.getByText('My profile', { exact: true })).toBeVisible()
      await page.keyboard.press('Escape')
      await navigate(page, '/opportunities')
      await normalContent(page, '/opportunities', true)
      claims = []
      waiting = new Promise(resolve => { release = resolve })
      await navigate(page, url)
      await expect.poll(() => evidence.calls.filter(p => p === '/api/me/application-claims').length).toBe(3)
      // Keep the last successful value while its same-account revalidation waits.
      if (url.includes('onboarding')) await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      else await normalContent(page, url, true)
      opened = await menu(page)
      await expect(opened.getByText('My profile', { exact: true })).toBeVisible()
      await page.keyboard.press('Escape')
      release(); waiting = null
      if (url.includes('onboarding')) await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      else await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toBeVisible()
      opened = await menu(page)
      await expect(opened.getByText('My profile', { exact: true })).toHaveCount(0)
      await expect(opened.getByText('My applications', { exact: true })).toHaveCount(0)
      await page.keyboard.press('Escape')
      await shot(page, `navigation-removed-${url.includes('onboarding') ? 'home' : 'summary'}`, size)
      await page.reload()
      if (url.includes('onboarding')) await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      else await expect(page.getByRole('heading', { name: 'Your next chapter.' })).toBeVisible()
      expect(evidence.calls.filter(p => p === '/api/me/application-claims')).toHaveLength(4)
    })
    test('UXBF4 overlapping home and owner summary arrivals share a pending claims read', async ({ page }) => {
      const evidence = await fixture(page, { claims: [] })
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      let release
      const waiting = new Promise(resolve => { release = resolve })
      await page.route('**/api/me/application-claims', async route => {
        evidence.calls.push('/api/me/application-claims')
        await waiting
        await route.fulfill({ json: { claims: [claim] } })
      })
      await navigate(page, '/onboarding/player')
      await expect.poll(() => evidence.calls.filter(p => p === '/api/me/application-claims').length).toBe(2)
      await navigate(page, '/local-players/9')
      await expect(page.getByRole('heading', { name: 'Synthetic Adult', exact: true })).toBeVisible()
      release()
      await normalContent(page, '/local-players/9', true)
      await page.waitForLoadState('networkidle')
      expect(evidence.calls.filter(p => p === '/api/me/application-claims')).toHaveLength(2)
    })
    for (const failure of ['bootstrap', 'claims']) test(`UXBF3 ${failure} retry restores both navigation shortcuts without reload`, async ({ page }) => {
      const evidence = await fixture(page, { featuresStatus: failure === 'bootstrap' ? 500 : 200, claimsStatus: failure === 'claims' ? 500 : 200, retrySuccess: true })
      await page.goto('/onboarding/player')
      await expect(applicationAlerts(page)).toHaveCount(1)
      const expectedErrors = [...evidence.errors]
      evidence.recover()
      await page.getByRole('button', { name: 'Retry applications' }).click()
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      if (size === 'mobile') await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
      else await page.getByRole('button', { name: 'Synthetic Viewer' }).click()
      const menu = page.getByRole(size === 'mobile' ? 'dialog' : 'menu')
      const profile = menu.getByRole(size === 'mobile' ? 'link' : 'menuitem', { name: 'My profile', exact: true })
      const applications = menu.getByRole(size === 'mobile' ? 'link' : 'menuitem', { name: 'My applications', exact: true })
      await expect(profile).toBeVisible()
      await expect(profile).toHaveAttribute('href', '/local-players/9')
      await expect(applications).toBeVisible()
      await expect(applications).toHaveAttribute('href', '/onboarding/player#my-applications')
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(failure === 'bootstrap' ? 2 : 1)
      expect(evidence.calls.filter(p => p === '/api/me/application-claims')).toHaveLength(failure === 'claims' ? 2 : 1)
      expect(evidence.errors).toEqual(expectedErrors)
      await shot(page, `${failure}-recovered-menu`, size)
    })
    test('UXBF3 account changes clear shared claims before a delayed response and on logout', async ({ page }) => {
      await fixture(page)
      await page.goto('/onboarding/player')
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      let resolve
      const waitOtherClaims = new Promise(r => { resolve = r })
      await page.route('**/api/me/application-claims', async route => {
        if (route.request().headers().authorization?.endsWith('uxbf3-other-token')) {
          await waitOtherClaims
          return route.fulfill({ json: { claims: [] } })
        }
        return route.fallback()
      })
      const switchToken = token => page.evaluate(async value => {
        const { APIService } = await import('/src/lib/api.js')
        APIService.setUserToken(value)
      }, token)
      await switchToken('uxbf3-other-token')
      await expect(page.getByText('Checking your profiles…', { exact: true })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Synthetic Adult · My profile →' })).toHaveCount(0)
      if (size === 'mobile') await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
      else await page.getByRole('button', { name: 'Synthetic Viewer' }).click()
      const menu = page.getByRole(size === 'mobile' ? 'dialog' : 'menu')
      await expect(menu.getByText('My profile', { exact: true })).toHaveCount(0)
      await expect(menu.getByText('My applications', { exact: true })).toHaveCount(0)
      await page.keyboard.press('Escape')
      resolve()
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      await switchToken('uxbf1-synthetic-token')
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toBeVisible()
      await switchToken('')
      await expect(page.getByRole('link', { name: 'Synthetic Adult · My profile →' })).toHaveCount(0)
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
    })
    test('UXBF3 a previous account response cannot restore old shared claims', async ({ page }) => {
      let resolve
      const waitClaims = new Promise(r => { resolve = r })
      await fixture(page, { waitClaims })
      await page.goto('/onboarding/player')
      await expect(page.getByText('Checking your profiles…', { exact: true })).toBeVisible()
      await page.route('**/api/me/application-claims', route => route.fulfill({ json: { claims: [] } }))
      await page.evaluate(async () => {
        const { APIService } = await import('/src/lib/api.js')
        APIService.setUserToken('uxbf3-other-token')
      })
      await expect(page.getByRole('heading', { name: 'Are you a player?' })).toBeVisible()
      resolve()
      await page.waitForLoadState('networkidle')
      await expect(page.getByRole('heading', { name: 'Your next step.' })).toHaveCount(0)
      await expect(page.getByRole('link', { name: 'Synthetic Adult · My profile →' })).toHaveCount(0)
      if (size === 'mobile') await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
      else await page.getByRole('button', { name: 'Synthetic Viewer' }).click()
      const menu = page.getByRole(size === 'mobile' ? 'dialog' : 'menu')
      await expect(menu.getByText('My profile', { exact: true })).toHaveCount(0)
      await expect(menu.getByText('My applications', { exact: true })).toHaveCount(0)
    })
    for (const urlId of [oid.toUpperCase(), 'F9c683D7-2c0F-57bA-aE18-3a2544Fa7c96']) test(`UXBF3 parent anchor accepts UUID case ${urlId}`, async ({ page }) => {
      let resolve
      const waitClaims = new Promise(r => { resolve = r })
      await fixture(page, { waitClaims })
      await page.goto(`/opportunities/${urlId}#parent-interest`)
      await expect(page.getByText('Checking your profiles…', { exact: true })).toBeVisible()
      resolve()
      const block = page.locator('#parent-interest')
      await expect(block).toBeFocused()
      await expect(block.getByLabel('Email address')).toBeInViewport({ ratio: 1 })
      await shot(page, `parent-interest-${urlId === oid.toUpperCase() ? 'uppercase' : 'mixed'}`, size)
    })
    for (const on of [true, false]) test(`UXBF3 no-id parent hash safely opens ${on ? 'list' : 'teaser'}`, async ({ page }) => {
      const evidence = await fixture(page, { role: 'visitor', on })
      await page.goto('/opportunities#parent-interest')
      await expect(page.getByRole('heading', { name: 'Room for your next step.' })).toBeVisible()
      if (on) await expect(page.getByRole('heading', { name: 'Open opportunities', exact: true })).toBeVisible()
      else await expect(page.getByRole('heading', { name: 'Hear first', exact: true })).toBeVisible()
      await page.waitForLoadState('networkidle')
      await expect(page.locator('#parent-interest')).toHaveCount(0)
      expect(evidence.calls.filter(p => p.startsWith('/api/me/'))).toEqual([])
      if (!on) expect(businessCalls(evidence.calls)).toEqual([])
      expect(evidence.errors).toEqual([])
    })
    test('parent-interest deep link scrolls and focuses signup after asynchronous detail load', async ({ page }) => {
      const evidence = await fixture(page, { role: 'visitor' })
      await page.goto(`/opportunities/${oid}#parent-interest`)
      const block = page.locator('#parent-interest')
      await expect(block).toBeFocused()
      await expect(block).toBeInViewport()
      await expect(block.getByRole('heading', { name: 'A path for younger players.' })).toBeVisible()
      await expect(block.getByLabel('Email address')).toBeVisible()
      expect(evidence.calls.filter(p => p.startsWith('/api/me/'))).toEqual([])
      await shot(page, 'parent-interest-anchor', size)
    })
  })
}
