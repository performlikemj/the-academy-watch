import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const appFileUrl = new URL('../src/App.jsx', import.meta.url)

test('mobile navigation drawer requests autoFocus to move focus into the drawer', async () => {
  const source = await fs.readFile(appFileUrl, 'utf8')

  const navDrawerMatch = source.match(/<Drawer\s+open={drawerOpen}[\s\S]*?>/)
  assert.ok(navDrawerMatch, 'Mobile nav Drawer should be present in App.jsx')

  const navDrawerTag = navDrawerMatch[0]
  const hasAutoFocus = /autoFocus\s*(=\s*{?true}?|\b)/.test(navDrawerTag)

  assert.ok(
    hasAutoFocus,
    'Mobile nav Drawer should enable autoFocus so focus shifts into the drawer content when it opens'
  )
})
