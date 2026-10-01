import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { LEGACY_PUBLIC_PAGES, LEGACY_PUBLIC_ROUTES, isLegacyPublicRoute } from '../src/lib/legacyRoutes.js'

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
