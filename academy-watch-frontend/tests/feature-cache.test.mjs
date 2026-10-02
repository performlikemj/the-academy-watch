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


test('API feature bootstrap stays page-session cached while live flags refresh after 15 seconds', async (t) => {
  let calls = 0, timestamp = 0
  const originalNow = Date.now
  Date.now = () => timestamp
  t.after(() => { Date.now = originalNow })
  const { APIService } = await import('../src/lib/api.js?c1-live-features')
  const { resetFeatures } = await import('../src/lib/features.js')
  resetFeatures()
  t.after(resetFeatures)
  t.mock.method(APIService, 'request', async (path) => {
    assert.equal(path, '/features')
    return { club_player_publication: ++calls === 1 }
  })
  const bootstrap = await APIService.getFeatures()
  const live = await APIService.getFeaturesLive()
  assert.equal(calls, 2)
  timestamp = 14999
  assert.deepEqual(await APIService.getFeaturesLive(), live)
  assert.deepEqual(await APIService.getFeatures(), bootstrap)
  assert.equal(calls, 2)
  timestamp = 15001
  await APIService.getFeaturesLive()
  assert.equal(calls, 3)
  assert.deepEqual(await APIService.getFeatures(), bootstrap)
  assert.equal(calls, 3)
})
