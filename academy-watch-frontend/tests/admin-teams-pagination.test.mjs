import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const adminTeamsFile = new URL('../src/pages/admin/AdminTeams.jsx', import.meta.url)

test('admin teams paginates tracked list', async () => {
  const src = await fs.readFile(adminTeamsFile, 'utf8')

  assert.match(
    src,
    /const \[trackedPage, setTrackedPage\]/,
    'Tracked teams list should track pagination state'
  )
  assert.match(
    src,
    /trackedTeamsPage/,
    'Tracked teams should compute a paginated slice'
  )
  assert.match(
    src,
    /trackedTeamsPage\.map/,
    'Tracked teams should render the paginated slice'
  )
})

test('admin teams paginates untracked list', async () => {
  const src = await fs.readFile(adminTeamsFile, 'utf8')

  assert.ok(
    !src.includes('untrackedTeams.slice(0, 50)'),
    'Untracked teams list should not be hard-limited to 50'
  )
  assert.match(
    src,
    /const \[untrackedPage, setUntrackedPage\]/,
    'Untracked teams list should track pagination state'
  )
  assert.match(
    src,
    /untrackedTeamsPage\.map/,
    'Untracked teams should render the paginated slice'
  )
})
