#!/usr/bin/env node

import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

export const PROMPT_VERSION = 'yuki-ios-v2-20260904'

const GRADE_SCHEMA = {
  title: 'StepGrade',
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'note'],
  properties: {
    verdict: { type: 'string', enum: ['pass', 'concern', 'fail'] },
    note: { type: 'string', minLength: 1, maxLength: 2000 },
  },
}
const RECOMMENDATION_SCHEMA = {
  title: 'YukiRecommendations',
  type: 'object',
  additionalProperties: false,
  required: ['recommendations'],
  properties: {
    recommendations: {
      type: 'array',
      maxItems: 3,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['text', 'rationale', 'evidence'],
        properties: {
          text: { type: 'string', minLength: 1, maxLength: 1000 },
          rationale: { type: 'string', minLength: 1, maxLength: 1000 },
          evidence: {
            type: 'array',
            minItems: 1,
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['journey', 'step_id', 'shot'],
              properties: {
                journey: { type: 'string' },
                step_id: { type: 'string' },
                shot: { type: 'string' },
              },
            },
          },
        },
      },
    },
  },
}
const JOURNEY_SCHEMA = {
  title: 'JourneyProposal',
  type: 'object',
  additionalProperties: false,
  required: ['propose', 'persona', 'journey', 'reason'],
  properties: {
    propose: { type: 'boolean' },
    persona: { type: 'string', maxLength: 1000 },
    journey: { type: 'string', maxLength: 1000 },
    reason: { type: 'string', maxLength: 1000 },
  },
}

