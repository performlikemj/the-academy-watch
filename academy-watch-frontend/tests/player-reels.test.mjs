import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { APIService, nextWindowIndex } = await import('../src/lib/api.js')
const { formatSeconds } = await import('../src/lib/video-utils.js')

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

const reelHelpers = new Function('formatSeconds', `
  ${extractFunction('orderReelWindows')}
  ${extractFunction('matchCaptionToWindow')}
  ${extractFunction('captionPresentation')}
  ${extractFunction('playerReadEvidence')}
  ${extractFunction('formatBriefEvidenceTime')}
  ${extractFunction('briefChecksPresentation')}
  return { orderReelWindows, matchCaptionToWindow, captionPresentation, playerReadEvidence, formatBriefEvidenceTime, briefChecksPresentation }
`)(formatSeconds)

const { formatVoteSummary, mismatchBadge } = identityHelpers
const { orderReelWindows, matchCaptionToWindow, captionPresentation, playerReadEvidence, formatBriefEvidenceTime, briefChecksPresentation } = reelHelpers

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

test('club reel and evidence requests never opt into admin headers', async () => {
  const originalRequest = APIService.request
  const calls = []
  APIService.request = async (...args) => {
    calls.push(args)
    return {}
  }

  try {
    await APIService.getClubMatchReel(7, 42)
    await APIService.clubVideoMediaToken(7, 42)
    await APIService.getClubVideoTrackletCrops(42, 9, 'club-token')
    await APIService.getClubVideoTrackletBbox(42, 9, 'club-token')
    await APIService.setRosterMemberBrief(7, 51, 'Hold width')
    await APIService.setClubSystemBrief(7, 'Press together')
    assert.deepEqual(calls, [
      ['/club/7/matches/42/reel'],
      ['/club/7/matches/42/media-token'],
      ['/admin/video/matches/42/tracklets/9/crops?token=club-token'],
      ['/admin/video/matches/42/tracklets/9/bbox-track?token=club-token'],
      ['/club/7/roster/51/brief', { method: 'PUT', body: JSON.stringify({ body: 'Hold width' }) }],
      ['/club/7/system-brief', { method: 'PUT', body: JSON.stringify({ body: 'Press together' }) }],
    ])
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

test('captionPresentation marks a tracking-grounded note as verified', () => {
  assert.deepEqual(captionPresentation({
    caption: 'Checks into space before receiving.',
    grounded: true,
    box_t: 21.25,
    box: [100, 120, 220, 420],
    evidence_iou: 0.72,
    caption_model: 'qwen3-vl:8b',
  }), {
    kind: 'verified',
    label: 'AI clip notes — qualitative',
    showActionType: true,
    verificationLabel: 'verified on player',
    verificationDetail: 'checked against tracking at t=21.25s (overlap 0.72)',
  })
})

test('captionPresentation withholds an explicitly ungrounded note', () => {
  assert.deepEqual(captionPresentation({
    caption: 'This unsupported prose must never render.',
    grounded: false,
    box_t: 25,
    box: [50, 50, 75, 100],
    evidence_iou: 0.18,
    caption_model: 'qwen3-vl:8b',
  }), {
    kind: 'withheld',
    label: 'Tracking verification',
    showActionType: false,
    message: 'No verified note for this clip',
  })
})

test('captionPresentation withholds null prose whenever the new grounding fields are present', () => {
  assert.deepEqual(captionPresentation({
    caption: null,
    box_t: null,
    box: null,
    evidence_iou: null,
    caption_model: 'qwen3-vl:8b',
  }), {
    kind: 'withheld',
    label: 'Tracking verification',
    showActionType: false,
    message: 'No verified note for this clip',
  })
})

test('captionPresentation preserves legacy player and context payload behavior', () => {
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
  assert.equal(captionPresentation(null), null)
})

test('playerReadEvidence counts index-aligned evidence and leaves legacy notes unchanged', () => {
  assert.deepEqual(playerReadEvidence({
    observations: ['First read', 'Second read', 'Third read'],
    evidence: [{ t: 20, box: [1, 2, 3, 4], iou: 0.8 }, null, { t: 28, box: [5, 6, 7, 8], iou: 0.6 }],
  }), { verified: 2, total: 3 })
  assert.equal(playerReadEvidence({ observations: ['Legacy read'] }), null)
})

test('formatBriefEvidenceTime renders evidence timestamps as mm:ss', () => {
  assert.equal(formatBriefEvidenceTime(2520.2), '42:00')
  assert.equal(formatBriefEvidenceTime(65.6), '1:06')
  assert.equal(formatBriefEvidenceTime(-1), null)
  assert.equal(formatBriefEvidenceTime(null), null)
})

test('briefChecksPresentation joins current club lines only when the server hash matches', () => {
  const note = {
    jersey_number: 8,
    brief_checks: [
      { expectation_index: 1, brief_hash: 'matching-hash', verdict: 'evidence_found', t: 2520 },
      { expectation_index: 2, brief_hash: 'matching-hash', verdict: 'no_evidence' },
    ],
  }
  const matchRoster = [
    { jersey_number: 8, club_roster_member_id: null },
    { jersey_number: 8, club_roster_member_id: 51 },
  ]
  const clubRoster = [{
    id: 51,
    brief: { body: 'Hold width\nRecover inside', hash: 'matching-hash', lines: ['Hold width', 'Recover inside'] },
  }]

  assert.deepEqual(briefChecksPresentation(note, matchRoster, clubRoster), {
    changed: false,
    items: [
      { expectationIndex: 1, expectation: 'Hold width', verdict: 'evidence_found', time: '42:00' },
      { expectationIndex: 2, expectation: 'Recover inside', verdict: 'no_evidence', time: null },
    ],
  })
  assert.deepEqual(briefChecksPresentation(note, matchRoster, [{
    id: 51,
    brief: { body: 'New brief', hash: 'new-hash', lines: ['New brief'] },
  }]), {
    changed: true,
    items: [],
  })
})

test('briefChecksPresentation keeps admin output text-blind', () => {
  assert.deepEqual(briefChecksPresentation({
    brief_checks: [{ expectation_index: 3, brief_hash: 'private-hash', verdict: 'evidence_found', t: 2520 }],
  }), {
    changed: false,
    items: [{ expectationIndex: 3, label: 'Expectation 3 — evidence at 42:00', verdict: 'evidence_found' }],
  })
})

test('evidence_found without a finite timestamp never renders the opposite verdict', () => {
  const note = {
    jersey_number: 8,
    brief_checks: [{ expectation_index: 1, brief_hash: 'matching-hash', verdict: 'evidence_found' }],
  }
  const matchRoster = [{ jersey_number: 8, club_roster_member_id: 51 }]
  const clubRoster = [{ id: 51, brief: { body: 'Hold width', hash: 'matching-hash', lines: ['Hold width'] } }]

  assert.deepEqual(briefChecksPresentation(note, matchRoster, clubRoster), {
    changed: false,
    items: [{ expectationIndex: 1, expectation: 'Hold width', verdict: 'evidence_found', time: null }],
  })
  assert.deepEqual(briefChecksPresentation(note), {
    changed: false,
    items: [{
      expectationIndex: 1,
      label: 'Expectation 1 — evidence (time unavailable)',
      verdict: 'evidence_found',
    }],
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
