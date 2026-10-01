import { expect, test } from '@playwright/test'

async function mockControl(page, handler, flags = { admin_programs: true, admin_people: true, admin_safety: true, admin_business: true }) {
    await page.addInitScript(() => {
        localStorage.setItem('academy_watch_user_token', 'synthetic-control-token')
        localStorage.setItem('academy_watch_is_admin', 'true')
        localStorage.setItem('academy_watch_admin_key', 'synthetic-control-key')
        localStorage.setItem('academy_watch_display_name_confirmed', 'true')
        localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    })
    await page.route('**/api/**', async route => {
        const url = new URL(route.request().url())
        if (url.pathname === '/api/features') return route.fulfill({ json: flags })
        if (url.pathname === '/api/auth/me') return route.fulfill({ json: { email: 'test@example.test', role: 'admin', display_name: 'Test Admin', display_name_confirmed: true } })
        if (url.pathname === '/api/admin/auth-check') return route.fulfill({ json: { ok: true } })
        const body = await handler?.(url, route.request())
        return route.fulfill({ json: body ?? {} })
    })
}
const empty = { rows: [], total: 0, limit: 30, offset: 0 }

for (const width of [1440, 390]) {
    test(`four pages show truthful empty states at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
        const errors = []
        page.on('pageerror', error => errors.push(error.message))
        await mockControl(page, url => {
            if (url.pathname.endsWith('/hidden')) return { suppressions: [], programs: [] }
            if (url.pathname.endsWith('/cases')) return { ...empty, open_count: 0, overdue_count: 0, active_suppressions: 0, hidden_programs: 0 }
            if (url.pathname.endsWith('/summary')) return { ...empty, currencies: {}, paying_clubs: 0, freeze: { api_football: false, newsletters_configured: false, newsletters_effective: false }, changes: [], coverage: 'Recorded receipts only.' }
            return empty
        })
        for (const [route, heading, message] of [
            ['programs', 'Every club, one list', 'No programs match this search.'],
            ['people', 'Everyone on the pitch', 'No accounts match this search.'],
            ['safety', 'Keep the game safe', 'No cases in this view.'],
            ['business', 'The books, the switches', 'No recorded cash movements in this date range.'],
        ]) {
            await page.goto(`/admin/${route}`)
            await expect(page.getByRole('heading', { name: heading })).toBeVisible()
            await expect(page.getByText(message)).toBeVisible()
            expect(await page.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.innerWidth)).toBe(true)
        }
        expect(errors).toEqual([])
    })
}

test('flag off keeps new navigation dark and existing destinations reachable', async ({ page }) => {
    await mockControl(page, () => empty, {})
    await page.goto('/admin/people')
    await expect(page.getByRole('heading', { name: 'Page unavailable' })).toBeVisible()
    const nav = page.getByRole('navigation', { name: 'Admin' })
    await expect(nav.getByRole('link', { name: 'People', exact: true })).toHaveCount(0)
    await expect(nav.getByRole('link', { name: 'Clubs', exact: true })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Accounts & writers', exact: true })).toBeVisible()
})

test('program hide and owner assignment call A1 and A2 contracts with reasons', async ({ page }) => {
    let hidden = false
    let owner = false
    const mutations = []
    const program = () => ({ id: 1, name: 'Test Program', slug: 'test-program', country: 'JP', region: 'Test', platform_status: 'approved', emergency_hidden: hidden, players: 0, managers: 1, matches: 0, claims_pending: 0, origin: 'local' })
    await mockControl(page, (url, request) => {
        if (request.method() === 'POST') {
            mutations.push([url.pathname, request.postDataJSON()])
            if (url.pathname.endsWith('/emergency-hide')) hidden = true
            if (url.pathname.endsWith('/owner')) owner = true
            return {}
        }
        if (url.pathname === '/api/admin/programs/1') return { program: program(), managers: [{ user_account_id: 2, display_name: 'Test Manager', status: 'active', standing: 'active', owner }], actions: { emergency: true, owner: true } }
        return { ...empty, rows: [program()], total: 1 }
    })
    await page.goto('/admin/programs')
    await page.getByRole('button', { name: /Test Program/ }).click()
    await page.getByLabel('Reason for emergency hide').fill('Reported publication')
    await page.getByRole('button', { name: 'Emergency hide', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm emergency hide', exact: true }).click()
    await expect(page.getByText('Emergency hidden', { exact: true })).toBeVisible()
    await page.getByLabel('Assign owner', { exact: true }).selectOption('2')
    await page.getByLabel('Reason for assign owner').fill('Explicit assignment')
    await page.getByRole('button', { name: 'Assign owner', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm assign owner', exact: true }).click()
    await expect(page.getByText('Owner · active')).toBeVisible()
    expect(mutations).toEqual([['/api/admin/programs/1/emergency-hide', { reason: 'Reported publication' }], ['/api/admin/programs/1/owner', { user_account_id: 2, reason: 'Explicit assignment' }]])
})

test('people metadata omits injected private content and suspension errors stay visible', async ({ page }) => {
    const person = { id: 2, display_name: 'Test Person', email: 'person@example.test', account_status: 'active', roles: ['guardian'], programs: [], approved_claims: 1, private_notes: 'PRIVATE NOTES SENTINEL', feedback: 'PRIVATE FEEDBACK SENTINEL', messages: 'PRIVATE MESSAGE SENTINEL' }
    await mockControl(page, url => url.pathname === '/api/admin/people/2' ? { person } : { ...empty, total: 1, rows: [person] })
    await page.goto('/admin/people')
    await page.getByRole('button', { name: /Test Person/ }).click()
    await expect(page.getByRole('heading', { name: 'Test Person' })).toBeVisible()
    await expect(page.getByText(/PRIVATE .* SENTINEL/)).toHaveCount(0)
    await page.getByLabel('Reason for suspend account').fill('Review required')
    await page.route('**/api/admin/users/2/suspend', route => route.fulfill({ status: 403, json: { error: 'Suspension denied' } }))
    await page.getByRole('button', { name: 'Suspend account', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm suspend account', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('Suspension denied')
})

test('case actions include version, record hidden state and retain hold on closure', async ({ page }) => {
    let incident = { id: 1, target_type: 'player_profile', target_id: '321', status: 'open', hidden: false, version: 1, notification_state: 'none' }
    await mockControl(page, (url, request) => {
        if (request.method() === 'POST') {
            const body = request.postDataJSON()
            expect(body.version).toBe(incident.version)
            incident = { ...incident, status: body.action === 'close' ? 'closed' : 'investigating', hidden: true, version: incident.version + 1, notification_state: 'queued' }
            return { case: incident }
        }
        if (url.pathname.endsWith('/hidden')) return { programs: [], suppressions: [] }
        if (url.pathname === '/api/admin/safety/cases/1') return { case: incident, evidence: { statement: 'Test reported evidence' }, events: [] }
        return { ...empty, total: 1, rows: [incident], open_count: 1, overdue_count: 0, active_suppressions: 0, hidden_programs: 0 }
    })
    await page.goto('/admin/safety')
    await page.getByRole('button', { name: /Case 1/ }).click()
    await page.getByLabel('Reason for this case action').fill('Hide pending review')
    await page.getByRole('button', { name: 'Hide now', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm hide now', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Hidden while we review' })).toBeVisible()
    await page.getByLabel('Reason for this case action').fill('Review completed')
    await page.getByRole('button', { name: 'Close case', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm close case', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Hide now', exact: true })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Hidden while we review' })).toBeVisible()
})

test('business filters dates, keeps currencies separate and has read-only switches', async ({ page }) => {
    const dates = []
    await mockControl(page, url => {
        if (!url.pathname.endsWith('/summary')) return {}
        dates.push([url.searchParams.get('from'), url.searchParams.get('to')])
        return { ...empty, total: 1, currencies: { USD: { money_in_cents: 2000, refunds_cents: 0 }, EUR: { money_in_cents: 1000, refunds_cents: 250 } }, paying_clubs: 0, rows: [{ source: 'billing', id: 1, product_code: 'gol', kind: 'receipt', amount_cents: 2000, currency: 'USD', purchaser_user_id: 2, stripe_url: 'https://dashboard.stripe.com/payments/pi_test' }], freeze: { api_football: true, newsletters_configured: false, newsletters_effective: true }, changes: [], coverage: 'Recorded cash only.' }
    })
    await page.goto('/admin/business')
    await expect(page.getByText('USD money in')).toBeVisible()
    await expect(page.getByText('EUR refunds')).toBeVisible()
    await expect(page.getByRole('switch')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Refund', exact: true })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Review in Stripe' })).toHaveAttribute('href', 'https://dashboard.stripe.com/payments/pi_test')
    await page.getByLabel('From', { exact: true }).fill('2026-09-01')
    await page.getByLabel('To', { exact: true }).fill('2026-09-30')
    await expect.poll(() => dates.at(-1)).toEqual(['2026-09-01', '2026-09-30'])
})


test('destructive confirmations name target, warn last owner and cancel without writing', async ({ page }) => {
    const writes = []
    const person = { id: 2, display_name: 'Only Owner', email: 'owner@example.test', account_status: 'active', roles: ['club_owner'], programs: [], approved_claims: 0 }
    await mockControl(page, (url, request) => {
        if (request.method() === 'POST') writes.push(url.pathname)
        return url.pathname === '/api/admin/people/2' ? { person, last_owner_programs: ['Fixture FC'] } : { ...empty, total: 1, rows: [person] }
    })
    await page.goto('/admin/people')
    await page.getByRole('button', { name: /Only Owner/ }).click()
    await page.getByLabel('Reason for suspend account').fill('Pending review')
    await page.getByRole('button', { name: 'Suspend account', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText('Only Owner (owner@example.test)')
    await expect(dialog).toContainText('last active owner of Fixture FC')
    await expect(dialog).toContainText('Pending review')
    expect(writes).toEqual([])
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(writes).toEqual([])
})

test('search is bounded and debounced across fast typing', async ({ page }) => {
    const searches = []
    await mockControl(page, url => { if (url.pathname === '/api/admin/people') searches.push(url.searchParams.get('q')); return empty })
    await page.goto('/admin/people')
    const input = page.getByRole('textbox', { name: 'Search people' })
    await expect(input).toHaveAttribute('maxlength', '120')
    await input.fill('a'); await input.fill('ad'); await input.fill('admin')
    await expect.poll(() => searches.at(-1)).toBe('admin')
    expect(searches).not.toContain('a'); expect(searches).not.toContain('ad')
})

for (const width of [1440, 390]) {
    test(`correct-code account access offers cancellation export and deletion at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
        await page.route('**/api/**', async route => {
            const path = new URL(route.request().url()).pathname
            if (path === '/api/auth/request-code') return route.fulfill({ json: { message: 'Login code sent' } })
            if (path === '/api/auth/verify-code') return route.fulfill({ status: 403, json: { error: 'Sign-in unavailable. You can still manage your subscription and account.', account_access_token: 'fixture-limited-access' } })
            if (path === '/api/account/export') {
                expect(route.request().headers().authorization).toBe('Bearer fixture-limited-access')
                return route.fulfill({ json: { account: { display_name: 'Fixture Account' } } })
            }
            return route.fulfill({ json: {} })
        })
        await page.goto('/settings')
        if (width === 390) await page.getByRole('button', { name: 'Toggle navigation menu' }).click()
        await page.getByRole('button', { name: /^sign in$/i }).click()
        await page.getByLabel('Email', { exact: true }).fill('fixture@example.test')
        await page.getByRole('button', { name: 'Send login code' }).click()
        await page.getByLabel('Verification code').fill('valid-fixture')
        await page.getByRole('button', { name: 'Verify & sign in' }).click()
        await expect(page.getByRole('button', { name: 'Manage or cancel subscription' })).toBeVisible()
        await expect(page.getByRole('button', { name: 'Delete my account' })).toBeVisible()
        await expect(page.getByRole('button', { name: 'Delete my account' })).toBeDisabled()
        const download = page.waitForEvent('download')
        await page.getByRole('button', { name: 'Export my data' }).click()
        expect((await download).suggestedFilename()).toBe('academy-watch-account.json')
        await expect(page.getByText('Your account export has been downloaded.')).toBeVisible()
        if (process.env.B3_SHOTS_DIR) await page.screenshot({ path: `${process.env.B3_SHOTS_DIR}/account-access-${width === 390 ? 'mobile' : 'desktop'}.png`, fullPage: true })
    })
}


