// Club staff access (dark behind the backend's CLUB_STAFF_ACCESS_ENABLED). Pure helpers — no React, no network.
// `access` is the server's /club/<id>/access/me payload; null means "flag off / claim-verified manager": everything
// the console did before stays available, exactly as it was.

export const ROLE_LABELS = {
  owner: 'Owner',
  manager: 'Club manager',
  coach: 'Coach',
  analyst: 'Analyst',
  viewer: 'Viewer',
}

export const INVITE_ROLES = ['coach', 'manager', 'analyst', 'viewer']
export const SCOPED_ROLES = new Set(['coach', 'analyst', 'viewer'])

export function can(access, capability) {
  return !access || (Array.isArray(access.capabilities) && access.capabilities.includes(capability))
}

// Which Club Home views this caller may open. access === null (flag off, or a claim-verified manager whose
// access hasn't been fetched) allows everything, exactly as before staff access existed.
export function clubViewAllowed(access, staffAccessEnabled = false) {
  const allow = (capability) => can(access, capability)
  return {
    today: true,
    map: allow('players.view'),
    squad: allow('players.view'),
    player: allow('players.view'),
    matches: allow('matches.view'),
    recruiting: allow('recruiting'),
    introductions: allow('contact'),
    branding: allow('branding'),
    profile: allow('branding'),
    squads: allow('players.manage'),
    roster: allow('players.manage'),
    staff: allow('staff.directory') || (Boolean(staffAccessEnabled) && allow('access.view')),
    affiliations: !access || Boolean(access.verified),
  }
}

// What the Scouts / Introductions view shows: 'panel' (the club introductions panel), 'unavailable' (the
// "not enabled" note while the contact rail flag is off or unknown) or 'hidden' (role lacks the contact capability).
export function introductionsPanelState(access, contactRail) {
  if (!can(access, 'contact')) return 'hidden'
  return contactRail === true ? 'panel' : 'unavailable'
}

export function staffAccessFromFeatures(res) {
  return Boolean(res && res.club_staff_access === true)
}

let cached = null
let inflight = null

// Resolves true/false; a successful answer is cached for the session, a failure answers false without caching.
export function loadStaffAccessFlag(fetchFeatures) {
  if (cached !== null) return Promise.resolve(cached)
  if (!inflight) {
    inflight = Promise.resolve()
      .then(() => fetchFeatures())
      .then((res) => {
        cached = staffAccessFromFeatures(res)
        return cached
      }, () => false)
      .finally(() => { inflight = null })
  }
  return inflight
}

export function peekStaffAccessFlag() {
  return cached
}

export function squadScopeLabel(entry, squads) {
  if (!entry || entry.all_squads || !SCOPED_ROLES.has(entry.role)) return 'All squads'
  const names = (entry.squad_ids || []).map((id) => squads.find((s) => s.id === id)?.name).filter(Boolean)
  return names.length ? names.join(', ') : 'No squads'
}
