#!/usr/bin/env node

import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import { computeExitCode, computeTotals, createDriver, ensureShotDirectory, loadChromium, shapeStepRecord } from './lib/driver.mjs'
import { gradeRecords } from './lib/grade.mjs'
import scoutDesk from './journeys/scout-desk.mjs'
import playerReels from './journeys/player-reels.mjs'
import clubConsole from './journeys/club-console.mjs'
import contactRail from './journeys/contact-rail.mjs'

const simDir = path.dirname(fileURLToPath(import.meta.url))
const repoDir = path.resolve(simDir, '..')
const backendDir = path.join(repoDir, 'academy-watch-backend')
const frontendDir = path.join(repoDir, 'academy-watch-frontend')
const journeyModules = [scoutDesk, playerReels, clubConsole, contactRail]
const journeyNames = ['scout-desk', 'player-reels', 'club-console', 'contact-rail']

function enabled(value, fallback = true) {
  if (value === undefined) return fallback
  return value === '1' || value.toLowerCase() === 'true'
}

function parseDotenv(source) {
  const result = {}
  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const match = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/)
    if (!match) continue
    let value = match[2].trim()
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      const quote = value[0]
      value = value.slice(1, -1)
      if (quote === '"') {
        value = value.replace(/\\n/g, '\n').replace(/\\r/g, '\r').replace(/\\t/g, '\t').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
      }
    } else {
      value = value.replace(/\s+#.*$/, '').trim()
    }
    result[match[1]] = value
  }
  return result
}

function present(value) {
  return typeof value === 'string' && value.length > 0
}

export function resolveCredentials(fromFile = {}, ambient = {}) {
  function resolve(fileKey, overrideKey) {
    if (present(ambient[overrideKey])) {
      return { value: ambient[overrideKey], source: `${overrideKey} override` }
    }
    if (present(fromFile[fileKey])) {
      return { value: fromFile[fileKey], source: 'backend .env' }
    }
    throw new Error(`${fileKey} is required via ${overrideKey} or the backend .env.`)
  }

  return {
    secretKey: resolve('SECRET_KEY', 'SIM_SECRET_KEY'),
    adminApiKey: resolve('ADMIN_API_KEY', 'SIM_ADMIN_API_KEY'),
  }
}

