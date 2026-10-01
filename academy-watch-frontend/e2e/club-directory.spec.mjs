/* global document, window */
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

// `seen` = every API URL requested; `searches` = each directory search body; `events` = analytics events sent.
async function mock(page, { flag, clubs = CLUBS, seen = [], searches = [], events = [], onSave, failing = false } = {}) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const reply = (json) => route.fulfill({ json })
    seen.push(url.pathname + url.search)
    if (url.pathname === '/api/features') return reply(flag ? { contact_rail: false, club_directory: true } : { contact_rail: false })
    if (url.pathname === '/api/meta/data-mode') return reply({ api_football_frozen: false })
    if (url.pathname === '/api/events') {
      events.push(...(route.request().postDataJSON()?.events || []))
      return route.fulfill({ status: 202, json: { accepted: 1 } })
    }
    if (url.pathname === '/api/club-directory/search' && route.request().method() === 'POST') {
      const search = route.request().postDataJSON() || {}
      searches.push(search)
      if (failing) return route.fulfill({ status: 503, json: { error: 'synthetic_unavailable' } })
      let rows = clubs
      if (search.programme) rows = rows.filter((row) => row.gender_programs.some((code) => search.programme.includes(code)))
      if (search.q) rows = rows.filter((row) => row.name.toLowerCase().includes(search.q.toLowerCase()))
      if (search.lat !== undefined) rows = rows.map((row, index) => ({ ...row, distance_km: row.venue ? 3.2 + index * 8 : null }))
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
  expect(seen.some((path) => path.startsWith('/api/programs') || path.startsWith('/api/club-directory'))).toBe(false)
})

