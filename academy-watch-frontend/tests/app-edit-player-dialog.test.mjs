import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const appFileUrl = new URL('../src/App.jsx', import.meta.url)

test('App component does not capture editingPlayerDialog state directly', async () => {
  const source = await fs.readFile(appFileUrl, 'utf8')
  const appIndex = source.indexOf('function App')

  assert.notEqual(appIndex, -1, 'App component should be defined')

  const appSource = source.slice(appIndex)
  const referencesDialog = appSource.includes('editingPlayerDialog')

  assert.equal(
    referencesDialog,
    false,
    'App component should not reference editingPlayerDialog which belongs to the admin page'
  )
})
