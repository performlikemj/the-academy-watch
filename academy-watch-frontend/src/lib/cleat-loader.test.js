import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createHash } from 'node:crypto'
import { LOGO_SOURCE_SHA256 } from './academy-watch-logo.js'
import { CLEAT_BOOT, CLEAT_CSS, CLEAT_SVG, CLUB_PALETTE, CLUB_COLOUR_MS, CLUB_TRANSITION_MS } from './cleat-loader.js'

test('boot splash uses the shared SVG and palette with no asset request', () => {
  const html = fs.readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  assert.ok(html.includes(CLEAT_BOOT))
  assert.ok(html.includes(CLEAT_CSS))
  assert.match(CLEAT_SVG, /data-brand-logo="academy-watch-winged-boot"/)
  for (const part of ['body', 'sole', 'wing']) assert.ok(CLEAT_SVG.includes(`data-brand-part="${part}"`))
  assert.doesNotMatch(CLEAT_SVG, /M20 47 Q20|M22 58 L33|M23 47 Q34/)
  assert.doesNotMatch(CLEAT_BOOT, /<img|<image|<use|href=|src=/)
  assert.match(CLEAT_BOOT, /role="status" aria-live="polite" aria-label="Loading"/)
})

test('club cycle advances every 1.2 seconds, includes black/gold and returns to green', () => {
  assert.equal(CLUB_COLOUR_MS, 1200)
  assert.equal(CLUB_TRANSITION_MS, 200)
  assert.deepEqual(CLUB_PALETTE.map(colour => colour.fill), ['#0F3D2E', '#7A1426', '#1F3E73', '#0B0E0D', '#E35D18', '#6CACE4'])
  assert.equal(CLUB_PALETTE[3].accent, '#CFAE62')
  assert.match(CLEAT_CSS, /7200ms ease infinite/)
  assert.match(CLEAT_CSS, /100%\{fill:#0F3D2E\}/)
  assert.ok(CLEAT_CSS.includes(`${1000 * 100 / 7200}%{fill:#0F3D2E}`))
  assert.ok(CLEAT_CSS.includes(`${1200 * 100 / 7200}%{fill:#7A1426}`))
  assert.doesNotMatch(CLEAT_CSS, /fill-opacity/)
})

test('reduced motion cancels every colour animation and forces a still green boot', () => {
  const reduced = CLEAT_CSS.slice(CLEAT_CSS.indexOf('@media(prefers-reduced-motion:reduce)'))
  assert.match(reduced, /\.cleat-loader \.cleat-body,\.cleat-loader \.cleat-accent\{animation:none;fill:#0F3D2E\}/)
  assert.doesNotMatch(CLEAT_CSS, /transform:|rotate|translate|cleat-laces/)
  assert.match(CLEAT_CSS, /\.cleat-wing\{fill:#FFFFFF;/)
})

test('contextual page loading messages suppress the shared visual caption', () => {
  for (const file of ['../App.jsx', '../pages/PlayerPage.jsx']) {
    const source = fs.readFileSync(new URL(file, import.meta.url), 'utf8')
    const contextual = [...source.matchAll(/<CleatLoader([^>]*)\/>\s*<p[^>]*>Loading[^<]*<\/p>/g)]
    assert.equal(contextual.length, file.includes('App') ? 4 : 1)
    for (const match of contextual) assert.match(match[1], /caption=\{false\}/)
  }
})

test('wing stays white with a thin ink contour only on light surfaces', () => {
  assert.match(CLEAT_SVG, /class="cleat-wing" data-brand-part="wing"/)
  assert.match(CLEAT_CSS, /\.cleat-wing\{fill:#FFFFFF;stroke:#0E1311;stroke-width:1\.5;paint-order:stroke fill\}/)
  assert.match(CLEAT_CSS, /\.dark \.cleat-loader \.cleat-wing,\.cleat-loader\[data-surface=night\] \.cleat-wing\{stroke:none\}/)
  assert.match(CLEAT_CSS, /\.cleat-loader\[data-surface=chalk\] \.cleat-wing\{stroke:#0E1311\}/)
})

test('trace provenance matches the unchanged launch brand source', () => {
  const source = fs.readFileSync(new URL('../../../academy-watch-ios/AcademyWatch/Assets.xcassets/LaunchBoot.imageset/LaunchBoot@3x.png', import.meta.url))
  assert.equal(createHash('sha256').update(source).digest('hex'), LOGO_SOURCE_SHA256)
})
