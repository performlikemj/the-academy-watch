import test from 'node:test'
import assert from 'node:assert/strict'

import { scopeBody, scopeFromEntry, scopeValid, toggleScopeSquad } from '../src/lib/staff-access.js'

const grant = (extra) => ({ role: 'coach', all_squads: false, squad_ids: [11, 12, 13], ...extra })

test('a multi-squad grant loads as its full squad list and saves back unchanged', () => {
  const scope = scopeFromEntry(grant())
  assert.deepEqual(scope, { all: false, ids: [11, 12, 13] })
  assert.deepEqual(scopeBody('coach', scope), { all_squads: false, squad_ids: [11, 12, 13] })
})

test('changing only the role keeps every squad; removing one drops exactly that one', () => {
  const scope = scopeFromEntry(grant())
  assert.deepEqual(scopeBody('analyst', scope), { all_squads: false, squad_ids: [11, 12, 13] })
  assert.deepEqual(scopeBody('viewer', toggleScopeSquad(scope, 12)), { all_squads: false, squad_ids: [11, 13] })
  // Ticking a squad back in keeps the list sorted and free of duplicates.
  assert.deepEqual(toggleScopeSquad(toggleScopeSquad(scope, 12), '12').ids, [11, 12, 13])
})

test('"All squads" sends no squad list, and unticking it brings the selection back', () => {
  const scope = scopeFromEntry(grant())
  const all = { ...scope, all: true }
  assert.deepEqual(scopeBody('coach', all), { all_squads: true, squad_ids: [] })
  assert.deepEqual(scopeBody('coach', { ...all, all: false }), { all_squads: false, squad_ids: [11, 12, 13] })
  assert.deepEqual(scopeFromEntry(grant({ all_squads: true, squad_ids: [] })), { all: true, ids: [] })
})

test('club managers are whole-club whatever was ticked; switching back to a scoped role restores it', () => {
  const scope = scopeFromEntry(grant())
  assert.deepEqual(scopeBody('manager', scope), { all_squads: true, squad_ids: [] })
  assert.equal(scopeValid('manager', { all: false, ids: [] }), true)
  assert.deepEqual(scopeBody('coach', scope), { all_squads: false, squad_ids: [11, 12, 13] })
  assert.deepEqual(scopeFromEntry({ role: 'manager', all_squads: true, squad_ids: [] }), { all: true, ids: [] })
})

test('a scoped grant with no squads is never widened to all squads', () => {
  const scope = scopeFromEntry(grant({ squad_ids: [] }))
  assert.deepEqual(scope, { all: false, ids: [] })
  assert.equal(scopeValid('coach', scope), false)
  assert.equal(scopeValid('coach', toggleScopeSquad(scope, 11)), true)
  assert.equal(scopeValid('coach', { all: true, ids: [] }), true)
})
