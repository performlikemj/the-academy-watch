// Synthetic control-room data for the calm admin specs. Every name is invented.
// The handler answers the list filters the way the server does, so a filtered
// screen in a spec is a filtered answer, not a client-side trim.

export const ALL_FLAGS = { admin_programs: true, admin_people: true, admin_safety: true, admin_business: true }

export const LONG_NAME = 'Bartholomew-Maximilian-Featherstonehaugh-Cholmondeley-Warburton-Montgomery-Fitzgerald-Beauchamp-Marjoribanks-Wriothesley'

const CLUBS = [
    { id: 1, name: 'Quillmere Athletic', slug: 'quillmere-athletic', city: 'Quillmere', region: 'Wendleshire', country: 'England', platform_status: 'approved', emergency_hidden: false, verified_at: '2026-08-14T10:00:00Z', origin: 'local', players: 24, managers: 2, matches: 9, claims_pending: 0 },
    { id: 2, name: 'Thrandby Wrens', slug: 'thrandby-wrens', city: 'Thrandby', region: 'Wendleshire', country: 'England', platform_status: 'approved', emergency_hidden: false, verified_at: null, origin: 'local', players: 17, managers: 1, matches: 4, claims_pending: 1 },
    { id: 3, name: 'Pellowick Town', slug: 'pellowick-town', city: 'Pellowick', region: 'Wendleshire', country: 'England', platform_status: 'pending', emergency_hidden: false, verified_at: null, origin: 'local', players: 0, managers: 0, matches: 0, claims_pending: 1 },
    { id: 4, name: 'Strathlorne Rovers', slug: 'strathlorne-rovers', city: 'Strathlorne', region: 'Lothian', country: 'Scotland', platform_status: 'approved', emergency_hidden: true, verified_at: '2026-07-02T09:00:00Z', origin: 'local', players: 31, managers: 1, matches: 12, claims_pending: 0 },
    { id: 5, name: `${LONG_NAME} Football Club`, slug: 'long-name-fc', city: 'Abertawe', region: 'Glamorgan', country: 'Wales', platform_status: 'suspended', emergency_hidden: false, verified_at: null, origin: 'local', players: 3, managers: 0, matches: 0, claims_pending: 0 },
]

const daysAgo = days => new Date(Date.now() - days * 86400000).toISOString()

const PEOPLE = [
    { id: 11, display_name: 'Idris Penhallow', email: 'idris@quillmere.example', account_status: 'active', roles: ['club_manager'], clubs: [1], kind: ['clubs'], created_at: daysAgo(210), last_login_at: daysAgo(1) },
    { id: 12, display_name: 'Ruth Calloway', email: 'ruth@quillmere.example', account_status: 'active', roles: ['club_manager', 'club_owner'], clubs: [1], kind: ['clubs'], created_at: daysAgo(300), last_login_at: daysAgo(3) },
    { id: 13, display_name: 'Milo Strand', email: 'milo@northfen.example', account_status: 'active', roles: ['scout_pending'], clubs: [], kind: ['scouts'], waiting: true, created_at: daysAgo(4), last_login_at: daysAgo(0), scout_verification: { id: 5, status: 'pending' } },
    { id: 14, display_name: 'Odette Farrow', email: 'odette@scouting.example', account_status: 'active', roles: ['verified_scout'], clubs: [], kind: ['scouts'], verified: true, created_at: daysAgo(120), last_login_at: daysAgo(12), scout_verification: { id: 6, status: 'approved' } },
    { id: 15, display_name: 'Pete Dunmore', email: 'pete@example.test', account_status: 'suspended', roles: ['player'], clubs: [], kind: ['players'], created_at: daysAgo(90), last_login_at: daysAgo(40), approved_claims: 1, suspension: { reason: 'Repeated abusive messages', by: 'admin@example.test', at: daysAgo(8) } },
    { id: 16, display_name: 'Hana Whitlock', email: 'hana@thrandby.example', account_status: 'active', roles: ['club_manager'], clubs: [2], kind: ['clubs'], created_at: daysAgo(20), last_login_at: daysAgo(2) },
    { id: 17, display_name: LONG_NAME, email: `${'a-very-long-mailbox-name-'.repeat(3)}owner@example.test`, account_status: 'active', roles: ['guardian'], clubs: [], kind: [], created_at: daysAgo(2), last_login_at: null },
    { id: 18, display_name: 'Test Admin', email: 'test@example.test', account_status: 'active', roles: ['admin'], clubs: [], kind: ['admins'], created_at: daysAgo(400), last_login_at: daysAgo(0) },
]

