import test from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizeNewsletterIds,
  formatSendPreviewSummary,
  formatDeleteSummary,
  resolveBulkActionPayload,
  formatBulkSelectionToast,
  computeReviewProgress,
  getReviewModalSizing,
} from '../src/lib/newsletter-admin.js'

test('normalizeNewsletterIds keeps unique positive ids in order of appearance', () => {
  const result = normalizeNewsletterIds([5, '3', 0, -1, 3, 5, 'foo', null])
  assert.deepEqual(result, [5, 3])
})

test('formatSendPreviewSummary reports successes and failures clearly', () => {
  const message = formatSendPreviewSummary({
    successIds: [7, 8],
    failureDetails: [
      { id: 9, error: new Error('boom') },
      { id: 10, error: { message: 'no auth' } },
    ],
  })
  assert.match(message, /Sent admin preview to 2 newsletters/i)
  assert.match(message, /failed for 2 newsletters: #9, #10/i)
})

test('formatDeleteSummary summarises deletions and errors', () => {
  const message = formatDeleteSummary({
    successIds: [2, 5, 8],
    failureDetails: [
      { id: 3, error: new Error('boom') },
      { id: 13, error: { message: 'denied' } },
    ],
  })
  assert.match(message, /Deleted 3 newsletters/i)
  assert.match(message, /failed to delete 2 newsletters: #3, #13/i)
})

test('resolveBulkActionPayload produces filter payload with exclusions', () => {
  const payload = resolveBulkActionPayload({
    useFilters: true,
    filterParams: { issue_start: '2025-09-01', issue_end: '2025-09-30', published_only: 'false' },
    totalMatched: 77,
    excludedIds: [9, '10', 9, 0],
    explicitIds: [],
  })

  assert.equal(payload.mode, 'filters')
  assert.deepEqual(payload.body.filter_params, {
    issue_start: '2025-09-01',
    issue_end: '2025-09-30',
    published_only: 'false',
  })
  assert.deepEqual(payload.body.exclude_ids, [9, 10])
  assert.equal(payload.body.expected_total, 77)
})

test('resolveBulkActionPayload falls back to explicit ids when filters are not active', () => {
  const payload = resolveBulkActionPayload({
    useFilters: false,
    filterParams: {},
    totalMatched: 0,
    excludedIds: [],
    explicitIds: [5, '6', 6, 'foo'],
  })

  assert.equal(payload.mode, 'ids')
  assert.deepEqual(payload.body.ids, [5, 6])
})

test('formatBulkSelectionToast summarises totals and exclusions', () => {
  const message = formatBulkSelectionToast({
    totalMatched: 77,
    totalExcluded: 5,
  })
  assert.equal(message, 'All 77 filtered newsletters selected. 5 are excluded.')
})

test('computeReviewProgress reports 1-indexed progress', () => {
  const progress = computeReviewProgress({ index: 11, total: 77 })
  assert.equal(progress, 'Newsletter 12 of 77')
})

test('getReviewModalSizing returns defaults with overrides', () => {
  const sizing = getReviewModalSizing({ minWidth: 600, minHeight: 420 })
  assert.equal(sizing.minWidth, 600)
  assert.equal(sizing.minHeight, 420)
  assert.ok(sizing.maxWidth >= sizing.minWidth)
  assert.ok(sizing.maxHeight >= sizing.minHeight)
  assert.equal(sizing.resize, 'both')
})
