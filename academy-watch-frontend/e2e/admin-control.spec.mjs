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
    await expect(page.getByText('Emergency hidden', { exact: true })).toBeVisible()
    await page.getByLabel('Assign owner', { exact: true }).selectOption('2')
    await page.getByLabel('Reason for assign owner').fill('Explicit assignment')
    await page.getByRole('button', { name: 'Assign owner', exact: true }).click()
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
    await expect(page.getByRole('heading', { name: 'Hidden while we review' })).toBeVisible()
    await page.getByLabel('Reason for this case action').fill('Review completed')
    await page.getByRole('button', { name: 'Close case', exact: true }).click()
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
