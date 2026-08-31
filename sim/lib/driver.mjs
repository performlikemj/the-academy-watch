import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'

const STEP_FAILURE = Symbol('sim-step-failure')

export function normalizeExpectation(expectation) {
  if (typeof expectation !== 'string') return null
  const value = expectation.trim()
  return value || null
}

export function shapeStepRecord({ journey, id, expectation, url, ok, error, shot, payload }) {
  const record = {
    journey: String(journey),
    id: String(id),
    expectation: normalizeExpectation(expectation),
    url: typeof url === 'string' ? url : '',
    ok: Boolean(ok),
    shot: String(shot),
  }
  if (!record.ok && error) record.error = String(error)
  if (payload !== undefined) record.payload = payload
  return record
}

export function computeTotals(journeys) {
  const steps = journeys.flatMap((journey) => journey.steps || [])
  const totals = {
    steps: steps.length,
    ok: steps.filter((step) => step.ok).length,
    pass: 0,
    concern: 0,
    fail: 0,
    ungraded: 0,
  }
  for (const step of steps) {
    if (Object.hasOwn(totals, step.verdict) && step.verdict !== 'ok' && step.verdict !== 'steps') {
      totals[step.verdict] += 1
    }
  }
  return totals
}

export function computeExitCode(journeys) {
  const steps = journeys.flatMap((journey) => journey.steps || [])
  return steps.some((step) => !step.ok || step.verdict === 'fail') ? 1 : 0
}

export function loadChromium(frontendDir) {
  const requireFromFrontend = createRequire(path.join(frontendDir, 'package.json'))
  const { chromium } = requireFromFrontend('@playwright/test')
  return chromium
}

function safeFilePart(value) {
  return String(value)
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'step'
}

function errorMessage(error) {
  if (error instanceof Error) return error.message
  return String(error)
}

export function createDriver({ page, baseUrl, shotsDir, records }) {
  let activeJourney = null

  async function step(id, expectation, action) {
    if (!activeJourney) throw new Error('step() must be called inside journey()')
    const shotName = `${safeFilePart(activeJourney)}__${safeFilePart(id)}.png`
    const shotPath = path.join(shotsDir, shotName)
    let actionError = null
    let payload

    try {
      payload = await action(page)
    } catch (error) {
      actionError = error
      if (error && typeof error === 'object' && 'payload' in error) payload = error.payload
    }

    try {
      await page.screenshot({ path: shotPath, fullPage: true })
    } catch (screenshotError) {
      actionError ||= screenshotError
    }

    const record = shapeStepRecord({
      journey: activeJourney,
      id,
      expectation,
      url: page.url(),
      ok: !actionError,
      error: actionError ? errorMessage(actionError) : undefined,
      shot: `shots/${shotName}`,
      payload,
    })
    records.push(record)

    if (actionError) {
      const failure = new Error(record.error)
      failure[STEP_FAILURE] = true
      throw failure
    }
    return payload
  }

  async function journey(name, fn) {
    if (activeJourney) throw new Error('journey() calls cannot be nested')
    activeJourney = String(name)
    try {
      await fn()
    } catch (error) {
      if (!error?.[STEP_FAILURE]) {
        const id = 'journey-error'
        const shotName = `${safeFilePart(activeJourney)}__${id}.png`
        try {
          await page.screenshot({ path: path.join(shotsDir, shotName), fullPage: true })
        } catch {
          // The page may already be gone; the original error is the useful one.
        }
        records.push(shapeStepRecord({
          journey: activeJourney,
          id,
          expectation: null,
          url: page.url(),
          ok: false,
          error: errorMessage(error),
          shot: `shots/${shotName}`,
        }))
      }
    } finally {
      activeJourney = null
    }
  }

  async function goto(relativePath, options = {}) {
    const target = new URL(relativePath, `${baseUrl.replace(/\/$/, '')}/`).href
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: options.timeout || 30_000 })
    await page.locator('body').waitFor({ state: 'visible', timeout: 10_000 })
  }

  return { journey, step, goto }
}

export async function ensureShotDirectory(shotsDir) {
  await fs.mkdir(shotsDir, { recursive: true })
}
