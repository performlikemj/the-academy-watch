import { test, expect } from '@playwright/test'

const seasons = {
  current_season: 2025,
  bounds: { min: 2024, max: 2025 },
  seasons: [
    { season: 2025, label: '2025/26', has_rollup: true, is_current: true },
    { season: 2024, label: '2024/25', has_rollup: true, is_current: false },
  ],
}

async function installApiMocks(page, requests) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const season = Number(url.searchParams.get('season') || 2025)

    if (url.pathname === '/api/seasons') {
      return route.fulfill({ json: seasons })
    }
    if (url.pathname === '/api/players/42/profile') {
      return route.fulfill({ json: { name: 'Test Prospect', position: 'Midfielder', age: 19 } })
    }
    if (url.pathname === '/api/players/42/stats') {
      requests.playerStats.push(url.href)
      return route.fulfill({
        json: {
          matches: [{ fixture_date: `${season}-09-01`, opponent: 'Test United', position: 'M', minutes: 90, goals: 1, assists: 0 }],
          summary: { season },
          provenance: { primary_source: 'fixtures', reconcile_flag: null, fixtures_minutes: 90, journey_minutes: 90 },
        },
      })
    }
    if (url.pathname === '/api/players/42/season-stats') {
      requests.playerSeasonStats.push(url.href)
      return route.fulfill({
        json: {
          season: `${season}/${season + 1}`,
          appearances: 1,
          minutes: 90,
          goals: 1,
          assists: 0,
          avg_rating: 7.2,
          clubs: [],
          provenance: { primary_source: 'fixtures', reconcile_flag: null, fixtures_minutes: 90, journey_minutes: 90 },
        },
      })
    }
    if (url.pathname === '/api/scout/players') {
      requests.scoutPlayers.push(url.href)
      return route.fulfill({ json: { season, players: [], total: 0, total_pages: 0 } })
    }
    if (url.pathname === '/api/scout/leaderboards') {
      return route.fulfill({
        json: {
          season,
          leaderboards: { top_scorers: [], top_assists: [], most_minutes: [], best_per90: [] },
        },
      })
    }

    return route.fulfill({ json: {} })
  })
}

test('PlayerPage picker switches season and updates the totals heading', async ({ page }) => {
  const requests = { playerStats: [], playerSeasonStats: [], scoutPlayers: [] }
  await installApiMocks(page, requests)

  await page.goto('/players/42?season=2025')
  await expect(page.getByRole('heading', { name: '2025/26 Totals' })).toBeVisible()

  await page.getByRole('combobox', { name: 'Select season' }).click()
  await page.getByRole('option', { name: /2024\/25/ }).click()

  await expect(page).toHaveURL(/season=2024/)
  await expect(page.getByRole('heading', { name: '2024/25 Totals' })).toBeVisible()
  await expect.poll(() => requests.playerStats.some((url) => url.includes('season=2024'))).toBe(true)
  await expect.poll(() => requests.playerSeasonStats.some((url) => url.includes('season=2024'))).toBe(true)
})

test('ScoutPage picker refetches players with the selected season', async ({ page }) => {
  const requests = { playerStats: [], playerSeasonStats: [], scoutPlayers: [] }
  await installApiMocks(page, requests)

  await page.goto('/scout?season=2025')
  await expect.poll(() => requests.scoutPlayers.some((url) => url.includes('season=2025'))).toBe(true)

  await page.getByRole('combobox', { name: 'Select season' }).click()
  await page.getByRole('option', { name: /2024\/25/ }).click()

  await expect(page).toHaveURL(/season=2024/)
  await expect.poll(() => requests.scoutPlayers.some((url) => url.includes('season=2024'))).toBe(true)
})
