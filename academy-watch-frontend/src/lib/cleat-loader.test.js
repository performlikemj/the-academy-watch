import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { CLEAT_BOOT, CLEAT_CSS, CLEAT_SVG, CLUB_PALETTE, CLUB_COLOUR_MS } from './cleat-loader.js'

test('boot splash uses the shared SVG and palette with no asset request', () => {
  const html = fs.readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  assert.ok(html.includes(CLEAT_BOOT))
  assert.ok(html.includes(CLEAT_CSS))
  assert.ok(CLEAT_SVG.includes('stroke-width="2"'))
  assert.doesNotMatch(CLEAT_BOOT, /<img|<image|<use|href=|src=/)
  assert.match(CLEAT_BOOT, /role="status" aria-live="polite" aria-label="Loading"/)
})

test('club cycle advances every 1.2 seconds, includes black/gold and returns to green', () => {
  assert.equal(CLUB_COLOUR_MS, 1200)
  assert.deepEqual(CLUB_PALETTE.map(colour => colour.fill), ['#0F3D2E', '#7A1426', '#1F3E73', '#0B0E0D', '#E35D18', '#6CACE4'])
  assert.equal(CLUB_PALETTE[3].accent, '#CFAE62')
  assert.match(CLEAT_CSS, /7200ms linear infinite/)
  assert.match(CLEAT_CSS, /100%\{fill:#0F3D2E;stroke:#0F3D2E\}/)
})

test('reduced motion cancels both animations and forces a still green boot', () => {
  const reduced = CLEAT_CSS.slice(CLEAT_CSS.indexOf('@media(prefers-reduced-motion:reduce)'))
  assert.match(reduced, /\.cleat-loader \.cleat-body,\.cleat-loader \.cleat-accent\{animation:none;fill:#0F3D2E\}/)
  assert.match(reduced, /\.cleat-accent\{stroke:#0F3D2E\}/)
})
