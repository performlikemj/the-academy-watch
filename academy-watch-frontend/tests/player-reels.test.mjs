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

const reelHelpers = new Function(`
  ${extractFunction('orderReelWindows')}
  ${extractFunction('matchCaptionToWindow')}
  ${extractFunction('captionPresentation')}
  return { orderReelWindows, matchCaptionToWindow, captionPresentation }
`)()

const { formatVoteSummary, mismatchBadge } = identityHelpers
const { orderReelWindows, matchCaptionToWindow, captionPresentation } = reelHelpers

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

test('orderReelWindows keeps chronological default and ranks top moments without mutation', () => {
  const windows = [
    { start_s: 30, end_s: 35, tracklet_id: 3, rank: 1 },
    { start_s: 10, end_s: 15, tracklet_id: 1, rank: 3 },
    { start_s: 20, end_s: 25, tracklet_id: 2, rank: 2 },
  ]

  assert.deepEqual(orderReelWindows(windows).map((window) => window.tracklet_id), [1, 2, 3])
  assert.deepEqual(orderReelWindows(windows, 'ranked').map((window) => window.tracklet_id), [3, 2, 1])
  assert.deepEqual(windows.map((window) => window.tracklet_id), [3, 1, 2])
})

test('matchCaptionToWindow requires roster identity, tracklet, and 50% overlap', () => {
  const window = { tracklet_id: 7, start_s: 10, end_s: 20 }
  const player = { roster_entry_id: 12 }
  const wrongTracklet = { roster_entry_id: 12, tracklet_id: 8, start_s: 10, end_s: 20, caption: 'wrong' }
  const underHalf = { roster_entry_id: 12, tracklet_id: 7, start_s: 19, end_s: 22, caption: 'too short' }
  const half = { roster_entry_id: 12, tracklet_id: 7, start_s: 18, end_s: 22, caption: 'matched' }

  assert.equal(matchCaptionToWindow(window, [wrongTracklet, underHalf, half], player), half)
  assert.equal(matchCaptionToWindow(window, [wrongTracklet, underHalf], player), null)
})

test('matchCaptionToWindow invalidates rebound and legacy captions', () => {
  const window = { tracklet_id: 7, start_s: 10, end_s: 20 }
  const player = { roster_entry_id: 12 }
  const rebound = { roster_entry_id: 99, tracklet_id: 7, start_s: 10, end_s: 20 }
  const legacy = { tracklet_id: 7, start_s: 10, end_s: 20 }
  const current = { roster_entry_id: 12, tracklet_id: 7, start_s: 10, end_s: 20 }

  assert.equal(matchCaptionToWindow(window, [rebound], player), null)
  assert.equal(matchCaptionToWindow(window, [legacy], player), null)
  assert.equal(matchCaptionToWindow(window, [rebound, legacy, current], player), current)
})

test('captionPresentation demotes unconfirmed-player captions without an action chip', () => {
  assert.deepEqual(captionPresentation({ player_visible: true }), {
    kind: 'player',
    label: 'AI clip notes — qualitative',
    showActionType: true,
  })
  assert.deepEqual(captionPresentation({ player_visible: false }), {
    kind: 'context',
    label: 'clip context — player not confirmed in frame',
    showActionType: false,
  })
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
