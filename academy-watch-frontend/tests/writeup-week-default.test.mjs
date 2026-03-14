import test from 'node:test'
import assert from 'node:assert/strict'

import { getDefaultWriteupWeek } from '../src/pages/writer/gameweekDefaults.js'

test('defaults new writeup to the week before the current week', () => {
  const gameweeks = [
    {
      id: '2025-10-13_2025-10-19',
      start_date: '2025-10-13',
      end_date: '2025-10-19',
      is_current: false,
    },
    {
      id: '2025-10-06_2025-10-12',
      start_date: '2025-10-06',
      end_date: '2025-10-12',
      is_current: true,
    },
    {
      id: '2025-09-29_2025-10-05',
      start_date: '2025-09-29',
      end_date: '2025-10-05',
      is_current: false,
    },
  ]

  const selected = getDefaultWriteupWeek(gameweeks)

  assert.deepEqual(selected, {
    id: '2025-09-29_2025-10-05',
    start_date: '2025-09-29',
    end_date: '2025-10-05',
    is_current: false,
  })
})

test('falls back to the current week when no previous week exists', () => {
  const gameweeks = [
    {
      id: '2025-10-06_2025-10-12',
      start_date: '2025-10-06',
      end_date: '2025-10-12',
      is_current: true,
    },
  ]

  const selected = getDefaultWriteupWeek(gameweeks)

  assert.deepEqual(selected, {
    id: '2025-10-06_2025-10-12',
    start_date: '2025-10-06',
    end_date: '2025-10-12',
    is_current: true,
  })
})

test('uses the week before the one containing the reference date when current is missing', () => {
  const gameweeks = [
    {
      id: '2025-10-13_2025-10-19',
      start_date: '2025-10-13',
      end_date: '2025-10-19',
      is_current: false,
    },
    {
      id: '2025-10-06_2025-10-12',
      start_date: '2025-10-06',
      end_date: '2025-10-12',
      is_current: false,
    },
    {
      id: '2025-09-29_2025-10-05',
      start_date: '2025-09-29',
      end_date: '2025-10-05',
      is_current: false,
    },
  ]

  const selected = getDefaultWriteupWeek(gameweeks, new Date('2025-10-08T12:00:00Z'))

  assert.deepEqual(selected, {
    id: '2025-09-29_2025-10-05',
    start_date: '2025-09-29',
    end_date: '2025-10-05',
    is_current: false,
  })
})
