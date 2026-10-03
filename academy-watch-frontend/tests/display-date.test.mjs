import assert from 'node:assert/strict'
import test from 'node:test'
import { formatDisplayDate } from '../src/lib/display-date.js'

for (const timezone of ['America/Los_Angeles', 'Asia/Tokyo', 'Europe/London']) {
  test(`UK dates keep date-only calendar day in ${timezone}`, () => {
    const old = process.env.TZ
    try {
      process.env.TZ = timezone
      assert.equal(formatDisplayDate('2026-09-27'), '27 Sept 2026')
      assert.equal(formatDisplayDate('2026-02-30'), null)
    } finally {
      if (old === undefined) delete process.env.TZ
      else process.env.TZ = old
    }
  })
}

test('naive Flask timestamps are UTC; time is explicit and no seconds clutter', () => {
  const old = process.env.TZ
  try {
    process.env.TZ = 'Europe/London'
    assert.equal(formatDisplayDate('2026-09-24T03:12:00', { withTime: true }), '24 Sept 2026, 04:12')
    assert.equal(formatDisplayDate('2026-09-24T03:12:00Z', { withTime: true }), '24 Sept 2026, 04:12')
    assert.equal(formatDisplayDate('2026-09-24T04:12:00+01:00'), '24 Sept 2026')
    assert.equal(formatDisplayDate('2026-09-27', { withTime: true }), '27 Sept 2026')
  } finally {
    if (old === undefined) delete process.env.TZ
    else process.env.TZ = old
  }
})

test('missing and invalid dates retain each view’s empty state', () => {
  for (const value of [null, undefined, '', 'bogus', '2026-15-42']) {
    assert.equal(formatDisplayDate(value), null)
    assert.equal(formatDisplayDate(value, { fallback: '—' }), '—')
  }
})
