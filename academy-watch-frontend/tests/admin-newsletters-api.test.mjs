import test from 'node:test'
import assert from 'node:assert/strict'

import {
  NEWSLETTER_GENERATE_ENDPOINT,
  NEWSLETTER_GENERATE_ALL_ENDPOINT,
  buildGenerateTeamRequest,
  buildGenerateAllRequest,
  buildSeedTeamRequest,
  buildSeedTop5Request,
  LOANS_SEED_TEAM_ENDPOINT,
} from '../src/pages/admin/admin-newsletters-api.js'

test('buildGenerateTeamRequest targets single-team endpoint with correct payload', () => {
  const req = buildGenerateTeamRequest({ teamId: 42, targetDate: '2025-11-03' })
  assert.equal(req.endpoint, NEWSLETTER_GENERATE_ENDPOINT)
  assert.equal(req.options.method, 'POST')
  const body = JSON.parse(req.options.body)
  assert.deepEqual(body, { team_id: 42, target_date: '2025-11-03', force_refresh: false })
  assert.equal(req.admin, true, 'admin headers should be sent for privileged generation')
})

test('buildGenerateAllRequest uses weekly-all endpoint and forwards date', () => {
  const req = buildGenerateAllRequest({ targetDate: '2025-11-03' })
  assert.equal(req.endpoint, NEWSLETTER_GENERATE_ALL_ENDPOINT)
  assert.equal(req.options.method, 'POST')
  const body = JSON.parse(req.options.body)
  assert.deepEqual(body, { target_date: '2025-11-03' })
  assert.equal(req.admin, true)
})

test('buildSeedTeamRequest targets seed-team endpoint with numeric ids and season', () => {
  const req = buildSeedTeamRequest({ teamId: '101', season: '2025', dryRun: true, overwrite: false })
  assert.equal(req.endpoint, LOANS_SEED_TEAM_ENDPOINT)
  assert.equal(req.options.method, 'POST')
  const body = JSON.parse(req.options.body)
  assert.deepEqual(body, {
    season: 2025,
    team_db_id: 101,
    dry_run: true,
    overwrite: false,
  })
  assert.equal(req.admin, true)
})

test('buildSeedTop5Request targets seed-top5 endpoint and uses season field', () => {
  const req = buildSeedTop5Request({ season: '2025', dryRun: true, overwrite: true })
  assert.equal(req.endpoint, '/admin/loans/seed-top5')
  assert.equal(req.options.method, 'POST')
  const body = JSON.parse(req.options.body)
  assert.deepEqual(body, {
    season: 2025,
    dry_run: true,
    overwrite: true,
  })
  assert.equal(req.admin, true)
})
