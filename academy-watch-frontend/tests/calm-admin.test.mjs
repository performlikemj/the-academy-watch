import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { clearLine, todayRows } from '../src/lib/admin-today.js'
import { clubCheckLine, clubCheckSummary, leagueOpen } from '../src/lib/club-checks.js'
import { clearableKeys, countLabel, nextFilterParams, pillText, readFilters } from '../src/lib/url-filters.js'

const full = {
    adult_authority_attested: true, authorization_method: 'signed_officer_authorization', authorization_reference: 'Signed 2026',
    official_email: '', organization_form: 'charity', registration_reference: 'REG-1', official_contact_name: 'A Person',
    official_contact_reference: 'Directory', safeguarding_contact_email: 'welfare@example.test', safeguarding_policy_url: '',
    safeguarding_policy_attested: true, eligible_organization_attested: true, payout_control_attested: true,
}

// Mirrors routes/funding.py `_evidence_meets_bar`: `complete` must agree with what the server will approve.
function serverBar(e) {
    const authorised = (e.authorization_method === 'official_domain_email' && e.official_email) || (e.authorization_method === 'signed_officer_authorization' && e.authorization_reference)
    return Boolean(e.adult_authority_attested && authorised && e.organization_form && e.registration_reference && e.official_contact_name
        && e.official_contact_reference && e.safeguarding_contact_email && e.safeguarding_policy_attested && e.eligible_organization_attested && e.payout_control_attested)
}

test('club checks: complete agrees with the server bar for every single gap', () => {
    assert.equal(clubCheckSummary(full).complete, true)
    assert.equal(clubCheckLine(clubCheckSummary(full)), '11 of 11 checks pass')
    for (const key of Object.keys(full)) {
        const gap = { ...full, [key]: typeof full[key] === 'boolean' ? false : '' }
        assert.equal(clubCheckSummary(gap).complete, serverBar(gap), key)
    }
    for (const route of ['official_domain_email', 'signed_officer_authorization', 'something_else', null]) {
        for (const email of ['', 'a@b.example']) for (const reference of ['', 'Signed']) {
            const evidence = { ...full, authorization_method: route, official_email: email, authorization_reference: reference }
            assert.equal(clubCheckSummary(evidence).complete, serverBar(evidence), `${route}/${email}/${reference}`)
        }
    }
    assert.equal(clubCheckSummary(null).complete, false)
})

test('club checks: the gap is named, optional proof is never counted', () => {
    const summary = clubCheckSummary({ ...full, payout_control_attested: false })
    assert.equal(clubCheckLine(summary), '10 of 11 checks pass · missing payout control')
    assert.deepEqual(summary.groups.filter(group => group.failing).map(group => group.title), ['Money'])
    assert.equal(summary.groups.find(group => group.key === 'safeguarding').total, 2)
    const several = clubCheckSummary({ ...full, payout_control_attested: false, registration_reference: '', official_contact_name: '' })
    assert.equal(clubCheckLine(several), '8 of 11 checks pass · missing registration, official contact and 1 more')
    assert.equal(leagueOpen({ registry_status: 'approved', admission_state: 'open' }), true)
    assert.equal(leagueOpen({ registry_status: 'proposed', admission_state: 'open' }), false)
})

test('today: zero queues are counted, never listed; safety leads', () => {
    const queues = [
        { key: 'takes', label: 'Community takes', href: '/admin/inbox?tab=takes', count: 0 },
        { key: 'club_profiles', label: 'Club profile revisions', href: '/admin/funding?tab=content', count: 2 },
        { key: 'reports', label: 'Open reports', href: '/admin/trust?tab=reports', count: 1 },
        { key: 'future_queue', label: 'Brand new things', href: '/admin/new', count: 4 },
    ]
    const today = todayRows({ queues })
    assert.deepEqual(today.rows.map(row => [row.key, row.title, row.area]), [
        ['reports', '1 safety report waiting', 'Safety'],
        ['club_profiles', '2 club page edits to approve', 'Content'],
        ['future_queue', '4 brand new things waiting', 'Review'],
    ])
    assert.equal(clearLine(today), 'Everything else is clear. 1 other queue has nothing waiting.')
    const quiet = todayRows({ queues: queues.map(queue => ({ ...queue, count: 0 })) })
    assert.deepEqual(quiet.rows, [])
    assert.equal(clearLine(quiet), 'Nothing is waiting. All 4 queues are clear.')
    assert.equal(clearLine(todayRows({ queues: [queues[2]] })), null)
})

