import { test, expect } from '@playwright/test'
import { env } from './helpers/env.js'
import {
    createDbClient,
    cleanupTestSubmissions,
    cleanupTestCommunityTakes,
    cleanupTestAcademyLeagues,
    getFirstActiveLoan,
    getLoanedPlayerById
} from './helpers/db.js'
import { loginWithCode, setAdminKey } from './helpers/auth.js'

let dbClient

test.describe.serial('Academy Watch Features', () => {
    test.beforeAll(async () => {
        if (!env.adminKey) {
            throw new Error('ADMIN_API_KEY is required for E2E tests')
        }

        dbClient = createDbClient()
        await dbClient.connect()

        // Clean up any leftover test data
        await cleanupTestSubmissions(dbClient, 'E2E%')
        await cleanupTestCommunityTakes(dbClient, 'E2E%')
        await cleanupTestAcademyLeagues(dbClient, 'E2E%')
    })

    test.afterAll(async () => {
        if (dbClient) {
            // Final cleanup
            await cleanupTestSubmissions(dbClient, 'E2E%')
            await cleanupTestCommunityTakes(dbClient, 'E2E%')
            await cleanupTestAcademyLeagues(dbClient, 'E2E%')
            await dbClient.end()
        }
    })

    // ========================================================================
    // Community Takes / Submit Take Tests
    // ========================================================================

    test.describe('Community Takes', () => {
        const testPlayerName = `E2E Test Player ${Date.now()}`
        const testTakeContent = `E2E Test Take - Great performance today! ${Date.now()}`

        test('public user can submit a take via /submit-take', async ({ page }) => {
            await page.goto('/submit-take')

            // Verify page title
            await expect(page.getByRole('heading', { name: 'The Academy Watch' })).toBeVisible()
            await expect(page.getByText('Share your thoughts on academy and loan players')).toBeVisible()

            // Fill out the form
            await page.getByLabel('Player Name').fill(testPlayerName)
            await page.getByLabel('Your Take').fill(testTakeContent)
            await page.getByLabel('Your Name').fill('E2E Tester')
            await page.getByLabel('Email').fill('e2e.tester@test.local')

            // Submit
            await page.getByRole('button', { name: /Submit Take/i }).click()

            // Verify success
            await expect(page.getByText('Take Submitted!')).toBeVisible()
            await expect(page.getByText('Thanks for your take')).toBeVisible()

            // Can submit another
            await expect(page.getByRole('button', { name: /Submit Another/i })).toBeVisible()
        })

        test('admin can see pending submission in curation dashboard', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/curation')

            // Verify page loaded
            await expect(page.getByRole('heading', { name: 'Community Curation' })).toBeVisible()

            // Go to User Submissions tab
            await page.getByRole('tab', { name: /User Submissions/i }).click()

            // Make sure we're viewing Pending submissions
            const statusFilter = page.locator('button[role="combobox"]').filter({ hasText: /Pending|Approved|Rejected/i })
            const filterText = await statusFilter.textContent()
            if (!filterText.includes('Pending')) {
                await statusFilter.click()
                await page.getByRole('option', { name: 'Pending' }).click()
            }

            // Look for the submission card
            const submissionCard = page.locator('.border.rounded-lg', { hasText: testPlayerName })
            await expect(submissionCard).toBeVisible({ timeout: 10000 })
            await expect(submissionCard).toContainText('E2E Tester')
        })

        test('admin can approve a submission', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/curation')

            // Go to User Submissions tab
            await page.getByRole('tab', { name: /User Submissions/i }).click()

            // Find and approve the submission
            const submissionCard = page.locator('.border.rounded-lg', { hasText: testPlayerName })
            await expect(submissionCard).toBeVisible({ timeout: 10000 })

            await submissionCard.getByRole('button', { name: /Approve/i }).click()

            // Verify success message
            await expect(page.getByRole('alert')).toContainText(/approved/i, { timeout: 5000 })

            // Verify it's no longer in pending list
            await expect(submissionCard).not.toBeVisible({ timeout: 5000 })
        })

        test('admin can create a take directly', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/curation')

            // Click Add Take button (in the Community Takes tab)
            await page.getByRole('tab', { name: /Community Takes/i }).click()
            await page.getByRole('button', { name: /Add Take/i }).click()

            // Fill out the dialog form
            const directTakePlayer = `E2E Direct Player ${Date.now()}`
            const directTakeContent = `E2E Direct Take - Admin created ${Date.now()}`

            // Author field
            await page.getByLabel('Author').fill('E2E Admin Author')

            // Player Name field
            await page.getByLabel('Player Name').fill(directTakePlayer)

            // Content field
            await page.getByLabel('Content').fill(directTakeContent)

            // Submit
            await page.getByRole('button', { name: /Create Take/i }).click()

            // Verify success
            await expect(page.getByRole('alert')).toContainText(/created/i, { timeout: 5000 })
        })
    })

    // ========================================================================
    // Academy League Management Tests
    // ========================================================================

    test.describe('Academy Tracking', () => {
        const testLeagueName = `E2E Test League ${Date.now()}`
        const testLeagueId = 99999 // Fake API league ID

        test('admin can access academy management page', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/academy')

            // Verify page loaded
            await expect(page.getByRole('heading', { name: 'Academy Tracking' })).toBeVisible()
            await expect(page.getByText('Manage youth league configurations')).toBeVisible()
        })

        test('admin can create a new academy league', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/academy')

            // Click Add League button
            await page.getByRole('button', { name: /Add League/i }).click()

            // Wait for dialog
            await expect(page.getByRole('dialog')).toBeVisible()

            // Fill out the form
            await page.getByLabel('API League ID').fill(String(testLeagueId))
            await page.getByLabel('League Name').fill(testLeagueName)
            await page.getByLabel(/Country/i).fill('England')

            // Submit
            await page.getByRole('button', { name: /Add League/i }).filter({ hasNotText: /Cancel/i }).click()

            // Verify success
            await expect(page.getByRole('alert')).toContainText(/added|created/i, { timeout: 5000 })

            // Verify league appears in list
            await expect(page.getByText(testLeagueName)).toBeVisible({ timeout: 5000 })
        })

        test('admin can delete an academy league', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/academy')

            // Find the league card
            const leagueCard = page.locator('.border.rounded-lg', { hasText: testLeagueName })
            await expect(leagueCard).toBeVisible({ timeout: 5000 })

            // Click delete button (the trash icon button)
            await leagueCard.getByRole('button').filter({ has: page.locator('svg') }).last().click()

            // Confirm in the dialog
            await expect(page.getByRole('dialog')).toBeVisible()
            await page.getByRole('button', { name: /^Delete$/i }).click()

            // Verify success
            await expect(page.getByRole('alert')).toContainText(/deleted/i, { timeout: 5000 })

            // Verify league no longer appears
            await expect(page.getByText(testLeagueName)).not.toBeVisible({ timeout: 5000 })
        })
    })

    // ========================================================================
    // Pathway Status Tests (AdminLoans)
    // ========================================================================

    test.describe('Pathway Status Management', () => {
        let testLoan = null

        test.beforeAll(async () => {
            // Get a loan to test with
            testLoan = await getFirstActiveLoan(dbClient)
        })

        test('admin can view and edit pathway status in loans page', async ({ page }) => {
            if (!testLoan) {
                test.skip(true, 'No active loans in database to test pathway status')
                return
            }

            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/loans')

            // Verify page loaded
            await expect(page.getByRole('heading', { name: 'Loans' })).toBeVisible()

            // Apply filters to show the loan
            await page.getByRole('button', { name: /Apply/i }).click()
            await page.waitForTimeout(1000)

            // Find the loan row
            const loanRow = page.locator('.border.rounded-lg', { hasText: testLoan.player_name }).first()
            await expect(loanRow).toBeVisible({ timeout: 10000 })

            // Verify pathway badge is visible (should be one of Academy, On Loan, First Team, or Released)
            const pathwayBadge = loanRow.locator('span', { hasText: /Academy|On Loan|First Team|Released/i })
            await expect(pathwayBadge).toBeVisible()

            // Click edit button (pencil icon)
            await loanRow.locator('button').first().click()

            // Verify edit form shows pathway fields
            await expect(page.getByLabel(/Pathway Status/i)).toBeVisible()
            await expect(page.getByLabel(/Current Level/i)).toBeVisible()

            // Change pathway status to Academy
            await page.getByLabel(/Pathway Status/i).selectOption('academy')
            await page.getByLabel(/Current Level/i).selectOption('U21')

            // Save
            await page.getByRole('button', { name: /Save/i }).click()

            // Verify success
            await expect(page.getByRole('alert')).toContainText(/updated/i, { timeout: 5000 })

            // Verify the badge now shows Academy
            await page.waitForTimeout(500) // Wait for state update
            const updatedRow = page.locator('.border.rounded-lg', { hasText: testLoan.player_name }).first()
            const updatedBadge = updatedRow.locator('span', { hasText: /Academy/i })
            await expect(updatedBadge).toBeVisible({ timeout: 5000 })

            // Verify in database
            const updatedLoan = await getLoanedPlayerById(dbClient, testLoan.id)
            expect(updatedLoan.pathway_status).toBe('academy')
            expect(updatedLoan.current_level).toBe('U21')

            // Reset to original status for clean test state
            await updatedRow.locator('button').first().click()
            await page.getByLabel(/Pathway Status/i).selectOption(testLoan.pathway_status || 'on_loan')
            if (testLoan.current_level) {
                await page.getByLabel(/Current Level/i).selectOption(testLoan.current_level)
            } else {
                await page.getByLabel(/Current Level/i).selectOption('')
            }
            await page.getByRole('button', { name: /Save/i }).click()
            await expect(page.getByRole('alert')).toContainText(/updated/i, { timeout: 5000 })
        })

        test('admin can filter loans by pathway status', async ({ page }) => {
            await loginWithCode(page, env.adminEmail, dbClient, { displayName: 'E2E Admin' })
            await setAdminKey(page, env.adminKey)

            await page.goto('/admin/loans')

            // Verify pathway filter exists
            const pathwayFilter = page.getByLabel(/Pathway/i)
            await expect(pathwayFilter).toBeVisible()

            // Select On Loan filter (should have results)
            await pathwayFilter.selectOption('on_loan')
            await page.getByRole('button', { name: /Apply/i }).click()

            // Wait for results
            await page.waitForTimeout(1000)

            // Check that the filter is applied - loan cards should exist or show empty state
            const loanCards = page.locator('.border.rounded-lg').filter({ hasText: /→/ })
            const cardCount = await loanCards.count()

            if (cardCount > 0) {
                // All visible badges should be On Loan
                for (let i = 0; i < Math.min(cardCount, 3); i++) {
                    const badge = loanCards.nth(i).locator('span', { hasText: /Academy|On Loan|First Team|Released/i })
                    await expect(badge).toContainText(/On Loan/i)
                }
            }

            // Reset filter
            await page.getByRole('button', { name: /Reset/i }).click()
        })
    })
})
