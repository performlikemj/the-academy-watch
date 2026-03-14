import test from 'node:test'
import assert from 'node:assert/strict'

import {
  seedSelectedButtonLabel,
  seedTop5ButtonLabel,
  buildMissingNamesParams,
  buildBackfillNamesPayload,
} from '../src/pages/admin/admin-newsletters-seeding.js'

test('seedSelectedButtonLabel reports progress with count', () => {
  assert.equal(seedSelectedButtonLabel({ isSeeding: true, selectionCount: 3 }), 'Seeding 3 teams...')
  assert.equal(seedSelectedButtonLabel({ isSeeding: true, selectionCount: 1 }), 'Seeding team...')
})

test('seedSelectedButtonLabel shows idle copy when not running', () => {
  assert.equal(seedSelectedButtonLabel({ isSeeding: false, selectionCount: 2 }), 'Seed Selected Teams')
})

test('seedTop5ButtonLabel reflects dry-run and busy states', () => {
  assert.equal(seedTop5ButtonLabel({ isSeeding: false, dryRun: true }), 'Preview Seeding')
  assert.equal(seedTop5ButtonLabel({ isSeeding: false, dryRun: false }), 'Seed Top-5 Leagues')
  assert.equal(seedTop5ButtonLabel({ isSeeding: true, dryRun: false }), 'Seeding top-5...')
})

test('buildMissingNamesParams coerces ids, enforces season for API ids, and propagates active flag', () => {
  const params = buildMissingNamesParams({ season: '2025', teamDbId: '17', activeOnly: false, limit: '50' })
  assert.deepEqual(params, {
    season: 2025,
    primary_team_db_id: 17,
    active_only: 'false',
    limit: 50,
  })

  assert.throws(() => buildMissingNamesParams({ teamApiId: '999' }), /season is required/i)
})

test('buildBackfillNamesPayload requires season and normalizes ids/dry-run flag', () => {
  const payload = buildBackfillNamesPayload({ season: '2024', teamApiId: '321', dryRun: true })
  assert.deepEqual(payload, {
    season: 2024,
    primary_team_api_id: 321,
    active_only: true,
    dry_run: true,
  })

  assert.throws(() => buildBackfillNamesPayload({ teamDbId: 3 }), /season is required/i)
})