test('flag on: lists verified clubs, filters, searches and opens a club page', async ({ page }) => {
  const searches = []
  await mock(page, { flag: true, searches })
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
  expect(searches.at(-1).programme).toEqual(['women', 'girls'])
  await expect(page).toHaveURL(/for=girls_women/)
  await page.getByRole('button', { name: 'Girls & women' }).click()

  await page.getByRole('searchbox').fill('gamma')
  await page.getByRole('search').getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('club-count')).toHaveText('1 verified club')
  expect(searches.at(-1).q).toBe('gamma')
  expect(page.url()).not.toContain('gamma')

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

test('flag on: location is sent coarse in the request body, never in any URL, and missing pins say so', async ({ browser }) => {
  const context = await browser.newContext({ geolocation: { latitude: 50.791234, longitude: -1.062345 }, permissions: ['geolocation'], locale: 'en-GB' })
  const page = await context.newPage()
  const seen = []
  const searches = []
  // Everything the browser asks any server for, mocked or not: this is what an access log would record.
  const requested = []
  page.on('request', (request) => requested.push(request.url()))
  await mock(page, { flag: true, seen, searches })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(3)
  await page.getByRole('button', { name: 'Use my location' }).click()
  await expect(page.getByText('Nearest first')).toBeVisible()
  await expect(page.getByTestId('club-row').first()).toContainText('2.0 mi')
  await expect(page.getByTestId('club-row').nth(2)).toContainText('Distance unavailable')
  const located = searches.filter((search) => search.lat !== undefined)
  expect(located.length).toBeGreaterThan(0)
  for (const search of located) expect([search.lat, search.lng]).toEqual([50.79, -1.06])
  await page.getByLabel('Distance').selectOption({ label: '25 mi' })
  await expect.poll(() => searches.at(-1).radius_km).toBe(40)
  expect(page.url()).not.toContain('50.79')
  for (const url of [...requested, ...seen]) {
    expect(url).not.toMatch(/50\.79|-1\.06|[?&](lat|lng|radius_km|q)=/)
  }
  await page.getByRole('button', { name: 'Stop using my location' }).click()
  await expect(page.getByRole('button', { name: 'Use my location' })).toBeVisible()
  await expect.poll(() => searches.at(-1).lat).toBeUndefined()
  await context.close()
})

// RB1-2 (the reviewer's probe, reversed): a postcode search used to land in the pageview path.
test('flag on: a postcode search stays out of the page URL, request URLs and product analytics', async ({ page }) => {
  const events = []
  const searches = []
  const requested = []
  page.on('request', (request) => requested.push(request.url()))
  await mock(page, { flag: true, events, searches })
  await page.goto('/clubs?q=ZZ99+9ZZ&level=amateur')
  await expect(page.getByTestId('club-count')).toBeVisible()
  // A search carried in an old link is neither run nor left in the address bar.
  await expect(page).toHaveURL(/\/clubs\?level=amateur$/)
  expect(searches.every((search) => search.q === undefined)).toBe(true)

  await page.getByRole('searchbox').fill('AB12 3CD')
  await page.getByRole('search').getByRole('button', { name: 'Search' }).click()
  await expect.poll(() => searches.at(-1)?.q).toBe('AB12 3CD')
  await page.getByRole('button', { name: 'Youth' }).click()
  await expect(page).toHaveURL(/for=youth/)
  expect(page.url()).not.toMatch(/AB12|3CD/)

  // Analytics did fire for this page (so the check below is not vacuous) and flushes on its 5 s timer.
  await expect.poll(() => events.some((event) => event.name === 'pageview' && /^\/clubs\?.*for=youth/.test(event.path || '')), { timeout: 15000 }).toBe(true)
  expect(events.filter((event) => event.name === 'pageview' && (event.path || '').startsWith('/clubs')).length).toBeGreaterThan(1)
  expect(JSON.stringify(events)).not.toMatch(/AB12|3CD|ZZ99|9ZZ/)
  // Apart from the old link this test itself opened, no request URL carries a search.
  for (const url of requested.filter((item) => !item.includes('/clubs?q=ZZ99'))) expect(url).not.toMatch(/AB12|3CD|ZZ99|[?&]q=/)
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

// The reviewer's passing browser probes (RB1), kept as regressions.
for (const mode of ['denied', 'unavailable']) {
  test(`flag on: location ${mode} says so and leaves the list and the town search working`, async ({ page }) => {
    await page.addInitScript((kind) => Object.defineProperty(navigator, 'geolocation', {
      value: kind === 'unavailable' ? undefined : { getCurrentPosition: (_ok, fail) => fail({ code: 1 }) }, configurable: true,
    }), mode)
    const searches = []
    await mock(page, { flag: true, searches })
    await page.goto('/clubs')
    await page.getByRole('button', { name: 'Use my location' }).click()
    await expect(page.getByText(mode === 'unavailable'
      ? 'This browser can’t share a location. Search by town or postcode instead.'
      : 'We couldn’t get your location. Search by town or postcode instead.')).toBeVisible()
    await expect(page.getByTestId('club-row')).toHaveCount(3)
    expect(searches.every((search) => search.lat === undefined)).toBe(true)
  })
}

test('flag on: club-supplied text renders literally, with no injected element and no sideways scroll', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.addInitScript(() => { window.directoryInjected = false })
  const injection = '<img src=x onerror="window.directoryInjected=true">'
  const hostile = club(9, 'Synthetic Hostile', {
    name: `${injection}${'A'.repeat(140)}`,
    venue: { name: `${injection}${'B'.repeat(70)}`, postcode: 'TT1 1AA', latitude: 51.5, longitude: -0.1 },
  })
  await mock(page, { flag: true, clubs: [hostile] })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(1)
  await expect(page.getByTestId('club-row')).toContainText(injection)
  expect(await page.evaluate(() => window.directoryInjected)).toBe(false)
  await expect(page.getByTestId('club-row').locator('img')).toHaveCount(0)
  await noSideScroll(page)
  await page.getByTestId('club-plot').getByRole('button').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('selected-club')).toContainText(injection)
})

test('flag on: a failed load offers a retry that recovers', async ({ page }) => {
  await mock(page, { flag: true, failing: true })
  await page.goto('/clubs')
  await expect(page.getByText('We couldn’t load the clubs.')).toBeVisible()
  await page.unroute('**/api/**')
  await mock(page, { flag: true })
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByTestId('club-row')).toHaveCount(3)
})

