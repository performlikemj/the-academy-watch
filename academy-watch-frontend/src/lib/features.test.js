import test from 'node:test'
import assert from 'node:assert/strict'
import { loadFeatures, peekFeatures, resetFeatures } from './features.js'

test('bootstrap shares concurrent requests and caches dark/ON keys for navigation', async () => {
  for (const data of [{ contact_rail: false }, { opportunities: true, applications: true }]) {
    resetFeatures()
    let calls = 0
    const fetch = async () => { calls++; return data }
    assert.deepEqual(await Promise.all([loadFeatures(fetch), loadFeatures(fetch), loadFeatures(fetch)]), [data, data, data])
    assert.equal(await loadFeatures(fetch), data)
    assert.equal(peekFeatures(), data)
    assert.equal(calls, 1)
  }
  resetFeatures()
})
test('failed bootstrap is unknown and retryable, including 429', async () => {
  resetFeatures()
  await assert.rejects(loadFeatures(() => Promise.reject(Object.assign(new Error('rate limited'), { status: 429 }))))
  assert.equal(peekFeatures(), null)
  const flags = { opportunities: true, applications: true }
  assert.equal(await loadFeatures(() => flags), flags)
  resetFeatures()
})
