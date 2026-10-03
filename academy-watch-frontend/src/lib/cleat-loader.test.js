import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { Buffer } from 'node:buffer'
import { createHash } from 'node:crypto'
import { LOGO_LAYERS, LOGO_PIXEL_SIZE, LOGO_SOURCE_SHA256 } from './academy-watch-logo.js'
import { CLEAT_BOOT, CLEAT_CSS, CLEAT_MARK, CLUB_PALETTE, CLUB_COLOUR_MS, CLUB_TRANSITION_MS, LOADER_HEIGHT, LOADER_WIDTH } from './cleat-loader.js'

const ink = '#0E1311'

test('boot splash inlines the shared loader with no asset request', () => {
  const html = fs.readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  assert.ok(html.includes(CLEAT_BOOT))
  assert.ok(html.includes(CLEAT_CSS))
  assert.match(CLEAT_MARK, /data-brand-logo="academy-watch-winged-boot"/)
  for (const part of ['art', 'boot', 'shade', 'light']) assert.ok(CLEAT_MARK.includes(`data-brand-part="${part}"`))
  assert.doesNotMatch(CLEAT_BOOT, /<img|<image|<use|<svg|href=|src=/)
  // Every image is an inline data URI: the splash never fetches anything.
  const urls = [...CLEAT_CSS.matchAll(/url\(([^)]*)\)/g)].map(match => match[1])
  assert.equal(urls.length, 4)
  for (const url of urls) assert.match(url, /^data:image\/webp;base64,/)
  assert.match(CLEAT_BOOT, /role="status" aria-live="polite" aria-label="Loading"/)
})

test('logo layers are the real artwork at 3x of the 144px loader', () => {
  assert.deepEqual(Object.keys(LOGO_LAYERS), ['art', 'boot', 'shade', 'light'])
  assert.equal(LOGO_PIXEL_SIZE.width, LOADER_WIDTH * 3)
  assert.equal(LOADER_HEIGHT, Math.round(LOADER_WIDTH * LOGO_PIXEL_SIZE.height / LOGO_PIXEL_SIZE.width))
  for (const url of Object.values(LOGO_LAYERS)) {
    const bytes = Buffer.from(url.split(',')[1], 'base64')
    assert.equal(bytes.subarray(0, 4).toString(), 'RIFF')
    assert.equal(bytes.subarray(8, 12).toString(), 'WEBP')
  }
  // The inline splash stays small: four layers, about 40 KB of WebP.
  const total = Object.values(LOGO_LAYERS).reduce((sum, url) => sum + Buffer.from(url.split(',')[1], 'base64').length, 0)
  assert.ok(total < 48_000, `logo layers ${total} bytes`)
})

test('club cycle advances every 1.2 seconds, includes black/gold and returns to green', () => {
  assert.equal(CLUB_COLOUR_MS, 1200)
  assert.equal(CLUB_TRANSITION_MS, 200)
  assert.deepEqual(CLUB_PALETTE.map(colour => colour.body), ['#0F3D2E', '#7A1426', '#1F3E73', '#0B0E0D', '#E35D18', '#6CACE4'])
  assert.deepEqual(CLUB_PALETTE.map(colour => colour.detail), [ink, ink, ink, '#CFAE62', ink, ink])
  assert.match(CLEAT_CSS, /\.cleat-shade\{background-color:#0F3D2E;[^}]*animation:cleat-clubs 7200ms ease infinite\}/)
  assert.match(CLEAT_CSS, /\.cleat-boot\{background-color:#0E1311;[^}]*animation:cleat-detail 7200ms ease infinite\}/)
  assert.ok(CLEAT_CSS.includes(`${1000 * 100 / 7200}%{background-color:#0F3D2E}`))
  assert.ok(CLEAT_CSS.includes(`${1200 * 100 / 7200}%{background-color:#7A1426}`))
  assert.match(CLEAT_CSS, /100%\{background-color:#0F3D2E\}/)
})

test('the boot is the shaded artwork recoloured, never a flat fill; the wing is never coloured', () => {
  // The art layer (real icon pixels, wing included) is never animated or recoloured.
  assert.match(CLEAT_CSS, /\.cleat-art\{background:url\(data:image\/webp;base64,[^)]+\) 0 0\/100% 100% no-repeat\}/)
  // Club colour is painted only through the boot's own shading mask; highlights stay white.
  assert.match(CLEAT_CSS, /\.cleat-shade\{[^}]*--cleat-mask:url\(data:image\/webp/)
  assert.match(CLEAT_CSS, /\.cleat-light\{background-color:#FFFFFF;--cleat-mask:url\(data:image\/webp[^}]*\}/)
  assert.doesNotMatch(CLEAT_CSS, /\.cleat-(art|light)\{[^}]*animation/)
  assert.doesNotMatch(CLEAT_CSS, /<path|fill:/)
})

test('reduced motion cancels every colour animation: one still green frame, no movement', () => {
  const reduced = CLEAT_CSS.slice(CLEAT_CSS.indexOf('@media(prefers-reduced-motion:reduce)'))
  assert.match(reduced, /\.cleat-loader \.cleat-boot,\.cleat-loader \.cleat-shade\{animation:none\}/)
  assert.doesNotMatch(CLEAT_CSS, /transform:|rotate|translate/)
})

test('dark surfaces get a light rim so a matching club colour never vanishes', () => {
  assert.match(CLEAT_CSS, /\.dark \.cleat-loader \.cleat-mark,\.cleat-loader\[data-surface=night\] \.cleat-mark\{filter:drop-shadow\(1px 0 0 rgba\(243,240,232,\.92\)\)/)
  assert.match(CLEAT_CSS, /\.cleat-loader\[data-surface=chalk\]\{color:#0E1311\}\.cleat-loader\[data-surface=chalk\] \.cleat-mark\{filter:none\}/)
})

test('contextual page loading messages suppress the shared visual caption', () => {
  for (const file of ['../App.jsx', '../pages/PlayerPage.jsx']) {
    const source = fs.readFileSync(new URL(file, import.meta.url), 'utf8')
    const contextual = [...source.matchAll(/<CleatLoader([^>]*)\/>\s*<p[^>]*>Loading[^<]*<\/p>/g)]
    assert.equal(contextual.length, file.includes('App') ? 4 : 1)
    for (const match of contextual) assert.match(match[1], /caption=\{false\}/)
  }
})

test('logo provenance matches the unchanged brand master', () => {
  const source = fs.readFileSync(new URL('../../public/assets/loan_army_assets/favicon-512x512.png', import.meta.url))
  assert.equal(createHash('sha256').update(source).digest('hex'), LOGO_SOURCE_SHA256)
})
