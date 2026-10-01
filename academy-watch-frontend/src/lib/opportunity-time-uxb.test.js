import test from 'node:test'
import assert from 'node:assert/strict'
import { whenRange } from './opportunity-time.js'

test('same-day opportunity range shows date and zone once, in venue zone', () => {
  assert.equal(whenRange('2026-10-17T10:30:00Z', '2026-10-17T13:00:00Z', 'Europe/London'), '17 Oct 2026, 11:30–14:00 BST (Europe/London)')
  assert.equal(whenRange('2026-10-17T23:30:00Z', '2026-10-18T00:30:00Z', 'Europe/London'), '18 Oct 2026, 00:30–01:30 BST (Europe/London)')
})
test('different local dates share one zone; DST offsets remain explicit', () => {
  assert.equal(whenRange('2026-10-17T22:00:00Z','2026-10-18T01:00:00Z','Europe/London'), '17 Oct 2026, 23:00 – 18 Oct 2026, 02:00 BST (Europe/London)')
  const dst = whenRange('2026-10-25T00:30:00Z','2026-10-25T01:30:00Z','Europe/London')
  assert.match(dst,/BST/); assert.match(dst,/GMT/)
})
test('range keeps defensive unsupported-zone and missing-date fallbacks', () => {
  assert.equal(whenRange(null, null, 'UTC'), 'Date to be arranged')
  assert.match(whenRange(Symbol('invalid'), '2026-10-18T01:00:00Z', 'UTC'), /^Date to be arranged/)
  assert.match(whenRange('invalid', '2026-10-18T01:00:00Z', 'UTC'), /^Date to be arranged/)
  assert.equal(whenRange('2026-10-17T10:30:00Z', '2026-10-17T13:00:00Z', 'Factory'), '17 Oct 2026, 10:30–13:00 UTC (UTC)')
})
