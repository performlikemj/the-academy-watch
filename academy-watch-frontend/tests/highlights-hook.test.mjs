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
  let states = [], effects = [], cursor = 0, effectCursor = 0, result, dirty = false
  const context = vm.createContext({
    APIService: { getFeaturesLive: loader },
    useState: initial => {
      const index = cursor++
      if (!(index in states)) states[index] = initial
      return [states[index], value => {
        states[index] = typeof value === 'function' ? value(states[index]) : value
        dirty = true
      }]
    },
    useEffect: (effect, deps) => {
      const index = effectCursor++
      const previous = effects[index]
      if (!previous || deps.some((value, i) => value !== previous.deps[i])) {
        previous?.cleanup?.()
        effects[index] = { deps, cleanup: effect() }
      }
    },
  })
  vm.runInContext(source, context)
  function render() {
    cursor = 0; effectCursor = 0; dirty = false
    result = context.useHighlightsState()
  }
  async function settle() {
    await new Promise(resolve => setImmediate(resolve))
    if (dirty) render()
    return { enabled: result.enabled, status: result.status }
  }
  return {
    async mount({ unmount = false } = {}) {
      effects.forEach(value => value.cleanup?.())
      states = []; effects = []
      render()
      if (unmount) effects.forEach(value => value.cleanup?.())
      return settle()
    },
    async retry() { result.retry(); render(); return settle() },
  }
}

test('initial failure stays unknown and Retry recovers without remounting', async () => {
  let calls = 0
  const read = createFeatureCache(async () => {
    if (++calls === 1) throw new Error('offline')
    return { highlights: true }
  })
  const hook = await hookHarness(read)
  assert.deepEqual(await hook.mount(), { enabled: null, status: 'failed' })
  assert.deepEqual(await hook.retry(), { enabled: true, status: 'known' })
  assert.equal(calls, 2)
})

test('a failed expired refresh retains known ON until a successful OFF', async () => {
  let calls = 0, timestamp = 0
  const read = createFeatureCache(async () => {
    calls++
    if (calls === 2) throw new Error('offline')
    return { highlights: calls === 1 }
  }, { ttl: 15, now: () => timestamp })
  const hook = await hookHarness(read)
  assert.deepEqual(await hook.mount(), { enabled: true, status: 'known' })
  timestamp = 16
  assert.deepEqual(await hook.retry(), { enabled: true, status: 'failed' })
  assert.deepEqual(await hook.retry(), { enabled: false, status: 'known' })
  assert.equal(calls, 3)
})

test('a fresh consumer does not infer OFF when the expired live read fails', async () => {
  let timestamp = 0, fail = false
  const read = createFeatureCache(async () => {
    if (fail) throw new Error('offline')
    return { highlights: true }
  }, { ttl: 15, now: () => timestamp })
  const hook = await hookHarness(read)
  assert.deepEqual(await hook.mount(), { enabled: true, status: 'known' })
  timestamp = 16; fail = true
  assert.deepEqual(await hook.mount(), { enabled: null, status: 'failed' })
  fail = false
  assert.deepEqual(await hook.retry(), { enabled: true, status: 'known' })
})

test('new highlights consumers preserve shared TTL and successful ON/OFF', async () => {
  let calls = 0, timestamp = 0, enabled = true
  const read = createFeatureCache(async () => { calls++; return { highlights: enabled } }, { ttl: 15, now: () => timestamp })
  const hook = await hookHarness(read)
  assert.deepEqual(await hook.mount(), { enabled: true, status: 'known' })
  timestamp = 16; enabled = false
  assert.deepEqual(await hook.mount(), { enabled: false, status: 'known' })
  assert.equal(calls, 2)
})

test('concurrent consumers share the first features request', async () => {
  let calls = 0
  const read = createFeatureCache(async () => { calls++; return { highlights: true } })
  const hooks = await Promise.all([hookHarness(read), hookHarness(read)])
  assert.deepEqual(await Promise.all(hooks.map(hook => hook.mount())), [
    { enabled: true, status: 'known' }, { enabled: true, status: 'known' },
  ])
  assert.equal(calls, 1)
})

test('unmounted highlights consumer ignores a delayed features result', async () => {
  const hook = await hookHarness(async () => ({ highlights: true }))
  assert.deepEqual(await hook.mount({ unmount: true }), { enabled: null, status: 'loading' })
})

test('a raced moderation hold explains why retrying the pick cannot work', async () => {
  const source = (await readFile(new URL('../src/components/highlights/useHighlights.js', import.meta.url), 'utf8'))
    .replace(/^import .*\n/gm, '').replace(/^export /gm, '')
  const context = vm.createContext({})
  vm.runInContext(source, context)
  const held = new Error('highlight_admin_taken_down'); held.status = 422
  assert.equal(context.message(held), 'This moment was taken down by The Academy Watch and cannot be picked.')
  assert.match(context.message({ status: 409 }), /Refresh/)
})
