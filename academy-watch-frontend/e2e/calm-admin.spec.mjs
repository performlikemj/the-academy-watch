// Calm admin area + the shared filter bar. Every API call is answered by
// e2e/fixtures/calm-admin.mjs, which filters lists the way the server does.
// CALM1_SHOT_DIR=<dir> also writes the proof screenshots (after/…).
import process from 'node:process'
import { expect, test } from '@playwright/test'
import { CLAIMS, LONG_NAME, mockCalmAdmin } from './fixtures/calm-admin.mjs'

const shotDir = process.env.CALM1_SHOT_DIR
const sizes = [[1440, 900], [390, 844]]
const fits = page => page.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.innerWidth)

async function shot(page, name) {
    if (!shotDir) return
    await page.waitForTimeout(350)
    await page.screenshot({ path: `${shotDir}/after/${name}-${page.viewportSize().width}.png`, fullPage: true, animations: 'disabled' })
}

async function noPageNoise(page) {
    // Calm rules 1 and 7: one sans title, no serif display headline, no mono ALL-CAPS labels.
    const main = page.locator('main').last()
    await expect(main.locator('h1')).toHaveCount(1)
    expect(await main.locator('h1').evaluate(node => getComputedStyle(node).fontFamily)).toMatch(/Geist/)
    expect(await main.locator('.display, .eyebrow').count()).toBe(0)
    const shouting = await main.evaluate(node => [...node.querySelectorAll('*')].filter(el => el.children.length === 0 && el.textContent.trim()
        && getComputedStyle(el).textTransform === 'uppercase' && /Mono/.test(getComputedStyle(el).fontFamily)).length)
    expect(shouting).toBe(0)
}

