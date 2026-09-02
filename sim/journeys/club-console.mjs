const SYNTHETIC_BRIEF = 'Maintain wide support before receiving\nRecover inside after possession changes.'

async function requireSyntheticFixture(page) {
  const result = await page.evaluate(async () => {
    const token = localStorage.getItem('academy_watch_user_token')
    const response = await fetch('/api/funding/claims/me', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) return { error: `fixture discovery returned HTTP ${response.status}` }
    const payload = await response.json()
    const claim = (payload.claims || []).find((row) => row?.status === 'approved' && row?.program?.platform_status === 'approved')
    return claim?.program || { error: 'no approved club-console fixture program was found' }
  })
  if (result.error) throw new Error(`club-console sim refused: ${result.error}`)
  if (!String(result.slug || '').endsWith('-dev-fixture') || result.country !== 'Development') {
    throw new Error('club-console sim refused: the selected program is not the synthetic development fixture')
  }
  return result
}

export default async function clubConsole({ journey, step, goto, page }) {
  const fixtureProgram = await requireSyntheticFixture(page)
  await journey('club-console', async () => {
    await step(
      'club-home',
      'page communicates clearly what the club user should do, showing either console tabs such as Roster or Matches, or an honest access or empty state',
      async (page) => {
        await goto('/my-club')
        await page.getByRole('heading', { name: fixtureProgram.name }).waitFor({ state: 'visible', timeout: 20_000 })
      },
    )
    await step(
      'brief-edit',
      'a synthetic coach brief saves for one synthetic fixture member and remains after reload',
      async (page) => {
        const editor = page.locator('textarea[id^="coach-brief-"]').first()
        await editor.waitFor({ state: 'visible', timeout: 20_000 })
        await editor.fill(SYNTHETIC_BRIEF)
        const responsePromise = page.waitForResponse((response) => (
          response.request().method() === 'PUT'
          && /\/api\/club\/\d+\/roster\/\d+\/brief$/.test(new URL(response.url()).pathname)
        ))
        await editor.locator('..').getByRole('button', { name: 'Save', exact: true }).click()
        const response = await responsePromise
        if (!response.ok()) throw new Error(`synthetic brief save returned HTTP ${response.status()}`)
        await page.reload({ waitUntil: 'domcontentloaded' })
        const reloaded = page.locator('textarea[id^="coach-brief-"]').first()
        await reloaded.waitFor({ state: 'visible', timeout: 20_000 })
        if (await reloaded.inputValue() !== SYNTHETIC_BRIEF) throw new Error('synthetic brief did not persist after reload')
      },
    )
    await step(
      'brief-in-reel',
      'the read-only synthetic fixture reel shows the Coach’s brief expected-vs-evidence block',
      async (page) => {
        await page.getByRole('tab', { name: 'Matches & reports' }).click()
        const reelButton = page.getByRole('button', { name: 'View player reels' }).first()
        await reelButton.waitFor({ state: 'visible', timeout: 20_000 })
        await reelButton.click()
        await page.getByText('AI match read (qualitative)', { exact: true }).click()
        await page.getByText("Coach's brief", { exact: true }).first().waitFor({ state: 'visible', timeout: 20_000 })
      },
    )
  })
}
