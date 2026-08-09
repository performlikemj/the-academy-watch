const STORAGE_KEY = 'aw.season'

function normalizeSeason(season) {
  const numeric = Number(season)
  return Number.isInteger(numeric) && /^\d{4}$/.test(String(numeric)) ? numeric : undefined
}

function get() {
  if (typeof window === 'undefined') return undefined

  try {
    return normalizeSeason(window.sessionStorage.getItem(STORAGE_KEY))
  } catch {
    return undefined
  }
}

function set(season) {
  const normalized = normalizeSeason(season)
  if (normalized == null || typeof window === 'undefined') return

  try {
    window.sessionStorage.setItem(STORAGE_KEY, String(normalized))
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}

function clear() {
  if (typeof window === 'undefined') return

  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}

export const seasonStore = { get, set, clear }

export default seasonStore
