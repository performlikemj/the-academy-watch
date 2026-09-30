import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transformWithOxc } from 'vite'
import { format } from 'date-fns'

const pageSource = readFileSync(new URL('../src/pages/PlayerPage.jsx', import.meta.url), 'utf8')
const panelsSource = readFileSync(new URL('../src/components/PublicMatchPanels.jsx', import.meta.url), 'utf8')

// Render the actual PlayerPage stats branch, with layout/chart primitives
// replaced by passthroughs. Keep its conditions, panels and match table intact.
const start = pageSource.indexOf('{apiFootballFrozen &&')
const end = pageSource.indexOf('{/* Academy Development Section', start)
assert.ok(start > 0 && end > start)
const section = pageSource.slice(start, end)
const panels = await transformWithOxc(panelsSource.replace('export function', 'function'), 'Panels.jsx', { jsx: { runtime: 'classic' } })
const PublicMatchPanels = new Function('React', `${panels.code}; return PublicMatchPanels`)(React)
const transformed = await transformWithOxc(`function StatsSection() { return <>${section}</> }`, 'StatsSection.jsx', { jsx: { runtime: 'classic' } })
const primitives = Object.fromEntries([...section.matchAll(/<([A-Z]\w*)[\s/>]/g)].map(([, name]) => [name, ({ children }) => React.createElement(React.Fragment, null, children)]))

for (const frozen of [false, true]) {
  test(`PlayerPage retains stored match rows with frozen=${frozen}`, () => {
    const scope = {
      ...primitives, React, PublicMatchPanels, apiFootballFrozen: frozen,
      stats: [{ opponent: 'Stored Opponent', minutes: 90, goals: 1, assists: 0, rating: '7.1', fixture_date: '2026-05-18' }],
      seasonStats: { public_match_data: { available: true, as_of: '2026-05-20', totals: { goals: 4 } }, club_verified: { available: true, totals: { goals: 2 } } },
      seasonTotals: { appearances: 1, minutes: 90, goals: 1, assists: 0, avgRating: 7.1 },
      academyStats: null, hasSeasonTotals: true, position: 'Midfielder',
      currentConfig: { options: [] }, selectedMetrics: [], chartData: [],
      CHART_GRID_COLOR: '#ccc', CHART_AXIS_COLOR: '#333', format,
    }
    const Component = new Function('scope', `with (scope) { ${transformed.code}; return StatsSection }`)(scope)
    const html = renderToStaticMarkup(React.createElement(Component))
    assert.match(html, /Match Log/)
    assert.match(html, /<table[\s>]/)
    assert.match(html, /Stored Opponent/)
    assert.equal(html.includes('Public match data — last updated 2026-05-20'), frozen)
    assert.equal(html.includes('Club-verified'), frozen)
    if (frozen) assert.ok(html.indexOf('Club-verified') < html.indexOf('<table'))
  })
}

function dataModeLoader(getDataMode) {
  const source = readFileSync(new URL('../src/hooks/useDataMode.js', import.meta.url), 'utf8')
    .replace(/^import .*\n/gm, '').replaceAll('export function', 'function')
  return new Function('APIService', `${source}; return loadDataMode`)({ getDataMode })
}

test('data mode shares one in-flight request across consumers and remounts', async () => {
  let calls = 0
  const mode = { api_football_frozen: true, newsletters_frozen: true }
  const load = dataModeLoader(async () => { calls += 1; return mode })
  const first = load()
  assert.equal(first, load())
  assert.deepEqual(await Promise.all([first, load()]), [mode, mode])
  assert.equal(await load(), mode)
  assert.equal(calls, 1)
})

test('data mode keeps safe defaults after a failed request without refetching', async () => {
  let calls = 0
  const load = dataModeLoader(async () => { calls += 1; throw new Error('offline') })
  assert.deepEqual(await load(), { api_football_frozen: false, newsletters_frozen: false })
  await load()
  assert.equal(calls, 1)
})