function usage() {
  console.log('Usage: grade.mjs <report-dir> <persona.md> <persona-manifest.json>')
}
function enabled(value, fallback = true) {
  if (value === undefined) return fallback
  return value === '1' || value.toLowerCase() === 'true'
}
function origin() {
  const value = process.env.OLLAMA_HOST || '100.82.160.117:11434'
  return /^https?:\/\//.test(value) ? value.replace(/\/$/, '') : `http://${value.replace(/\/$/, '')}`
}
function options() {
  const value = process.env.SIM_NUM_CTX
  if (value === 'omit') return { temperature: 0 }
  if (value !== undefined && value.trim() !== '65536') throw new Error('SIM_NUM_CTX must be omit or exactly 65536')
  return { temperature: 0, num_ctx: 65536 }
}
function localHost(value) {
  return ['localhost', '127.0.0.1', '::1'].includes(new URL(value).hostname)
}
function localBusy() {
  return spawnSync('pgrep', ['-f', 'qwen_match_analysis|run_bench|filmroom_worker|h3'], { stdio: 'ignore' }).status === 0
}
function parseObject(raw) {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw) : raw
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null
  } catch { return null }
}
function exactKeys(value, keys) {
  return value && Object.keys(value).sort().join('\0') === [...keys].sort().join('\0')
}
function clean(value, maximum) {
  if (typeof value !== 'string') return null
  const result = value.trim()
  return result && [...result].length <= maximum ? result : null
}
function schemaPrompt(instruction, schema, context) {
  return [instruction, 'Return one JSON object matching this Pydantic-shaped strict JSON Schema. No extra keys or prose.', JSON.stringify(schema), context].join('\n\n')
}
function responseContent(response) {
  if (typeof response?.message?.content === 'string' && response.message.content.trim()) return response.message.content
  return typeof response?.message?.thinking === 'string' ? response.message.thinking : ''
}
function budgetSeconds() {
  const value = Number(process.env.SIM_GRADE_BUDGET_S || '600')
  if (!Number.isFinite(value) || value <= 0) throw new Error('SIM_GRADE_BUDGET_S must be a positive number')
  return value
}
function imageByteBudget() {
  const value = Number(process.env.SIM_GRADE_IMAGE_BYTES || String(40 * 1024 * 1024))
  if (!Number.isInteger(value) || value <= 0) throw new Error('SIM_GRADE_IMAGE_BYTES must be a positive integer')
  return value
}
function cacheDigest(buffers, expectation, model) {
  const hash = crypto.createHash('sha256')
  for (const buffer of buffers) hash.update(buffer)
  hash.update(expectation)
  hash.update(model)
  hash.update(PROMPT_VERSION)
  return hash.digest('hex')
}
async function cached(context, key, call) {
  const file = path.join(context.cacheDir, `${key}.json`)
  try { return JSON.parse(await fs.readFile(file, 'utf8')) } catch {}
  if (Date.now() >= context.deadline || context.calls >= context.maxCalls) throw new Error('budget-exhausted')
  context.calls += 1
  const value = await call()
  await fs.mkdir(context.cacheDir, { recursive: true })
  await fs.writeFile(file, `${JSON.stringify(value)}\n`)
  return value
}
async function chat(context, prompt, images) {
  const remaining = context.deadline - Date.now()
  if (remaining <= 0) throw new Error('budget-exhausted')
  const message = { role: 'user', content: prompt }
  if (images.length) message.images = images.map((bytes) => bytes.toString('base64'))
  const response = await fetch(`${context.origin}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model: context.model,
      messages: [message],
      think: false,
      stream: false,
      format: 'json',
      options: options(),
    }),
    signal: AbortSignal.timeout(Math.min(120_000, remaining)),
  })
  if (!response.ok) throw new Error(`Ollama HTTP ${response.status}`)
  return responseContent(await response.json())
}
function validGrade(value) {
  if (!exactKeys(value, ['verdict', 'note']) || !['pass', 'concern', 'fail'].includes(value.verdict)) return null
  const note = clean(value.note, 2000)
  return note ? { verdict: value.verdict, note } : null
}
function evidenceIndex(report) {
  const index = new Map()
  for (const journey of report.journeys) {
    for (const step of journey.steps) index.set(`${journey.name}\0${step.id}`, step.shot)
  }
  return index
}
function validRecommendations(value, report, model) {
  if (!exactKeys(value, ['recommendations']) || !Array.isArray(value.recommendations) || value.recommendations.length > 3) return null
  const known = evidenceIndex(report)
  const result = []
  for (const item of value.recommendations) {
    if (!exactKeys(item, ['text', 'rationale', 'evidence']) || !Array.isArray(item.evidence) || !item.evidence.length) return null
    const text = clean(item.text, 1000)
    const rationale = clean(item.rationale, 1000)
    if (!text || !rationale) return null
    const evidence = []
    for (const ref of item.evidence) {
      if (!exactKeys(ref, ['journey', 'step_id', 'shot'])) return null
      const expectedShot = known.get(`${ref.journey}\0${ref.step_id}`)
      if (!expectedShot || expectedShot !== ref.shot) return null
      evidence.push({ journey: ref.journey, step_id: ref.step_id, shot: ref.shot })
    }
    result.push({ text, rationale, evidence, model, prompt_version: PROMPT_VERSION })
  }
  return result
}
function validJourneyProposal(value) {
  if (!exactKeys(value, ['propose', 'persona', 'journey', 'reason']) || typeof value.propose !== 'boolean') return null
  if (!value.propose) return [value.persona, value.journey, value.reason].every((field) => field === '') ? false : null
  const persona = clean(value.persona, 1000)
  const journey = clean(value.journey, 1000)
  const reason = clean(value.reason, 1000)
  return persona && journey && reason ? { persona, journey, reason } : null
}
function unavailable(step, note) {
  return { ...step, verdict: 'ungraded', note }
}
async function gradeStep(step, context) {
  if (!step.ok) return { ...step, verdict: 'fail', note: clean(step.note, 2000) || 'The step action failed mechanically.' }
  const expectation = typeof step.expectation === 'string' ? step.expectation.trim() : ''
  if (!expectation) return { ...step, verdict: 'observed', note: step.note || 'Observed only.' }
  if (!context.enabled) return unavailable(step, 'Vision grading disabled by SIM_GRADE=0.')
  if (context.unavailable) return unavailable(step, context.unavailable)
  let bytes
  try { bytes = await fs.readFile(path.join(context.reportDir, step.shot)) }
  catch { return unavailable(step, 'The screenshot could not be read.') }
  if (context.imageBytes + bytes.length > context.imageByteLimit) return unavailable(step, 'Vision grading budget exhausted; no verdict was inferred.')
  context.imageBytes += bytes.length
  const prompt = schemaPrompt(
    'Judge only visible screenshot evidence. pass is fully satisfied; concern is partial or visibly odd; fail is contradicted or absent.',
    GRADE_SCHEMA,
    `Expectation:\n${expectation}`,
  )
  const key = cacheDigest([bytes], expectation, context.model)
  try {
    const raw = await cached(context, key, async () => parseObject(await chat(context, prompt, [bytes])))
    const value = validGrade(raw)
    return value ? { ...step, ...value } : unavailable(step, 'The grader returned invalid JSON.')
  } catch (error) {
    if (error.message === 'budget-exhausted' || error.name === 'TimeoutError') return unavailable(step, 'Vision grading budget exhausted; no verdict was inferred.')
    context.unavailable = 'Vision grading unavailable; no model verdict was inferred.'
    return unavailable(step, context.unavailable)
  }
}
async function recommendationQuestion(journey, report, confirmedFacts, context) {
  if (!context.enabled || context.unavailable) return []
  const selected = []
  const images = []
  let bytesUsed = 0
  for (const step of journey.steps) {
    if (!step.expectation?.trim()) continue
    try {
      const bytes = await fs.readFile(path.join(context.reportDir, step.shot))
      if (context.imageBytes + bytesUsed + bytes.length > context.imageByteLimit) break
      bytesUsed += bytes.length
      images.push(bytes)
      selected.push({ journey: journey.name, step_id: step.id, expectation: step.expectation, ok: step.ok, verdict: step.verdict, note: step.note, shot: step.shot })
    } catch {}
  }
  if (!selected.length) return []
  context.imageBytes += bytesUsed
  const prompt = schemaPrompt(
    'Using only confirmed persona facts and the selected screenshot records, return up to three advisory changes Yuki would request. Every item must cite at least one supplied journey, step_id, and shot exactly. Do not invent biography.',
    RECOMMENDATION_SCHEMA,
    `Confirmed facts:\n${JSON.stringify(confirmedFacts)}\n\nSelected records:\n${JSON.stringify(selected)}`,
  )
  const key = cacheDigest(images, JSON.stringify(selected), context.model)
  try {
    const raw = await cached(context, key, async () => parseObject(await chat(context, prompt, images)))
    return validRecommendations(raw, report, context.model) || []
  } catch { return [] }
}
async function journeyProposal(report, confirmedFacts, context) {
  if (!context.enabled || context.unavailable) return []
  const summary = report.journeys.map((journey) => ({
    name: journey.name,
    steps: journey.steps.map(({ id, expectation, note }) => ({ id, expectation, note })),
  }))
  const prompt = schemaPrompt(
    'Propose at most one new screenshot-verifiable journey. If none is useful set propose=false and all text fields empty. Never execute it.',
    JOURNEY_SCHEMA,
    `Confirmed facts:\n${JSON.stringify(confirmedFacts)}\n\nExisting journeys:\n${JSON.stringify(summary)}`,
  )
  const key = cacheDigest([], JSON.stringify(summary), context.model)
  try {
    const raw = await cached(context, key, async () => parseObject(await chat(context, prompt, [])))
    const value = validJourneyProposal(raw)
    return value && value !== false ? [value] : []
  } catch { return [] }
}
function totals(journeys) {
  const steps = journeys.flatMap((journey) => journey.steps)
  return {
    steps: steps.length,
    ok: steps.filter((step) => step.ok).length,
    pass: steps.filter((step) => step.verdict === 'pass').length,
    concern: steps.filter((step) => step.verdict === 'concern').length,
    fail: steps.filter((step) => step.verdict === 'fail').length,
    ungraded: steps.filter((step) => step.verdict === 'ungraded').length,
  }
}
async function readConfirmedPersona(personaPath, manifestPath) {
  const markdown = await fs.readFile(personaPath)
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'))
  const digest = crypto.createHash('sha256').update(markdown).digest('hex')
  if (manifest.persona_digest !== digest) throw new Error('persona manifest digest does not match persona markdown')
  const confirmed = new Map()
  const proposed = new Set()
  for (const line of markdown.toString('utf8').split(/\r?\n/)) {
    const fact = line.match(/^- (Y-[0-9]{3}) \| status: (confirmed|proposed) \| citation: `([^`]+)` \| (.+)$/)
    if (!fact) continue
    if (fact[2] === 'confirmed') confirmed.set(fact[1], { id: fact[1], citation: fact[3], text: fact[4] })
    else proposed.add(fact[1])
  }
  if (!Array.isArray(manifest.facts) || manifest.facts.some((fact) => {
    const source = confirmed.get(fact?.id)
    return proposed.has(fact?.id) || !source || source.text !== fact.text || source.citation !== fact.citation
  })) {
    throw new Error('persona manifest facts are invalid')
  }
  return manifest.facts
}

export async function gradeReport(report, confirmedFacts, settings = {}) {
  const budget = settings.budgetSeconds || budgetSeconds()
  const context = {
    enabled: settings.enabled ?? enabled(process.env.SIM_GRADE, true),
    reportDir: settings.reportDir,
    cacheDir: settings.cacheDir || process.env.SIM_GRADE_CACHE_DIR || path.join(settings.reportDir, '..', '.cache'),
    origin: settings.origin || origin(),
    model: settings.model || process.env.SIM_VISION_MODEL || 'qwen3-vl:8b',
    deadline: Date.now() + budget * 1000,
    maxCalls: Math.max(1, Math.floor(budget / 30)),
    calls: 0,
    imageBytes: 0,
    imageByteLimit: imageByteBudget(),
    unavailable: null,
  }
  if (context.enabled && localHost(context.origin) && localBusy()) {
    context.unavailable = 'Vision grading deferred because the local Ollama busy guard matched.'
  } else if (context.enabled && !localHost(context.origin)) {
    console.log(`grader: remote Ollama host ${new URL(context.origin).host}; local busy guard skipped`)
  }
  for (const journey of report.journeys) {
    const graded = []
    for (const step of journey.steps) graded.push(await gradeStep(step, context))
    journey.steps = graded
  }
  report.recommendations = []
  for (const journey of report.journeys) {
    const rows = await recommendationQuestion(journey, report, confirmedFacts, context)
    for (const row of rows) {
      const key = `${row.text.toLowerCase()}\0${row.rationale.toLowerCase()}`
      if (report.recommendations.length < 3 && !report.recommendations.some((known) => `${known.text.toLowerCase()}\0${known.rationale.toLowerCase()}` === key)) report.recommendations.push(row)
    }
  }
  report.proposals = (await journeyProposal(report, confirmedFacts, context)).slice(0, 1)
  report.totals = totals(report.journeys)
  return report
}

async function main() {
  if (process.argv.includes('-h') || process.argv.includes('--help')) { usage(); return }
  if (process.argv.length !== 5) { usage(); process.exitCode = 2; return }
  const reportDir = path.resolve(process.argv[2])
  const reportPath = path.join(reportDir, 'report.json')
  const facts = await readConfirmedPersona(path.resolve(process.argv[3]), path.resolve(process.argv[4]))
  const report = JSON.parse(await fs.readFile(reportPath, 'utf8'))
  const graded = await gradeReport(report, facts, { reportDir })
  await fs.writeFile(reportPath, `${JSON.stringify(graded, null, 2)}\n`)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { await main() } catch (error) { console.error(`grader: ${error.message}`); process.exitCode = 2 }
}
