// The public bootstrap is shared by every feature consumer for this page session.
// Only successful responses are cached; failure is unknown, never a dark/off signal.
let cached = null
let inflight = null

export function peekFeatures() { return cached }
export function loadFeatures(fetchFeatures) {
  if (cached !== null) return Promise.resolve(cached)
  if (!inflight) {
    const request = Promise.resolve().then(fetchFeatures).then(data => {
      if (inflight === request) cached = data
      return data
    }).finally(() => { if (inflight === request) inflight = null })
    inflight = request
  }
  return inflight
}
export function resetFeatures() { cached = null; inflight = null }

// MyClub expiry releases only the pending bootstrap, retaining successful cache.
export function releaseFeatureBootstrap() { inflight = null }