test('today: a waiting club and scout are named, and never counted twice', () => {
    const claims = [{ id: 9, program: { name: 'Example Town' }, evidence: { ...full, payout_control_attested: false } }]
    const scouts = { total: 1, rows: [{ full_name: 'Sam Example', role_title: 'Scout', organization: 'Example Scouting' }] }
    const counted = [{ key: 'club_claims', href: '/admin/funding?tab=claims', count: 1 }, { key: 'scout_verifications', href: '/admin/trust?tab=verifications', count: 1 }]
    for (const queues of [counted, []]) {
        const { rows } = todayRows({ queues, claims, scouts })
        assert.deepEqual(rows.map(row => [row.title, row.summary, row.href]), [
            ['Example Town wants to be a verified club', '10 of 11 checks pass · missing payout control', '/admin/funding?tab=claims&claim=9'],
            ['Sam Example asks to be a verified scout', 'Scout · Example Scouting', '/admin/trust?tab=verifications'],
        ])
    }
    assert.deepEqual(todayRows({ queues: [], claims: [], scouts: { total: 0, rows: [] } }), { rows: [], clear: 2, counted: 2 })
    const money = todayRows({ revenue: { past_due: 2, webhook_failed_last_24h: 0 }, ops: { tracked: { placeholder_names: 3, owning_club_active: 0 } }, businessHref: '/admin/business' })
    assert.deepEqual(money.rows.map(row => [row.title, row.href]), [['2 subscriptions are past due', '/admin/business'], ['3 players have placeholder names', '/admin/operations']])
})

test('filters: defaults stay out of the address, everything else round-trips', () => {
    const defaults = { q: '', role: 'all', sort: 'name', club: '' }
    let params = nextFilterParams(new URLSearchParams('tab=people'), { role: 'clubs', club: 3, sort: 'name', q: '' }, defaults)
    assert.equal(params.toString(), 'tab=people&role=clubs&club=3')
    assert.deepEqual(readFilters(params, defaults), { q: '', role: 'clubs', sort: 'name', club: '3' })
    params = nextFilterParams(params, { role: 'all', club: '' }, defaults)
    assert.equal(params.toString(), 'tab=people')
})

test('filters: pill text, what Clear resets, and the count words', () => {
    const club = { key: 'club', label: 'Club', anyLabel: 'All clubs', selectedLabel: 'Example Town' }
    const type = { key: 'role', label: 'Type', anyLabel: 'Everyone', defaultValue: 'all', options: [{ value: 'clubs', label: 'Club staff' }] }
    const sort = { key: 'sort', label: 'Sort', neutral: true, defaultValue: 'name', options: [{ value: 'name', label: 'Name A–Z' }, { value: 'newest', label: 'Newest first' }] }
    const more = { key: 'more', label: 'More', group: [{ key: 'verified', label: 'Verified', options: [{ value: 'yes', label: 'Verified scout' }] }, { key: 'joined', label: 'Joined', options: [] }] }
    const values = { club: '7', role: 'all', sort: 'newest', verified: 'yes', joined: '' }
    assert.equal(pillText(club, values), 'Club: Example Town')
    assert.equal(pillText(type, values), 'Type: Everyone')
    assert.equal(pillText(type, { role: 'clubs' }), 'Type: Club staff')
    assert.equal(pillText(sort, values), 'Sort: Newest first')
    assert.equal(pillText(sort, { sort: 'name' }), 'Sort: Name A–Z')
    assert.equal(pillText(more, values), 'More: Verified')
    assert.equal(pillText(more, {}), 'More')
    assert.deepEqual(clearableKeys([club, type, more, sort], values), ['club', 'verified'])
    assert.equal(countLabel(1, 'person', 'people'), '1 person')
    assert.equal(countLabel(1234, 'person', 'people'), '1,234 people')
    assert.equal(countLabel(undefined, 'person', 'people'), '')
})

test('the calm admin pages keep to the house rules in source', async () => {
    for (const file of ['pages/admin/AdminDashboard.jsx', 'pages/admin/AdminPeople.jsx', 'pages/admin/AdminPrograms.jsx', 'components/filter/FilterBar.jsx']) {
        const source = await fs.readFile(new URL(`../src/${file}`, import.meta.url), 'utf8')
        const broken = source.match(/font-mono|\beyebrow\b|className="[^"]*\bdisplay\b|AdminPageHeader|new Date\([^)]*\)\.toLocaleString\(\)/)
        assert.equal(broken, null, `${file}: ${broken?.[0]}`)
    }
    // One filter bar: pages filter by asking the server, never by trimming the rows they hold.
    for (const file of ['pages/admin/AdminPeople.jsx', 'pages/admin/AdminPrograms.jsx']) {
        const source = await fs.readFile(new URL(`../src/${file}`, import.meta.url), 'utf8')
        assert.match(source, /<FilterBar/, file)
        assert.doesNotMatch(source, /rows\.filter\(/, file)
    }
})
