import test from 'node:test'
import assert from 'node:assert/strict'
import { contactRailFromFeatures, loadContactRail, peekContactRail, resetContactRail } from '../src/lib/contact-flags.js'

test('contactRailFromFeatures reads only an explicit true', () => {
  assert.equal(contactRailFromFeatures({ contact_rail: true }), true)
  assert.equal(contactRailFromFeatures({ contact_rail: 'true' }), false)
  assert.equal(contactRailFromFeatures({}), false)
  assert.equal(contactRailFromFeatures(null), false)
})

test('loadContactRail caches a successful answer and dedupes concurrent calls', async () => {
  resetContactRail()
  let calls = 0
  const fetcher = async () => { calls += 1; return { contact_rail: true } }
  const [a, b] = await Promise.all([loadContactRail(fetcher), loadContactRail(fetcher)])
  assert.equal(a, true)
  assert.equal(b, true)
  assert.equal(calls, 1)
  assert.equal(await loadContactRail(fetcher), true)
  assert.equal(calls, 1)
  assert.equal(peekContactRail(), true)
})

test('a failed fetch answers false and is not cached', async () => {
  resetContactRail()
  let calls = 0
  const failing = async () => { calls += 1; throw new Error('offline') }
  assert.equal(await loadContactRail(failing), false)
  assert.equal(peekContactRail(), null)
  assert.equal(await loadContactRail(async () => { calls += 1; return { contact_rail: false } }), false)
  assert.equal(calls, 2)
  assert.equal(peekContactRail(), false)
})
