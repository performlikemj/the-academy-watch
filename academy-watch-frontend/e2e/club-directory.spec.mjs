/* global document */
import { expect, test } from '@playwright/test'

// Synthetic API data only (Clubs near you, dark behind CLUB_DIRECTORY_ENABLED).
const club = (id, name, extra = {}) => ({
  id, slug: name.toLowerCase().replace(/\s+/g, '-'), name, crest_url: null,
  brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' },
  country: 'Testland', region: 'Test Shire', city: 'Test Town', league: { name: 'Synthetic League' },
  verified: true, verified_at: null, venue: null, club_level: null, gender_programs: [], age_groups: [], activities: [],
  squad_count: 0, distance_km: null, ...extra,
})
const CLUBS = [
  club(1, 'Synthetic Alpha FC', { venue: { name: 'Alpha Ground', postcode: 'TT1 1AA', latitude: 50.8, longitude: -1.1 }, club_level: 'semi_pro', gender_programs: ['men', 'women'], squad_count: 5 }),
  club(2, 'Synthetic Beta Girls', { venue: { name: null, postcode: null, latitude: 50.86, longitude: -1.02 }, club_level: 'grassroots', gender_programs: ['girls'], squad_count: 1 }),
  club(3, 'Synthetic Gamma Town'),
]
const program = { id: 7, name: 'Synthetic Staff Club', slug: 'synthetic-staff-club', platform_status: 'approved', brand: { primary_color: '#0F3D2E', accent_color: '#CFAE62' } }

async function mock(page, { flag, clubs = CLUBS, seen = [], onSave } = {}) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const reply = (json) => route.fulfill({ json })
    seen.push(url.pathname + url.search)
    if (url.pathname === '/api/features') return reply(flag ? { contact_rail: false, club_directory: true } : { contact_rail: false })
    if (url.pathname === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (url.pathname === '/api/programs') {
      let rows = clubs
      const programme = url.searchParams.get('programme')
      if (programme) rows = rows.filter((row) => row.gender_programs.some((code) => programme.split(',').includes(code)))
      if (url.searchParams.get('q')) rows = rows.filter((row) => row.name.toLowerCase().includes(url.searchParams.get('q').toLowerCase()))
      if (url.searchParams.get('lat')) rows = rows.map((row, index) => ({ ...row, distance_km: row.venue ? 3.2 + index * 8 : null }))
      return reply({ clubs: rows, page: 1, per_page: 20, total: rows.length, has_more: false, filters: { levels: [], programmes: [] } })
    }
    if (url.pathname === '/api/programs/synthetic-alpha-fc') {
      return reply({ program: { ...CLUBS[0], is_verified_program: true, provenance: { label: 'Self-reported' }, program_provided: null, external_support: null, updates: [], roster_links: null,
        ...(flag ? { directory: { venue: CLUBS[0].venue, club_level: 'semi_pro', gender_programs: ['men', 'women'], squad_count: 5 } } : {}) } })
    }
    if (url.pathname === '/api/funding/claims/me') return reply({ claims: [{ id: 31, status: 'approved', relationship_type: 'club_official', program }] })
    if (url.pathname === '/api/me/club-claims') return reply({ claims: [] })
    if (url.pathname === '/api/me/club') return reply({ clubs: [] })
    if (url.pathname === '/api/club/7/roster') return reply({ program, members: [], count: 0 })
    if (url.pathname === '/api/club/7/map') return reply({ program, squads: [], staff: [], unassigned_count: 0 })
    if (url.pathname === '/api/club/7/matches') return reply({ matches: [], total: 0 })
    if (url.pathname === '/api/club/7/updates') return reply({ updates: [] })
    if (url.pathname === '/api/club/7/profile') {
      const revision = { id: 1, status: 'approved', summary: 'Synthetic summary.', age_groups: [], activities: [], funding_purpose: null, official_url: null, safeguarding_url: null, media_urls: [], external_support: null, review_reason: null, reviewed_at: null, created_at: '2026-09-30T10:00:00' }
      const directory = { venue_name: 'Alpha Ground', postcode: 'TT1 1AA', latitude: 50.8, longitude: -1.1, club_level: 'semi_pro', gender_programs: ['men'] }
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON()
        onSave?.(body)
        return reply({ pending: { ...revision, id: 2, status: 'pending', ...(flag ? { directory: body.directory } : {}) } })
      }
      return reply({ program, approved: flag ? { ...revision, directory } : revision, pending: null, limits: { summary_max: 2000, funding_purpose_max: 1000, updates_pending_max: 5 } })
    }
    return reply({})
  })
}

async function noSideScroll(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
}

test('flag off: /clubs is still the teaser and the directory API is never called', async ({ page }) => {
  const seen = []
  await mock(page, { flag: false, seen })
  await page.goto('/clubs')
  await expect(page.getByText('Tell me when it opens.')).toBeVisible()
  await expect(page.getByText('Find a club · coming soon')).toBeVisible()
  await expect(page.getByTestId('club-count')).toHaveCount(0)
  expect(seen.some((path) => path.startsWith('/api/programs'))).toBe(false)
})

