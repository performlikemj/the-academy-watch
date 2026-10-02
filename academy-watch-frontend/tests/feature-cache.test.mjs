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


async function featureReaders(t, name) {
  let timestamp = 0
  const originalNow = Date.now
  Date.now = () => timestamp
  t.after(() => { Date.now = originalNow })
  const { APIService } = await import(`../src/lib/api.js?${name}`)
  const { resetFeatures, peekFeatures } = await import('../src/lib/features.js')
  resetFeatures()
  t.after(resetFeatures)
  return { APIService, peekFeatures, advanceTo: value => { timestamp = value } }
}

for (const first of ['getFeatures', 'getFeaturesLive']) {
  test(`API feature readers share the first in-flight request with ${first} first`, async (t) => {
    const { APIService } = await featureReaders(t, `c1-shared-${first}`)
    let resolveFetch
    const request = t.mock.method(APIService, 'request', path => {
      assert.equal(path, '/features')
      return new Promise(resolve => { resolveFetch = resolve })
    })
    const second = first === 'getFeatures' ? 'getFeaturesLive' : 'getFeatures'
    const reads = [APIService[first](), APIService[second]()]
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(request.mock.callCount(), 1)
    const flags = { club_player_publication: false }
    resolveFetch(flags)
    assert.deepEqual(await Promise.all(reads), [flags, flags])
  })
}

test('live features reuse a fresh page-session value without another request', async (t) => {
  const { APIService, advanceTo } = await featureReaders(t, 'c1-fresh-page')
  const request = t.mock.method(APIService, 'request', async () => ({ club_player_publication: true }))
  const bootstrap = await APIService.getFeatures()
  advanceTo(14999)
  assert.strictEqual(await APIService.getFeaturesLive(), bootstrap)
  assert.equal(request.mock.callCount(), 1)
})

test('live features fetch a stale page-session value while bootstrap remains cached', async (t) => {
  const { APIService, advanceTo } = await featureReaders(t, 'c1-stale-page')
  let enabled = true
  const request = t.mock.method(APIService, 'request', async () => ({ club_player_publication: enabled }))
  const bootstrap = await APIService.getFeatures()
  enabled = false
  advanceTo(15000)
  assert.deepEqual(await APIService.getFeaturesLive(), { club_player_publication: false })
  assert.equal(request.mock.callCount(), 2)
  assert.strictEqual(await APIService.getFeatures(), bootstrap)
  assert.equal(request.mock.callCount(), 2)
})

test('publication OFF is observed by the next 30-second live poll', async (t) => {
  const { APIService, advanceTo } = await featureReaders(t, 'c1-next-poll')
  let enabled = true
  const request = t.mock.method(APIService, 'request', async () => ({ club_player_publication: enabled }))
  const bootstrap = await APIService.getFeatures()
  assert.deepEqual(await APIService.getFeaturesLive(), bootstrap)
  enabled = false
  advanceTo(14999)
  assert.deepEqual(await APIService.getFeaturesLive(), bootstrap)
  assert.equal(request.mock.callCount(), 1)
  advanceTo(30000)
  assert.deepEqual(await APIService.getFeaturesLive(), { club_player_publication: false })
  assert.equal(request.mock.callCount(), 2)
  assert.strictEqual(await APIService.getFeatures(), bootstrap)
})

test('failed shared bootstrap remains unknown and retries with one shared request', async (t) => {
  const { APIService, peekFeatures } = await featureReaders(t, 'c1-failed-shared')
  let fail = true
  const request = t.mock.method(APIService, 'request', async () => {
    if (fail) throw new Error('offline')
    return { club_player_publication: false }
  })
  const failed = await Promise.allSettled([APIService.getFeaturesLive(), APIService.getFeatures()])
  assert.deepEqual(failed.map(result => result.status), ['rejected', 'rejected'])
  assert.equal(peekFeatures(), null)
  assert.equal(request.mock.callCount(), 1)
  fail = false
  const recovered = await Promise.all([APIService.getFeatures(), APIService.getFeaturesLive()])
  assert.deepEqual(recovered, [{ club_player_publication: false }, { club_player_publication: false }])
  assert.equal(request.mock.callCount(), 2)
})
