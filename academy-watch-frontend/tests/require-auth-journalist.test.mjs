import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const appFile = new URL('../src/App.jsx', import.meta.url)

test('RequireAuth accepts and enforces requireJournalist', async () => {
  const src = await fs.readFile(appFile, 'utf8')
  const start = src.indexOf('function RequireAuth(')
  assert.notEqual(start, -1, 'RequireAuth must exist in App.jsx')
  const body = src.slice(start, src.indexOf('\n}\n', start) + 3)
  assert.match(body, /function RequireAuth\(\{ children, requireJournalist = false \}\)/, 'RequireAuth must take a requireJournalist prop with a false default')
  assert.match(body, /const \{ token, isJournalist \} = useAuth\(\)/, 'RequireAuth must read isJournalist from useAuth')
  assert.match(body, /requireJournalist && !isJournalist/, 'RequireAuth must redirect non-journalists when requireJournalist is set')
  assert.match(src, /<RequireAuth requireJournalist>/, 'the writer editor route must still pass requireJournalist')
})
