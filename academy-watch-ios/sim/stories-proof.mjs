#!/usr/bin/env node
// Mechanical proof only; copied to an adopter's sim/. No model calls or dependencies.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

export const digest = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex')
const read = (file) => JSON.parse(fs.readFileSync(file, 'utf8'))
const json = (value) => `${JSON.stringify(value, null, 2)}\n`
export function storyTotals(rows) {
  return {
    proven: rows.filter((s) => s.proof === 'proven').length,
    unproven: rows.filter((s) => s.proof === 'unproven').length,
    failing: rows.filter((s) => s.proof === 'failing').length,
    judged: rows.filter((s) => s.verdict !== undefined).length,
    contradicted: rows.filter((s) => s.verdict === 'contradicted').length,
    confusing: rows.filter((s) => s.verdict === 'confusing').length,
  }
}
function unique(list, key) { return Array.isArray(list) && new Set(list.map((v) => v?.[key])).size === list.length }
function shotExists(reportDir, shot) {
  if (typeof shot !== 'string' || path.isAbsolute(shot)) return false
  const file = path.resolve(reportDir, shot)
  try { return file.startsWith(`${path.resolve(reportDir)}/`) && fs.statSync(file).isFile() && fs.realpathSync(file).startsWith(`${fs.realpathSync(reportDir)}/`) } catch { return false }
}
export function assemble(appDir, reportDir, inventory, report, audit) {
  if (!Array.isArray(inventory?.stories) || !unique(inventory.stories,'id') || !Array.isArray(inventory.screens)) throw new Error('invalid story inventory')
  const actions = { visible:'assertVisible', absent:'assertAbsent', selected:'assertSelected' }
  return inventory.stories.map((story) => {
    const row = { ...Object.fromEntries(['app_revision','config_digest'].filter(k => report[k] !== undefined).map(k => [k,report[k]])), id:story.id,persona:story.persona,proof:'unproven',journey:story.proof?.journey ?? null,evidence:[] }
    const unproven = (reason) => ({ ...row, reason })
    if (report.run_error) return unproven('run_error')
    if (!story.proof || !story.proof.asserts?.length) return unproven('no_proof')
    const { journey, asserts } = story.proof
    if (!/^[a-z0-9-]+$/.test(journey)) throw new Error(`invalid journey id for ${story.id}`)
    const file = path.join(appDir,'sim/journeys',`${journey}.json`)
    if (!fs.existsSync(file)) return unproven('journey_missing')
    const selected = audit.selected_journeys?.filter((s) => s.name === journey) || []
    if (!selected.length) return unproven('not_selected')
    const runs = audit.journeys?.filter((s) => s.name === journey) || []
    const shown = report.journeys?.filter((s) => s.name === journey) || []
    if (selected.length !== 1 || runs.length !== 1 || shown.length !== 1) return unproven('journey_missing')
    const run = runs[0], displayed = shown[0], bytes = fs.readFileSync(file)
    if (digest(bytes) !== selected[0].hash || digest(bytes) !== run.journey_hash) return unproven('hash_mismatch')
    let source
    try { source = JSON.parse(bytes) } catch { return unproven('journey_missing') }
    if (source.platform === 'web' && asserts.some(a => a.kind === 'absent') && !asserts.some(a => ['visible','selected'].includes(a.kind) && inventory.screens.some(s => s.id === a.screen && s.status === 'instrumented'))) return unproven('no_proof')
    if (source.name !== journey || !unique(source.steps,'id') || !source.steps.length || !unique(run.steps,'id') || !unique(displayed.steps,'id')) return unproven('journey_missing')
    if (asserts.some(a => [...run.steps, ...displayed.steps].some(s => s.id === a.step && s.settle_reason === 'timeout'))) return { ...row, proof:'failing', reason:'unsettled_assert' }
    if (run.steps.some((s) => s.ok === false) || displayed.steps.some((s) => s.ok === false)) return { ...row, proof:'failing' }
    if (run.run_mode === 'checkpoint') return unproven('checkpoint_only')
    // No inference from an old receipt: explicit full mode and every source step are mandatory.
    if (run.run_mode !== 'full' || run.checkpoint_only === true || run.steps.length !== source.steps.length || displayed.steps.length !== source.steps.length) return unproven('journey_missing')
    for (let i=0; i<source.steps.length; i++) {
      const step = run.steps[i], shownStep = displayed.steps[i]
      if (step.id !== source.steps[i].id || step.ok !== true || shownStep.id !== step.id || shownStep.ok !== true || shownStep.shot !== step.shot || !shotExists(reportDir,step.shot)) return unproven('journey_missing')
    }
    const refs = []
    for (const a of asserts) {
      const screen = inventory.screens.find((s) => s.id === a.screen)
      if (!screen || screen.status !== 'instrumented' || !screen.proof_id) return unproven('no_proof')
      const step = source.steps.find((s) => s.id === a.step)
      if (!step?.action || Object.keys(step.action).length !== 1 || !actions[a.kind] || step.action[actions[a.kind]]?.id !== screen.proof_id ||
          (a.kind !== 'visible' && source.version !== '1.3')) return unproven('no_proof')
      const executed = run.steps.find((s) => s.id === a.step)
      if (!executed || executed.ok !== true) return unproven('journey_missing')
      if (!refs.some((r) => r.step_id === a.step)) refs.push({step_id:a.step,shot:executed.shot})
    }
    return { ...row,proof:'proven',evidence:refs }
  })
}
export function loadProof(appDir, reportDir) {
  const bytes = fs.readFileSync(path.join(appDir,'sim/stories.json'))
  const inventory = JSON.parse(bytes)
  const report = read(path.join(reportDir,'report.json'))
  const audit = read(path.join(reportDir,'steps.json'))
  return { inventory, report, audit, stories_digest:digest(bytes), stories:assemble(appDir,reportDir,inventory,report,audit) }
}
export function main() {
  const args = process.argv.slice(2)
  if (args.includes('--help') || args.includes('-h')) { console.log('Usage: stories-proof.mjs --report-dir report-dir --app-dir app-dir [--app-head sha] [--require-proven <ids...>]\nWithout report-dir, uses latest dated sim/report child. Acceptance exits 2 with plain reasons. --app-head requires SIM_PROOF_TEST=1 (tests only; never app gates/nightlies).'); return }
  let reportDir, appDir, appHead, required = null
  while (args.length) {
    const arg = args.shift()
    if (arg === '--app-dir' && args[0] && !args[0].startsWith('--')) appDir = path.resolve(args.shift())
    else if (arg === '--report-dir' && args[0] && !args[0].startsWith('--')) reportDir = path.resolve(args.shift())
    else if (arg === '--app-head' && args[0] && !args[0].startsWith('--')) appHead = args.shift()
    else if (arg === '--require-proven') {
      const ids = []
      while (args.length && !args[0].startsWith('--')) ids.push(args.shift())
      if (!ids.length || ids.some((id) => !/^[a-z0-9-]+$/.test(id))) throw new Error('--require-proven needs story ids')
      required = [...(required || []), ...ids]
    }
    else if (!arg.startsWith('-') && !reportDir) reportDir = path.resolve(arg)
    else throw new Error('invalid arguments; see --help')
  }
  if (appHead !== undefined && process.env.SIM_PROOF_TEST !== '1') throw new Error('--app-head is test-only; requires SIM_PROOF_TEST=1; app gates/nightlies must use real HEAD')
  if (!appDir) throw new Error('--app-dir is required')
  if (!fs.existsSync(path.join(appDir,'sim/stories.json'))) {
    if (required) throw new Error('story inventory missing; required stories are unproven')
    if (reportDir && read(path.join(reportDir,'report.json')).report_version === '2.1') throw new Error('2.1 inventory missing')
    console.log('stories-proof: no inventory (legacy v2)'); return
  }
  if (!reportDir) {
    const root = path.resolve(appDir,process.env.SIM_REPORT_DIR || 'sim/report')
    const latest = fs.readdirSync(root).filter((s) => /^\d{8}T\d{6}Z(?:-\d+)?$/.test(s) && fs.statSync(path.join(root,s)).isDirectory()).sort((a,b) => a.localeCompare(b, 'en', {numeric:true})).at(-1)
    if (!latest) throw new Error('no published story report')
    reportDir = path.join(root,latest)
  }
  const result = loadProof(appDir,reportDir)
  if (required) {
    const head = appHead ?? spawnSync('git',['-C',appDir,'rev-parse','HEAD'],{encoding:'utf8'}).stdout?.trim()
    if (!head || !/^[a-f0-9]{40,64}$/.test(head) || result.report.app_revision !== head) { console.error('stories-proof: app_revision does not match app HEAD'); process.exitCode=2 }
    for (const id of required) {
      const row = result.stories.find((s) => s.id === id)
      if (row?.proof !== 'proven') { console.error(`stories-proof: ${id}: ${row?.reason || row?.proof || 'story_missing'}`); process.exitCode=2 }
    }
    if (!process.exitCode) console.log(`stories-proof: required stories proven: ${required.join(', ')}`)
    return
  }
  const { report, stories, stories_digest } = result
  Object.assign(report,{report_version:'2.1',stories_digest,stories})
  report.totals.stories = storyTotals(stories)
  fs.writeFileSync(path.join(reportDir,'stories.json'),json(stories))
  fs.writeFileSync(path.join(reportDir,'report.json'),json(report))
  console.log(`stories-proof: ${JSON.stringify(report.totals.stories)}`)
}
if (process.argv[1] && fs.existsSync(process.argv[1]) && (fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url) || fs.realpathSync(process.argv[1]) === fileURLToPath(new URL('../../swift-ios/templates/sim/stories-proof.mjs', import.meta.url)))) {
  try { main() } catch(e) { console.error(`stories-proof: ${e.message}`); process.exitCode=2 }
}
