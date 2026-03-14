import test from 'node:test'
import assert from 'node:assert/strict'

import { NEWSLETTER_ACTION_GRID_CLASS } from '../src/pages/admin/admin-newsletters-layout.js'

test('newsletter action cards stay single-column until large screens to avoid squishing', () => {
  assert.ok(
    NEWSLETTER_ACTION_GRID_CLASS.includes('lg:grid-cols-2'),
    'layout should switch to two columns at large breakpoints'
  )
  assert.ok(
    !NEWSLETTER_ACTION_GRID_CLASS.includes('md:grid-cols-2'),
    'layout should not force two columns at medium widths where the sidebar constrains space'
  )
})
