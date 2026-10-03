// The public bootstrap is shared by every feature consumer for this page session.
// Only successful responses are cached; failure is unknown, never a dark/off signal.
let cached = null
let inflight = null

export function peekFeatures() { return cached }
export function loadFeatures(fetchFeatures) {
  if (cached !== null) return Promise.resolve(cached)
  if (!inflight) {
    inflight = Promise.resolve().then(fetchFeatures).then(data => {
      cached = data
      return data
    }).finally(() => { inflight = null })
  }
  return inflight
}
export function resetFeatures() { cached = null; inflight = null }
