import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { EventEmitter } from 'node:events'
import fs from 'node:fs/promises'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { computeExitCode, computeTotals, shapeStepRecord } from '../lib/driver.mjs'
import { gradeRecords, normalizeGrade, parseGradeJSON, validateProposal } from '../lib/grade.mjs'
import { assertSyntheticFixture, selectSyntheticFixtureProgram, SYNTHETIC_BRIEF } from '../journeys/club-console.mjs'
import { bootServers, createReportWorkspace, createTeardownController, finishReport, frontendCommand, recordFixtureSeedJourneyError, refuseListener, resolveCredentials, resolvePaths, signalExitCode } from '../run.mjs'
import { viteOptions } from '../lib/vite-server.mjs'

const simDir = fileURLToPath(new URL('../', import.meta.url))
const repoDir = path.resolve(simDir, '..')

async function tempDirectory(t) {
  const dir = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'sim-nightly-')))
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  return dir
}

test('unset path overrides preserve report/cache defaults and derive Python from the runner', () => {
  assert.deepEqual(resolvePaths({}), {
    reportRoot: path.join(repoDir, 'sim', 'report'),
    python: path.join(repoDir, '.loan', 'bin', 'python'),
    viteCacheDir: undefined,
  })
  assert.deepEqual(frontendCommand({ hostname: 'localhost', port: '5173' }), {
    command: 'pnpm', args: ['dev', '--host', 'localhost', '--port', '5173', '--strictPort'],
  })
})

test('absolute report/cache overrides and SIM_PYTHON take precedence', async (t) => {
  const dir = await tempDirectory(t)
  assert.deepEqual(resolvePaths({ SIM_REPORT_DIR: dir, SIM_VITE_CACHE_DIR: dir, SIM_PYTHON: '/custom/python' }), {
    reportRoot: dir, viteCacheDir: dir, python: '/custom/python',
  })
  for (const key of ['SIM_REPORT_DIR', 'SIM_VITE_CACHE_DIR']) {
    for (const value of ['relative/path', '']) {
      assert.throws(() => resolvePaths({ [key]: value }), new RegExp(`${key} must be an absolute path`))
    }
  }
})

test('external cache launch uses Vite API cacheDir while retaining config discovery and strict port', async (t) => {
  const dir = await tempDirectory(t)
  const launch = frontendCommand({ hostname: '127.0.0.1', port: '5173', viteCacheDir: dir })
  assert.equal(launch.command, process.execPath)
  assert.deepEqual(launch.args, [path.join(simDir, 'lib', 'vite-server.mjs'), '127.0.0.1', '5173'])
  assert.deepEqual(viteOptions('127.0.0.1', '5173', dir), {
    root: `${path.join(repoDir, 'academy-watch-frontend')}/`,
    cacheDir: dir,
    server: { host: '127.0.0.1', port: 5173, strictPort: true },
  })
  assert.throws(() => viteOptions('localhost', '5173', 'relative'), /absolute path/)
})

for (const fatal of [false, true]) {
  test(`external report root publishes complete artifacts atomically after a real step (fatal=${fatal})`, async (t) => {
    const root = path.join(await tempDirectory(t), 'external', 'reports')
    const runAt = '2026-09-10T01:02:03.456Z'
    const stamp = runAt.replace(/[:.]/g, '-')
    const workspace = await createReportWorkspace(resolvePaths({ SIM_REPORT_DIR: root }).reportRoot, stamp)
    t.after(workspace.discard)
    await fs.mkdir(workspace.shotsDir)
    await fs.writeFile(path.join(workspace.shotsDir, 'step.png'), 'screenshot')
    assert.equal(path.dirname(workspace.reportDir), root)
    assert.deepEqual((await fs.readdir(root)).filter((name) => !name.startsWith('.')), [])
    const publish = workspace.publish
    workspace.publish = async () => {
      await assert.rejects(fs.stat(workspace.finalDir), { code: 'ENOENT' })
      for (const name of ['steps.json', 'report.json', 'shots/step.png']) {
        assert.ok((await fs.stat(path.join(workspace.reportDir, name))).isFile())
      }
      await publish()
    }
    const records = [shapeStepRecord({
      journey: 'scout-desk', id: 'browse', expectation: 'Loaded', ok: true,
      url: 'http://localhost:5173', shot: 'shots/step.png',
    })]
    assert.equal(await finishReport({
      workspace, records, executedSteps: 1, runAt, baseUrl: 'http://localhost:5173', gradeEnabled: false,
      fatalError: fatal ? new Error('late failure') : null,
    }), fatal ? 1 : 0)
    assert.deepEqual(await fs.readdir(root), [stamp])
    assert.deepEqual(JSON.parse(await fs.readFile(path.join(workspace.finalDir, 'steps.json'))), records)
    const report = JSON.parse(await fs.readFile(path.join(workspace.finalDir, 'report.json')))
    assert.equal(report.app, 'loanarmy-web')
    assert.equal(report.totals.steps, 1)
    assert.equal(report.journeys[0].steps[0].verdict, 'ungraded')
    assert.equal(report.run_error, fatal ? 'late failure' : undefined)
    assert.equal(await fs.readFile(path.join(workspace.finalDir, 'shots/step.png'), 'utf8'), 'screenshot')
  })
}

