import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { APIService, nextWindowIndex } = await import('../src/lib/api.js')

const playerReelSource = readFileSync(new URL('../src/components/video/PlayerReel.jsx', import.meta.url), 'utf8')

function extractFunction(name) {
  const declaration = `function ${name}`
  const declarationIndex = playerReelSource.indexOf(declaration)
  assert.notEqual(declarationIndex, -1, `${name} should be defined in PlayerReel.jsx`)
  const exportIndex = playerReelSource.lastIndexOf('export ', declarationIndex)
  const start = exportIndex >= 0 && declarationIndex - exportIndex < 16 ? exportIndex : declarationIndex
  const braceStart = playerReelSource.indexOf('{', declarationIndex)
  let depth = 0
  for (let index = braceStart; index < playerReelSource.length; index += 1) {
    if (playerReelSource[index] === '{') depth += 1
    if (playerReelSource[index] === '}') depth -= 1
    if (depth === 0) return playerReelSource.slice(start, index + 1).replace(/^export /, '')
  }
  throw new Error(`Could not extract ${name}`)
}

const identityHelpers = new Function(`
  ${extractFunction('realNumber')}
  ${extractFunction('formatVoteSummary')}
  ${extractFunction('mismatchBadge')}
  return { formatVoteSummary, mismatchBadge }
`)()

const { formatVoteSummary, mismatchBadge } = identityHelpers

test('getVideoReel calls the admin reel endpoint', async () => {
  const originalRequest = APIService.request
  const calls = []
  APIService.request = async (...args) => {
    calls.push(args)
    return { players: [] }
  }

  try {
    const response = await APIService.getVideoReel(42)
    assert.deepEqual(response, { players: [] })
    assert.deepEqual(calls, [['/admin/video/matches/42/reel', {}, { admin: true }]])
  } finally {
    APIService.request = originalRequest
  }
})

test('nextWindowIndex stays live before the end and advances at the boundary', () => {
  const windows = [
    { start_s: 10, end_s: 12 },
    { start_s: 20, end_s: 24 },
  ]

  assert.equal(nextWindowIndex(11.99, windows, 0), 0)
  assert.equal(nextWindowIndex(12, windows, 0), 1)
  assert.equal(nextWindowIndex(24, windows, 1), -1)
})

test('nextWindowIndex handles empty and invalid playlist state', () => {
  const windows = [{ start_s: 5, end_s: 8 }]
  assert.equal(nextWindowIndex(5, [], 0), -1)
  assert.equal(nextWindowIndex(5, windows, -1), 0)
  assert.equal(nextWindowIndex(5, windows, 99), 0)
})

test('formatVoteSummary orders model reads by strength and includes honest suggestions', () => {
  const summary = formatVoteSummary([
    { voted_number: 17, vote_total: 2, suggested_number: 17 },
    { voted_number: 12, vote_total: 43, suggested_number: 9 },
    { voted_number: 12, vote_total: 4, suggested_number: 12 },
  ])

  assert.equal(summary, 'model reads: #12 × 47 · #17 × 2 · #9 suggested')
})

test('formatVoteSummary never invents counts for suggestion-only evidence', () => {
  assert.equal(
    formatVoteSummary([{ voted_number: null, vote_total: 0, suggested_number: 6 }]),
    'model reads: #6 suggested',
  )
  assert.equal(formatVoteSummary([{ voted_number: '12', vote_total: 50, suggested_number: null }]), 'model reads: no usable number')
})

test('mismatchBadge uses the strongest real mismatching vote', () => {
  assert.equal(mismatchBadge({
    jersey_number: 2,
    number_mismatch: true,
    chains: [
      { voted_number: 17, vote_total: 2, suggested_number: 17 },
      { voted_number: 12, vote_total: 43, suggested_number: 2 },
      { voted_number: 2, vote_total: 90, suggested_number: 2 },
    ],
  }), 'reads say #12')
})

test('mismatchBadge is absent without a mismatch and falls back to a real suggestion', () => {
  assert.equal(mismatchBadge({ jersey_number: 8, number_mismatch: false, chains: [] }), null)
  assert.equal(mismatchBadge({
    jersey_number: 8,
    number_mismatch: true,
    chains: [{ voted_number: null, vote_total: 0, suggested_number: 12 }],
  }), 'model suggests #12')
})
