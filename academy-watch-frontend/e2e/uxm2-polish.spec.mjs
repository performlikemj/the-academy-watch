/* global document, innerWidth, getComputedStyle, window */
import { expect, test } from '@playwright/test'

const program = { id: 7, name: 'Synthetic Club', slug: 'synthetic-club', platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
const squads = [{ id: 11, name: 'Synthetic First team', member_count: 1 }]
const all = ['players.view', 'players.manage', 'matches.view', 'matches.upload', 'feedback', 'recruiting', 'contact', 'results', 'player_invitations', 'branding', 'staff.directory', 'access.view', 'access.manage', 'billing']
const member = { id: 8, available: true, display_name: 'Synthetic Player', subject_type: 'local', local_player_id: 8, squad_id: 11, shirt_number: 8, brief: { body: 'Check both shoulders', lines: ['Check both shoulders'] } }
const expiredInvite = { id: 'expired-1', email: 'synthetic.coach@example.test', role: 'coach', all_squads: false, squad_ids: [11], status: 'expired', created_at: '2026-09-12T10:00:00Z', expires_at: '2026-09-19T10:00:00Z' }

async function mock(page, { role = 'owner', subscription = 'club_bundle', emailSent = true, onInvite, onBrief, entitlements } = {}) {
  const admin = role === 'admin'
  const access = { program_id: 7, role, verified: true, whole_club: ['owner', 'manager'].includes(role), squad_ids: [11], capabilities: role === 'owner' ? all : role === 'manager' ? all.filter(c => !['access.manage', 'billing'].includes(c)) : ['players.view', 'matches.view', ...(role === 'coach' ? ['feedback', 'matches.upload'] : [])] }
  let matches = [{ id: 42, status: 'created', opponent_name: 'Synthetic Newest', competition: 'Wendle & District Senior League — Premier Division', match_date: '2026-09-27', roster: [] }, { id: 41, status: 'created', opponent_name: 'Synthetic Older', match_date: '2026-09-20', roster: [] }]
  let brief = member.brief
  let invites = [expiredInvite, { ...expiredInvite, id: 'pending-1', email: 'pending@example.test', status: 'pending', expires_at: '2030-10-07T10:00:00Z' }]
  await page.addInitScript(({ admin }) => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-user')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (admin) {
      localStorage.setItem('academy_watch_is_admin', 'true')
      localStorage.setItem('academy_watch_admin_key', 'synthetic-admin')
    }
  }, { admin })
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const reply = json => route.fulfill({ json })
    if (path === '/api/auth/me') return reply({ email: 'synthetic@example.test', role: admin ? 'admin' : 'user', display_name: 'Synthetic Account', display_name_confirmed: true, scout_pro: { enabled: false } })
    if (path === '/api/features') return reply({ club_staff_access: true, contact_rail: true })
    if (path === '/api/funding/claims/me') return reply({ claims: ['owner', 'manager'].includes(role) ? [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] : [] })
    if (path === '/api/me/club-access') return reply({ programs: ['owner', 'manager'].includes(role) ? [] : [{ program, access }] })
    if (path === '/api/me/club-claims') return reply({ claims: [] })
    if (path === '/api/me/club') return reply({ clubs: [] })
    if (path === '/api/club/7/access/me') return reply({ access })
    if (path === '/api/club/7/roster') return reply({ program, members: [{ ...member, brief }], count: 1 })
    if (path === '/api/club/7/map') return reply({ program, squads, staff: [], unassigned_count: 0 })
    if (path === '/api/club/7/invitations') return reply({ invitations: [{ id: 'accepted-1', player_api_id: -8, player_name: member.display_name, roster_member_id: 8, status: 'accepted' }] })
    if (path === '/api/club/7/roster/8/profile') return reply({ identity: { ...member, brief, squad: squads[0] }, ...(role === 'viewer' ? {} : { coach_brief: brief }), pathway: [{ id: 'history-1', squad_name: 'Synthetic Reserves', started_at: '2026-01-01', ended_at: '2026-09-01' }, { id: 'current-8', squad_id: 11, squad_name: squads[0].name, started_at: null, ended_at: null }] })
    if (path === '/api/club/7/roster/8/brief') {
      onBrief?.(route.request().postDataJSON())
      brief = { body: route.request().postDataJSON().body, lines: [route.request().postDataJSON().body] }
      return reply({ member: { ...member, brief } })
    }
    if (path === '/api/club/7/squads') return reply({ squads })
    if (path === '/api/club/7/matches') {
      if (route.request().method() === 'POST') {
        const created = { id: 43, status: 'created', roster: [], ...route.request().postDataJSON() }
        matches.push(created)
        return route.fulfill({ status: 201, json: created })
      }
      return reply({ matches, total: matches.length })
    }
    if (/^\/api\/club\/7\/matches\/\d+$/.test(path)) {
      const id = Number(path.split('/').at(-1))
      const match = matches.find(row => row.id === id)
      if (route.request().method() === 'PATCH') Object.assign(match, route.request().postDataJSON())
      return reply(match)
    }
    if (path === '/api/club/7/results') return reply({ results: [{ result: { id: 'r1', version: 1, match_date: '2026-09-27', opponent: 'Wendle & District < "Rovers" >', result_for: 2, result_against: 1 }, matches: [] }] })
    if (path === '/api/club/7/access') return reply({ people: [{ user_account_id: 1, display_name: 'Synthetic Owner', role: 'owner', permissions: [true] }], invites, activity: [], matrix: { rows: ['See players'] } })
    if (path === '/api/club/7/staff-invites') {
      const body = route.request().postDataJSON()
      onInvite?.(body)
      invites = invites.map(i => i.id === expiredInvite.id ? { ...i, id: 'replacement', status: 'pending', expires_at: '2030-10-07T10:00:00Z' } : i)
      return route.fulfill({ status: 201, json: { invite: invites[0], email_sent: emailSent } })
    }
    if (path === '/api/billing/config') return reply({ enabled: true, products: [], packs: [] })
    if (path === '/api/billing/me') return reply({ has_billing_account: true, subscriptions: [{ id: 1, product_code: subscription, status: 'active', unit_amount: 2900, currency: 'gbp', interval: 'month', current_period_end: '2026-10-27T00:00:00Z' }] })
    if (path === '/api/scout/entitlements') return reply({ entitlements: entitlements || { tier: subscription === 'scout_pro' ? 'pro' : 'free', features: { gol_chat: true } } })
    if (path === '/api/scout/verification') return reply({ verification: { status: 'approved', full_name: 'Synthetic Scout', role_title: 'Scout', organization: 'Synthetic Club', submitted_at: '2026-09-27T12:00:00Z' } })
    if (path === '/api/admin/scout-verifications') return reply({ verifications: [{ id: 'v1', full_name: 'Synthetic Scout', status: 'pending', submitted_at: '2026-09-27T12:00:00Z' }] })
    if (path === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    return reply({})
  })
}

