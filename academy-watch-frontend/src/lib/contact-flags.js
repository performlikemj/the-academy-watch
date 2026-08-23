// Contact-rail feature flag — the client-side twin of the backend's CONTACT_RAIL_ENABLED. Pure module (no React, no
// network) so it is unit-testable; the hook in src/hooks/useContactRail.js wires it to GET /api/features.
let cached = null
let inflight = null

export function contactRailFromFeatures(res) {
  return Boolean(res && res.contact_rail === true)
}

// Resolves to true/false. A successful answer is cached for the session; a failed fetch answers false without
// caching, so the next mount asks again.
export function loadContactRail(fetchFeatures) {
  if (cached !== null) return Promise.resolve(cached)
  if (!inflight) {
    inflight = Promise.resolve()
      .then(() => fetchFeatures())
      .then((res) => {
        cached = contactRailFromFeatures(res)
        return cached
      }, () => false)
      .finally(() => { inflight = null })
  }
  return inflight
}

export function peekContactRail() {
  return cached
}

export function resetContactRail() {
  cached = null
  inflight = null
}
