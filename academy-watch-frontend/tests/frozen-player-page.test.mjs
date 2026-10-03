import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transformWithOxc } from 'vite'
import { format } from 'date-fns'

const pageSource = readFileSync(new URL('../src/pages/PlayerPage.jsx', import.meta.url), 'utf8')
const { providerTotals, summarizeSeason } = await import('../src/lib/player-card.js')

// Render the actual PlayerPage provider-detail branch, with layout/chart primitives
// replaced by passthroughs. Keep its conditions and match table intact.
const start = pageSource.indexOf('{/* Provider detail:')
const end = pageSource.indexOf('{/* Academy Development Section', start)
assert.ok(start > 0 && end > start)
const section = pageSource.slice(start, end)
const transformed = await transformWithOxc(`function StatsSection() { return <>${section}</> }`, 'StatsSection.jsx', { jsx: { runtime: 'classic' } })
const primitives = Object.fromEntries([...section.matchAll(/<([A-Z]\w*)[\s/>]/g)].map(([, name]) => [name, ({ children }) => React.createElement(React.Fragment, null, children)]))

for (const frozen of [false, true]) {
  test(`PlayerPage retains stored match rows with frozen=${frozen}`, () => {
    const seasonStats = { public_match_data: { available: true, as_of: '2026-05-20', totals: { appearances: 6, minutes: 480, goals: 4 } }, club_verified: { available: true, totals: { goals: 2 } } }
    const scope = {
      ...primitives, React, apiFootballFrozen: frozen, isLocalPlayer: false,
      stats: [{ opponent: 'Stored Opponent', minutes: 90, goals: 1, assists: 0, rating: '7.1', fixture_date: '2026-05-18' }],
      seasonStats, provider: providerTotals(seasonStats),
      academyStats: null, position: 'Midfielder',
      currentConfig: { options: [] }, selectedMetrics: [], chartData: [],
      CHART_GRID_COLOR: '#ccc', CHART_AXIS_COLOR: '#333', format,
    }
    const Component = new Function('scope', `with (scope) { ${transformed.code}; return StatsSection }`)(scope)
    const html = renderToStaticMarkup(React.createElement(Component))
    assert.match(html, /Match Log/)
    assert.match(html, /<table[\s>]/)
    assert.match(html, /Stored Opponent/)
  })
}

// The season block above that branch (PlayerSeason) replaced the two source
// panels. Frozen mode still states the public-data freshness and still never
// adds public and club figures together.
test('the season block keeps the frozen public-data freshness line and source separation', () => {
  const seasonStats = { public_match_data: { available: true, as_of: '2026-05-20', totals: { appearances: 6, minutes: 480, goals: 4, assists: 0 } }, club_verified: { available: true, totals: { goals: 2 } } }
  const clubLines = { matches: 1, appearances: 1, full_matches: 1, minutes: 90, goals: 2, assists: 0, yellows: 0, reds: 0, cards_known: true, club_confirmed: 1, self_reported_only: 0, differing: 0 }
  const frozenSummary = summarizeSeason({ lines: [{}], totals: clubLines, provider: providerTotals(seasonStats), frozen: true })

  assert.equal(frozenSummary.source, 'provider')
  assert.ok(frozenSummary.sentence.startsWith('Public match data — last updated 2026-05-20.'))
  assert.match(frozenSummary.sentence, /not added to these totals/)
  assert.equal(frozenSummary.tiles.find((tile) => tile.key === 'contribution').value, '4')
  assert.equal(frozenSummary.tiles.find((tile) => tile.key === 'minutes').value, '480')
  assert.match(pageSource, /<PlayerSeason[\s\S]*?frozen=\{apiFootballFrozen\}/)
  assert.doesNotMatch(pageSource, /PublicMatchPanels/)
})

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
