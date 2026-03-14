import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const adminUsersFile = new URL('../src/pages/admin/AdminUsers.jsx', import.meta.url)

test('admin coverage editor loads loan destinations for loan-team suggestions', async () => {
  const src = await fs.readFile(adminUsersFile, 'utf8')

  assert.match(
    src,
    /getLoanDestinations/,
    'AdminUsers should fetch loan destinations so loan-team options include teams from active loans'
  )
})

test('loan-team suggestions are not hard-capped to 50 options', async () => {
  const src = await fs.readFile(adminUsersFile, 'utf8')

  assert.ok(
    !src.includes('slice(0, 50)'),
    'Loan-team suggestions should not be hard-limited to 50 options'
  )
})
