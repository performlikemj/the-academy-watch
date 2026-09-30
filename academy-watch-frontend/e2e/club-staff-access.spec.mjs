/* global document, innerWidth */
import { expect, test } from '@playwright/test'

// Synthetic API data only (club staff access, dark behind CLUB_STAFF_ACCESS_ENABLED).
const program = { id: 7, name: 'Synthetic Staff Club', slug: 'synthetic-staff-club', platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
const squads = [{ id: 11, name: 'First team', member_count: 1 }, { id: 12, name: 'Under-18s', member_count: 1 }]
const ALL = ['players.view', 'players.manage', 'matches.view', 'matches.upload', 'feedback', 'recruiting', 'contact', 'results', 'player_invitations', 'branding', 'staff.directory', 'access.view', 'access.manage', 'billing']
const matrix = { rows: ["See their squads' players", 'Upload matches & see reports', 'Send feedback to players', 'Recruiting & trials', 'Decide on scout requests', 'Edit club page & branding', 'Billing & staff access'], roles: { owner: [true, true, true, true, true, true, true], coach: [true, true, true, false, false, false, false] } }

async function mock(page, { flag, role = 'owner', onInvite, seen = [] }) {
  await page.addInitScript(() => localStorage.setItem('academy_watch_user_token', 'synthetic-user'))
  const coach = role === 'coach'
  const access = coach
    ? { program_id: 7, role: 'coach', verified: false, whole_club: false, squad_ids: [12], capabilities: ['players.view', 'matches.view', 'matches.upload', 'feedback'] }
    : { program_id: 7, role: 'owner', verified: true, whole_club: true, squad_ids: [], capabilities: ALL }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const reply = json => route.fulfill({ json })
    seen.push(url.pathname)
    if (url.pathname === '/api/features') return reply(flag ? { contact_rail: false, club_staff_access: true } : { contact_rail: false })
    if (url.pathname === '/api/funding/claims/me') return reply({ claims: coach ? [] : [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] })
    if (url.pathname === '/api/me/club-access') return reply({ programs: coach ? [{ program, access }] : [] })
    if (url.pathname === '/api/me/club-claims') return reply({ claims: [] })
    if (url.pathname === '/api/me/club') return reply({ clubs: [] })
    if (url.pathname === '/api/club/7/access/me') return reply({ access })
    if (url.pathname === '/api/club/7/roster') return reply({ program, members: [], count: 0 })
    if (url.pathname === '/api/club/7/map') return reply({ program, squads: coach ? [squads[1]] : squads, staff: [], unassigned_count: coach ? 0 : 2 })
    if (url.pathname === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    if (url.pathname === '/api/club/7/staff-invites') {
      onInvite?.(route.request().postDataJSON())
      return route.fulfill({ status: 201, json: { invite: { id: 'i-2' }, email_sent: true } })
    }
    if (url.pathname === '/api/club/7/access') return reply({
      me: access,
      people: [{ user_account_id: 1, display_name: 'Synthetic Owner', email: 'owner@example.test', role: 'owner', verified: true, all_squads: true, squad_ids: [], editable: false },
        { user_account_id: 2, display_name: 'Synthetic Coach', email: 'coach@example.test', role: 'coach', verified: false, all_squads: false, squad_ids: [12], grant_id: 5, version: 1, editable: true }],
      invites: [{ id: 'i-1', email: 'pending@example.test', role: 'viewer', all_squads: false, squad_ids: [11], status: 'pending', created_at: '2026-09-30T10:00:00Z', expires_at: '2026-10-07T10:00:00Z' }],
      activity: [], matrix,
    })
    if (url.pathname === '/api/me/staff-invites/preview') {
      const token = route.request().postDataJSON().token
      return reply(token === 'wrong-account-token-000000' ? { state: 'invite_wrong_account', role: 'coach' } : { state: 'ready', role: 'coach', program: { id: 7, name: 'Synthetic Staff Club' } })
    }
    if (url.pathname === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    return reply({})
  })
}

test('flag off: Staff screen is today\'s and no access endpoints are called', async ({ page }) => {
  const seen = []
  await mock(page, { flag: false, seen })
  await page.goto('/my-club?program=7&view=staff')
  await expect(page.getByRole('heading', { name: 'Staff & roles' })).toBeVisible()
  await expect(page.getByText('Roles do not grant login access.')).toBeVisible()
  await expect(page.getByRole('heading', { name: /Who can see/ })).toHaveCount(0)
  expect(seen.filter(p => p.includes('/access') || p.includes('club-access'))).toEqual([])
})

for (const width of [1440, 390]) {
  test(`owner sees the access board and invites with a squad scope at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    let body
    await mock(page, { flag: true, onInvite: b => { body = b } })
    await page.goto('/my-club?program=7&view=staff')
    await expect(page.getByRole('heading', { name: /Who can see/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Staff directory' })).toBeVisible()
    await expect(page.getByText('Pending · Viewer')).toBeVisible()
    await page.locator('#sa-email').fill('new.coach@example.test')
    await page.locator('#sa-role').selectOption('coach')
    await page.locator('#sa-scope').selectOption({ label: 'Under-18s' })
    await page.getByRole('button', { name: 'Send invite' }).click()
    await expect(page.getByText('Invite sent to new.coach@example.test.')).toBeVisible()
    expect(body).toEqual({ email: 'new.coach@example.test', role: 'coach', all_squads: false, squad_ids: [12] })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })
}

test('scoped coach sees only their capabilities', async ({ page }) => {
  await mock(page, { flag: true, role: 'coach' })
  await page.goto('/my-club?program=7&view=map')
  const nav = page.locator('.ch-sidebar')
  await expect(nav.getByRole('button', { name: 'Matches' })).toBeVisible()
  for (const hidden of ['Settings', 'Scouts', 'Recruiting', 'Staff & access']) await expect(nav.getByRole('button', { name: hidden })).toHaveCount(0)
  await expect(page.getByText('Only people your club has given access can see this map.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit branding' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Add squad/ })).toHaveCount(0)
  await expect(page.locator('.ch-sidebar').getByRole('button', { name: /Unassigned/ })).toHaveCount(0)
  // A URL for a view the role lacks falls back to the club map instead of calling a forbidden API.
  await page.goto('/my-club?program=7&view=branding')
  await expect(page.getByRole('heading', { name: 'Club map' })).toBeVisible()
})

test('invite page: signed-in ready state and wrong account', async ({ page }) => {
  await mock(page, { flag: true })
  await page.goto('/staff-invite#token=ready-token-000000000000')
  await expect(page.getByRole('heading', { name: 'Synthetic Staff Club' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Accept invitation' })).toBeVisible()
  await page.goto('/staff-invite#token=wrong-account-token-000000')
  await expect(page.getByRole('heading', { name: 'This invite is for a different email' })).toBeVisible()
})

test('invite page signed out asks to sign in with the invited email', async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({ json: {} }))
  await page.goto('/staff-invite#token=ready-token-000000000000')
  await expect(page.getByRole('button', { name: 'Sign in to accept' })).toBeVisible()
})
