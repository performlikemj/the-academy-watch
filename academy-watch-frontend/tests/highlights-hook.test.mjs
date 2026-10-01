import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { createFeatureCache } from '../src/lib/feature-cache.js'

// Run the real hook's effects with deterministic mount/unmount and shared-cache time.
// The browser spec separately covers React rendering and native media errors.
async function hookHarness(loader) {
  const source = (await readFile(new URL('../src/components/highlights/useHighlights.js', import.meta.url), 'utf8'))
    .replace(/^import .*\n/gm, '').replace(/^export /gm, '')
  let state, effects = []
  const context = vm.createContext({
    APIService: { getFeatures: loader },
    useState: initial => { state = initial; return [state, value => { state = value }] },
    useEffect: effect => effects.push(effect),
  })
  vm.runInContext(source, context)
  return {
    async mount({ unmount = false } = {}) {
      effects = []
      context.useHighlightsState()
      const cleanup = effects.map(effect => effect())
      if (unmount) cleanup.forEach(stop => stop())
      await new Promise(resolve => setImmediate(resolve))
      return JSON.parse(JSON.stringify(state))
    },
  }
}

test('fresh highlights consumers recover after the shared feature request fails', async () => {
  let calls = 0
  const read = createFeatureCache(async () => {
    if (++calls === 1) throw new Error('offline')
    return { highlights: true }
  })
  const hook = await hookHarness(read)
  assert.deepEqual(await hook.mount(), { enabled: false, loaded: true })
  assert.deepEqual(await hook.mount(), { enabled: true, loaded: true })
  assert.equal(calls, 2)
})

test('new highlights consumers use shared TTL instead of retaining flags for the session', async () => {
  let calls = 0, timestamp = 0, enabled = true
  const read = createFeatureCache(async () => { calls++; return { highlights: enabled } }, { ttl: 15, now: () => timestamp })
  const hook = await hookHarness(read)
  assert.deepEqual(await hook.mount(), { enabled: true, loaded: true })
  timestamp = 16; enabled = false
  assert.deepEqual(await hook.mount(), { enabled: false, loaded: true })
  assert.equal(calls, 2)
})

test('unmounted highlights consumer ignores a delayed features result', async () => {
  const hook = await hookHarness(async () => ({ highlights: true }))
  assert.deepEqual(await hook.mount({ unmount: true }), { enabled: false, loaded: false })
})