const personDto = person => ({
    id: person.id, display_name: person.display_name, email: person.email, account_status: person.account_status,
    created_at: person.created_at, last_login_at: person.last_login_at, roles: person.roles, waiting: !!person.waiting,
    programs: person.clubs.map(id => ({ id, name: CLUBS.find(club => club.id === id).name, status: 'approved' })),
    approved_claims: person.approved_claims || 0, scout_verification: person.scout_verification || null,
})

function peopleMatching(params, { skipClub = false } = {}) {
    const q = (params.get('q') || '').toLowerCase()
    const role = params.get('role') || 'all'
    const standing = params.get('standing') || 'all'
    const club = params.get('club')
    const age = value => value ? (Date.now() - new Date(value).getTime()) / 86400000 : Infinity
    return PEOPLE.filter(person => {
        if (q && !`${person.display_name} ${person.email}`.toLowerCase().includes(q)) return false
        if (role !== 'all' && !person.kind.includes(role)) return false
        if (standing === 'waiting' ? !person.waiting : standing !== 'all' && person.account_status !== standing) return false
        if (!skipClub && club) { if (club === 'none' ? person.clubs.length : !person.clubs.includes(Number(club))) return false }
        if (params.get('verified') === 'yes' && !person.verified) return false
        if (params.get('verified') === 'no' && person.verified) return false
        const joined = { '7d': 7, '30d': 30, year: 365 }[params.get('joined')]
        if (joined && age(person.created_at) > joined) return false
        const seen = params.get('seen')
        if (seen === 'quiet' ? age(person.last_login_at) < 90 : seen && age(person.last_login_at) > { '7d': 7, '30d': 30 }[seen]) return false
        return true
    }).sort((left, right) => left.display_name.localeCompare(right.display_name))
}

const evidence = overrides => ({
    adult_authority_attested: true, authorization_method: 'signed_officer_authorization', official_email: 'secretary@pellowick.example',
    authorization_reference: 'Officer declaration, secretary since 2007', organization_form: 'unincorporated_association',
    registration_reference: 'WCFA-TEST-0655', official_contact_name: 'Les Oakenshaw, Chairman',
    official_contact_reference: 'County FA directory entry', safeguarding_contact_email: 'welfare@pellowick.example',
    safeguarding_policy_url: 'https://pellowick.example/safeguarding', safeguarding_policy_attested: true,
    eligible_organization_attested: true, payout_control_attested: true, ...overrides,
})
const league = { id: 1, name: 'Wendle & District Senior League', registry_status: 'approved', admission_state: 'open', region: 'Wendleshire', country: 'England', level: 'recreational', gender_program: 'both', age_bands: ['Open'], data_tier: 'self_reported' }
const claim = (id, club, status, extra = {}) => ({
    id, status, relationship_type: 'club_official', applicant_email: `secretary@${club.slug}.example`, created_at: daysAgo(3),
    program: { id: club.id, name: club.name, slug: club.slug, legal_name: `${club.name} FC`, region: club.region, country: club.country, is_verified_program: status === 'approved', provenance: { label: 'Self-reported' }, league },
    evidence: evidence(), connect: null, audit_trail: [{ action: 'claim_submitted', reason: 'Submitted by the club secretary', created_at: daysAgo(3) }], ...extra,
})
export const CLAIMS = [
    claim(31, CLUBS[2], 'pending', { evidence: evidence({ payout_control_attested: false }) }),
    claim(32, CLUBS[1], 'pending'),
    claim(33, CLUBS[0], 'approved'),
    claim(34, CLUBS[4], 'pending', { evidence: evidence({ payout_control_attested: false, safeguarding_contact_email: '', official_contact_reference: '' }) }),
]