// Copy only sim sources into a fake checkout: subprocess tests cannot read the
// real backend dotenv, seed a database, launch apps, or reach external services.
async function runnerFixture(t) {
  const dir = await tempDirectory(t)
  await fs.mkdir(path.join(dir, 'sim'))
  await fs.copyFile(path.join(simDir, 'run.mjs'), path.join(dir, 'sim', 'run.mjs'))
  for (const name of ['lib', 'journeys']) {
    await fs.cp(path.join(simDir, name), path.join(dir, 'sim', name), { recursive: true })
  }
  await fs.mkdir(path.join(dir, 'academy-watch-backend'))
  const env = {
    PATH: process.env.PATH,
    SIM_SECRET_KEY: 'synthetic-test-secret', SIM_ADMIN_API_KEY: 'synthetic-test-admin',
    SIM_GRADE: '0', SIM_EXTERNAL: '1',
  }
  return { dir, env }
}

for (const override of [false, true]) {
  test(`fatal pre-journey CLI error exits non-zero without publishing output (override=${override})`, async (t) => {
    const { dir, env } = await runnerFixture(t)
    const root = override ? path.join(dir, 'external-reports') : path.join(dir, 'sim', 'report')
    if (override) env.SIM_REPORT_DIR = root
    // Missing repo-relative Python fails before fixture seeding/server startup.
    const result = spawnSync(process.execPath, [path.join(dir, 'sim', 'run.mjs')], {
      cwd: os.tmpdir(), env, encoding: 'utf8', timeout: 10_000,
    })
    assert.ifError(result.error)
    assert.equal(result.status, 1, result.stderr)
    assert.match(result.stderr, /Admin bearer minting failed/)
    assert.deepEqual(await fs.readdir(root), [])
    if (override) await assert.rejects(fs.stat(path.join(dir, 'sim', 'report')), { code: 'ENOENT' })
  })
}

test('fixture-seeding fatal error with a synthetic record still publishes no report', async (t) => {
  const { dir, env } = await runnerFixture(t)
  const python = path.join(dir, '.loan', 'bin', 'python')
  await fs.mkdir(path.dirname(python), { recursive: true })
  await fs.writeFile(python, '#!/bin/sh\nif [ "$1" = "-c" ]; then\n  echo synthetic-token\nelse\n  echo synthetic-seed-refusal >&2\n  exit 1\nfi\n', { mode: 0o755 })
  const result = spawnSync(process.execPath, [path.join(dir, 'sim', 'run.mjs')], {
    cwd: os.tmpdir(), env, encoding: 'utf8', timeout: 10_000,
  })
  assert.ifError(result.error)
  assert.equal(result.status, 1, result.stderr)
  assert.match(result.stderr, /Synthetic sim fixture seeding failed/)
  assert.match(result.stderr, /synthetic-seed-refusal/)
  assert.deepEqual(await fs.readdir(path.join(dir, 'sim', 'report')), [])
})

async function loopbackListener(t) {
  const server = net.createServer((socket) => socket.end())
  try {
    await new Promise((resolve, reject) => {
      server.once('error', reject)
      server.listen(0, '127.0.0.1', resolve)
    })
  } catch (error) {
    if (['EPERM', 'EACCES'].includes(error.code)) {
      t.skip(`Sandbox-only: loopback bind denied (${error.code})`)
      return null
    }
    throw error
  }
  t.after(() => new Promise((resolve, reject) => {
    if (!server.listening) return resolve()
    server.close((error) => error ? reject(error) : resolve())
  }))
  return server
}

for (const occupiedPort of [5001, 5173]) {
  test(`default port ${occupiedPort} refusal prevents spawning (mocked TCP)`, async (t) => {
    const checked = []
    const sockets = []
    t.mock.method(net, 'createConnection', ({ host, port }) => {
      assert.equal(host, '127.0.0.1')
      checked.push(port)
      const socket = new EventEmitter()
      socket.setTimeout = () => socket
      socket.destroy = () => { socket.destroyed = true }
      sockets.push(socket)
      queueMicrotask(() => {
        if (port === occupiedPort) socket.emit('connect')
        else socket.emit('error', Object.assign(new Error('refused'), { code: 'ECONNREFUSED' }))
      })
      return socket
    })
    const processes = []
    await assert.rejects(bootServers({
      baseUrl: 'http://localhost:5173', backendPort: '5001',
      python: '/must-not-spawn/python', backendEnv: {}, secrets: [], processes,
    }), new RegExp(`Port ${occupiedPort} already has a listener`))
    assert.deepEqual(checked, occupiedPort === 5001 ? [5001] : [5001, 5173])
    assert.deepEqual(processes, [])
    assert.ok(sockets.every((socket) => socket.destroyed))
  })
}

for (const role of ['backend', 'frontend']) {
  test(`occupied ${role} port is refused before spawning; foreign listener survives`, async (t) => {
    const server = await loopbackListener(t)
    if (!server) return
    const busyPort = server.address().port
    const freeServer = await loopbackListener(t)
    if (!freeServer) return
    const freePort = freeServer.address().port
    await new Promise((resolve) => freeServer.close(resolve))
    await refuseListener(freePort)
    const processes = []
    await assert.rejects(bootServers({
      baseUrl: `http://127.0.0.1:${role === 'frontend' ? busyPort : freePort}`,
      backendPort: String(role === 'backend' ? busyPort : freePort),
      python: '/must-not-spawn/python', backendEnv: {}, secrets: [], processes,
    }), new RegExp(`Port ${busyPort} already has a listener on 127\\.0\\.0\\.1; refusing to start`))
    assert.deepEqual(processes, [])
    assert.equal(server.listening, true)
    // A second successful TCP connection proves the listener remains usable.
    await assert.rejects(refuseListener(busyPort), new RegExp(`Port ${busyPort} already has a listener`))
  })
}

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
