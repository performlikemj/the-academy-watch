// A short-lived, in-flight shared read. No persistence across page loads.
export function createFeatureCache(fetchFeatures, { ttl = 15000, now = Date.now } = {}) {
  let pending = null, value = null, expires = 0
  return function read() {
    if (pending) return pending
    if (value && now() < expires) return Promise.resolve(value)
    pending = Promise.resolve().then(fetchFeatures).then(flags => {
      value = flags; expires = now() + ttl
      return flags
    }).finally(() => { pending = null })
    return pending
  }
}
