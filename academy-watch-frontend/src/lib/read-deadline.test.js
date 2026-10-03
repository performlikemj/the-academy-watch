import test from 'node:test'
import assert from 'node:assert/strict'
import { readWithDeadline, CLUB_ENTRY_DEADLINE_MS } from './read-deadline.js'
import { APIService } from './api.js'
import { resetFeatures, peekFeatures } from './features.js'

async function drain() { for (let i = 0; i < 12; i++) await Promise.resolve() }
function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('read deadline rejects an unanswered read and aborts its transport', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let signal
  const read = readWithDeadline(value => { signal = value; return new Promise(() => {}) })
  const rejection = assert.rejects(read, { name: 'TimeoutError' })
  await drain()
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS)
  await rejection
  assert.equal(signal.aborted, true)
})

test('body consumption is bounded even when a transport ignores abort', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const body = deferred()
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, status: 200, json: () => body.promise }))
  const read = readWithDeadline(signal => APIService.getMyClubClaims({ signal }))
  const rejection = assert.rejects(read, { name: 'TimeoutError' })
  await drain()
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS)
  await rejection
  body.resolve({ claims: ['expired'] })
  await drain()
})

for (const bodyHeld of [false, true]) test(`shared bootstrap releases expired ${bodyHeld ? 'body' : 'fetch'} and ignores its late answer`, async t => {
  resetFeatures()
  t.after(resetFeatures)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const old = deferred()
  let calls = 0
  let oldSignal
  const flags = { club_staff_access: true }
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    calls++
    if (calls === 1) {
      oldSignal = options.signal
      if (bodyHeld) return { ok: true, status: 200, json: () => old.promise }
      return old.promise
    }
    return { ok: true, status: 200, json: async () => flags }
  })
  const first = APIService.getFeatures()
  const shared = APIService.getFeaturesLive()
  const rejected = Promise.all([assert.rejects(first, { name: 'TimeoutError' }), assert.rejects(shared, { name: 'TimeoutError' })])
  await drain()
  assert.equal(calls, 1)
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS)
  await rejected
  assert.equal(oldSignal.aborted, true)
  assert.equal(peekFeatures(), null)
  assert.equal(await APIService.getFeatures(), flags)
  const stale = { club_staff_access: false }
  old.resolve(bodyHeld ? stale : { ok: true, status: 200, json: async () => stale })
  await drain()
  assert.equal(peekFeatures(), flags)
  assert.equal(await APIService.getFeaturesLive(), flags)
  assert.equal(calls, 2)
})
