import fs from 'node:fs/promises'
import path from 'node:path'

const GRADE_PROMPT = `Does this screenshot satisfy the expectation? Reply {"verdict":"pass|concern|fail", "note":str}. 'concern' = partially satisfied or something looks broken/odd; note one sentence.`
const EXPLORATION_PROMPT = `This app is a football academy scouting platform: scouts, players, clubs. Review these screenshots and propose ONE useful new persona and journey idea. Reply {"persona":str,"journey":str,"first_step":str}. Do not execute it.`
const DEFAULT_NUM_CTX = 65536

function ollamaOptions() {
  const options = { temperature: 0 }
  const configured = process.env.SIM_NUM_CTX
  const raw = configured === undefined ? String(DEFAULT_NUM_CTX) : configured.trim()
  if (!/^\d+$/.test(raw)) throw new Error('SIM_NUM_CTX must be a non-negative integer')
  const numCtx = Number(raw)
  if (!Number.isSafeInteger(numCtx)) throw new Error('SIM_NUM_CTX must be a non-negative integer')
  if (numCtx > 0) options.num_ctx = numCtx
  return options
}

export function normalizeGrade(value) {
  if (!value || typeof value !== 'object') {
    return { verdict: 'ungraded', note: 'The grader returned invalid JSON.' }
  }
  const verdict = typeof value.verdict === 'string' ? value.verdict.trim().toLowerCase() : ''
  const note = typeof value.note === 'string' ? value.note.trim() : ''
  if (!['pass', 'concern', 'fail'].includes(verdict) || !note) {
    return { verdict: 'ungraded', note: 'The grader returned invalid JSON.' }
  }
  return { verdict, note }
}

export function parseGradeJSON(raw) {
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return normalizeGrade(parsed)
  } catch {
    return { verdict: 'ungraded', note: 'The grader returned invalid JSON.' }
  }
}

function parseGradeAttempt(raw) {
  const result = parseGradeJSON(raw)
  return { valid: result.verdict !== 'ungraded', result }
}

export function validateProposal(value) {
  if (!value || typeof value !== 'object') return null
  const proposal = {}
  for (const key of ['persona', 'journey', 'first_step']) {
    if (typeof value[key] !== 'string' || !value[key].trim()) return null
    proposal[key] = value[key].trim()
  }
  return proposal
}

function messageContent(response) {
  return response?.message?.content
}

async function ollamaChat({ ollamaUrl, model, prompt, images }) {
  const response = await fetch(`${ollamaUrl.replace(/\/$/, '')}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model,
      messages: [{ role: 'user', content: prompt, images }],
      think: false,
      stream: false,
      format: 'json',
      options: ollamaOptions(),
    }),
    signal: AbortSignal.timeout(120_000),
  })
  if (!response.ok) throw new Error(`Ollama returned HTTP ${response.status}`)
  return messageContent(await response.json())
}

async function imageBase64(filePath) {
  return (await fs.readFile(filePath)).toString('base64')
}

async function gradeOne({ record, reportDir, ollamaUrl, model, chat }) {
  let image
  try {
    image = await imageBase64(path.join(reportDir, record.shot))
  } catch {
    return { verdict: 'ungraded', note: 'The screenshot could not be read.' }
  }

  const prompt = `${GRADE_PROMPT}\n\nExpectation: ${record.expectation}`
  try {
    const first = parseGradeAttempt(await chat({ ollamaUrl, model, prompt, images: [image] }))
    if (first.valid) return first.result
    const second = parseGradeAttempt(await chat({ ollamaUrl, model, prompt, images: [image] }))
    return second.result
  } catch (error) {
    return { verdict: 'ungraded', note: `Vision grading unavailable: ${error.message}` }
  }
}

function mergeGrade(record, result) {
  if (record.ok !== false) return { ...record, ...result }

  const mechanicalError = typeof record.error === 'string' && record.error.trim()
    ? record.error.trim()
    : 'The step action failed mechanically.'
  return {
    ...record,
    ...result,
    verdict: 'fail',
    note: `${mechanicalError}\nScreenshot grader: ${result.note}`,
  }
}

async function contentRichImages(records, reportDir) {
  const candidates = []
  for (const record of records) {
    const filePath = path.join(reportDir, record.shot)
    try {
      const stat = await fs.stat(filePath)
      candidates.push({ filePath, size: stat.size })
    } catch {
      // A missing failed-step screenshot cannot contribute to exploration.
    }
  }
  candidates.sort((a, b) => b.size - a.size)
  return Promise.all(candidates.slice(0, 3).map(({ filePath }) => imageBase64(filePath)))
}

async function proposeJourney({ records, reportDir, ollamaUrl, model, chat }) {
  const images = await contentRichImages(records, reportDir)
  if (!images.length) return []
  try {
    const raw = await chat({ ollamaUrl, model, prompt: EXPLORATION_PROMPT, images })
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    const proposal = validateProposal(parsed)
    return proposal ? [proposal] : []
  } catch {
    return []
  }
}

export async function gradeRecords(records, options) {
  const { enabled, reportDir, ollamaUrl, model, chat = ollamaChat } = options
  if (!enabled) {
    return {
      records: records.map((record) => mergeGrade(record, {
        verdict: record.expectation ? 'ungraded' : 'observed',
        note: record.expectation ? 'Vision grading disabled by SIM_GRADE=0.' : 'Observed only.',
      })),
      proposals: [],
    }
  }

  const graded = []
  for (const record of records) {
    if (!record.expectation) {
      graded.push(mergeGrade(record, { verdict: 'observed', note: 'Observed only.' }))
      continue
    }
    const result = await gradeOne({ record, reportDir, ollamaUrl, model, chat })
    graded.push(mergeGrade(record, result))
  }

  return {
    records: graded,
    proposals: await proposeJourney({ records, reportDir, ollamaUrl, model, chat }),
  }
}
