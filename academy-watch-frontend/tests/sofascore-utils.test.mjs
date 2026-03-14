import test from 'node:test'
import assert from 'node:assert/strict'

import { buildSofascoreEmbedUrl, normalizeSofascoreId } from '../src/lib/sofascore.js'

test('buildSofascoreEmbedUrl builds dark-theme widget url by default', () => {
  const url = buildSofascoreEmbedUrl(1101989)
  assert.equal(url, 'https://widgets.sofascore.com/embed/player/1101989?widgetTheme=dark')
})

test('buildSofascoreEmbedUrl returns null for invalid ids', () => {
  assert.equal(buildSofascoreEmbedUrl(null), null)
  assert.equal(buildSofascoreEmbedUrl(''), null)
  assert.equal(buildSofascoreEmbedUrl('abc'), null)
})

test('normalizeSofascoreId coerces numeric strings', () => {
  assert.equal(normalizeSofascoreId('1101989'), 1101989)
  assert.equal(normalizeSofascoreId(1101989), 1101989)
  assert.equal(normalizeSofascoreId(' 1101989 '), 1101989)
})

test('normalizeSofascoreId rejects non-numeric inputs', () => {
  assert.equal(normalizeSofascoreId('abc'), null)
  assert.equal(normalizeSofascoreId(undefined), null)
})
