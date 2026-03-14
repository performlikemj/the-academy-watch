import test from 'node:test'
import assert from 'node:assert/strict'

import { getAdminQuickLinks } from '../src/lib/admin-quick-links.js'

test('sandbox link is included and marked for SPA navigation', () => {
  const links = getAdminQuickLinks()
  const sandbox = links.find((link) => link.label === 'Sandbox checks')

  assert.ok(sandbox, 'expected sandbox quick link to exist')
  assert.equal(sandbox.href, '/admin/sandbox')
  assert.equal(sandbox.spa, true)
})