export const dashboardStats = { players: { total: 1284, academy: 610, on_loan: 402, first_team: 233, released: 39 }, teams: { tracked: 46 }, newsletters: { total: 18, published: 15, drafts: 3 } }
const QUEUES = [
    ['manual', 'Manual players', '/admin/inbox?tab=manual', 0], ['takes', 'Community takes', '/admin/inbox?tab=takes', 0],
    ['submissions', 'Quick takes', '/admin/inbox?tab=submissions', 0], ['flags', 'Player flags', '/admin/inbox?tab=flags', 0],
    ['tracking', 'Tracking requests', '/admin/inbox?tab=tracking', 0], ['links', 'Player links', '/admin/inbox?tab=links', 0],
    ['club_claims', 'Club claims', '/admin/funding?tab=claims', 1], ['club_profiles', 'Club profile revisions', '/admin/funding?tab=content', 2],
    ['club_updates', 'Club updates', '/admin/funding?tab=content', 0], ['scout_verifications', 'Scout verifications', '/admin/trust?tab=verifications', 1],
    ['profile_claims', 'Player profile claims', '/admin/showcase?tab=claims', 0], ['reports', 'Open reports', '/admin/trust?tab=reports', 3],
    ['safeguarding', 'Safeguarding cases', '/admin/safety', 3],
]

/**
 * options: flags, quiet (nothing waiting anywhere), claims (override list),
 * hold(url) -> Promise to delay an answer, onRequest(url, request).
 */
