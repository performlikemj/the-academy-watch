import test from 'node:test'
import assert from 'node:assert/strict'

import { mapLoansToPlayerOptions } from '../src/pages/writer/loanPlayerOptions.js'

test('maps loan API shape to player options', () => {
  const result = mapLoansToPlayerOptions([
    { player_id: 101, player_name: 'Amad Diallo' },
    { player: { id: 202, name: 'Hannibal Mejbri' } },
  ])

  assert.deepEqual(result, [
    { id: 101, name: 'Amad Diallo' },
    { id: 202, name: 'Hannibal Mejbri' },
  ])
})

test('filters out entries without ids and sorts alphabetically', () => {
  const result = mapLoansToPlayerOptions([
    { player_name: 'Missing Id' },
    { player_id: 7, player_name: 'Zidan Iqbal' },
    { player: { id: 6, name: 'Alvaro Fernandez' } },
  ])

  assert.deepEqual(result, [
    { id: 6, name: 'Alvaro Fernandez' },
    { id: 7, name: 'Zidan Iqbal' },
  ])
})
