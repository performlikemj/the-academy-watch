// Frozen public league/newsletter pages. Flip only when public access is approved.
export const LEGACY_PUBLIC_PAGES = false

export const LEGACY_PUBLIC_ROUTES = Object.freeze([
  '/dream-team',
  '/academy',
  '/academy/cohorts/:id',
  '/academy/analytics',
  '/teams',
  '/teams/:teamSlug',
  '/newsletters',
  '/newsletters/:id',
  '/newsletters/historical',
  '/newsletters/:id/writer/:journalistId',
  '/journalists',
  '/journalists/:id',
  '/writeups/:commentaryId',
  '/submit-take',
])

export function isLegacyPublicRoute(href) {
  if (!href) return false
  let pathname
  try {
    const base = globalThis.location?.origin || 'https://theacademywatch.com'
    const url = new URL(href, base)
    if (url.origin !== base && !['theacademywatch.com', 'www.theacademywatch.com'].includes(url.hostname)) return false
    pathname = url.pathname
  } catch {
    return false
  }
  return LEGACY_PUBLIC_ROUTES.some((route) => {
    const pattern = route.split('/').map((part) => part.startsWith(':') ? '[^/]+' : part).join('/')
    return new RegExp(`^${pattern}/?$`, 'i').test(pathname)
  })
}
