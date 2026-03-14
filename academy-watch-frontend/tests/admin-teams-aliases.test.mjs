import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const adminTeamsFile = new URL('../src/pages/admin/AdminTeams.jsx', import.meta.url)

test('team aliases description avoids JSX-breaking arrow', async () => {
  const src = await fs.readFile(adminTeamsFile, 'utf8')

  assert.ok(
    !src.includes('->'),
    'AdminTeams should avoid a raw "->" in JSX text to prevent Vite warnings'
  )
})

test('team aliases description uses friendly mapping wording', async () => {
  const src = await fs.readFile(adminTeamsFile, 'utf8')

  assert.match(
    src,
    /maps to/i,
    'AdminTeams should describe alias mapping using wording like "maps to"'
  )
})
