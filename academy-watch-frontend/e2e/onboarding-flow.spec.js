import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import {
  createDbClient,
  ensureJournalistUser,
  clearJournalistAssignments,
  getFirstTeam
} from './helpers/db.js'
import { loginWithCode, setAdminKey } from './helpers/auth.js'

let dbClient
let journalistUser
let journalistDisplayName
let originalDisplayName
let parentClubName = 'Manchester United'
let customLoanTeamName
let adminContext
let adminPage
let journalistContext
let journalistPage
const attributionName = 'E2E Fanzine'
const attributionUrlRaw = 'fanzine.example.com'
const attributionUrlNormalized = `https://${attributionUrlRaw}`

const getJournalistRow = (page) => {
  const usersTable = page.getByRole('table')
  return usersTable.getByRole('row', { name: new RegExp(env.journalistEmail, 'i') }).first()
}

test.describe.serial('Partner onboarding flow', () => {
  test.beforeAll(async ({ browser }) => {
    if (!env.adminKey) {
      throw new Error('ADMIN_API_KEY is required for onboarding E2E tests')
    }

    dbClient = createDbClient()
    await dbClient.connect()

    journalistUser = await ensureJournalistUser(dbClient, env.journalistEmail, {
      displayName: 'E2E Fanzine Writer'
    })
    originalDisplayName = journalistUser.display_name
    journalistDisplayName = 'E2E Fanzine Writer'

    if (originalDisplayName !== journalistDisplayName) {
      await dbClient.query(
        'UPDATE user_accounts SET display_name = $1, display_name_lower = $2 WHERE id = $3',
        [journalistDisplayName, journalistDisplayName.toLowerCase(), journalistUser.id]
      )
    }

    await clearJournalistAssignments(dbClient, journalistUser.id)
    await dbClient.query(
      'UPDATE user_accounts SET attribution_name = NULL, attribution_url = NULL WHERE id = $1',
      [journalistUser.id]
    )
    await dbClient.query('DELETE FROM manual_player_submissions WHERE user_id = $1', [journalistUser.id])

    const parentClubResult = await dbClient.query(
      'SELECT name FROM teams WHERE LOWER(name) = LOWER($1) LIMIT 1',
      [parentClubName]
    )
    if (!parentClubResult.rows.length) {
      const fallbackTeam = await getFirstTeam(dbClient)
      parentClubName = fallbackTeam.name
    }

    customLoanTeamName = `E2E Fanzine FC ${Date.now()}`

    adminContext = await browser.newContext()
    adminPage = await adminContext.newPage()
    await loginWithCode(adminPage, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
    await setAdminKey(adminPage, env.adminKey)

    journalistContext = await browser.newContext()
    journalistPage = await journalistContext.newPage()
    await loginWithCode(journalistPage, env.journalistEmail, dbClient, { displayName: journalistDisplayName })
  })

  test.afterAll(async () => {
    if (dbClient) {
      if (journalistUser?.id) {
        await clearJournalistAssignments(dbClient, journalistUser.id)
        await dbClient.query('DELETE FROM manual_player_submissions WHERE user_id = $1', [journalistUser.id])
        await dbClient.query(
          'UPDATE user_accounts SET attribution_name = NULL, attribution_url = NULL WHERE id = $1',
          [journalistUser.id]
        )
        if (originalDisplayName && originalDisplayName !== journalistDisplayName) {
          await dbClient.query(
            'UPDATE user_accounts SET display_name = $1, display_name_lower = $2 WHERE id = $3',
            [originalDisplayName, originalDisplayName.toLowerCase(), journalistUser.id]
          )
        }
      }
      await dbClient.end()
    }
    if (adminPage) {
      await adminPage.close()
    }
    if (adminContext) {
      await adminContext.close()
    }
    if (journalistPage) {
      await journalistPage.close()
    }
    if (journalistContext) {
      await journalistContext.close()
    }
  })

  test('journalist can update attribution and URL normalizes', async () => {
    const page = journalistPage

    await page.goto('/settings')

    await page.getByLabel('Attribution Name (Optional)').fill(attributionName)
    await page.getByLabel('Attribution URL (Optional)').fill(attributionUrlRaw)
    await page.getByRole('button', { name: /Save Profile/i }).click()

    await expect(page.getByText('Profile updated successfully.')).toBeVisible()

    await page.reload()
    await expect(page.getByLabel('Attribution URL (Optional)')).toHaveValue(attributionUrlNormalized)

    await page.goto('/journalists')
    await page.getByPlaceholder('Search journalists...').fill(journalistDisplayName)
    await expect(page.getByRole('link', { name: attributionName })).toBeVisible()
  })

  test('admin assigns coverage and journalist sees it', async () => {
    const page = adminPage

    await page.goto('/admin/users')
    await page.getByPlaceholder('Search users...').fill(env.journalistEmail)
    await getJournalistRow(page).click()
    await page.getByRole('button', { name: /Edit Coverage/i }).click()

    const parentClubsTab = page.getByRole('tab', { name: /Parent Clubs/i })
    await parentClubsTab.click()
    const parentClubSelect = page.getByText('Select Parent Clubs').locator('..').getByRole('combobox')
    await parentClubSelect.click()
    await page.getByPlaceholder('Search teams or leagues…').fill(parentClubName)
    await page.getByRole('option', { name: parentClubName }).click()
    await page.getByRole('button', { name: 'Done' }).click()

    await page.getByRole('tab', { name: /Loan Teams/i }).click()
    const loanTeamInput = page.getByPlaceholder(/Enter team name/i)
    await loanTeamInput.fill(customLoanTeamName)
    const addLoanTeamButton = page.getByLabel('Add Loan Team').locator('..').getByRole('button')
    await addLoanTeamButton.click()

    await expect(page.getByText('Assigned Loan Teams').locator('..')).toContainText(customLoanTeamName)
    await expect(page.getByText('Assigned Loan Teams').locator('..')).toContainText('(custom)')

    await page.getByRole('button', { name: /Save Coverage/i }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5000 })

    await journalistPage.goto('/writer/dashboard')

    const parentCoverageSection = journalistPage.getByRole('heading', { name: 'Parent Clubs (all loanees)' }).locator('..')
    await expect(parentCoverageSection).toBeVisible()
    await expect(parentCoverageSection).toContainText(parentClubName)

    const loanCoverageSection = journalistPage.getByRole('heading', { name: 'Loan Destinations (players on loan there)' }).locator('..')
    await expect(loanCoverageSection).toBeVisible()
    await expect(loanCoverageSection).toContainText(customLoanTeamName)
  })

  test('manual player submission validates and approval flow works', async () => {
    await journalistPage.goto('/writer/dashboard')
    await journalistPage.getByRole('button', { name: /Suggest Player/i }).click()

    await journalistPage.getByLabel('Player Name *').fill(' ')
    await journalistPage.getByLabel('Team Name *').fill(' ')
    await journalistPage.getByRole('button', { name: /Submit Player/i }).click()
    await expect(journalistPage.getByText('Player Name and Team Name are required')).toBeVisible()

    const playerName = `E2E Onboard Player ${Date.now()}`
    const teamName = `E2E Onboard Team ${Date.now()}`
    await journalistPage.getByLabel('Player Name *').fill(playerName)
    await journalistPage.getByLabel('Team Name *').fill(teamName)
    await journalistPage.getByLabel('League (Optional)').fill('E2E League')
    await journalistPage.getByLabel('Position (Optional)').fill('Forward')
    await journalistPage.getByLabel('Notes / Source (Optional)').fill('E2E onboarding test')
    await journalistPage.getByRole('button', { name: /Submit Player/i }).click()

    await expect(journalistPage.getByText(/Player submitted successfully/i)).toBeVisible()

    await journalistPage.getByRole('tab', { name: /My Submissions/i }).click()
    await expect(journalistPage.getByText(playerName)).toBeVisible()
    await expect(journalistPage.getByText('Pending')).toBeVisible()

    await adminPage.goto('/admin/manual-players')

    const submissionCard = adminPage.locator('.border.rounded-lg', { hasText: playerName })
    await expect(submissionCard).toBeVisible()
    await submissionCard.getByRole('button', { name: /Approve/i }).click()
    await adminPage.getByPlaceholder(/e.g. Added to database/i).fill('Approved via onboarding E2E')
    await adminPage.getByRole('button', { name: /Confirm Approval/i }).click()

    await adminPage.getByRole('tab', { name: /Approved/i }).click()
    await expect(adminPage.getByText(playerName)).toBeVisible()

    await journalistPage.goto('/writer/dashboard')
    await journalistPage.getByRole('button', { name: /Suggest Player/i }).click()
    await journalistPage.getByRole('tab', { name: /My Submissions/i }).click()

    const submissionsPanel = journalistPage.getByRole('tabpanel', { name: /My Submissions/i })
    await expect(submissionsPanel).toContainText(playerName)
    await expect(submissionsPanel).toContainText('Approved')
    await expect(submissionsPanel).toContainText('Approved via onboarding E2E')
  })
})
