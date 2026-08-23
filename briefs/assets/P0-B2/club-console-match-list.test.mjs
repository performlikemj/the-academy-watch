import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const consoleFile = new URL('../src/pages/MyClubConsole.jsx', import.meta.url)
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
