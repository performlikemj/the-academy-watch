import test from 'node:test'
import assert from 'node:assert/strict'

import { buildPlayerNameUpdatePayload } from '../src/lib/admin-players.js'

test('buildPlayerNameUpdatePayload trims whitespace and rejects empty results', () => {
  assert.equal(
    buildPlayerNameUpdatePayload(42, '   '),
    null,
    'blank names should return null payload'
  )

  assert.equal(
    buildPlayerNameUpdatePayload(42, ' Player 42 '),
    null,
    'unchanged names should not trigger updates'
  )

  assert.deepEqual(
    buildPlayerNameUpdatePayload(42, '   New Name   ', 'Player 42'),
    { playerId: 42, payload: { name: 'New Name' } },
    'trimmed name should be returned with original id'
  )
})
