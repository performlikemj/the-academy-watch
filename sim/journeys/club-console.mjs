export default async function clubConsole({ journey, step, goto }) {
  await journey('club-console', async () => {
    await step(
      'club-home',
      'page communicates clearly what the club user should do, showing either console tabs such as Roster or Matches, or an honest access or empty state',
      async (page) => {
        await goto('/my-club')
        await page.locator('body').getByText(/roster|matches|club|access|claim|sign in|no program/i).first().waitFor({ state: 'visible', timeout: 20_000 })
      },
    )
  })
}
