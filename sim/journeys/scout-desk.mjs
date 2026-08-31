export default async function scoutDesk({ journey, step, goto }) {
  await journey('scout-desk', async () => {
    await step('browse-players', 'a table or grid of players with stats is visible', async (page) => {
      await goto('/scout')
      await page.getByRole('heading', { name: /scout desk/i }).waitFor({ timeout: 15_000 })
      const playerLinks = page.locator('a[href^="/players/"]')
      await playerLinks.first().waitFor({ state: 'visible', timeout: 20_000 })

      const search = page.getByRole('textbox', { name: /search players/i })
      let searched = false
      if (await search.count()) {
        const firstName = (await playerLinks.first().innerText()).split('\n')[0].trim()
        if (firstName) {
          await search.fill(firstName)
          await page.waitForTimeout(500)
          await playerLinks.first().waitFor({ state: 'visible', timeout: 10_000 })
          searched = true
        }
      }
      return { search_interacted: searched }
    })

    await step('open-player', 'the player page has finished loading and shows player profile or stats content', async (page) => {
      const firstPlayer = page.locator('a[href^="/players/"]').first()
      await firstPlayer.waitFor({ state: 'visible', timeout: 10_000 })
      const startedAt = Date.now()
      await firstPlayer.click()
      await page.waitForURL(/\/players\/[^/?#]+/, { timeout: 20_000 })
      const playerUrl = page.url()
      try {
        const contentState = await Promise.race([
          page.getByTitle('Report incorrect data').waitFor({ state: 'visible', timeout: 30_000 }).then(() => 'loaded'),
          page.getByText('Failed to load player data.', { exact: true }).waitFor({ state: 'visible', timeout: 30_000 }).then(() => 'error'),
        ])
        if (contentState === 'error') throw new Error('Player page entered its load-error state.')
      } catch (error) {
        const failure = new Error(`Player content did not reach its loaded state: ${error.message}`)
        failure.payload = { player_url: playerUrl, load_ms: Date.now() - startedAt }
        throw failure
      }
      return { player_url: playerUrl, load_ms: Date.now() - startedAt }
    })
  })
}
