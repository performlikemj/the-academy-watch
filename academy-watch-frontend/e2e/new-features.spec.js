import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import {
    createDbClient,
    ensureJournalistUser,
    clearJournalistAssignments
} from './helpers/db.js'
import { loginWithCode, setAdminKey } from './helpers/auth.js'

let dbClient
let journalistUser

test.describe.serial('Team Aliases and Manual Players', () => {
    test.beforeAll(async () => {
        if (!env.adminKey) {
            throw new Error('ADMIN_API_KEY is required for E2E tests')
        }

        dbClient = createDbClient()
        await dbClient.connect()

        // Create or get test journalist user
        journalistUser = await ensureJournalistUser(dbClient, env.journalistEmail, {
            displayName: 'E2E Test Journalist'
        })

        // Clear any existing assignments
        await clearJournalistAssignments(dbClient, journalistUser.id)
    })

    test.afterAll(async () => {
        if (dbClient) {
            // Clean up
            if (journalistUser?.id) {
                await clearJournalistAssignments(dbClient, journalistUser.id)
                // Clean up manual submissions
                await dbClient.query('DELETE FROM manual_player_submissions WHERE user_id = $1', [journalistUser.id])
                // Clean up aliases
                await dbClient.query('DELETE FROM team_aliases WHERE alias LIKE $1', ['E2E%'])
            }
            await dbClient.end()
        }
    })

    test('admin can manage team aliases', async ({ page }) => {
        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/teams')

        // Click Aliases tab
        await page.getByRole('tab', { name: /Aliases/i }).click()

        // Create new alias
        const canonicalName = 'Manchester United'
        const aliasName = `E2E Alias ${Date.now()}`

        await page.getByPlaceholder('e.g. Manchester United').fill(canonicalName)
        await page.getByPlaceholder('e.g. Man Utd').fill(aliasName)
        await page.getByRole('button', { name: /Add Alias/i }).click()

        // Verify alias appears in list
        await expect(page.getByRole('alert')).toContainText(/Alias created successfully/i)
        const aliasRow = page.getByRole('row', { name: new RegExp(`${aliasName}.*${canonicalName}`, 'i') })
        await expect(aliasRow).toBeVisible()

        // Delete alias
        await page.on('dialog', dialog => dialog.accept())
        await aliasRow.getByRole('button').click()

        // Verify alias removed
        await expect(page.getByRole('row', { name: new RegExp(aliasName, 'i') })).toHaveCount(0)
    })

    test('writer can submit manual player and admin can review', async ({ page }) => {
        // 1. Writer submits player
        await loginWithCode(page, env.journalistEmail, dbClient, { displayName: 'E2E Journalist' })

        await page.goto('/writer/dashboard')

        // Open modal
        await page.getByRole('button', { name: /Suggest Player/i }).click()

        // Fill form
        const playerName = `E2E Player ${Date.now()}`
        const teamName = `E2E Team ${Date.now()}`

        await page.getByLabel(/Player Name/i).fill(playerName)
        await page.getByLabel(/Team Name/i).fill(teamName)
        await page.getByLabel(/League/i).fill('E2E League')
        await page.getByLabel(/Position/i).fill('Forward')
        await page.getByLabel(/Notes/i).fill('E2E Test Note')

        // Submit
        await page.getByRole('button', { name: /Submit Player/i }).click()

        // Verify success message
        await expect(page.getByText(/Player submitted successfully/i)).toBeVisible()

        // Check history tab
        await page.getByRole('tab', { name: /My Submissions/i }).click()
        await expect(page.getByText(playerName)).toBeVisible()
        await expect(page.getByText('Pending')).toBeVisible()

        // 2. Admin reviews submission
        await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
        await setAdminKey(page, env.adminKey)

        await page.goto('/admin/manual-players')

        // Find submission
        const submissionCard = page.locator('.border.rounded-lg', { hasText: playerName })
        await expect(submissionCard).toBeVisible()

        // Approve
        await submissionCard.getByRole('button', { name: /Approve/i }).click()

        // Fill admin note in dialog
        await page.getByPlaceholder(/e.g. Added to database/i).fill('Approved via E2E')
        await page.getByRole('button', { name: /Confirm Approval/i }).click()

        // Verify moved from pending
        await expect(submissionCard).not.toBeVisible()

        // Check approved tab
        await page.getByRole('tab', { name: /Approved/i }).click()
        await expect(page.getByText(playerName)).toBeVisible()

        // 3. Writer sees status update
        await loginWithCode(page, env.journalistEmail, dbClient, { displayName: 'E2E Journalist' })
        await page.goto('/writer/dashboard')
        await page.getByRole('button', { name: /Suggest Player/i }).click()
        await page.getByRole('tab', { name: /My Submissions/i }).click()

        const submissionsPanel = page.getByRole('tabpanel', { name: /My Submissions/i })
        await expect(submissionsPanel).toContainText(playerName)
        await expect(submissionsPanel).toContainText('Approved')
        await expect(submissionsPanel).toContainText('Approved via E2E')
    })
})
