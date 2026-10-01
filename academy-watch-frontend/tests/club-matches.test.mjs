import assert from 'node:assert/strict'
import test from 'node:test'
import { sortClubMatches } from '../src/lib/club-matches.js'

test('match order follows dates, undated last and descending id ties without mutating input', () => {
  const rows = [{ id: 9, match_date: null }, { id: 3, match_date: '2026-09-27' }, { id: 4, match_date: '2026-09-27' }, { id: 12, match_date: '2026-09-20' }, { id: 10 }]
  assert.deepEqual(sortClubMatches(rows).map(row => row.id), [4, 3, 12, 10, 9])
  assert.deepEqual(rows.map(row => row.id), [9, 3, 4, 12, 10])
})
