import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const consoleFile = process.env.CONSOLE_SRC
  ? new URL(process.env.CONSOLE_SRC, `file://${process.cwd()}/`)
  : new URL('../src/pages/MyClubConsole.jsx', import.meta.url)
const apiFile = new URL('../src/lib/api.js', import.meta.url)

test('the club console lists matches from the backend and keeps no localStorage index', async () => {
  const src = await fs.readFile(consoleFile, 'utf8')
  assert.ok(src.includes('APIService.listClubMatches(programId)'), 'loadMatches must call the list endpoint')
  assert.ok(!src.includes('localStorage'), 'no localStorage match index may remain')
  assert.ok(!src.includes('loadMatchIds') && !src.includes('saveMatchIds') && !src.includes('MATCH_INDEX_VERSION'), 'index helpers must be deleted')
  assert.ok(!src.includes('No matches in this browser yet'), 'the browser-only empty state copy must be gone')
})

test('APIService.listClubMatches hits GET /club/<id>/matches', async () => {
  const src = await fs.readFile(apiFile, 'utf8')
  const start = src.indexOf('static async listClubMatches(')
  assert.notEqual(start, -1)
  const body = src.slice(start, src.indexOf('\n    }\n', start))
  assert.ok(body.includes('`/club/${encodeURIComponent(programId)}/matches`'))
})

test('the roster editor only renders a match fetched in full (list rows carry no roster)', async () => {
  const src = await fs.readFile(consoleFile, 'utf8')
  const panel = src.slice(src.indexOf('function MatchesPanel('), src.indexOf('function ClubProfile('))
  assert.ok(panel.includes('const hydrated = Array.isArray(selectedMatch?.roster)'), 'hydration is keyed on a roster array being present')
  assert.ok(panel.includes('APIService.getClubMatch(programId, selectedMatchId)'), 'the selected match is fetched in full')
  const guard = panel.indexOf('{selectedMatch && !hydrated ? (')
  const detail = panel.indexOf('<MatchDetail')
  assert.ok(guard !== -1 && detail !== -1 && guard < detail, 'MatchDetail renders only behind the hydration guard')
})

test('club match create and detail forms expose the three camera preflight selects', async () => {
  const src = await fs.readFile(consoleFile, 'utf8')
  for (const field of ['camera_view', 'camera_motion', 'pitch_lines_visible']) {
    assert.ok(src.includes(`'${field}'`), `${field} must be part of MATCH_FORM_FIELDS`)
    assert.ok(src.split(`field="${field}"`).length - 1 >= 2, `${field} must render in create and detail forms`)
  }
  for (const label of ['Camera view', 'Camera motion', 'Pitch lines visible']) {
    assert.ok(src.split(`label="${label}"`).length - 1 >= 2, `${label} must be rendered as plain copy in both forms`)
  }
})
