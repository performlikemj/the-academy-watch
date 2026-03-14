import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeWriterTeams } from '../src/pages/writer/writerTeams.js'

test('normalizeWriterTeams returns parent assignments with direction metadata', () => {
  const input = [
    { team_id: 10, team_name: 'Manchester United' },
    { team_id: 20, team_name: 'Arsenal' },
  ]

  assert.deepEqual(normalizeWriterTeams(input), [
    {
      key: 'parent:10',
      team_id: 10,
      team_name: 'Manchester United',
      assignment_type: 'parent',
      direction: 'loaned_from',
      is_custom_team: false,
    },
    {
      key: 'parent:20',
      team_id: 20,
      team_name: 'Arsenal',
      assignment_type: 'parent',
      direction: 'loaned_from',
      is_custom_team: false,
    },
  ])
})

test('normalizeWriterTeams includes loan team assignments with loaned_to direction', () => {
  const input = {
    parent_club_assignments: [
      { team_id: 30, team_name: 'Ajax' },
    ],
    loan_team_assignments: [
      { loan_team_id: 99, loan_team_name: 'Falkirk' },
    ],
  }

  assert.deepEqual(normalizeWriterTeams(input), [
    {
      key: 'parent:30',
      team_id: 30,
      team_name: 'Ajax',
      assignment_type: 'parent',
      direction: 'loaned_from',
      is_custom_team: false,
    },
    {
      key: 'loan:99',
      team_id: 99,
      team_name: 'Falkirk',
      assignment_type: 'loan',
      direction: 'loaned_to',
      is_custom_team: false,
    },
  ])
})

test('normalizeWriterTeams falls back to empty array for unknown payloads', () => {
  assert.deepEqual(normalizeWriterTeams(null), [])
  assert.deepEqual(normalizeWriterTeams({}), [])
})
