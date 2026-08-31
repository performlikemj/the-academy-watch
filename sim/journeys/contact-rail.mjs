export default async function contactRail({ journey, step, goto }) {
  await journey('contact-rail', async () => {
    await step(
      'introductions',
      'either the introductions surface or a clear unavailable card is visible',
      async (page) => {
        await goto('/introductions')
        await page.getByText(/^introductions$/i).first().waitFor({ state: 'visible', timeout: 20_000 })
      },
    )

    await step('scout-affordances', null, async (page) => {
      await goto('/scout')
      await page.getByRole('heading', { name: /scout desk/i }).waitFor({ state: 'visible', timeout: 15_000 })
      const introduceButtons = page.getByRole('button', { name: /introduce/i })
      return { introduce_affordances_present: (await introduceButtons.count()) > 0 }
    })
  })
}
