import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const dialogFileUrl = new URL('../src/components/ui/dialog.jsx', import.meta.url)

test('DialogContent provides fallback aria-describedby text when no description is supplied', async () => {
  const source = await fs.readFile(dialogFileUrl, 'utf8')

  const contentBlock = source.match(/<DialogPrimitive\.Content[\s\S]*?<\/DialogPrimitive\.Content>/)
  assert.ok(contentBlock, 'DialogPrimitive.Content block should exist')

  assert.match(
    contentBlock[0],
    /aria-describedby=/,
    'DialogPrimitive.Content should set aria-describedby to satisfy a11y'
  )

  assert.match(
    contentBlock[0],
    /sr-only/,
    'DialogContent should render a hidden fallback description for screen readers'
  )

  assert.match(
    source,
    /Dialog content and actions\./,
    'DialogContent should expose a default description string for fallback accessibility'
  )
})
