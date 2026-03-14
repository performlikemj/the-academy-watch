import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const previewFileUrl = new URL('../src/components/admin/NewsletterPreviewDialog.jsx', import.meta.url)

test('Newsletter preview iframe allows scripts inside sandboxed preview', async () => {
  const source = await fs.readFile(previewFileUrl, 'utf8')

  const iframeMatch = source.match(/<iframe[^>]*sandbox="([^"]+)"[^>]*>/)
  assert.ok(iframeMatch, 'NewsletterPreviewDialog should include an iframe with a sandbox attribute')

  assert.match(
    iframeMatch[1],
    /\ballow-scripts\b/,
    'Iframe sandbox should allow scripts so previews can run inline JS'
  )
})
