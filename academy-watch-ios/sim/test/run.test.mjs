import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const sim = fileURLToPath(new URL('../', import.meta.url))

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sim-preflight-'))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  const app = path.join(root, 'app worktree')
  const bin = path.join(root, 'bin')
  const temporary = path.join(root, 'tmp')
  for (const dir of [bin, temporary, path.join(app, 'AcademyWatch.xcodeproj')]) {
    fs.mkdirSync(dir, { recursive: true })
  }
  const fake = fs.readFileSync(path.join(sim, 'test/fake-tools.cjs'), 'utf8')
  for (const tool of ['xcodebuild', 'xcrun', 'plutil']) {
    fs.writeFileSync(path.join(bin, tool), `#!${process.execPath}\n${fake}`, { mode: 0o755 })
  }
  fs.symlinkSync(process.execPath, path.join(bin, 'node'))
  const journey = {
    version: '1.2', name: 'preflight',
    fixture_evidence: {
      offered_inputs: [{ claim: 'fixture', source: 'fixture:1' }],
      server_state: [], server_state_reason: 'offline',
      layout: [{ claim: 'fixture', source: 'fixture:1' }],
      preflight: { kind: 'none', note: 'offline' },
    },
    steps: [{ id: 'checkpoint', checkpoint: true, expectation: '', action: { launch: {} } }],
  }
  fs.writeFileSync(path.join(app, 'journey.json'), JSON.stringify(journey))
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !key.startsWith('SIM_') && !key.startsWith('HARNESS_')))
  Object.assign(env, {
    PATH: `${bin}:/usr/bin:/bin`, TMPDIR: temporary,
    SIM_APP_ROOT: app, SIM_SCHEME: 'AcademyWatchExperience', SIM_UI_TEST_TARGET: 'AcademyWatchUITests',
    SIM_TEST_ROOT: root,
  })
  function run(extra = {}) {
    fs.writeFileSync(path.join(root, 'calls.jsonl'), '')
    const result = spawnSync('/bin/bash', [path.join(sim, 'run.sh'), '--journey', 'journey.json',
      '--out', path.join(root, 'reports'), '--no-grade'], {
      env: { ...env, ...extra }, encoding: 'utf8', timeout: 15000, killSignal: 'SIGKILL',
    })
    const output = result.stdout + result.stderr
    assert.ifError(result.error)
    assert.equal(result.status, 2, output)
    assert.deepEqual(fs.readdirSync(temporary), [], 'temporary directory must be cleaned')
    const calls = fs.readFileSync(path.join(root, 'calls.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse)
    return { calls, output, xcode: calls.filter((call) => call.tool === 'xcodebuild') }
  }
  return { app, journey, run }
}

test('canonical iOS 27.0 runtime reaches the build boundary', (t) => {
  const result = fixture(t).run()
  assert.match(result.output, /Destination source: pack canonical/)
  assert.match(result.output, /Destination: platform=iOS Simulator,name=iPhone 17,OS=27\.0/)
  assert.equal(result.xcode.length, 1)
  assert.match(result.output, /build-for-testing failed/)
})

test('a hung simctl runtimes query is killed and retried', (t) => {
  const started = Date.now()
  const result = fixture(t).run({ SIM_TEST_SIMCTL_HANG: 'list runtimes:first', SIM_SIMCTL_TIMEOUT: '1' })
  assert.ok(Date.now() - started < 15000)
  assert.match(result.output, /simctl list runtimes attempt 1 timed out after 1s/)
  assert.equal(result.calls.filter((call) => call.args.join(' ') === 'simctl list runtimes').length, 2)
  assert.equal(result.xcode.length, 1)
  assert.match(result.output, /build-for-testing failed/)
})

for (const query of ['list runtimes', 'list devices']) {
  test(`a simctl ${query} query that never answers exits 2 within the bound`, (t) => {
    const f = fixture(t)
    if (query === 'list devices') {
      f.journey.preconditions = [{ kind: 'push', bundle_id: 'fake', payload: {} }]
      fs.writeFileSync(path.join(f.app, 'journey.json'), JSON.stringify(f.journey))
    }
    const started = Date.now()
    const result = f.run({ SIM_TEST_SIMCTL_HANG: `${query}:always`, SIM_SIMCTL_TIMEOUT: '1', SIM_SIMCTL_ATTEMPTS: '2' })
    assert.ok(Date.now() - started < 15000)
    assert.ok(result.output.includes(`run.sh: simctl ${query} did not answer after 2 attempts`), result.output)
    assert.ok(!result.output.includes('runtime is not installed'))
    assert.ok(result.output.includes(`simctl ${query} attempt 2 timed out after 1s`), result.output)
    assert.equal(result.xcode.length, 0)
  })
}
