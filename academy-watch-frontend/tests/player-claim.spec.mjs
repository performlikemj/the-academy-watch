import { expect, test } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5180'

test('tracked-player self-claim submits the required contract status', async ({ page }) => {
  const claimRequests = []

  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-player-token')
    localStorage.setItem('academy_watch_display_name', 'Test Prospect')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.pathname === '/api/players/42/profile') {
      return route.fulfill({ json: { name: 'Test Prospect', position: 'Midfielder', age: 20 } })
    }
    if (url.pathname === '/api/players/42/showcase') {
      return route.fulfill({
        json: {
          claim_status: 'unclaimed',
          reel: [],
          photos: [],
          affiliations: [],
          verified_footage: [],
          profile: null,
        },
      })
    }
    if (url.pathname === '/api/me/claims') {
      return route.fulfill({ json: { claims: [] } })
    }
    if (url.pathname === '/api/players/42/claim' && request.method() === 'POST') {
      claimRequests.push({
        method: request.method(),
        pathname: url.pathname,
        body: request.postDataJSON(),
      })
      return route.fulfill({
        json: {
          claim: {
            id: 17,
            player_api_id: 42,
            relationship_type: 'player',
            contract_status: 'contracted',
            status: 'pending',
          },
        },
      })
    }

    return route.fulfill({ json: {} })
  })

  await page.goto(new URL('/players/42', baseURL).href)
  await page.getByRole('button', { name: 'Claim this profile' }).click()

  const submit = page.getByRole('button', { name: 'Submit claim' })
  await expect(submit).toBeDisabled()
  await page.getByRole('combobox', { name: 'Contract status' }).click()
  await page.getByRole('option', { name: 'Contracted' }).click()
  await page.getByPlaceholder('Anything that helps us verify your claim').fill('This is my profile.')
  await submit.click()

  await expect.poll(() => claimRequests).toEqual([{
    method: 'POST',
    pathname: '/api/players/42/claim',
    body: {
      relationship_type: 'player',
      message: 'This is my profile.',
      contract_status: 'contracted',
    },
  }])
})
