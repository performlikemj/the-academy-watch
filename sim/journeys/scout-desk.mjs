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

    await step('open-player', 'a player page with stats or profile sections', async (page) => {
      const firstPlayer = page.locator('a[href^="/players/"]').first()
      await firstPlayer.waitFor({ state: 'visible', timeout: 10_000 })
      await firstPlayer.click()
      await page.waitForURL(/\/players\/[^/?#]+/, { timeout: 20_000 })
      await page.getByRole('heading').first().waitFor({ state: 'visible', timeout: 15_000 })
    })
  })
}
