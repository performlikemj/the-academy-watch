import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildSelectUpdates,
  mergeCollapseState,
  toggleCollapseState,
  sandboxCardHeaderClasses,
  sofascoreRowKey,
  buildSofascoreUpdatePayload,
} from '../src/lib/admin-sandbox.js'

const params = [
  { name: 'season', type: 'number' },
  { name: 'team_name', type: 'select' },
  { name: 'team_db_id', type: 'hidden' },
  { name: 'api_team_id', type: 'hidden' },
]

test('selecting a team copies metadata into hidden fields', () => {
  const option = { value: 'Arsenal', team_db_id: 123, team_id: 456 }

  const updates = buildSelectUpdates(params[1], option, params)

  assert.deepEqual(updates, {
    team_name: 'Arsenal',
    team_db_id: '123',
    api_team_id: '456',
  })
})


test('clearing the selection removes the dependent values', () => {
  const updates = buildSelectUpdates(params[1], null, params)

  assert.deepEqual(updates, {
    team_name: '',
    team_db_id: '',
    api_team_id: '',
  })
})

test('mergeCollapseState marks all tasks collapsed by default', () => {
  const previous = {}
  const tasks = [{ task_id: 'alpha' }, { task_id: 'beta' }]

  const merged = mergeCollapseState(previous, tasks)

  assert.deepEqual(merged, { alpha: true, beta: true })
})

test('mergeCollapseState keeps existing overrides and prunes missing tasks', () => {
  const previous = { alpha: false, beta: true, stale: false }
  const tasks = [{ task_id: 'alpha' }, { task_id: 'gamma' }]

  const merged = mergeCollapseState(previous, tasks)

  assert.deepEqual(merged, { alpha: false, gamma: true })
})

test('toggleCollapseState flips the specified entry without mutating the original object', () => {
  const original = { alpha: true, beta: true }

  const next = toggleCollapseState(original, 'alpha')

  assert.deepEqual(next, { alpha: false, beta: true })
  assert.notEqual(next, original)
  assert.deepEqual(original, { alpha: true, beta: true })
})

test('sandboxCardHeaderClasses applies sticky positioning with nav offset', () => {
  const classes = sandboxCardHeaderClasses()

  assert.ok(classes.includes('sticky'), 'expected sticky positioning')
  assert.ok(classes.includes('top-16'), 'expected top offset to avoid nav overlap')
  assert.ok(classes.includes('bg-white'), 'expected solid background for readability')
})

test('sofascoreRowKey prefers player id but falls back to supplemental id', () => {
  assert.equal(sofascoreRowKey({ player_id: 555 }), 'player-555')
  assert.equal(sofascoreRowKey({ player_id: null, supplemental_id: 42, is_supplemental: true }), 'supp-42')
  assert.match(sofascoreRowKey({}), /^row-/)
})

test('buildSofascoreUpdatePayload includes supplemental id when player id missing', () => {
  const playerRow = { player_id: 777, player_name: 'Core Row' }
  const supplementalRow = { supplemental_id: 12, player_name: 'Supp Row', is_supplemental: true }

  assert.deepEqual(buildSofascoreUpdatePayload(playerRow, '1101989'), {
    player_id: 777,
    sofascore_id: '1101989',
    player_name: 'Core Row',
  })

  assert.deepEqual(buildSofascoreUpdatePayload(supplementalRow, '1101989'), {
    supplemental_id: 12,
    sofascore_id: '1101989',
    player_name: 'Supp Row',
  })
})