test('a report cannot restore another requester hold and keeps original evidence visible', async ({ page }) => {
    const incident = { id: 4, target_type: 'player_profile', target_id: '321', status: 'investigating', hidden: true, owns_hold: false, version: 2, notification_state: 'queued' }
    await mockControl(page, url => {
        if (url.pathname.endsWith('/hidden')) return { programs: [], suppressions: [] }
        if (url.pathname === '/api/admin/safety/cases/4') return { case: incident, evidence: { statement: 'Guardian original evidence' }, events: [{ id: 1, action: 'hide', reason: 'Separate admin review' }] }
        return { ...empty, total: 1, rows: [incident], open_count: 1, overdue_count: 0, active_suppressions: 1, hidden_programs: 0 }
    })
    await page.goto('/admin/safety')
    await page.getByRole('button', { name: /Case 4/ }).click()
    await expect(page.getByText('Guardian original evidence', { exact: true })).toBeVisible()
    await expect(page.getByText('Separate admin review', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Restore case hold', exact: true })).toHaveCount(0)
    await expect(page.getByText(/Another moderation decision owns this hold/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Open existing report moderation' })).toBeVisible()
})

for (const width of [1440, 390]) {
    test(`hidden inventory pages each complete collection independently at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
        const reads = []
        await mockControl(page, url => {
            if (url.pathname.endsWith('/hidden')) {
                const programOffset = Number(url.searchParams.get('program_offset') || 0)
                const suppressionOffset = Number(url.searchParams.get('suppression_offset') || 0)
                reads.push([programOffset, suppressionOffset])
                const all = Array.from({ length: 35 }, (_, i) => i + 1)
                return { limit: 30, program_offset: programOffset, suppression_offset: suppressionOffset,
                    program_total: 35, suppression_total: 35,
                    program_has_more: programOffset === 0, suppression_has_more: suppressionOffset === 0,
                    programs: all.slice(programOffset, programOffset + 30).map(id => ({ id, name: `Fixture Club ${id}` })),
                    suppressions: all.slice(suppressionOffset, suppressionOffset + 30).map(id => ({ id, player_api_id: 1000 + id })) }
            }
            return { ...empty, open_count: 0, overdue_count: 0, active_suppressions: 35, hidden_programs: 35 }
        })
        await page.goto('/admin/safety')
        const players = page.getByRole('region', { name: 'Player suppressions inventory' })
        const clubs = page.getByRole('region', { name: 'Club holds inventory' })
        await expect(players).toContainText('35 total')
        await expect(clubs).toContainText('35 total')
        await players.getByRole('button', { name: 'Next', exact: true }).click()
        await expect(players.getByText('Player 1035', { exact: true })).toBeVisible()
        await expect(players.getByRole('button', { name: 'Next', exact: true })).toBeDisabled()
        await expect(clubs.getByText('Fixture Club 1', { exact: true })).toBeVisible()
        await clubs.getByRole('button', { name: 'Next', exact: true }).click()
        await expect(clubs.getByText('Fixture Club 35', { exact: true })).toBeVisible()
        expect(reads).toContainEqual([0, 30])
        expect(reads).toContainEqual([30, 30])
        expect(await page.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.innerWidth)).toBe(true)
        if (process.env.B3F5_SHOT_DIR) {
            await page.evaluate(() => globalThis.scrollTo(0, 0))
            await page.screenshot({ path: `${process.env.B3F5_SHOT_DIR}/inventory-${width}.png`, fullPage: true, animations: 'disabled' })
        }
    })
    test(`restore case hold requires named confirmation and cancel never writes at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
        const writes = []
        let incident = { id: 1, target_type: 'player_profile', target_id: '321', status: 'closed', hidden: true, owns_hold: true, hold_requested: true, version: 3, notification_state: 'none' }
        await mockControl(page, (url, request) => {
            if (request.method() === 'POST') {
                writes.push(request.postDataJSON())
                incident = { ...incident, hidden: false, owns_hold: false, hold_requested: false, version: 4 }
                return { case: incident }
            }
            if (url.pathname.endsWith('/hidden')) return { programs: [], suppressions: [], limit: 30, program_total: 0, suppression_total: 0 }
            if (url.pathname === '/api/admin/safety/cases/1') return { case: incident, evidence: { statement: 'Synthetic case evidence' }, events: [] }
            return { ...empty, total: 1, rows: [incident], open_count: 0, overdue_count: 0, active_suppressions: 1, hidden_programs: 0 }
        })
        await page.goto('/admin/safety')
        await page.getByRole('button', { name: /Case 1/ }).click()
        await page.getByLabel('Reason to restore the case hold').fill('Review complete')
        await page.getByRole('button', { name: 'Restore case hold', exact: true }).click()
        const dialog = page.getByRole('dialog')
        await expect(dialog).toContainText('case 1 · player_profile 321')
        await expect(dialog).toContainText('Review complete')
        expect(writes).toEqual([])
        if (process.env.B3F5_SHOT_DIR) await page.screenshot({ path: `${process.env.B3F5_SHOT_DIR}/restore-confirm-${width}.png`, animations: 'disabled' })
        await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
        expect(writes).toEqual([])
        await page.getByRole('button', { name: 'Restore case hold', exact: true }).click()
        await page.getByRole('button', { name: 'Confirm restore case hold', exact: true }).click()
        await expect.poll(() => writes).toEqual([{ action: 'restore', reason: 'Review complete', version: 3 }])
        await expect(page.getByRole('heading', { name: 'Review the request' })).toBeVisible()
    })
}