test('flag on: lists verified clubs, filters, searches and opens a club page', async ({ page }) => {
  const seen = []
  await mock(page, { flag: true, seen })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-count')).toHaveText('3 verified clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(3)
  await expect(page.getByTestId('club-row').first()).toContainText('Semi-pro · 5 squads · men, women')
  await expect(page.getByText('Tell me when it opens.')).toHaveCount(0)
  // Only clubs with approved coordinates are plotted; the rest are said to be missing.
  await expect(page.getByTestId('club-plot').getByRole('button')).toHaveCount(2)
  await expect(page.getByText('1 club in this list hasn’t pinned a ground yet')).toBeVisible()
  await page.getByTestId('club-plot').getByRole('button', { name: 'Synthetic Beta Girls' }).click()
  await expect(page.getByTestId('selected-club')).toContainText('Synthetic Beta Girls')

  await page.getByRole('button', { name: 'Girls & women' }).click()
  await expect(page.getByTestId('club-count')).toHaveText('2 verified clubs')
  expect(seen.at(-1)).toContain('programme=women%2Cgirls')
  await expect(page).toHaveURL(/for=girls_women/)
  await page.getByRole('button', { name: 'Girls & women' }).click()

  await page.getByRole('searchbox').fill('gamma')
  await page.getByRole('search').getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('club-count')).toHaveText('1 verified club')
  expect(seen.at(-1)).toContain('q=gamma')

  await page.getByRole('searchbox').fill('nowhere at all')
  await page.getByRole('search').getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('club-empty')).toContainText('No verified clubs match that yet.')
  await page.getByRole('button', { name: 'Clear search and filters' }).click()
  await expect(page.getByTestId('club-row')).toHaveCount(3)

  await page.getByTestId('club-row').first().click()
  await expect(page).toHaveURL(/\/programs\/synthetic-alpha-fc$/)
  await expect(page.getByTestId('club-find-us')).toContainText('Alpha Ground')
  await expect(page.getByRole('link', { name: 'All clubs' })).toBeVisible()
})

test('flag on: location is sent coarse, never put in the URL, and missing pins say so', async ({ browser }) => {
  const context = await browser.newContext({ geolocation: { latitude: 50.791234, longitude: -1.062345 }, permissions: ['geolocation'], locale: 'en-GB' })
  const page = await context.newPage()
  const seen = []
  await mock(page, { flag: true, seen })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(3)
  await page.getByRole('button', { name: 'Use my location' }).click()
  await expect(page.getByText('Nearest first')).toBeVisible()
  await expect(page.getByTestId('club-row').first()).toContainText('2.0 mi')
  await expect(page.getByTestId('club-row').nth(2)).toContainText('Distance unavailable')
  const located = seen.filter((path) => path.includes('lat='))
  expect(located.length).toBeGreaterThan(0)
  for (const path of located) expect(path).toMatch(/lat=50\.79&lng=-1\.06(&|$)/)
  expect(page.url()).not.toContain('50.79')
  await page.getByLabel('Distance').selectOption({ label: '25 mi' })
  await expect.poll(() => seen.at(-1)).toContain('radius_km=40')
  await page.getByRole('button', { name: 'Stop using my location' }).click()
  await expect(page.getByRole('button', { name: 'Use my location' })).toBeVisible()
  await expect.poll(() => seen.at(-1)).not.toContain('lat=')
  await context.close()
})

test('flag on: phone layout has no sideways scroll, with and without clubs', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mock(page, { flag: true })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(3)
  await noSideScroll(page)
  await page.unroute('**/api/**')
  await mock(page, { flag: true, clubs: [] })
  await page.reload()
  await expect(page.getByTestId('club-empty')).toContainText('No verified clubs are listed yet.')
  await expect(page.getByRole('button', { name: 'I’m interested' }).or(page.getByRole('button', { name: "I'm interested" }))).toBeVisible()
  await noSideScroll(page)
})

for (const flag of [false, true]) {
  test(`club profile form ${flag ? 'sends' : 'never sends'} the directory fields when the flag is ${flag ? 'on' : 'off'}`, async ({ page }) => {
    let saved = null
    await page.addInitScript(() => localStorage.setItem('academy_watch_user_token', 'synthetic-user'))
    await mock(page, { flag, onSave: (body) => { saved = body } })
    await page.goto('/my-club')
    await page.getByRole('button', { name: 'Settings' }).click()
    await page.getByRole('button', { name: 'Club profile' }).click()
    await expect(page.getByLabel('Summary')).toHaveValue('Synthetic summary.')
    if (!flag) {
      await expect(page.getByTestId('directory-fields')).toHaveCount(0)
      await page.getByRole('button', { name: 'Save for review' }).click()
      await expect(page.getByText('Profile submitted for review.')).toBeVisible()
      expect(saved).not.toBeNull()
      expect('directory' in saved).toBe(false)
      return
    }
    await expect(page.getByTestId('approved-directory')).toContainText('Alpha Ground · TT1 1AA')
    await expect(page.getByLabel('Ground or venue')).toHaveValue('Alpha Ground')
    await page.getByLabel('Latitude (optional)').fill('51.5010, -0.1416')
    await expect(page.getByLabel('Longitude (optional)')).toHaveValue('-0.1416')
    await page.getByLabel('Longitude (optional)').fill('')
    await page.getByRole('button', { name: 'Save for review' }).click()
    await expect(page.getByText('Add both latitude and longitude, or leave both empty.')).toBeVisible()
    expect(saved).toBeNull()
    await page.getByLabel('Longitude (optional)').fill('-0.1416')
    await page.getByLabel('Level').selectOption('grassroots')
    await page.getByLabel('Girls').check()
    await page.getByRole('button', { name: 'Save for review' }).click()
    await expect(page.getByText('Profile submitted for review.')).toBeVisible()
    expect(saved.directory).toEqual({ venue_name: 'Alpha Ground', postcode: 'TT1 1AA', latitude: 51.501, longitude: -0.1416, club_level: 'grassroots', gender_programs: ['men', 'girls'] })
  })
}
