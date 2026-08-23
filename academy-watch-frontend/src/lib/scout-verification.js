// Client-side shaping for the scout verification form. Mirrors routes/trust.py limits so the user sees
// the problem before the server does. Pure functions — unit-tested without React.

export const LIMITS = { full_name: 200, organization: 200, role_title: 120, statement: 2000, evidence_url: 500, evidence_urls: 10 }

export function parseEvidenceUrls(text) {
  const seen = new Set()
  const urls = []
  for (const raw of String(text || '').split(/\r?\n/)) {
    const url = raw.trim()
    if (!url || seen.has(url)) continue
    seen.add(url)
    urls.push(url)
  }
  return urls
}

export function buildVerificationPayload(fields) {
  const full_name = String(fields.full_name || '').trim()
  const organization = String(fields.organization || '').trim()
  const role_title = String(fields.role_title || '').trim()
  const statement = String(fields.statement || '').trim()
  const evidence_urls = parseEvidenceUrls(fields.evidence_text)
  const errors = []
  if (!full_name) errors.push('Full name is required.')
  if (full_name.length > LIMITS.full_name) errors.push(`Full name must be at most ${LIMITS.full_name} characters.`)
  if (!organization) errors.push('Organisation is required.')
  if (organization.length > LIMITS.organization) errors.push(`Organisation must be at most ${LIMITS.organization} characters.`)
  if (!role_title) errors.push('Role is required.')
  if (role_title.length > LIMITS.role_title) errors.push(`Role must be at most ${LIMITS.role_title} characters.`)
  if (!statement) errors.push('Statement is required.')
  if (statement.length > LIMITS.statement) errors.push(`Statement must be at most ${LIMITS.statement} characters.`)
  if (evidence_urls.length === 0) errors.push('Add at least one https:// link that shows your role (club site, LinkedIn, federation listing).')
  if (evidence_urls.length > LIMITS.evidence_urls) errors.push(`At most ${LIMITS.evidence_urls} links.`)
  for (const url of evidence_urls) {
    if (!/^https:\/\/\S+$/i.test(url) || url.length > LIMITS.evidence_url) {
      errors.push(`Not an https:// link: ${url}`)
      break
    }
  }
  if (errors.length) return { ok: false, errors }
  return { ok: true, payload: { full_name, organization, role_title, statement, evidence_urls } }
}

export function describeVerificationStatus(verification) {
  if (!verification) return { tone: 'none', title: 'Not verified yet', body: 'Verified scouts can introduce themselves to players. Tell us who you are and we will review it.' }
  switch (verification.status) {
    case 'approved':
      return { tone: 'approved', title: 'You are a verified scout', body: 'You can introduce yourself to players from the Scout Desk.' }
    case 'pending':
      return { tone: 'pending', title: 'Verification under review', body: 'We review applications by hand. You will be able to introduce yourself once approved.' }
    case 'rejected':
      return { tone: 'rejected', title: 'Verification not approved', body: verification.review_notes ? `Reviewer note: ${verification.review_notes}` : 'You can apply again with more evidence.' }
    case 'revoked':
      return { tone: 'revoked', title: 'Verification revoked', body: verification.revocation_reason ? `Reason: ${verification.revocation_reason}` : 'Contact support if you think this is a mistake.' }
    default:
      return { tone: 'none', title: 'Not verified yet', body: 'Tell us who you are and we will review it.' }
  }
}

export function canApply(verification) {
  return !verification || !['pending', 'approved'].includes(verification.status)
}
