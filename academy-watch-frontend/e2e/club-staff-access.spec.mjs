/* global document, innerWidth */
import path from 'node:path'
import { expect, test } from '@playwright/test'

// Synthetic API data only (club staff access, dark behind CLUB_STAFF_ACCESS_ENABLED).
const program = { id: 7, name: 'Synthetic Staff Club', slug: 'synthetic-staff-club', platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }
const squads = [{ id: 11, name: 'First team', member_count: 1 }, { id: 12, name: 'Under-18s', member_count: 1 }, { id: 13, name: 'Under-16s', member_count: 1 }]
const ALL = ['players.view', 'players.manage', 'matches.view', 'matches.upload', 'feedback', 'recruiting', 'contact', 'results', 'player_invitations', 'branding', 'staff.directory', 'access.view', 'access.manage', 'billing']
// Row labels only; each person carries their own `permissions` (their resolved capabilities).
const matrix = { rows: ["See their squads' players", 'Upload matches & see reports', 'Send feedback to players', 'Recruiting & trials', 'Decide on scout requests', 'Edit club page & branding', 'Billing & staff access'] }
const MARKS = {
  owner: [true, true, true, true, true, true, true],
  invitedManager: [true, true, true, true, false, true, false],
  coach: [true, true, true, false, false, false, false],
  analyst: [true, true, false, false, false, false, false],
  viewer: [true, false, false, false, false, false, false],
}
const boardPeople = () => [
  { user_account_id: 1, display_name: 'Synthetic Owner', email: 'owner@example.test', role: 'owner', verified: true, all_squads: true, squad_ids: [], editable: false, permissions: MARKS.owner },
  { user_account_id: 2, display_name: 'Synthetic Coach', email: 'coach@example.test', role: 'coach', verified: false, all_squads: false, squad_ids: [12], grant_id: 5, version: 1, editable: true, permissions: MARKS.coach },
  { user_account_id: 3, display_name: 'Synthetic Three-Squad Coach', email: 'three@example.test', role: 'coach', verified: false, all_squads: false, squad_ids: [11, 12, 13], grant_id: 6, version: 1, editable: true, permissions: MARKS.coach },
  { user_account_id: 4, display_name: 'Synthetic Invited Manager', email: 'invited.manager@example.test', role: 'manager', verified: false, all_squads: true, squad_ids: [], grant_id: 7, version: 1, editable: true, permissions: MARKS.invitedManager },
]

// Optional evidence capture: A2_SHOTS_DIR=<dir> writes PNGs there; unset (CI) it does nothing.
async function shot(page, name, focus) {
  if (!process.env.A2_SHOTS_DIR) return
  await page.locator(focus).evaluate(el => el.scrollIntoView({ block: 'center' }))
  await page.screenshot({ path: path.join(process.env.A2_SHOTS_DIR, `${name}.png`) })
}

async function mock(page, { flag, role = 'owner', onInvite, onPatch, seen = [] }) {
  const people = boardPeople()
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
    const grant = /^\/api\/club\/7\/access\/(\d+)$/.exec(url.pathname)
    if (grant && route.request().method() === 'PATCH') {
      // Behaves like the server: the stored grant becomes exactly what was sent.
      const body = route.request().postDataJSON()
      const person = people.find(p => p.grant_id === Number(grant[1]))
      onPatch?.(body)
      Object.assign(person, { role: body.role, all_squads: body.all_squads, squad_ids: body.squad_ids, version: person.version + 1, permissions: MARKS[body.role] || MARKS.invitedManager })
      return reply({ grant: {} })
    }
    if (url.pathname === '/api/club/7/access') return reply({
      me: access,
      people,
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
    const scope = page.locator('#sa-scope')
    await expect(scope.getByRole('checkbox', { name: 'All squads' })).toBeChecked()
    await scope.getByRole('checkbox', { name: 'All squads' }).uncheck()
    // A scoped role with nothing ticked is refused before any request.
    await page.getByRole('button', { name: 'Send invite' }).click()
    await expect(page.getByRole('alert')).toHaveText('Choose a squad, or All squads.')
    expect(body).toBeUndefined()
    await scope.getByRole('checkbox', { name: 'Under-18s' }).check()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await scope.getByRole('checkbox', { name: 'First team' }).check()
    await shot(page, `staff-access-invite-multi-squad-${width === 1440 ? 'desktop' : 'mobile'}`, '.sa-invite')
    await page.getByRole('button', { name: 'Send invite' }).click()
    await expect(page.getByText('Invite sent to new.coach@example.test.')).toBeVisible()
    expect(body).toEqual({ email: 'new.coach@example.test', role: 'coach', all_squads: false, squad_ids: [11, 12] })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })
}