// RB1V-N2: three searches' worth of full pages; `hold` keeps one named response back until the test lets it go.
async function pagedSearches(page, hold) {
  const searches = []
  const rows = (first, name, extra) => Array.from({ length: 20 }, (_, index) => club(first + index, `${name} ${index}`, extra))
  let release
  const held = new Promise((resolve) => { release = resolve })
  await mock(page, { flag: true })
  await page.route('**/api/club-directory/search', async (route) => {
    const search = route.request().postDataJSON() || {}
    const youth = Boolean(search.programme)
    const pageNumber = search.page || 1
    searches.push(`${youth ? 'youth' : 'all'}:${pageNumber}`)
    if (searches.at(-1) === hold) await held
    const clubs = youth
      ? rows(pageNumber === 1 ? 201 : 301, pageNumber === 1 ? 'Synthetic Youth First' : 'Synthetic Youth Second', { gender_programs: ['boys'] })
      : rows(pageNumber === 1 ? 101 : 151, pageNumber === 1 ? 'Synthetic Adult Old' : 'Synthetic Adult More')
    return route.fulfill({ json: { clubs, page: pageNumber, per_page: 20, total: 40, has_more: pageNumber === 1, filters: { levels: [], programmes: [] } } })
  })
  return { searches, release }
}

const rowNames = async (page) => (await page.getByTestId('club-row').allTextContents()).map((text) => text.match(/Synthetic \w+ \w+/)[0])

test('flag on: changing a filter while the list is loading never mixes two searches', async ({ page }) => {
  const { searches, release } = await pagedSearches(page, 'youth:1')
  const more = page.getByRole('button', { name: 'Show more clubs', exact: true })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(20)
  await expect(more).toBeEnabled()

  // The reviewer's sequence: pick Youth, and while its first page is still on its way, ask for more.
  await page.getByRole('button', { name: 'Youth', exact: true }).click()
  await expect.poll(() => searches.includes('youth:1')).toBe(true)
  await expect(more).toBeDisabled()
  await more.click({ force: true })
  await more.dispatchEvent('click')
  await page.waitForTimeout(300)
  expect(searches).toEqual(['all:1', 'youth:1'])
  expect(new Set(await rowNames(page))).toEqual(new Set(['Synthetic Adult Old']))

  release()
  await expect(page.getByTestId('club-row').first()).toContainText('Synthetic Youth First 0')
  await expect(page.getByTestId('club-row')).toHaveCount(20)
  expect(new Set(await rowNames(page))).toEqual(new Set(['Synthetic Youth First']))

  // Paging starts again from the new search's first page.
  await expect(more).toBeEnabled()
  await more.click()
  await expect(page.getByTestId('club-row')).toHaveCount(40)
  expect(searches).toEqual(['all:1', 'youth:1', 'youth:2'])
  const names = await rowNames(page)
  expect(names.slice(0, 20).every((name) => name === 'Synthetic Youth First')).toBe(true)
  expect(names.slice(20).every((name) => name === 'Synthetic Youth Second')).toBe(true)
  await expect(more).toHaveCount(0)
})

test('flag on: a "show more" answer that arrives after the filter changed is dropped', async ({ page }) => {
  const { searches, release } = await pagedSearches(page, 'all:2')
  const more = page.getByRole('button', { name: 'Show more clubs', exact: true })
  await page.goto('/clubs')
  await expect(page.getByTestId('club-row')).toHaveCount(20)
  await more.click()
  await expect.poll(() => searches.includes('all:2')).toBe(true)
  await expect(more).toBeDisabled()

  await page.getByRole('button', { name: 'Youth', exact: true }).click()
  await expect(page.getByTestId('club-row').first()).toContainText('Synthetic Youth First 0')
  release()
  await page.waitForTimeout(300)
  await expect(page.getByTestId('club-row')).toHaveCount(20)
  expect(new Set(await rowNames(page))).toEqual(new Set(['Synthetic Youth First']))
  expect(searches).toEqual(['all:1', 'all:2', 'youth:1'])

  await more.click()
  await expect(page.getByTestId('club-row')).toHaveCount(40)
  expect(new Set((await rowNames(page)).slice(20))).toEqual(new Set(['Synthetic Youth Second']))
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
