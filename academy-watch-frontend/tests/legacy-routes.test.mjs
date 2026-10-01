import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { LEGACY_PUBLIC_PAGES, LEGACY_PUBLIC_ROUTES, isLegacyPublicRoute } from '../src/lib/legacyRoutes.js'

const swaConfig = JSON.parse(await readFile(new URL('../public/staticwebapp.config.json', import.meta.url), 'utf8'))

// SWA evaluates the first match; these rules use exact paths or a terminal '*'.
function swaRuleFor(pathname) {
  return swaConfig.routes.find(({ route }) => route.endsWith('*')
    ? pathname.startsWith(route.slice(0, -1))
    : pathname === route)
}

test('SWA permanent redirect patterns stay in sync with the frozen client routes', () => {
  const expected = new Set(LEGACY_PUBLIC_ROUTES.map((route) => {
    const root = `/${route.split('/')[1]}`
    return route === root ? root : `${root}/*`
  }))
  const redirects = swaConfig.routes.filter((rule) => rule.redirect !== undefined)
  assert.deepEqual(redirects.map(({ route }) => route).sort(), [...expected].sort())
  for (const rule of redirects) {
    assert.deepEqual(rule, { route: rule.route, redirect: '/', statusCode: 301 })
  }
  for (const route of LEGACY_PUBLIC_ROUTES) {
    const pathname = route.replace(/:[^/]+/g, '42')
    assert.equal(swaRuleFor(pathname)?.redirect, '/', pathname)
    assert.equal(swaRuleFor(pathname)?.statusCode, 301, pathname)
  }
  for (const route of [...expected].filter((route) => route.endsWith('/*'))) {
    for (const suffix of ['', '42', '42/more/details']) {
      const pathname = route.slice(0, -1) + suffix
      assert.equal(swaRuleFor(pathname)?.statusCode, 301, pathname)
    }
  }
})

test('SWA legacy redirects leave active, operational, asset and look-alike paths alone', () => {
  const protectedPaths = [
    '/', '/index.html', '/scout', '/scout/watchlist', '/settings', '/clubs',
    '/programs/test', '/opportunities', '/my-club', '/local-players/7',
    '/manage', '/unsubscribe', '/verify', '/auth/callback',
    '/subscriptions/unsubscribe/token', '/p/42', '/p/42/card.png', '/sitemap.xml',
    '/assets/app.js', '/assets/app.css', '/robots.txt', '/favicon.ico',
    '/logo.png', '/manifest.webmanifest', '/images/academy.png',
    '/academy-foo', '/academy.html', '/teamsheet', '/teams-old/42',
    '/dream-team-builder', '/newsletters-archive', '/journalists-extra/42',
    '/writeups-old/42', '/submit-takeaway',
  ]
  for (const root of ['admin', 'writer', 'curator', 'players', 'api']) {
    for (const suffix of ['', '/', '/42', '/teams/42', '/newsletters/42', '/academy/analytics']) {
      protectedPaths.push(`/${root}${suffix}`)
    }
  }
  for (const pathname of protectedPaths) {
    assert.equal(swaRuleFor(pathname)?.redirect, undefined, pathname)
  }
})

test('SWA keeps the existing SPA fallback, asset caching and security headers', () => {
  assert.deepEqual(swaConfig.navigationFallback, {
    rewrite: '/index.html',
    exclude: ['/assets/*', '/*.ico', '/*.png', '/*.webmanifest', '/robots.txt'],
  })
  assert.deepEqual(swaConfig.globalHeaders, {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
  })
  assert.deepEqual(swaRuleFor('/assets/app.js'), {
    route: '/assets/*', headers: { 'Cache-Control': 'public, max-age=31536000, immutable' },
  })
})

test('all frozen legacy paths, including query strings, match; allowed paths stay available', () => {
  assert.equal(LEGACY_PUBLIC_PAGES, false)
  assert.equal(LEGACY_PUBLIC_ROUTES.length, 14)
  for (const pattern of LEGACY_PUBLIC_ROUTES) {
    const path = pattern.replace(/:[^/]+/g, '42')
    assert.ok(isLegacyPublicRoute(path), path)
    assert.ok(isLegacyPublicRoute(`${path}/?season=2025#details`), path)
  }
  assert.equal(isLegacyPublicRoute('https://theacademywatch.com/newsletters/42'), true)
  assert.equal(isLegacyPublicRoute('https://external.example/teams/42'), false)
  for (const path of ['/players/42', '/local-players/7', '/scout', '/scout/watchlist', '/programs/test', '/clubs', '/opportunities', '/my-club', '/onboarding/player', '/pricing', '/account/billing', '/settings', '/admin/newsletters', '/admin/teams', '/admin/cohorts', '/writer/editor/42', '/curator/dashboard', '/privacy']) {
    assert.equal(isLegacyPublicRoute(path), false, path)
  }
})

test('public robots lets crawlers observe legacy noindex and redirects', async () => {
  const robots = await readFile(new URL('../public/robots.txt', import.meta.url), 'utf8')
  for (const route of LEGACY_PUBLIC_ROUTES) {
    assert.ok(!robots.includes(`Disallow: /${route.split('/')[1]}`), route)
  }
  assert.match(robots, /^Allow: \/$/m)
  assert.match(robots, /^Sitemap: https:\/\/theacademywatch\.com\/sitemap\.xml$/m)
})
