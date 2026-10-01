import test from 'node:test'
import assert from 'node:assert/strict'
import { createFeatureCache } from '../src/lib/feature-cache.js'

test('feature cache shares simultaneous consumers and revalidates after expiry', async () => {
  let calls = 0, timestamp = 0, enabled = true
  const read = createFeatureCache(async () => { calls++; return { club_player_publication: enabled } }, { ttl: 15, now: () => timestamp })
  const results = await Promise.all([read(), read(), read()])
  assert.equal(calls, 1)
  assert.deepEqual(results[0], { club_player_publication: true })
  await read(); assert.equal(calls, 1)
  timestamp = 16; enabled = false
  assert.deepEqual(await read(), { club_player_publication: false })
  assert.equal(calls, 2)
})

test('failed feature requests can recover and are not cached', async () => {
  let calls = 0
  const read = createFeatureCache(async () => { if (++calls === 1) throw new Error('offline'); return { club_player_publication: false } })
  await assert.rejects(read(), /offline/)
  assert.deepEqual(await read(), { club_player_publication: false })
  assert.equal(calls, 2)
})
