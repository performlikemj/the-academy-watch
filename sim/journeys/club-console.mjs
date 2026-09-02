export const SYNTHETIC_BRIEF = 'Maintain wide support before receiving\nRecover inside after possession changes.'
const SIM_PROGRAM_SUFFIX = '-sim-fixture'

export function assertSyntheticFixture(program, roster) {
  if (!String(program?.slug || '').endsWith(SIM_PROGRAM_SUFFIX) || program?.country !== 'Development') {
    throw new Error('club-console sim refused: the selected program is not the dedicated synthetic sim fixture')
  }
  if (!roster || !Array.isArray(roster.members) || !roster.system_brief) {
    throw new Error('club-console sim refused: the synthetic roster response is incomplete')
  }
  const bodies = [roster.system_brief.body, ...roster.members.map((member) => member?.brief?.body)]
  if (bodies.some((body) => body !== null && body !== SYNTHETIC_BRIEF)) {
    throw new Error('club-console sim refused: the synthetic sim fixture contains a non-synthetic brief')
  }
  return { program, roster }
}

async function requireSyntheticFixture(page) {
  const result = await page.evaluate(async ({ suffix }) => {
    const token = localStorage.getItem('academy_watch_user_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const response = await fetch('/api/funding/claims/me', {
      headers,
    })
    if (!response.ok) return { error: `fixture discovery returned HTTP ${response.status}` }
    const payload = await response.json()
    const claim = (payload.claims || []).find((row) => (
      row?.status === 'approved'
      && row?.program?.platform_status === 'approved'
      && String(row?.program?.slug || '').endsWith(suffix)
    ))
    if (!claim?.program) return { error: 'no approved synthetic sim fixture program was found' }
    const rosterResponse = await fetch(`/api/club/${claim.program.id}/roster`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!rosterResponse.ok) return { error: `synthetic roster returned HTTP ${rosterResponse.status}` }
    return { program: claim.program, roster: await rosterResponse.json() }
  }, { suffix: SIM_PROGRAM_SUFFIX })
  if (result.error) throw new Error(`club-console sim refused: ${result.error}`)
  return assertSyntheticFixture(result.program, result.roster)
}

export async function selectSyntheticFixtureProgram(page, fixtureProgram) {
  const fixtureHeading = page.getByRole('heading', { name: fixtureProgram.name, exact: true })
  try {
    try {
      await fixtureHeading.waitFor({ state: 'visible', timeout: 3_000 })
    } catch {
      const programSwitcher = page.getByLabel('Switch club program')
      await programSwitcher.waitFor({ state: 'visible', timeout: 20_000 })
      await programSwitcher.click()
      await page.getByRole('option', { name: fixtureProgram.name, exact: true }).click()
    }
    await fixtureHeading.waitFor({ state: 'visible', timeout: 20_000 })
  } catch (error) {
    await page.goto('about:blank')
    throw error
  }
}

export default async function clubConsole({ journey, step, goto, page }) {
  await journey('club-console', async () => {
    const { program: fixtureProgram } = await requireSyntheticFixture(page)
    await step(
      'club-home',
      'page communicates clearly what the club user should do, showing either console tabs such as Roster or Matches, or an honest access or empty state',
      async (page) => {
        await goto('/my-club')
        await selectSyntheticFixtureProgram(page, fixtureProgram)
      },
    )
    await step(
      'brief-edit',
      'a synthetic coach brief saves for one synthetic fixture member and remains after reload',
      async (page) => {
        const editors = page.locator('textarea[id^="coach-brief-"]')
        await editors.first().waitFor({ state: 'visible', timeout: 20_000 })
        let editor = null
        for (let index = 0; index < await editors.count(); index += 1) {
          const candidate = editors.nth(index)
          const value = await candidate.inputValue()
          if (value === '' || value === SYNTHETIC_BRIEF) {
            editor = candidate
            break
          }
        }
        if (!editor) throw new Error('club-console sim refused: no empty or synthetic coach-brief editor is available')
        const editorId = await editor.getAttribute('id')
        await editor.fill(SYNTHETIC_BRIEF)
        const responsePromise = page.waitForResponse((response) => (
          response.request().method() === 'PUT'
          && /\/api\/club\/\d+\/roster\/\d+\/brief$/.test(new URL(response.url()).pathname)
        ))
        await editor.locator('..').getByRole('button', { name: 'Save', exact: true }).click()
        const response = await responsePromise
        if (!response.ok()) throw new Error(`synthetic brief save returned HTTP ${response.status()}`)
        await page.reload({ waitUntil: 'domcontentloaded' })
        const reloaded = page.locator(`textarea[id="${editorId}"]`)
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
