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
