import assert from 'node:assert/strict'
import test from 'node:test'

import { computeExitCode, computeTotals, shapeStepRecord } from '../lib/driver.mjs'
import { normalizeGrade, parseGradeJSON, validateProposal } from '../lib/grade.mjs'
import { resolveCredentials } from '../run.mjs'

function journeys(...steps) {
  return [{ name: 'sample', steps }]
}

test('computeTotals counts actions and grading verdicts', () => {
  const result = computeTotals(journeys(
    { ok: true, verdict: 'pass' },
    { ok: true, verdict: 'concern' },
    { ok: false, verdict: 'fail' },
    { ok: true, verdict: 'ungraded' },
    { ok: true, verdict: 'observed' },
  ))
  assert.deepEqual(result, { steps: 5, ok: 4, pass: 1, concern: 1, fail: 1, ungraded: 1 })
})

test('computeExitCode fails on an action error', () => {
  assert.equal(computeExitCode(journeys({ ok: false, verdict: 'ungraded' })), 1)
})

test('computeExitCode fails on a fail verdict', () => {
  assert.equal(computeExitCode(journeys({ ok: true, verdict: 'fail' })), 1)
})

test('computeExitCode allows concerns and observed steps', () => {
  assert.equal(computeExitCode(journeys(
    { ok: true, verdict: 'concern' },
    { ok: true, verdict: 'observed' },
  )), 0)
})

test('shapeStepRecord normalizes expectation and optional fields', () => {
  assert.deepEqual(shapeStepRecord({
    journey: 'scout-desk',
    id: 'browse',
    expectation: '   ',
    url: 'http://localhost:5173/scout',
    ok: false,
    error: 'boom',
    shot: 'shots/scout-desk__browse.png',
    payload: { searched: true },
  }), {
    journey: 'scout-desk',
    id: 'browse',
    expectation: null,
    url: 'http://localhost:5173/scout',
    ok: false,
    error: 'boom',
    shot: 'shots/scout-desk__browse.png',
    payload: { searched: true },
  })
})

test('grader JSON parsing normalizes valid values', () => {
  assert.deepEqual(parseGradeJSON('{"verdict":" PASS ","note":"Looks complete."}'), {
    verdict: 'pass',
    note: 'Looks complete.',
  })
})

test('invalid grader JSON becomes ungraded', () => {
  assert.deepEqual(parseGradeJSON('not json'), {
    verdict: 'ungraded',
    note: 'The grader returned invalid JSON.',
  })
  assert.equal(normalizeGrade({ verdict: 'maybe', note: 'No.' }).verdict, 'ungraded')
})

test('proposal validation accepts only the complete shape', () => {
  assert.deepEqual(validateProposal({
    persona: 'Academy director',
    journey: 'Review emerging prospects',
    first_step: 'Open the Scout Desk',
  }), {
    persona: 'Academy director',
    journey: 'Review emerging prospects',
    first_step: 'Open the Scout Desk',
  })
  assert.equal(validateProposal({ persona: 'Scout', journey: '', first_step: 'Open scout' }), null)
  assert.equal(validateProposal({ persona: 'Scout', journey: 'Browse' }), null)
})

test('credential overrides win over backend dotenv values', () => {
  assert.deepEqual(resolveCredentials(
    { SECRET_KEY: 'file-secret', ADMIN_API_KEY: 'file-admin' },
    { SIM_SECRET_KEY: 'override-secret', SIM_ADMIN_API_KEY: 'override-admin' },
  ), {
    secretKey: { value: 'override-secret', source: 'SIM_SECRET_KEY override' },
    adminApiKey: { value: 'override-admin', source: 'SIM_ADMIN_API_KEY override' },
  })
})

test('ambient credential names are ignored when backend dotenv has values', () => {
  assert.deepEqual(resolveCredentials(
    { SECRET_KEY: 'file-secret', ADMIN_API_KEY: 'file-admin' },
    { SECRET_KEY: 'stale-shell-secret', ADMIN_API_KEY: 'stale-shell-admin' },
  ), {
    secretKey: { value: 'file-secret', source: 'backend .env' },
    adminApiKey: { value: 'file-admin', source: 'backend .env' },
  })
})

test('missing credential override and backend dotenv value is an error', () => {
  assert.throws(
    () => resolveCredentials({ ADMIN_API_KEY: 'file-admin' }, {}),
    /SECRET_KEY is required via SIM_SECRET_KEY or the backend \.env\./,
  )
  assert.throws(
    () => resolveCredentials({ SECRET_KEY: 'file-secret' }, {}),
    /ADMIN_API_KEY is required via SIM_ADMIN_API_KEY or the backend \.env\./,
  )
})
