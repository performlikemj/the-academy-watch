import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const adminUsersFile = new URL('../src/pages/admin/AdminUsers.jsx', import.meta.url)

test('journalist analytics table is horizontally scrollable on small screens', async () => {
  const src = await fs.readFile(adminUsersFile, 'utf8')

  assert.match(
    src,
    /overflow-x-auto/,
    'journalist stats table should sit in an overflow-x-auto wrapper to avoid squishing on mobile'
  )
})

test('user header layout can wrap on narrow viewports', async () => {
  const src = await fs.readFile(adminUsersFile, 'utf8')

  assert.match(
    src,
    /flex-col[^\\n]+md:flex-row|md:flex-row[^\\n]+flex-col/,
    'page header should stack vertically by default and switch to row layout on medium screens'
  )
})
