// The club verification checks, grouped the way an admin reads them. `required`
// mirrors the server's approval bar (routes/funding.py `_evidence_meets_bar`):
// a claim can be approved only when every required check passes.

const text = value => typeof value === 'string' && value.trim().length > 0
const ROUTES = { official_domain_email: 'Official-domain email', signed_officer_authorization: 'Signed officer authorisation' }

function words(value) {
    return String(value || '').replaceAll('_', ' ').replace(/^\w/, letter => letter.toUpperCase())
}

function check(label, short, ok, value, { required = true, attested = false } = {}) {
    return { label, short, ok: !!ok, required, value: attested ? (ok ? 'attested' : 'not attested') : (ok ? value : 'not supplied'), missing: attested ? 'not attested' : 'not supplied' }
}

export function clubCheckGroups(evidence) {
    const e = evidence || {}
    const route = e.authorization_method
    const byEmail = route === 'official_domain_email'
    const byOfficer = route === 'signed_officer_authorization'
    return [
        {
            key: 'identity', title: 'Who they are', checks: [
                check('Organisation form', 'organisation form', text(e.organization_form), words(e.organization_form)),
                check('League or legal registration', 'registration', text(e.registration_reference), e.registration_reference),
                check('Official contact', 'official contact', text(e.official_contact_name), e.official_contact_name),
                check('Contact cross-check', 'contact cross-check', text(e.official_contact_reference), e.official_contact_reference),
            ],
        },
        {
            key: 'authority', title: 'Who can act for the club', checks: [
                check('Adult authority', 'adult authority', e.adult_authority_attested === true, null, { attested: true }),
                check('Authorisation route', 'authorisation route', byEmail || byOfficer, ROUTES[route]),
                check('Official-domain email', 'official-domain email', text(e.official_email), e.official_email, { required: byEmail || !byOfficer }),
                check('Signed officer authorisation', 'signed officer authorisation', text(e.authorization_reference), e.authorization_reference, { required: byOfficer }),
            ],
        },
        {
            key: 'safeguarding', title: 'Safeguarding', checks: [
                check('Safeguarding contact', 'safeguarding contact', text(e.safeguarding_contact_email), e.safeguarding_contact_email),
                check('Safeguarding controls', 'safeguarding controls', e.safeguarding_policy_attested === true, null, { attested: true }),
                check('Policy page', 'policy page', text(e.safeguarding_policy_url), e.safeguarding_policy_url, { required: false }),
            ],
        },
        {
            key: 'money', title: 'Money', checks: [
                check('Organisation-only recipient', 'organisation-only recipient', e.eligible_organization_attested === true, null, { attested: true }),
                check('Payout control', 'payout control', e.payout_control_attested === true, null, { attested: true }),
            ],
        },
    ].map(group => {
        const required = group.checks.filter(item => item.required)
        return { ...group, passed: required.filter(item => item.ok).length, total: required.length, failing: required.some(item => !item.ok) }
    })
}

/** { passed, total, missing: [{ short, missing }], complete, groups } for one claim's evidence. */
export function clubCheckSummary(evidence) {
    const groups = clubCheckGroups(evidence)
    const required = groups.flatMap(group => group.checks.filter(item => item.required))
    const missing = required.filter(item => !item.ok)
    return { groups, passed: required.length - missing.length, total: required.length, missing, complete: missing.length === 0 }
}

/** "11 of 11 checks pass" / "10 of 11 checks pass · missing payout control". */
export function clubCheckLine(summary) {
    const base = `${summary.passed} of ${summary.total} checks pass`
    if (summary.complete) return base
    const names = summary.missing.map(item => item.short)
    return `${base} · missing ${names.length > 2 ? `${names.slice(0, 2).join(', ')} and ${names.length - 2} more` : names.join(' and ')}`
}

export function leagueOpen(league) {
    return league?.registry_status === 'approved' && league?.admission_state === 'open'
}