export async function mockCalmAdmin(page, options = {}) {
    const flags = options.flags ?? ALL_FLAGS
    const claims = options.claims ?? CLAIMS
    const quiet = !!options.quiet
    await page.addInitScript(() => {
        localStorage.setItem('academy_watch_user_token', 'synthetic-control-token')
        localStorage.setItem('academy_watch_is_admin', 'true')
        localStorage.setItem('academy_watch_admin_key', 'synthetic-control-key')
        localStorage.setItem('academy_watch_display_name_confirmed', 'true')
        localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    })
    await page.route('**/api/**', async route => {
        const request = route.request()
        const url = new URL(request.url())
        const path = url.pathname.replace(/^\/api/, '')
        const params = url.searchParams
        options.onRequest?.(url, request)
        await options.hold?.(url)
        const override = await options.handler?.(url, request)
        if (override !== undefined) return route.fulfill(override.status ? override : { json: override })
        const json = body => route.fulfill({ json: body })
        if (path === '/features') return json(flags)
        if (path === '/auth/me') return json({ email: 'test@example.test', role: 'admin', display_name: 'Test Admin', display_name_confirmed: true })
        if (path === '/admin/auth-check') return json({ ok: true })
        if (path === '/admin/dashboard-stats') return json(dashboardStats)
        if (path === '/admin/control/overview') {
            const queues = QUEUES.map(([key, label, href, count]) => ({ key, label, href, count: quiet ? 0 : key === 'club_claims' ? claims.filter(row => row.status === 'pending').length : count }))
            return json({ queues, total: queues.reduce((sum, queue) => sum + queue.count, 0), overdue_safeguarding: quiet ? 0 : 1, revenue: { active_subscriptions: 4, mrr_cents: 11600, currency: 'gbp', mrr_by_currency: { gbp: 11600 }, past_due: quiet ? 0 : 1, webhook_failed_last_24h: 0 } })
        }
        if (path === '/admin/billing/summary') return json({ active_subscriptions: 4, mrr_cents: 11600, currency: 'gbp', mrr_by_currency: { gbp: 11600 }, past_due: 0, webhook_failed_last_24h: 0 })
        if (path === '/admin/ops/overview') return json({ tracked: { active: 1245, placeholder_names: 0, owning_club_active: 0 }, jobs: { active: 0 } })
        if (path === '/admin/analytics/summary') return json({ totals: { pageview: 4210, profile_view: 913, search_performed: 120 }, daily: [{ date: new Date().toISOString().slice(0, 10), count: 310 }], distinct_sessions: 640 })
        if (path === '/admin/community-takes/stats') return json({ takes: { pending: quiet ? 0 : 2 }, submissions: { pending: 0 } })
        if (path === '/admin/flags/stats') return json({ by_status: { pending: 0 } })
        if (['/admin/manual-players', '/admin/tracking-requests', '/admin/player-links/pending'].includes(path)) return json([])
        if (path === '/admin/jobs/active') return json({ jobs: [] })
        if (path === '/admin/scout-verifications') {
            const status = params.get('status') || 'pending'
            const rows = quiet || status !== 'pending' ? [] : [{ id: 5, full_name: 'Milo Strand', organization: 'Northfen Scouting Collective', role_title: 'Regional scout', status: 'pending', user_account_id: 13 }]
            return json({ verifications: rows, total: status === 'approved' ? 7 : rows.length, limit: 30, offset: 0 })
        }
        if (path === '/admin/reports') return json({ reports: [], total: quiet ? 0 : 3 })
        if (path === '/admin/funding/leagues') return json({ leagues: [league] })
        if (path === '/admin/funding/claims') {
            const status = params.get('status') || 'pending'
            return json({ claims: quiet ? [] : claims.filter(row => status === 'all' || row.status === status) })
        }
        if (path === '/admin/funding/demand') return json({ programs: [], by_region: [], by_league: [] })
        if (path === '/admin/funding/profile-revisions') return json({ revisions: quiet ? [] : [{ id: 1, status: 'pending', program: { id: 3, name: 'Pellowick Town' }, summary: 'A volunteer-run senior club.', age_groups: ['Open'], activities: ['Training'] }] })
        if (path === '/admin/funding/program-updates') return json({ updates: [] })
        if (path === '/admin/people/clubs') {
            const base = peopleMatching(params, { skipClub: true })
            const q = (params.get('club_q') || '').toLowerCase()
            return json({
                // Like the server: clubs with someone in them, plus the chosen club even when it has nobody.
                clubs: CLUBS.map(club => ({ id: club.id, name: club.name, count: base.filter(person => person.clubs.includes(club.id)).length })).filter(club => (club.count || String(club.id) === params.get('club')) && club.name.toLowerCase().includes(q)),
                no_club: base.filter(person => !person.clubs.length).length,
            })
        }
        if (path === '/admin/people') {
            const rows = peopleMatching(params)
            return json({ rows: rows.map(personDto), total: rows.length, limit: 30, offset: 0 })
        }
        const person = path.match(/^\/admin\/people\/(\d+)$/)
        if (person) {
            const found = PEOPLE.find(row => row.id === Number(person[1]))
            return json({ person: { ...personDto(found), ...(found.suspension ? { suspension: found.suspension } : {}) }, last_owner_programs: found.id === 12 ? ['Quillmere Athletic'] : [] })
        }
        if (path === '/admin/programs/countries') {
            const counts = {}
            for (const club of CLUBS) counts[club.country] = (counts[club.country] || 0) + 1
            return json({ countries: Object.entries(counts).map(([value, count]) => ({ value, count })) })
        }
        if (path === '/admin/programs') {
            const q = (params.get('q') || '').toLowerCase()
            const status = params.get('status') || 'all'
            const rows = CLUBS.filter(club => (!q || `${club.name} ${club.city} ${club.region}`.toLowerCase().includes(q))
                && (status === 'all' || (status === 'hidden' ? club.emergency_hidden : club.platform_status === status))
                && (!params.get('country') || club.country === params.get('country'))
                && (!params.get('verified') || (params.get('verified') === 'yes') === !!club.verified_at))
            return json({ rows, total: rows.length, limit: 30, offset: 0 })
        }
        const program = path.match(/^\/admin\/programs\/(\d+)$/)
        if (program) return json({ program: CLUBS.find(row => row.id === Number(program[1])), managers: [{ user_account_id: 12, display_name: 'Ruth Calloway', status: 'active', standing: 'active', owner: true }], actions: { emergency: true, owner: true } })
        return json({})
    })
}