for (const width of [1440, 390]) {
  test(`editing a three-squad grant keeps every squad it did not remove at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const size = width === 1440 ? 'desktop' : 'mobile'
    const patches = []
    await mock(page, { flag: true, onPatch: b => patches.push(b) })
    await page.goto('/my-club?program=7&view=staff')
    await page.getByRole('button', { name: /Synthetic Three-Squad Coach/ }).click()
    const scope = page.locator('#sa-edit-scope')
    await expect(scope.getByRole('checkbox', { name: 'All squads' })).not.toBeChecked()
    for (const name of ['First team', 'Under-18s', 'Under-16s']) await expect(scope.getByRole('checkbox', { name })).toBeChecked()
    await expect(scope.getByText('3 of 3 squads selected.')).toBeVisible()
    await shot(page, `staff-access-multi-squad-editor-${size}`, '.sa-editor')

    // Untouched save: the same set goes back.
    await page.getByRole('button', { name: 'Save access' }).click()
    await expect(page.getByText('Access updated. It applies straight away.')).toBeVisible()
    expect(patches.at(-1)).toEqual({ role: 'coach', all_squads: false, squad_ids: [11, 12, 13], expected_version: 1 })

    // Role only: all three squads still go back.
    await page.locator('#sa-edit-role').selectOption('analyst')
    await page.getByRole('button', { name: 'Save access' }).click()
    await expect.poll(() => patches.length).toBe(2)
    expect(patches.at(-1)).toEqual({ role: 'analyst', all_squads: false, squad_ids: [11, 12, 13], expected_version: 2 })

    // Remove one: exactly the other two go back.
    await scope.getByRole('checkbox', { name: 'Under-18s' }).uncheck()
    await expect(scope.getByText('2 of 3 squads selected.')).toBeVisible()
    await shot(page, `staff-access-multi-squad-editor-one-removed-${size}`, '.sa-editor')
    await page.getByRole('button', { name: 'Save access' }).click()
    await expect.poll(() => patches.length).toBe(3)
    expect(patches.at(-1)).toEqual({ role: 'analyst', all_squads: false, squad_ids: [11, 13], expected_version: 3 })
    await expect(page.getByRole('button', { name: /Synthetic Three-Squad Coach/ })).toContainText('First team, Under-16s')

    // Removing every squad is refused, not turned into "All squads".
    await scope.getByRole('checkbox', { name: 'First team' }).uncheck()
    await scope.getByRole('checkbox', { name: 'Under-16s' }).uncheck()
    await page.getByRole('button', { name: 'Save access' }).click()
    await expect(page.getByRole('alert')).toHaveText('Choose a squad, or All squads.')
    expect(patches.length).toBe(3)

    // "All squads" is its own choice and sends no squad list.
    await scope.getByRole('checkbox', { name: 'All squads' }).check()
    await page.getByRole('button', { name: 'Save access' }).click()
    await expect.poll(() => patches.length).toBe(4)
    expect(patches.at(-1)).toEqual({ role: 'analyst', all_squads: true, squad_ids: [], expected_version: 4 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  })
}

test('the permission list shows each person\'s own rights, not a per-role table', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await mock(page, { flag: true })
  await page.goto('/my-club?program=7&view=staff')
  const scoutRow = page.locator('.sa-perm').filter({ hasText: 'Decide on scout requests' })
  await page.getByRole('button', { name: /Synthetic Invited Manager/ }).click()
  await expect(page.getByRole('heading', { name: 'What a club manager can do' })).toBeVisible()
  await expect(scoutRow.locator('.sa-mark')).toHaveText('—')
  await expect(page.locator('.sa-perm').filter({ hasText: 'Edit club page & branding' }).locator('.sa-mark')).toHaveText('Yes')
  await expect(page.getByText('Invited managers can’t decide on scout requests.')).toBeVisible()
  await shot(page, 'staff-access-invited-manager-desktop', '.sa-aside')
  await page.getByRole('button', { name: /Synthetic Owner/ }).click()
  await expect(scoutRow.locator('.sa-mark')).toHaveText('Yes')
  await expect(page.getByText('Invited managers can’t decide on scout requests.')).toHaveCount(0)
})

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