async function backendEnvironment() {
  const envPath = path.join(backendDir, '.env')
  let fromFile = {}
  try {
    fromFile = parseDotenv(await fs.readFile(envPath, 'utf8'))
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const credentials = resolveCredentials(fromFile, process.env)
  return {
    env: {
      ...fromFile,
      ...process.env,
      SECRET_KEY: credentials.secretKey.value,
      ADMIN_API_KEY: credentials.adminApiKey.value,
    },
    credentials,
  }
}

function mintAuth({ python, secretKey, adminEmail }) {
  const script = [
    'import os',
    'from itsdangerous import URLSafeTimedSerializer',
    'serializer = URLSafeTimedSerializer(secret_key=os.environ["SIM_MINT_SECRET"], salt="user-auth")',
    'print(serializer.dumps({"email": os.environ["SIM_MINT_EMAIL"], "role": "admin"}))',
  ].join('; ')
  const result = spawnSync(python, ['-c', script], {
    cwd: backendDir,
    env: { ...process.env, SIM_MINT_SECRET: secretKey, SIM_MINT_EMAIL: adminEmail },
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  })
  if (result.status !== 0 || !result.stdout.trim()) {
    throw new Error('Admin bearer minting failed with the configured SIM_PYTHON.')
  }
  return result.stdout.trim()
}

function seedSimFixture({ python, backendEnv, adminEmail, secrets }) {
  const result = spawnSync(
    python,
    ['scripts/dev/seed_sim_club_fixture.py', '--manager-email', adminEmail],
    {
      cwd: backendDir,
      env: {
        ...backendEnv,
        ALLOW_SIM_FIXTURE_SEED: '1',
        FLASK_DEBUG: 'false',
        SKIP_API_HANDSHAKE: '1',
      },
      encoding: 'utf8',
      maxBuffer: 4 * 1024 * 1024,
    },
  )
  if (result.status !== 0) {
    const detail = redact(`${result.stdout || ''}\n${result.stderr || ''}`.trim(), secrets)
    throw new Error(`Synthetic sim fixture seeding failed.${detail ? `\n${detail}` : ''}`)
  }
  const summary = result.stdout.trim().split(/\r?\n/).filter(Boolean).at(-1)
  if (summary) console.log(summary)
}

export function recordFixtureSeedJourneyError(records, error) {
  const message = error instanceof Error ? error.message : String(error)
  records.push(shapeStepRecord({
    journey: 'club-console',
    id: 'journey-error',
    expectation: null,
    url: '',
    ok: false,
    error: message,
    shot: 'shots/club-console__journey-error.png',
  }))
}

function redact(text, secrets) {
  let clean = String(text)
  for (const secret of secrets.filter(Boolean)) clean = clean.split(secret).join('[REDACTED]')
  return clean
}

function spawnManaged(name, command, args, options, secrets) {
  // A dedicated process group lets teardown stop pnpm and only the children it
  // created, without discovering or killing unrelated listeners by port.
  const child = spawn(command, args, { ...options, detached: true, stdio: ['ignore', 'pipe', 'pipe'] })
  let logTail = ''
  const collect = (chunk) => {
    logTail = `${logTail}${chunk}`.slice(-16_000)
  }
  child.stdout.on('data', collect)
  child.stderr.on('data', collect)
  child.on('error', collect)
  return {
    name,
    child,
    tail: () => redact(logTail, secrets),
  }
}

async function stopManaged(processes) {
  for (const managed of [...processes].reverse()) {
    const child = managed.child
    if (child.exitCode !== null || child.signalCode !== null) continue
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch (error) {
      if (error.code !== 'ESRCH') throw error
    }
    await Promise.race([
      new Promise((resolve) => child.once('exit', resolve)),
      new Promise((resolve) => setTimeout(resolve, 5_000)),
    ])
    try {
      process.kill(-child.pid, 0)
      process.kill(-child.pid, 'SIGKILL')
    } catch (error) {
      if (error.code !== 'ESRCH') throw error
    }
  }
}

async function waitForHealth(url, managed, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs
  // This avoids accepting an unrelated server already bound to the same port
  // during the short window before the just-spawned process reports EADDRINUSE.
  const earliestHealthy = Date.now() + (managed ? 1_000 : 0)
  let lastError = 'not ready'
  while (Date.now() < deadline) {
    if (managed && (managed.child.exitCode !== null || managed.child.signalCode !== null)) {
      throw new Error(`${managed.name} exited before becoming healthy.\n${managed.tail()}`)
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(3_000) })
      if (response.ok && Date.now() >= earliestHealthy) {
        await new Promise((resolve) => setTimeout(resolve, 100))
        if (managed && (managed.child.exitCode !== null || managed.child.signalCode !== null)) continue
        return
      }
      lastError = `HTTP ${response.status}`
    } catch (error) {
      lastError = error.message
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  const tail = managed ? `\n${managed.tail()}` : ''
  throw new Error(`Timed out waiting for ${url}: ${lastError}${tail}`)
}

async function bootServers({ baseUrl, backendPort, python, backendEnv, secrets, processes }) {
  const parsedBase = new URL(baseUrl)
  if (parsedBase.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(parsedBase.hostname)) {
    throw new Error('Self-boot requires SIM_BASE_URL to use http://localhost or http://127.0.0.1; use SIM_EXTERNAL=1 otherwise.')
  }
  const frontendPort = parsedBase.port || '80'
  const backend = spawnManaged(
    'backend',
    python,
    [
      '-m',
      'flask',
      '--app',
      'src.main',
      'run',
      '--host',
      '127.0.0.1',
      '--port',
      backendPort,
      '--no-debugger',
      '--no-reload',
    ],
    {
      cwd: backendDir,
      env: {
        ...backendEnv,
        API_USE_STUB_DATA: 'true',
        SKIP_API_HANDSHAKE: '1',
        FLASK_DEBUG: 'false',
      },
    },
    secrets,
  )
  processes.push(backend)
  await waitForHealth(`http://127.0.0.1:${backendPort}/api/health`, backend)

  const frontend = spawnManaged(
    'frontend',
    'pnpm',
    ['dev', '--host', parsedBase.hostname, '--port', frontendPort, '--strictPort'],
    {
      cwd: frontendDir,
      env: {
        ...process.env,
        E2E_DISABLE_HMR_OVERLAY: 'true',
        VITE_API_PROXY_TARGET: `http://127.0.0.1:${backendPort}`,
      },
    },
    secrets,
  )
  processes.push(frontend)
  await waitForHealth(baseUrl, frontend)
}

export function signalExitCode(signal) {
  if (signal === 'SIGINT') return 130
  if (signal === 'SIGTERM') return 143
  throw new Error(`Unsupported shutdown signal: ${signal}`)
}

export function createTeardownController({ stop, close, exit }) {
  let teardownPromise = null
  let signalReceived = false

  function teardown() {
    if (!teardownPromise) {
      teardownPromise = (async () => {
        let firstError = null
        try {
          await stop()
        } catch (error) {
          firstError = error
        }
        try {
          await close()
        } catch (error) {
          firstError ||= error
        }
        if (firstError) throw firstError
      })()
    }
    return teardownPromise
  }

  async function handleSignal(signal) {
    const exitCode = signalExitCode(signal)
    if (signalReceived) {
      exit(exitCode)
      return exitCode
    }
    signalReceived = true
    try {
      await teardown()
    } catch {
      // Signal teardown is best-effort; the requested non-zero exit is authoritative.
    }
    exit(exitCode)
    return exitCode
  }

  return { teardown, handleSignal }
}

function publicStep(step) {
  const result = {
    id: step.id,
    expectation: step.expectation,
    ok: step.ok,
    verdict: step.verdict,
    note: step.note,
    shot: step.shot,
  }
  if (step.error) result.error = step.error
  if (step.payload !== undefined) result.payload = step.payload
  return result
}

function groupJourneys(records) {
  return journeyNames.map((name) => ({
    name,
    steps: records.filter((record) => record.journey === name).map(publicStep),
  }))
}

function printSummary(journeys, totals, reportDir) {
  const header = ['Journey', 'Steps', 'OK', 'Pass', 'Concern', 'Fail', 'Ungraded', 'Observed']
  const rows = journeys.map((journey) => {
    const steps = journey.steps
    return [
      journey.name,
      steps.length,
      steps.filter((step) => step.ok).length,
      steps.filter((step) => step.verdict === 'pass').length,
      steps.filter((step) => step.verdict === 'concern').length,
      steps.filter((step) => step.verdict === 'fail').length,
      steps.filter((step) => step.verdict === 'ungraded').length,
      steps.filter((step) => step.verdict === 'observed').length,
    ].map(String)
  })
  rows.push(['TOTAL', totals.steps, totals.ok, totals.pass, totals.concern, totals.fail, totals.ungraded,
    journeys.flatMap((journey) => journey.steps).filter((step) => step.verdict === 'observed').length].map(String))
  const widths = header.map((title, index) => Math.max(title.length, ...rows.map((row) => row[index].length)))
  const format = (row) => row.map((cell, index) => cell.padEnd(widths[index])).join(' | ')
  console.log(format(header))
  console.log(widths.map((width) => '-'.repeat(width)).join('-+-'))
  for (const row of rows) console.log(format(row))
  console.log(`Report: ${path.relative(repoDir, reportDir)}/report.json`)
}

async function main() {
  const runAt = new Date().toISOString()
  const timestamp = runAt.replace(/[:.]/g, '-')
  const reportDir = path.join(simDir, 'report', timestamp)
  const shotsDir = path.join(reportDir, 'shots')
  await ensureShotDirectory(shotsDir)

  const baseUrl = process.env.SIM_BASE_URL || 'http://localhost:5173'
  const backendPort = process.env.SIM_BACKEND_PORT || '5001'
  const python = process.env.SIM_PYTHON || '/Users/michaeljones/Projects/loanarmy/.loan/bin/python'
  const adminEmail = process.env.SIM_ADMIN_EMAIL || 'mj@bywayofmj.com'
  const matchId = process.env.SIM_MATCH_ID || '4'
  const gradeEnabled = enabled(process.env.SIM_GRADE, true)
  const ollamaUrl = process.env.OLLAMA_URL || 'http://127.0.0.1:11434'
  const model = process.env.SIM_VISION_MODEL || 'qwen3.8:27b-obliterated-q8'
  const external = enabled(process.env.SIM_EXTERNAL, false)
  const seedFixture = enabled(process.env.SIM_SEED_FIXTURE, true)
  const secrets = []
  const records = []
  const managed = []
  let browser = null
  let fatalError = null
  const teardownController = createTeardownController({
    stop: () => stopManaged(managed),
    close: async () => {
      const activeBrowser = browser
      browser = null
      if (activeBrowser) await activeBrowser.close()
    },
    exit: (code) => process.exit(code),
  })
  const handleSigint = () => { void teardownController.handleSignal('SIGINT') }
  const handleSigterm = () => { void teardownController.handleSignal('SIGTERM') }
  process.on('SIGINT', handleSigint)
  process.on('SIGTERM', handleSigterm)

  try {
    const backend = await backendEnvironment()
    const env = backend.env
    const secretKey = backend.credentials.secretKey.value
    const adminKey = backend.credentials.adminApiKey.value
    secrets.push(secretKey, adminKey)
    console.log('App Sim Lane: loanarmy-web')
    console.log(`Base URL: ${baseUrl}`)
    console.log(`Backend port: ${backendPort}`)
    console.log(`Credentials: secret_key: ${backend.credentials.secretKey.source}; admin_api_key: ${backend.credentials.adminApiKey.source}`)
    const token = mintAuth({ python, secretKey, adminEmail })
    secrets.push(token)
    if (seedFixture) {
      try {
        seedSimFixture({ python, backendEnv: env, adminEmail, secrets })
      } catch (error) {
        recordFixtureSeedJourneyError(records, error)
        throw error
      }
    }

    if (external) {
      await waitForHealth(baseUrl, null, 30_000)
    } else {
      await bootServers({ baseUrl, backendPort, python, backendEnv: env, secrets, processes: managed })
    }

    const chromium = loadChromium(frontendDir)
    browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    await context.addInitScript(({ tokenValue, adminKeyValue }) => {
      localStorage.setItem('academy_watch_user_token', tokenValue)
      localStorage.setItem('academy_watch_admin_key', adminKeyValue)
      localStorage.setItem('academy_watch_is_admin', 'true')
      localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    }, { tokenValue: token, adminKeyValue: adminKey })
    const page = await context.newPage()
    page.setDefaultTimeout(15_000)
    const driver = createDriver({ page, baseUrl, shotsDir, records })

    for (const runJourney of journeyModules) {
      await runJourney({ ...driver, page, baseUrl, matchId })
    }
  } catch (error) {
    fatalError = error
  } finally {
    try {
      await teardownController.teardown()
    } catch (error) {
      fatalError ||= error
    }
  }

  await fs.writeFile(path.join(reportDir, 'steps.json'), `${JSON.stringify(records, null, 2)}\n`)
  const grading = await gradeRecords(records, {
    enabled: gradeEnabled,
    reportDir,
    ollamaUrl,
    model,
  })
  const journeys = groupJourneys(grading.records)
  const totals = computeTotals(journeys)
  const report = {
    app: 'loanarmy-web',
    run_at: runAt,
    base_url: baseUrl,
    journeys,
    totals,
    proposals: grading.proposals,
  }
  if (fatalError) report.run_error = redact(fatalError.message, secrets)
  await fs.writeFile(path.join(reportDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`)
  printSummary(journeys, totals, reportDir)

  if (fatalError) {
    console.error(`Run error: ${redact(fatalError.message, secrets)}`)
    process.exitCode = 1
  } else {
    process.exitCode = computeExitCode(journeys)
  }
  process.off('SIGINT', handleSigint)
  process.off('SIGTERM', handleSigterm)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
