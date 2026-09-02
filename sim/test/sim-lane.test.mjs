import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { computeExitCode, computeTotals, shapeStepRecord } from '../lib/driver.mjs'
import { gradeRecords, normalizeGrade, parseGradeJSON, validateProposal } from '../lib/grade.mjs'
import { assertSyntheticFixture, selectSyntheticFixtureProgram, SYNTHETIC_BRIEF } from '../journeys/club-console.mjs'
import { createTeardownController, recordFixtureSeedJourneyError, resolveCredentials, signalExitCode } from '../run.mjs'

function journeys(...steps) {
  return [{ name: 'sample', steps }]
}

const cleanSimProgram = {
  id: 9,
  slug: 'academy-watch-synthetic-sim-fixture',
  country: 'Development',
}

const cleanSimRoster = {
  system_brief: { body: null },
  members: [{ brief: { body: null } }, { brief: { body: SYNTHETIC_BRIEF } }],
}

test('club-console guard refuses the bridge development program', () => {
  assert.throws(
    () => assertSyntheticFixture({ ...cleanSimProgram, slug: 'afc-yorkies-dev-fixture' }, cleanSimRoster),
    /dedicated synthetic sim fixture/,
  )
})

test('club-console guard refuses a sim program containing a real brief', () => {
  assert.throws(
    () => assertSyntheticFixture(cleanSimProgram, {
      ...cleanSimRoster,
      members: [{ brief: { body: 'A real coach brief must never enter the sim.' } }],
    }),
    /non-synthetic brief/,
  )
})

test('club-console guard allows only the clean dedicated sim fixture', () => {
  assert.deepEqual(assertSyntheticFixture(cleanSimProgram, cleanSimRoster), {
    program: cleanSimProgram,
    roster: cleanSimRoster,
  })
})

test('club-console failed program switch blanks the page before rethrowing', async () => {
  const calls = []
  const switchError = new Error('program switch timed out')
  const fixtureHeading = {
    waitFor: async ({ timeout }) => {
      calls.push(`heading:${timeout}`)
      throw switchError
    },
  }
  const programSwitcher = {
    waitFor: async () => { calls.push('switcher:wait') },
    click: async () => { calls.push('switcher:click') },
  }
  const option = { click: async () => { calls.push('option:click') } }
  const page = {
    getByRole: (role) => role === 'heading' ? fixtureHeading : option,
    getByLabel: () => programSwitcher,
    goto: async (url) => { calls.push(`goto:${url}`) },
  }

  await assert.rejects(selectSyntheticFixtureProgram(page, { name: 'Synthetic Sim' }), switchError)
  assert.deepEqual(calls, [
    'heading:3000',
    'switcher:wait',
    'switcher:click',
    'option:click',
    'heading:20000',
    'goto:about:blank',
  ])
})

test('fixture seed refusal is recorded as a club-console journey error', () => {
  const records = []
  recordFixtureSeedJourneyError(records, new Error('Synthetic sim fixture seeding failed: real brief'))
  assert.deepEqual(records, [{
    journey: 'club-console',
    id: 'journey-error',
    expectation: null,
    url: '',
    ok: false,
    shot: 'shots/club-console__journey-error.png',
    error: 'Synthetic sim fixture seeding failed: real brief',
  }])
})

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

