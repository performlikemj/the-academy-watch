import test from 'node:test'
import assert from 'node:assert/strict'

import {
  seedSelectedButtonLabel,
  seedTop5ButtonLabel,
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

// buildMissingNamesParams / buildBackfillNamesPayload tests removed with the
// helpers — the Missing Names feature they fed was deleted from
// AdminNewsletters (its APIService methods no longer exist).