for (const width of [1440, 390]) {
  test(`club relationship uses the server name at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mock(page)
    await page.goto('/my-club?program=7&view=roster')
    const relationships = page.getByRole('region', { name: 'Club relationships' }).or(page.locator('[aria-label="Club relationships"]'))
    await expect(relationships.getByRole('link', { name: 'Synthetic Player' })).toBeVisible()
    await expect(relationships).not.toContainText('Player -8')
  })

  test(`expired invite keeps role and scope when sent again at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    let body
    await mock(page, { onInvite: b => { body = b } })
    await page.goto('/my-club?program=7&view=staff')
    await page.getByRole('button', { name: /synthetic.coach@example.test/ }).click()
    await expect(page.getByText('Expired · Coach', { exact: true })).toBeVisible()
    await expect(page.getByText('Pending · Coach', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Send again', exact: true }).click()
    await expect(page.getByRole('status')).toHaveText('Invite sent to synthetic.coach@example.test. The previous link no longer works.')
    expect(body).toEqual({ email: expiredInvite.email, role: 'coach', all_squads: false, squad_ids: [11] })
    await expect(page.getByText('Expired · Coach', { exact: true })).toHaveCount(0)
  })

  test(`current squad and recorded history appear; coach edits brief at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    let body
    await mock(page, { role: 'coach', onBrief: b => { body = b } })
    await page.goto('/my-club?program=7&player=8')
    const pathway = page.locator('.ch-player-secondary').filter({ hasText: 'Pathway at Synthetic Club' })
    await expect(pathway).toContainText('Synthetic Reserves')
    await expect(pathway).toContainText(squads[0].name)
    await expect(pathway).toContainText('Current squad · assignment date not recorded')
    await expect(page.getByRole('button', { name: 'Move squad', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Upload photo', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Edit brief', exact: true }).click()
    await page.getByRole('textbox', { name: 'Coach brief', exact: true }).fill('Scan before receiving')
    await page.getByRole('button', { name: 'Save brief', exact: true }).click()
    expect(body).toEqual({ body: 'Scan before receiving' })
    await expect(page.locator('.ch-brief-lines')).toHaveText('Scan before receiving')
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })

  test(`result text escapes once and matches retain server date order at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mock(page)
    await page.goto('/my-club?program=7&view=matches')
    await expect(page.getByText('2–1 vs Wendle & District < "Rovers" >', { exact: true })).toBeVisible()
    await expect(page.getByText('27 Sept 2026', { exact: true }).first()).toBeVisible()
    await expect(page.locator('Rovers')).toHaveCount(0)
    const matches = page.locator('button > div > p').filter({ hasText: /^vs Synthetic (Newest|Older)/ })
    await expect(matches).toHaveText(['vs Synthetic Newest', 'vs Synthetic Older'])
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })

  for (const [product, label] of [['club_bundle', 'Club bundle'], ['scout_pro', 'Scout Pro']]) {
    test(`${label} is named without offered products at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await mock(page, { subscription: product })
      await page.goto('/account/billing')
      await expect(page.getByRole('heading', { name: label, exact: true })).toBeVisible()
      await expect(page.getByText('Renews on 27 Oct 2026')).toBeVisible()
      await expect(page.getByText('Paid plan', { exact: true })).toHaveCount(0)
      if (product === 'club_bundle') await expect(page.getByText('Scout access', { exact: true })).toHaveCount(0)
      else await expect(page.getByText('Scout access', { exact: true })).toBeVisible()
    })
  }
}

for (const role of ['manager', 'analyst', 'viewer']) {
  test(`${role} retains its staff and brief permissions`, async ({ page }) => {
    await mock(page, { role })
    if (role === 'manager') {
      await page.goto('/my-club?program=7&view=staff')
      await page.getByRole('button', { name: /synthetic.coach@example.test/ }).click()
      await expect(page.getByText('Expired · Coach', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Send again', exact: true })).toHaveCount(0)
    } else {
      await page.goto('/my-club?program=7&player=8')
      await expect(page.getByRole('heading', { name: /Synthetic Player/, exact: false })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Edit brief', exact: true })).toHaveCount(0)
      if (role === 'viewer') await expect(page.locator('.ch-brief-lines')).toHaveCount(0)
      else await expect(page.locator('.ch-brief-lines')).toHaveText('Check both shoulders')
    }
  })
}

test('resend email failure is presented honestly', async ({ page }) => {
  await mock(page, { emailSent: false })
  await page.goto('/my-club?program=7&view=staff')
  await page.getByRole('button', { name: /synthetic.coach@example.test/ }).click()
  await page.getByRole('button', { name: 'Send again', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Invite saved for synthetic.coach@example.test, but the email didn’t send. Try again later.')
})

test('verification and admin review use UK dates', async ({ page }) => {
  await mock(page, { role: 'admin' })
  await page.goto('/scout/verification')
  await expect(page.getByText('Submitted 27 Sept 2026', { exact: true })).toBeVisible()
  await page.goto('/admin/trust')
  await expect(page.getByText('Submitted 27 Sept 2026', { exact: true })).toBeVisible()
})

for (const width of [390, 1440]) for (const route of ['/my-club?program=7&view=staff', '/account/billing', '/admin/trust']) {
  test(`${width}px last content/footers clear one GOL launcher on ${route}`, async ({ page }) => {
    const height = width === 390 ? 844 : 900
    await page.setViewportSize({ width, height })
    await mock(page, { role: route.startsWith('/admin') ? 'admin' : 'owner' })
    await page.goto(route)
    await expect(page.getByRole('heading').first()).toBeVisible()
    const launcher = page.getByRole('button', { name: 'Open GOL Assistant chat', exact: true })
    await expect(launcher).toHaveCount(1)
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    const button = await launcher.boundingBox()
    expect(width - button.x - button.width).toBeCloseTo(16, 0)
    expect(height - button.y - button.height).toBeCloseTo(16, 0)
    await expect(page.locator('.app-main')).toHaveCSS('padding-bottom', '0px')
    const content = page.locator(route.startsWith('/admin') ? '.fl-admin-main' : '.app-footer')
    const space = await content.evaluate(el => parseFloat(getComputedStyle(el).paddingBottom))
    expect(space).toBeGreaterThanOrEqual(88)
    if (width === 390 && route.startsWith('/my-club')) {
      const tabs = await page.locator('.ch-rail > button:visible').all()
      for (const tab of tabs) { const box = await tab.boundingBox(); expect(box.x + box.width).toBeLessThan(button.x) }
    }
    const last = page.locator(route.startsWith('/admin') ? '.app-main button' : '.app-footer a').last()
    if (await last.count()) {
      const bounds = await last.boundingBox()
      expect(bounds.y + bounds.height).toBeLessThanOrEqual(button.y)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })
}


for (const width of [390, 1440]) {
  for (const entitlements of [
    { tier: 'pro', source: 'grandfather', grandfathered_until: '2026-12-31', features: { gol_chat: true } },
    { tier: 'pro', source: 'subscription', features: { gol_chat: true } },
  ]) {
    test(`club owner keeps separate Scout Pro access (${entitlements.source}) at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await mock(page, { entitlements })
      await page.goto('/account/billing')
      await expect(page.getByRole('heading', { name: 'Club bundle', exact: true })).toBeVisible()
      await expect(page.getByText('Scout access', { exact: true })).toBeVisible()
      await expect(page.getByText('Scout Pro', { exact: true })).toBeVisible()
      if (entitlements.source === 'grandfather') await expect(page.getByText('Grandfathered until 31 Dec 2026')).toBeVisible()
    })
  }

  test(`match creation and date edits immediately re-sort at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mock(page)
    await page.goto('/my-club?program=7&view=matches')
    const rows = page.locator('button > div > p').filter({ hasText: /^vs Synthetic/ })
    await expect(rows).toHaveText(['vs Synthetic Newest', 'vs Synthetic Older'])
    await page.getByRole('button', { name: 'Create match', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Opponent', { exact: true }).fill('Synthetic Middle')
    await dialog.getByLabel('Match date', { exact: true }).fill('2026-09-23')
    await dialog.getByRole('button', { name: 'Create match', exact: true }).click()
    await expect(rows).toHaveText(['vs Synthetic Newest', 'vs Synthetic Middle', 'vs Synthetic Older'])
    await page.locator('#date-43').fill('2026-09-28')
    await page.getByRole('button', { name: 'Save details', exact: true }).click()
    await expect(rows).toHaveText(['vs Synthetic Middle', 'vs Synthetic Newest', 'vs Synthetic Older'])
    await page.locator('#date-43').fill('')
    await page.getByRole('button', { name: 'Save details', exact: true }).click()
    await expect(rows).toHaveText(['vs Synthetic Newest', 'vs Synthetic Older', 'vs Synthetic Middle'])
  })

  test(`launcher reservation disappears with the launcher at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mock(page)
    await page.goto('/account/billing')
    await expect(page.locator('.app-footer')).toHaveCSS('padding-bottom', '88px')
    await expect(page.locator('.app-main')).toHaveCSS('padding-bottom', '0px')
    await page.locator('[data-gol-launcher]').evaluate(el => el.remove())
    await expect(page.locator('.app-footer')).toHaveCSS('padding-bottom', '48px')
    await expect(page.locator('.app-main')).toHaveCSS('padding-bottom', '0px')
  })

  test(`fitting admin layout has no outer 88px scroll band at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mock(page, { role: 'admin' })
    await page.goto('/admin/trust')
    await expect(page.locator('.fl-admin-main')).toBeVisible()
    await expect(page.locator('.app-main')).toHaveCSS('padding-bottom', '0px')
    const outer = await page.locator('.app-main').boundingBox()
    const inner = await page.locator('.app-main > div').boundingBox()
    expect(outer.height).toBeCloseTo(inner.height, 0)
    // Fit short content inside the real admin shell, retaining sidebar/header.
    await page.locator('.fl-admin-main').evaluate(el => { el.replaceChildren() })
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBe(width === 390 ? 844 : 900)
  })
}
