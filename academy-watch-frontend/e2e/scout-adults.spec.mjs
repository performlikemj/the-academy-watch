import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`scout age chips use adult U21/U23 ranges at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await page.addInitScript(() => localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true'))
    const playerQueries = []
    const leaderboardQueries = []
    await page.route('**/api/**', route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/scout/players') {
        playerQueries.push(url.searchParams)
        return route.fulfill({ json: { players: [], total: 0, page: 1, per_page: 25, total_pages: 0 } })
      }
      if (url.pathname === '/api/scout/leaderboards') {
        leaderboardQueries.push(url.searchParams)
        return route.fulfill({ json: { leaderboards: {}, limit: 5, phase: 'all' } })
      }
      if (url.pathname === '/api/seasons') return route.fulfill({ json: {
        current_season: 2025, bounds: { min: 2025, max: 2025 },
        seasons: [{ season: 2025, label: '2025/26', is_current: true }],
      } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/scout')
    await expect(page.getByRole('button', { name: 'U18', exact: true })).toHaveCount(0)
    for (const [chip, maximum] of [['U21', '20'], ['U23', '22']]) {
      await page.getByRole('button', { name: chip, exact: true }).click()
      await expect.poll(() => playerQueries.at(-1)?.get('max_age')).toBe(maximum)
      await expect.poll(() => leaderboardQueries.at(-1)?.get('max_age')).toBe(maximum)
    }
  })
}
