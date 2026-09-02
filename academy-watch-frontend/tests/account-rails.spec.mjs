import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'

const ACCOUNT_EMAIL = 'alex.scout@example.com'
const PLAYER_ID = 284324
const LOCAL_PLAYER_URL_ID = 17
const LOCAL_PLAYER_CANONICAL_ID = 23

test.use({ baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5180' })

async function mockSignedInApi(page, customHandler) {
  await page.addInitScript(({ email }) => {
    localStorage.setItem('academy_watch_user_token', 'mock-user-token')
    localStorage.setItem('academy_watch_display_name', 'Alex Scout')
    localStorage.setItem('academy_watch_is_admin', 'false')
    localStorage.setItem('academy_watch_is_journalist', 'false')
    localStorage.setItem('academy_watch_is_curator', 'false')
    localStorage.setItem('academy_watch_admin_key', 'mock-admin-key')
    localStorage.setItem('academy_watch_curator_key', 'mock-curator-key')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    localStorage.setItem('account-rails-fixture-email', email)
  }, { email: ACCOUNT_EMAIL })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (customHandler && await customHandler({ route, request, url })) return

    if (url.pathname === '/api/auth/me') {
      return route.fulfill({
        json: {
          email: ACCOUNT_EMAIL,
          role: 'user',
          account_role: 'scout',
          user_id: 42,
          display_name: 'Alex Scout',
          display_name_confirmed: true,
          is_journalist: false,
          is_curator: false,
          is_verified_scout: true,
        },
      })
    }
    if (url.pathname === '/api/features') return route.fulfill({ json: { contact_rail: false } })
    if (url.pathname === '/api/teams') return route.fulfill({ json: [] })
    if (url.pathname === '/api/subscriptions/me') return route.fulfill({ json: [] })
    if (url.pathname === '/api/user/email-preferences') {
      return route.fulfill({ json: { email_delivery_preference: 'individual' } })
    }
    if (url.pathname === '/api/user/all-subscriptions') {
      return route.fulfill({ json: { free_subscriptions: [], paid_subscriptions: [], journalist_follows: [] } })
    }
    if (url.pathname === '/api/scout/watchlist') {
      return route.fulfill({ json: { entries: [], digest_opt_in: true } })
    }
    if (url.pathname === '/api/scout/watchlist/ids') {
      return route.fulfill({ json: { player_ids: [] } })
    }
    if (url.pathname === '/api/me/claims') return route.fulfill({ json: { claims: [] } })

    if (url.pathname === `/api/players/${PLAYER_ID}/profile`) {
      return route.fulfill({
        json: {
          player_id: PLAYER_ID,
          name: 'Alex Prospect',
          position: 'Defender',
          nationality: 'England',
          age: 20,
          status: 'on_loan',
          parent_team_name: 'Northbank Academy',
          current_club_name: 'Harbour FC',
        },
      })
    }
    if (url.pathname === `/api/players/${PLAYER_ID}/stats`) return route.fulfill({ json: [] })
    if (url.pathname === `/api/players/${PLAYER_ID}/season-stats`) return route.fulfill({ json: null })
    if (url.pathname === `/api/players/${PLAYER_ID}/commentaries`) {
      return route.fulfill({ json: { commentaries: [], authors: [], total_count: 0 } })
    }
    if (url.pathname === `/api/players/${PLAYER_ID}/academy-stats`) return route.fulfill({ json: null })
    if (url.pathname === `/api/players/${PLAYER_ID}/journey/map`) return route.fulfill({ json: null })
    if (url.pathname === `/api/local-players/${LOCAL_PLAYER_URL_ID}`) {
      return route.fulfill({
        json: {
          player: {
            id: LOCAL_PLAYER_CANONICAL_ID,
            display_name: 'Community Prospect',
            birth_year: 2004,
            position: 'Midfielder',
            club_name: 'Harbour FC',
            country: 'England',
            status: 'approved',
          },
        },
      })
    }

    return route.fulfill({ json: {} })
  })
}

test('account export downloads the authenticated user data as JSON', async ({ page }) => {
  const exportPayload = {
    exported_at: '2026-09-02T00:00:00+00:00',
    account: { email: ACCOUNT_EMAIL, display_name: 'Alex Scout' },
    watchlist_entries: [],
  }

  await mockSignedInApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/account/export' && request.method() === 'GET') {
      await route.fulfill({ json: exportPayload })
      return true
    }
    return false
  })

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Account', exact: true })).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download my data' }).click()
  const download = await downloadPromise

  expect(download.suggestedFilename()).toMatch(/^academy-watch-export-\d{4}-\d{2}-\d{2}\.json$/)
  const body = JSON.parse(await readFile(await download.path(), 'utf8'))
  expect(body).toEqual(exportPayload)
})

