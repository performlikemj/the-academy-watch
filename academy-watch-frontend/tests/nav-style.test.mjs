import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

test('navbar links use neutral, non-underlined styling by default', async () => {
  const appSource = await fs.readFile(new URL('../src/App.jsx', import.meta.url), 'utf8')

  // Ensure the linkClasses definition keeps links neutral (theme foreground) and removes default underlines.
  assert.match(appSource, /linkClasses[^]*no-underline/, 'linkClasses should include no-underline to prevent blue underlines')
  assert.match(appSource, /linkClasses[^]*text-foreground\/80/, 'linkClasses should default to neutral theme text for inactive links')
})