test('vision grading requests pin the Ollama context', async (t) => {
  const reportDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sim-num-ctx-'))
  t.after(() => fs.rm(reportDir, { recursive: true, force: true }))
  await fs.mkdir(path.join(reportDir, 'shots'))
  await fs.writeFile(path.join(reportDir, 'shots', 'scout.png'), 'screenshot')

  const originalFetch = globalThis.fetch
  const originalNumCtx = process.env.SIM_NUM_CTX
  const requestBodies = []
  delete process.env.SIM_NUM_CTX
  globalThis.fetch = async (_url, init) => {
    const body = JSON.parse(init.body)
    requestBodies.push(body)
    const content = body.messages[0].content.includes('Expectation:')
      ? JSON.stringify({ verdict: 'pass', note: 'The page is ready.' })
      : JSON.stringify({
          persona: 'Academy scout',
          journey: 'Review a prospect',
          first_step: 'Open the Scout Desk',
        })
    return { ok: true, json: async () => ({ message: { content } }) }
  }
  t.after(() => {
    globalThis.fetch = originalFetch
    if (originalNumCtx === undefined) delete process.env.SIM_NUM_CTX
    else process.env.SIM_NUM_CTX = originalNumCtx
  })

  await gradeRecords([{
    journey: 'scout-desk',
    id: 'browse',
    expectation: 'The Scout Desk should load.',
    ok: true,
    shot: 'shots/scout.png',
  }], {
    enabled: true,
    reportDir,
    ollamaUrl: 'http://stubbed-model.invalid',
    model: 'stubbed-model',
  })

  assert.equal(requestBodies.length, 2)
  for (const body of requestBodies) assert.equal(body.options.num_ctx, 65536)
})

test('mechanical failure caps a passing model grade and preserves both notes', async (t) => {
  const reportDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sim-grade-'))
  t.after(() => fs.rm(reportDir, { recursive: true, force: true }))
  await fs.mkdir(path.join(reportDir, 'shots'))
  await fs.writeFile(path.join(reportDir, 'shots', 'reel-playback.png'), 'screenshot')

  const mechanicalError = 'The reel playhead did not advance.'
  const modelNote = 'The video player is shown with the play button and is ready to play.'
  const grading = await gradeRecords([{
    journey: 'player-reels',
    id: 'reel-playback',
    expectation: 'The reel should be playing.',
    ok: false,
    error: mechanicalError,
    shot: 'shots/reel-playback.png',
  }], {
    enabled: true,
    reportDir,
    ollamaUrl: 'http://stubbed-model.invalid',
    model: 'stubbed-model',
    chat: async ({ prompt }) => prompt.includes('Expectation:')
      ? JSON.stringify({ verdict: 'pass', note: modelNote })
      : JSON.stringify({
          persona: 'Academy scout',
          journey: 'Review a player reel',
          first_step: 'Open the player page',
        }),
  })

  const [record] = grading.records
  assert.equal(record.verdict, 'fail')
  assert.ok(record.note.indexOf(mechanicalError) < record.note.indexOf(modelNote))
  assert.deepEqual(computeTotals(journeys(record)), {
    steps: 1,
    ok: 0,
    pass: 0,
    concern: 0,
    fail: 1,
    ungraded: 0,
  })
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

test('teardown is ordered and once-only across repeated callers', async () => {
  const calls = []
  const controller = createTeardownController({
    stop: async () => { calls.push('stop') },
    close: async () => { calls.push('close') },
    exit: () => assert.fail('normal teardown must not exit'),
  })

  await Promise.all([controller.teardown(), controller.teardown()])
  await controller.teardown()

  assert.deepEqual(calls, ['stop', 'close'])
})

test('signal teardown uses conventional exit codes and a second signal exits immediately', async () => {
  const calls = []
  const exits = []
  let releaseStop
  const stopGate = new Promise((resolve) => { releaseStop = resolve })
  const controller = createTeardownController({
    stop: async () => {
      calls.push('stop')
      await stopGate
    },
    close: async () => { calls.push('close') },
    exit: (code) => { exits.push(code) },
  })

  const firstSignal = controller.handleSignal('SIGINT')
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(calls, ['stop'])

  await controller.handleSignal('SIGTERM')
  assert.deepEqual(exits, [143])

  releaseStop()
  await firstSignal
  assert.deepEqual(calls, ['stop', 'close'])
  assert.deepEqual(exits, [143, 130])
  assert.equal(signalExitCode('SIGINT'), 130)
  assert.equal(signalExitCode('SIGTERM'), 143)
})
