/* global window */
import { test, expect } from '@playwright/test'

test.skip(process.env.UXM1_REAL_BACKEND !== '1', 'Run with the foreground e2e/helpers/uxm1-backend.py fixture.')

for (const width of [1440, 390]) {
  test.describe(`${width}px real API`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } })
    test('real server display season retains tracked stats when fixtures lag the calendar', async ({ page, request }) => {
      const response = await request.get('/api/seasons')
      expect(response.ok()).toBe(true)
      const directory = await response.json()
      expect(directory.display_season).toBe(directory.current_season - 1)
      const label = `${directory.display_season}/${String(directory.display_season + 1).slice(-2)}`
      const reads = []
      page.on('response', response => {
        const url = new URL(response.url())
        if (/\/api\/(scout\/(players|leaderboards)|players\/42\/(stats|season-stats))$/.test(url.pathname)) {
          reads.push({ url, status: response.status() })
        }
      })
      await page.goto('/scout')
      await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText(label)
      await expect(page.getByRole('row').filter({ hasText: 'Real Tracked Adult' }).getByRole('link', { name: /Real Tracked Adult/ })).toBeVisible()
      for (const path of ['/api/scout/players', '/api/scout/leaderboards']) {
        await expect.poll(() => reads.some(r => r.url.pathname === path)).toBe(true)
      }
      await page.goto('/players/42')
      await expect(page.getByRole('heading', { name: `${label} Totals` })).toBeVisible()
      const stats = await request.get(`/api/players/42/stats?season=${directory.display_season}`)
      expect(stats.ok()).toBe(true)
      const matchRows = await stats.json()
      expect(Array.isArray(matchRows)).toBe(true)
      expect(matchRows).toHaveLength(1)
      expect(matchRows[0].minutes).toBe(90)
      const totals = await request.get(`/api/players/42/season-stats?season=${directory.display_season}`)
      expect(totals.ok()).toBe(true)
      expect((await totals.json()).minutes).toBe(90)
      expect(reads.length).toBeGreaterThanOrEqual(4)
      expect(reads.every(r => r.status === 200 && !r.url.searchParams.has('season'))).toBe(true)
    })

    for (const [id, name, source, appearances, minutes] of [
      [43, 'Real Shadow Adult', 'shadow', 15, 1200],
      [44, 'Real Limited Adult', 'limited-coverage', 30, 2500],
    ]) {
      test(`real ${source} defaults retain latest totals outside the display season`, async ({ page, request }) => {
        const directory = await (await request.get('/api/seasons')).json()
        // These are the unchanged main route's default and explicitly scoped reads.
        const defaults = await request.get(`/api/players/${id}/season-stats`)
        expect(defaults.ok()).toBe(true)
        const baseline = await defaults.json()
        expect(baseline.public_match_data?.primary_source ?? baseline.source).toBe(source)
        expect(baseline.appearances).toBe(appearances)
        expect(baseline.minutes).toBe(minutes)
        const scoped = await request.get(`/api/players/${id}/season-stats?season=${directory.display_season}`)
        expect(scoped.ok()).toBe(true)
        expect((await scoped.json()).appearances).toBe(0)
        const reads = []
        page.on('response', response => {
          const url = new URL(response.url())
          if ([`/api/players/${id}/stats`, `/api/players/${id}/season-stats`, `/api/players/${id}/matches`].includes(url.pathname)) {
            reads.push({ url, response })
          }
        })
        await page.goto(`/players/${id}`)
        await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
        const label = `${directory.display_season}/${String(directory.display_season + 1).slice(-2)}`
        const responseYear = Number.parseInt(String(baseline.season), 10)
        const responseLabel = `${responseYear}/${String(responseYear + 1).slice(-2)}`
        await expect(page.getByRole('heading', { name: `${responseLabel} Totals` })).toBeVisible()
        await expect(page.getByRole('combobox', { name: 'Select season' })).toContainText(label)
        await expect(page.getByText('Appearances', { exact: true }).locator('..').locator('.display')).toHaveText(String(appearances))
        for (const suffix of ['stats', 'season-stats']) {
          expect(reads.some(r => r.url.pathname.endsWith(`/${suffix}`))).toBe(true)
        }
        expect(reads.filter(r => !r.url.pathname.endsWith('/matches')).every(r => r.response.status() === 200 && !r.url.searchParams.has('season'))).toBe(true)
        expect(reads.filter(r => r.url.pathname.endsWith('/matches')).every(r => r.url.searchParams.get('season') === String(responseYear))).toBe(true)
        const browserTotals = await reads.find(r => r.url.pathname.endsWith('/season-stats')).response.json()
        expect(browserTotals.appearances).toBe(baseline.appearances)
        expect(browserTotals.minutes).toBe(baseline.minutes)
        if (process.env.UXM1_SHOTS) {
          await expect(page.locator('[data-slot="skeleton"]')).toHaveCount(0)
          await page.screenshot({ path: `${process.env.UXM1_SHOTS}/real-${id}-default-${width}.png`, fullPage: true })
        }
        // Picking display season really scopes the same page and changes its totals.
        await page.getByRole('combobox', { name: 'Select season' }).click()
        await page.getByRole('option', { name: `${directory.current_season}/${String(directory.current_season + 1).slice(-2)}` }).click()
        await page.getByRole('combobox', { name: 'Select season' }).click()
        await page.getByRole('option', { name: label, exact: true }).click()
        await expect(page).toHaveURL(new RegExp(`season=${directory.display_season}$`))
        await expect(page.getByText('Appearances', { exact: true }).locator('..').locator('.display')).toHaveText('0')
        await expect.poll(() => reads.some(r => r.url.pathname.endsWith('/season-stats') && r.url.searchParams.get('season') === String(directory.display_season))).toBe(true)
      })
    }

    test('real community games list contains multiple seasons despite stored history and totals season', async ({ page, request }) => {
      const directory = await (await request.get('/api/seasons')).json()
      await page.addInitScript(season => window.sessionStorage.setItem('aw.season', String(season)), directory.display_season - 1)
      const games = []
      page.on('response', response => {
        if (new URL(response.url()).pathname === '/api/players/-71/matches') games.push(response)
      })
      await page.goto('/local-players/71')
      await expect(page.getByRole('heading', { name: 'Real Community Adult', exact: true })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'vs Previous Season United', exact: true })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'vs Display Season City', exact: true })).toBeVisible()
      const label = `${directory.display_season}/${String(directory.display_season + 1).slice(-2)}`
      await expect(page.getByRole('heading', { name: `${label} Totals` })).toBeVisible()
      expect(games.length).toBeGreaterThan(0)
      expect(games.every(r => r.status() === 200 && !new URL(r.url()).searchParams.has('season'))).toBe(true)
      const data = await games[0].json()
      expect(data.total).toBe(2)
      expect(new Set(data.matches.map(m => m.season)).size).toBe(2)
    })


    for (const [localId, providerId, name, appearances] of [
      [72, 43, 'Real Linked Shadow Adult', 15], [73, 44, 'Real Linked Limited Adult', 30],
    ]) {
      test(`real linked local ${localId} keeps provider defaults and response label`, async ({ page, request }) => {
        const baseline = await (await request.get(`/api/players/${providerId}/season-stats`)).json()
        const reads = []
        page.on('response', response => {
          const url = new URL(response.url())
          if (url.pathname === `/api/players/${providerId}/season-stats`) reads.push(url)
        })
        await page.addInitScript(() => window.sessionStorage.setItem('aw.season', '2020'))
        await page.goto(`/local-players/${localId}`)
        await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
        const year = Number.parseInt(String(baseline.season), 10)
        await expect(page.getByRole('heading', { name: `${year}/${String(year + 1).slice(-2)} Totals` })).toBeVisible()
        await expect(page.getByText('Appearances', { exact: true }).locator('..').locator('.display')).toHaveText(String(appearances))
        expect(reads.length).toBeGreaterThan(0)
        expect(reads.every(url => !url.searchParams.has('season'))).toBe(true)
        if (process.env.UXM1_SHOTS) await page.screenshot({ path: `${process.env.UXM1_SHOTS}/real-linked-${localId}-${width}.png`, fullPage: true })
        const directory = await (await request.get('/api/seasons')).json()
        await page.goto(`/local-players/${localId}?season=${directory.display_season}`)
        await expect(page.getByText('Appearances', { exact: true }).locator('..').locator('.display')).toHaveText('0')
        expect(reads.some(url => url.searchParams.get('season') === String(directory.display_season))).toBe(true)
      })
    }
  })
}
