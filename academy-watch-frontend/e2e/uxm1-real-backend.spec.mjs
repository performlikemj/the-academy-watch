/* global window */
import { test, expect } from '@playwright/test'

test.skip(process.env.UXM1_REAL_BACKEND !== '1', 'Run with the foreground e2e/helpers/uxm1-backend.py fixture.')

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
  expect(reads.every(r => r.status === 200 && r.url.searchParams.get('season') === String(directory.display_season))).toBe(true)
})

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