for (const [width, height] of sizes) {
    test.describe(`${width}px`, () => {
        test.beforeEach(async ({ page }) => { await page.setViewportSize({ width, height }) })

        test('Today lists only what is waiting, then says the rest is clear', async ({ page }) => {
            await mockCalmAdmin(page)
            await page.goto('/admin/dashboard')
            const queue = page.getByTestId('inbox-pending')
            await expect(page.getByRole('heading', { level: 1, name: 'Today' })).toBeVisible()
            // The one waiting club and the one waiting scout are named; every row is a queue with something in it.
            await expect(queue.getByRole('link', { name: /Milo Strand asks to be a verified scout/ })).toContainText('Regional scout · Northfen Scouting Collective')
            await expect(queue.getByRole('link', { name: /3 clubs want to be verified/ })).toHaveAttribute('href', '/admin/funding?tab=claims')
            await expect(queue.getByRole('link', { name: /3 safety reports waiting/ })).toHaveAttribute('href', '/admin/trust?tab=reports')
            await expect(queue.getByRole('link', { name: /2 club page edits to approve/ })).toHaveAttribute('href', '/admin/funding?tab=content')
            await expect(queue.getByRole('link', { name: /1 subscription is past due/ })).toHaveAttribute('href', '/admin/business')
            await expect(queue.getByRole('listitem')).toHaveCount(6)
            for (const hidden of ['Manual players', 'manually added', 'Quick takes', 'tracking request']) await expect(queue).not.toContainText(hidden)
            await expect(page.getByTestId('today-clear')).toHaveText('Everything else is clear. 8 other queues have nothing waiting.')
            const numbers = page.getByTestId('today-numbers')
            for (const [label, value] of [['Tracked players', '1,284'], ['Clubs', '5'], ['Verified scouts', '7'], ['Monthly recurring revenue', '£116.00']]) {
                await expect(numbers.locator('div', { hasText: label }).last()).toBeVisible()
                await expect(numbers).toContainText(value)
            }
            await noPageNoise(page)
            expect(await fits(page)).toBe(true)
            await shot(page, 'today')
            // The detail is one click away, not on the page.
            await expect(page.getByTestId('ops-tile-active')).toBeHidden()
            await page.getByText('Data health').click()
            await expect(page.getByTestId('ops-tile-active')).toContainText('1,245')
        })

        test('Today with nothing waiting and a number without a source', async ({ page }) => {
            await mockCalmAdmin(page, { quiet: true, handler: url => url.pathname === '/api/admin/dashboard-stats' ? { status: 503, json: { error: 'unavailable' } } : undefined })
            await page.goto('/admin/dashboard')
            await expect(page.getByTestId('today-clear')).toHaveText('Nothing is waiting. All 13 queues are clear.')
            await expect(page.getByTestId('inbox-pending').getByRole('listitem')).toHaveCount(0)
            // A number with no answer is left out, never shown as zero.
            await expect(page.getByTestId('today-numbers')).not.toContainText('Tracked players')
            await expect(page.getByTestId('today-numbers')).toContainText('Verified scouts')
            await shot(page, 'today-clear')
        })

        test('club approval leads with the answer and the one gap', async ({ page }) => {
            const posts = []
            await mockCalmAdmin(page, { handler: (url, request) => { if (request.method() === 'POST') { posts.push([url.pathname, request.postDataJSON()]); return {} } } })
            await page.goto('/admin/funding?tab=claims')
            const list = page.getByRole('tabpanel')
            await expect(list.getByRole('button', { name: /Pellowick Town/ })).toContainText('10 of 11 checks pass · missing payout control')
            await expect(list.getByRole('button', { name: /Thrandby Wrens/ })).toContainText('11 of 11 checks pass')
            await expect(page.getByText('Club content to approve')).toHaveCount(0)
            expect(await fits(page)).toBe(true)
            await shot(page, 'approval-list')

            await list.getByRole('button', { name: /Pellowick Town/ }).click()
            await expect(page).toHaveURL(/tab=claims&claim=31/)
            await expect(page.getByRole('heading', { level: 1, name: 'Pellowick Town' })).toBeVisible()
            await expect(page.getByText('Wants to be a verified club · Wendle & District Senior League · Wendleshire, England')).toBeVisible()
            const decision = page.getByRole('region', { name: 'Decision' })
            await expect(decision).toContainText('10 of 11 checks pass')
            await expect(decision).toContainText('Missing: payout control — not attested')
            // The server refuses an approval below the bar, so the page does not offer one.
            await expect(decision.getByRole('button', { name: 'Approve' })).toBeDisabled()
            await expect(decision.getByRole('button', { name: 'Reject' })).toBeEnabled()
            await expect(page.getByRole('button', { name: /Ask for/ })).toHaveCount(0)
            // Groups are collapsed; the one with a failure starts open.
            const checks = page.getByRole('region', { name: 'Checks' })
            await expect(checks.locator('details[open]')).toHaveCount(1)
            await expect(checks.locator('details[open] summary')).toContainText('Money · 1 of 2 pass')
            await expect(checks.getByText('Organisation form · Unincorporated association')).toBeHidden()
            await noPageNoise(page)
            expect(await fits(page)).toBe(true)
            await shot(page, 'approval-one-missing')

            await page.goBack()
            await page.getByRole('tabpanel').getByRole('button', { name: /Thrandby Wrens/ }).click()
            const ready = page.getByRole('region', { name: 'Decision' })
            await expect(ready).toContainText('11 of 11 checks pass')
            await expect(ready).toContainText('Nothing is missing')
            await expect(page.getByRole('region', { name: 'Checks' }).locator('details[open]')).toHaveCount(0)
            await shot(page, 'approval-all-pass')
            await ready.getByRole('button', { name: 'Approve' }).click()
            await page.getByLabel('Review reason').fill('Evidence checked against the county register')
            await page.getByRole('button', { name: 'Approve claim' }).click()
            await expect.poll(() => posts).toEqual([['/api/admin/funding/claims/32/approve', { reason: 'Evidence checked against the county register' }]])
            await expect(page.getByRole('status').filter({ hasText: 'Claim approved' })).toBeVisible()
        })

        test('a long club name and several gaps stay inside the approval page', async ({ page }) => {
            await mockCalmAdmin(page)
            await page.goto('/admin/funding?tab=claims&claim=34')
            await expect(page.getByRole('heading', { level: 1 })).toContainText(LONG_NAME)
            await expect(page.getByRole('region', { name: 'Decision' })).toContainText('8 of 11 checks pass')
            await expect(page.getByRole('region', { name: 'Checks' }).locator('details[open]')).toHaveCount(3)
            expect(await fits(page)).toBe(true)
            await shot(page, 'approval-long-name')
        })

        test('content review has its own tab, off the approval view', async ({ page }) => {
            await mockCalmAdmin(page)
            await page.goto('/admin/funding?tab=content')
            await expect(page.getByRole('tab', { name: 'Content review' })).toHaveAttribute('aria-selected', 'true')
            await expect(page.getByText('Club content to approve')).toBeVisible()
            await expect(page.getByRole('heading', { name: 'Pellowick Town' })).toBeVisible()
            expect(await fits(page)).toBe(true)
        })

        test('People: every filter is answered by the server and lives in the address', async ({ page }) => {
            const asked = []
            await mockCalmAdmin(page, { onRequest: url => { if (url.pathname === '/api/admin/people') asked.push(url.search) } })
            await page.goto('/admin/people')
            const bar = page.getByRole('group', { name: 'People filters' })
            const count = page.getByTestId('filter-count')
            const accounts = page.getByRole('region', { name: 'Accounts' })
            await expect(count).toHaveText('8 people')
            await expect(bar.getByRole('button', { name: 'Clear', exact: true })).toHaveCount(0)
            await shot(page, 'people')

            // Club: a list you can type into, with a count per club and "No club".
            await bar.getByRole('button', { name: /^Club: All clubs/ }).click()
            const clubs = page.getByRole('listbox', { name: 'Club' })
            await expect(clubs.getByRole('option', { name: /Quillmere Athletic/ })).toContainText('2')
            await expect(clubs.getByRole('option', { name: /No club/ })).toContainText('5')
            await shot(page, 'people-club-filter-open')
            await page.getByPlaceholder('Type a club name…').fill('quill')
            await expect(clubs.getByRole('option', { name: /Thrandby Wrens/ })).toHaveCount(0)
            await clubs.getByRole('option', { name: /Quillmere Athletic/ }).click()
            await expect(page).toHaveURL(/[?&]club=1(&|$)/)
            await expect(count).toHaveText('2 people')
            await expect(bar.getByRole('button', { name: /^Club: Quillmere Athletic/ })).toBeVisible()

            await bar.getByRole('button', { name: /^Type: Everyone/ }).click()
            await page.getByRole('option', { name: 'Club staff' }).click()
            await bar.getByRole('button', { name: /^Status: Any/ }).click()
            await page.getByRole('option', { name: 'Active', exact: true }).click()
            await bar.getByRole('button', { name: /^More/ }).click()
            await page.getByRole('listbox', { name: 'Joined' }).getByRole('option', { name: 'In the last year' }).click()
            await page.getByRole('listbox', { name: 'Last seen' }).getByRole('option', { name: 'In the last 7 days' }).click()
            await page.keyboard.press('Escape')
            await expect(bar.getByRole('button', { name: /^More: Joined, Last seen/ })).toBeVisible()
            await expect(page).toHaveURL(/club=1.*role=clubs.*standing=active.*joined=year.*seen=7d/)
            expect(asked.at(-1)).toContain('club=1')
            expect(asked.at(-1)).toContain('role=clubs')
            expect(asked.at(-1)).toContain('standing=active')
            expect(asked.at(-1)).toContain('joined=year')
            expect(asked.at(-1)).toContain('seen=7d')
            await expect(count).toHaveText('2 people')
            await expect(accounts.getByRole('button', { name: /Idris Penhallow/ })).toContainText('Club manager · Quillmere Athletic')
            expect(await fits(page)).toBe(true)
            await shot(page, 'people-every-filter')

            // A reload and a shared link show the same list; back walks the filters one at a time.
            await page.reload()
            await expect(count).toHaveText('2 people')
            await expect(bar.getByRole('button', { name: /^Club: Quillmere Athletic/ })).toBeVisible()
            await page.goBack()
            await expect(page).not.toHaveURL(/seen=7d/)
            await expect(page).toHaveURL(/joined=year/)

            // ✕ clears one filter; Clear resets them all.
            await bar.getByRole('button', { name: 'Clear Type' }).click()
            await expect(page).not.toHaveURL(/role=/)
            await bar.getByRole('button', { name: 'Clear', exact: true }).click()
            await expect(page).toHaveURL(/\/admin\/people$/)
            await expect(count).toHaveText('8 people')
        })

        test('People: zero results, search, and the slim detail panel', async ({ page }) => {
            await mockCalmAdmin(page)
            await page.goto('/admin/people?club=2&standing=suspended')
            await expect(page.getByTestId('filter-count')).toHaveText('0 people')
            await expect(page.getByText('No accounts match this search.')).toBeVisible()
            await expect(page.getByRole('group', { name: 'People filters' }).getByRole('button', { name: /^Club: Thrandby Wrens/ })).toBeVisible()
            expect(await fits(page)).toBe(true)
            await shot(page, 'people-zero-results')

            await page.goto('/admin/people?standing=waiting')
            await expect(page.getByRole('region', { name: 'Accounts' }).getByRole('button', { name: /Milo Strand/ })).toContainText('Waiting for approval')
            await expect(page.getByTestId('filter-count')).toHaveText('1 person')

            await page.goto('/admin/people')
            await page.getByRole('searchbox', { name: 'Search people' }).fill('pete')
            await expect(page).toHaveURL(/q=pete/)
            await page.getByRole('button', { name: /Pete Dunmore/ }).click()
            await expect(page).toHaveURL(/person=15/)
            const panel = page.getByRole('complementary', { name: 'Account details' })
            const name = panel.getByRole('heading', { name: 'Pete Dunmore' })
            await expect(name).toBeVisible()
            expect(await name.evaluate(node => getComputedStyle(node).fontSize)).toBe('20px')
            await expect(panel.getByText('Suspension reason')).toBeVisible()
            await expect(panel).toContainText('Repeated abusive messages')
            await expect(panel).toContainText(/\d{1,2} \w{3} \d{4}, \d{2}:\d{2}/)
            await expect(panel.getByRole('button', { name: 'Restore…' })).toBeVisible()
            await noPageNoise(page)
            expect(await fits(page)).toBe(true)
            await shot(page, 'people-detail-suspended')

            await page.goto('/admin/people?person=11')
            const active = page.getByRole('complementary', { name: 'Account details' })
            await expect(active.getByRole('button', { name: 'Suspend…' })).toBeVisible()
            await expect(active.getByRole('link', { name: 'Writer permissions' })).toBeHidden()
            await active.getByLabel('More actions').click()
            await expect(active.getByRole('link', { name: 'Writer permissions' })).toHaveAttribute('href', '/admin/users')
            await shot(page, 'people-detail')
        })

        test('People: long names wrap and a slow answer does not move the page', async ({ page }) => {
            let release
            const gate = new Promise(resolve => { release = resolve })
            let slow = false
            await mockCalmAdmin(page, { hold: url => slow && url.pathname === '/api/admin/people' ? gate : undefined })
            await page.goto('/admin/people?joined=7d')
            await expect(page.getByRole('button', { name: new RegExp(LONG_NAME) })).toBeVisible()
            expect(await fits(page)).toBe(true)
            await shot(page, 'people-long-names')

            await page.goto('/admin/people')
            const count = page.getByTestId('filter-count')
            await expect(count).toHaveText('8 people')
            const list = page.getByRole('region', { name: 'Accounts' })
            slow = true
            await page.getByRole('group', { name: 'People filters' }).getByRole('button', { name: /^Status: Any/ }).click()
            await page.getByRole('option', { name: 'Suspended' }).click()
            // While the answer is on its way the old count and rows stay where they are …
            await expect(list).toHaveAttribute('aria-busy', 'true')
            await expect(count).toHaveText('8 people')
            await expect(list.getByRole('listitem')).toHaveCount(8)
            const during = await list.boundingBox()
            await shot(page, 'people-loading')
            release()
            await expect(count).toHaveText('1 person')
            // … and the new answer lands in the same place: no spinner swap, no jump.
            const after = await list.boundingBox()
            expect([after.x, after.y]).toEqual([during.x, during.y])
        })

        test('Clubs: status, verified and country filters with counts', async ({ page }) => {
            const asked = []
            await mockCalmAdmin(page, { onRequest: url => { if (url.pathname === '/api/admin/programs') asked.push(url.search) } })
            await page.goto('/admin/programs')
            await expect(page.getByRole('heading', { level: 1, name: 'Clubs' })).toBeVisible()
            const bar = page.getByRole('group', { name: 'Club filters' })
            const count = page.getByTestId('filter-count')
            await expect(count).toHaveText('5 clubs')
            await expect(page.getByRole('button', { name: new RegExp(LONG_NAME) })).toBeVisible()
            await noPageNoise(page)
            expect(await fits(page)).toBe(true)
            await shot(page, 'clubs')

            await bar.getByRole('button', { name: /^Country: Anywhere/ }).click()
            await expect(page.getByRole('option', { name: /England/ })).toContainText('3')
            await page.getByRole('option', { name: /England/ }).click()
            await bar.getByRole('button', { name: /^Status: Any/ }).click()
            await page.getByRole('option', { name: 'Approved', exact: true }).click()
            await bar.getByRole('button', { name: /^Verified: Any/ }).click()
            await page.getByRole('option', { name: 'Verified', exact: true }).click()
            await expect(page).toHaveURL(/country=England.*status=approved.*verified=yes/)
            await expect(count).toHaveText('1 club')
            expect(asked.at(-1)).toContain('country=England')
            expect(asked.at(-1)).toContain('status=approved')
            expect(asked.at(-1)).toContain('verified=yes')
            await page.getByRole('button', { name: /Quillmere Athletic/ }).click()
            const panel = page.getByRole('complementary', { name: 'Club details' })
            await expect(panel.getByRole('heading', { name: 'Quillmere Athletic' })).toBeVisible()
            expect(await fits(page)).toBe(true)
            await shot(page, 'clubs-every-filter')

            await page.goto('/admin/programs?status=rejected')
            await expect(count).toHaveText('0 clubs')
            await expect(page.getByText('No clubs match this search.')).toBeVisible()
            await shot(page, 'clubs-zero-results')
        })

        test('flags off: the list pages stay dark and Today asks only what it asked before', async ({ page }) => {
            const asked = []
            await mockCalmAdmin(page, { flags: {}, onRequest: url => asked.push(url.pathname) })
            await page.goto('/admin/people?club=1')
            await expect(page.getByRole('heading', { name: 'Page unavailable' })).toBeVisible()
            await page.goto('/admin/programs')
            await expect(page.getByRole('heading', { name: 'Page unavailable' })).toBeVisible()
            await page.goto('/admin/dashboard')
            await expect(page.getByTestId('inbox-pending').getByRole('link', { name: /2 community takes to review/ })).toHaveAttribute('href', '/admin/inbox?tab=takes')
            await expect(page.getByTestId('today-numbers')).toContainText('Tracked teams')
            await expect(page.getByTestId('revenue-summary')).toContainText('£116.00')
            expect(asked.filter(path => /\/admin\/(control|business|people|programs)/.test(path))).toEqual([])
            await shot(page, 'today-flags-off')
        })
    })
}

test('the fixture claims cover one gap, none and several', () => {
    expect(CLAIMS.filter(claim => claim.status === 'pending')).toHaveLength(3)
})