test('account deletion requires the account email, posts confirmation, logs out, and returns home', async ({ page }) => {
  const deleteRequests = []

  await mockSignedInApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/account/delete' && request.method() === 'POST') {
      deleteRequests.push({
        body: request.postDataJSON(),
        authorization: request.headers().authorization,
      })
      await route.fulfill({
        json: {
          deleted: true,
          deletion_event_id: 91,
          completed_at: '2026-09-02T00:00:00+00:00',
          counts: {},
        },
      })
      return true
    }
    return false
  })

  await page.goto('/settings')
  await page.getByRole('button', { name: 'Delete my account' }).click()

  const confirmButton = page.getByRole('button', { name: 'Delete account now' })
  const confirmation = page.getByLabel('Type your account email to confirm')
  await expect(confirmButton).toBeDisabled()

  await confirmation.fill('someone-else@example.com')
  await expect(confirmButton).toBeDisabled()
  expect(deleteRequests).toHaveLength(0)

  await confirmation.fill(ACCOUNT_EMAIL)
  await expect(confirmButton).toBeEnabled()
  await confirmButton.click()

  await expect(page).toHaveURL('/')
  await expect.poll(() => deleteRequests).toEqual([{
    body: { confirm: 'DELETE' },
    authorization: 'Bearer mock-user-token',
  }])
  await expect.poll(() => page.evaluate(() => localStorage.getItem('academy_watch_user_token'))).toBeNull()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('academy_watch_admin_key'))).toBeNull()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('academy_watch_curator_key'))).toBeNull()
})

test('player report dialog posts the moderation subject, reason, and optional details', async ({ page }) => {
  const reportRequests = []

  await mockSignedInApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/reports' && request.method() === 'POST') {
      const body = request.postDataJSON()
      reportRequests.push({ body, authorization: request.headers().authorization })
      await route.fulfill({
        status: 201,
        json: {
          report: {
            id: 73,
            ...body,
            status: 'open',
            resolution_notes: null,
            created_at: '2026-09-02T00:00:00+00:00',
            resolved_at: null,
          },
        },
      })
      return true
    }
    return false
  })

  await page.goto(`/players/${PLAYER_ID}`)
  await expect(page.getByLabel('Report incorrect data')).toBeVisible()
  await page.getByRole('button', { name: 'Report', exact: true }).click()

  await page.getByRole('combobox', { name: 'Reason' }).click()
  await page.getByRole('option', { name: 'Misrepresentation' }).click()
  await page.getByLabel('Details (optional)').fill('The profile is presenting another person’s identity.')
  await page.getByRole('button', { name: 'Submit report' }).click()

  await expect(page.getByRole('heading', { name: 'Report submitted' })).toBeVisible()
  await expect.poll(() => reportRequests).toEqual([{
    body: {
      subject_type: 'player_profile',
      subject_id: String(PLAYER_ID),
      reason_code: 'misrepresentation',
      details: 'The profile is presenting another person’s identity.',
    },
    authorization: 'Bearer mock-user-token',
  }])
})

test('local player report uses the loaded canonical local identity', async ({ page }) => {
  const reportRequests = []

  await mockSignedInApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/reports' && request.method() === 'POST') {
      const body = request.postDataJSON()
      reportRequests.push(body)
      await route.fulfill({ status: 201, json: { report: { id: 74, ...body, status: 'open' } } })
      return true
    }
    return false
  })

  await page.goto(`/local-players/${LOCAL_PLAYER_URL_ID}`)
  await expect(page.getByRole('heading', { name: 'Community Prospect' })).toBeVisible()
  await page.getByRole('button', { name: 'Report', exact: true }).click()
  await page.getByRole('button', { name: 'Submit report' }).click()

  await expect(page.getByRole('heading', { name: 'Report submitted' })).toBeVisible()
  await expect.poll(() => reportRequests).toEqual([{
    subject_type: 'player_profile',
    subject_id: `local:${LOCAL_PLAYER_CANONICAL_ID}`,
    reason_code: 'inappropriate_content',
    details: null,
  }])
})

test('an expired report session is cleared and returned to the login flow', async ({ page }) => {
  await mockSignedInApi(page, async ({ route, request, url }) => {
    if (url.pathname === '/api/reports' && request.method() === 'POST') {
      await route.fulfill({ status: 401, json: { error: 'authentication required' } })
      return true
    }
    return false
  })

  await page.goto(`/players/${PLAYER_ID}`)
  await page.getByRole('button', { name: 'Report', exact: true }).click()
  await page.getByRole('button', { name: 'Submit report' }).click()

  await expect(page.getByRole('heading', { name: 'Sign in to The Academy Watch' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('academy_watch_user_token'))).toBeNull()
})
