function playbackError(message, payload) {
  const error = new Error(message)
  error.payload = payload
  return error
}

export default async function playerReels({ journey, step, goto, matchId }) {
  await journey('player-reels', async () => {
    await step('player-cards', 'the Player reels section is visible with player cards', async (page) => {
      await goto(`/admin/video/${encodeURIComponent(matchId)}`)
      const heading = page.getByRole('heading', { name: /player reels/i })
      await heading.waitFor({ state: 'visible', timeout: 30_000 })
      await heading.locator('xpath=ancestor::section[1]').locator('article').first().waitFor({ state: 'visible', timeout: 15_000 })
    })

    await step('open-reel', 'the open player reel shows a video element and an on-camera playlist', async (page) => {
      const section = page.locator('section[aria-labelledby="player-reels-heading"]')
      const card = section.locator('article').first()
      await card.locator('button[aria-expanded]').first().click()
      await card.locator('video').waitFor({ state: 'attached', timeout: 15_000 })
      await card.getByText(/on-camera playlist/i).waitFor({ state: 'visible', timeout: 10_000 })
    })

    await step('reel-playback', 'the player reel video plays and advances through its footage', async (page) => {
      const section = page.locator('section[aria-labelledby="player-reels-heading"]')
      const card = section.locator('article').first()
      const video = card.locator('video')
      await video.waitFor({ state: 'attached', timeout: 10_000 })
      const before = await video.evaluate((element) => element.currentTime)
      const paused = await video.evaluate((element) => element.paused)
      if (paused) await card.getByRole('button', { name: /^play$/i }).click()
      await page.waitForTimeout(12_000)
      const after = await video.evaluate((element) => element.currentTime)
      const payload = { current_time_before: before, current_time_after: after }
      if (!Number.isFinite(after) || after <= before + 0.25) {
        throw playbackError('The reel playhead did not advance.', payload)
      }
      return payload
    })

    await step('verify-identity', 'the Verify identity panel shows player crops or a vote summary', async (page) => {
      const section = page.locator('section[aria-labelledby="player-reels-heading"]')
      const card = section.locator('article').first()
      await card.getByRole('button', { name: /verify identity/i }).click()
      await card.getByText(/identity evidence|bound chain evidence|vote|crop/i).first().waitFor({ state: 'visible', timeout: 15_000 })
    })
  })
}
