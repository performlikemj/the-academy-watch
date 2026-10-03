import test from 'node:test'
import assert from 'node:assert/strict'
import { readWithDeadline, CLUB_ENTRY_DEADLINE_MS } from './entry-read.js'
import { APIService, abandonMyClubFeatureRead } from '../../lib/api.js'
import { resetFeatures, peekFeatures } from '../../lib/features.js'
import { loadClubDirectoryFlag, resetClubDirectoryFlag } from '../../lib/club-directory.js'

async function drain() { for (let i = 0; i < 20; i++) await Promise.resolve() }
function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('MyClub deadline bounds an unanswered body and aborts only that read', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const body = deferred()
  let signal
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    signal = options.signal
    return { ok: true, status: 200, json: () => body.promise }
  })
  const read = readWithDeadline(signal => APIService.request('/me/club-claims', { signal }))
  const rejection = assert.rejects(read, { name: 'TimeoutError' })
  await drain()
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS)
  await rejection
  assert.equal(signal.aborted, true)
  body.resolve({ claims: ['expired'] })
  await drain()
})

test('valid20-second features enables the real directory adapter and shares one main-style read', async t => {
  resetFeatures(); resetClubDirectoryFlag()
  t.after(() => { resetFeatures(); resetClubDirectoryFlag() })
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const response = deferred()
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return response.promise })
  let directory
  const pending = loadClubDirectoryFlag(() => APIService.getFeatures()).then(value => { directory = value })
  const live = APIService.getFeaturesLive()
  await drain()
  t.mock.timers.tick(20000)
  await drain()
  assert.equal(directory, undefined)
  assert.equal(calls, 1)
  response.resolve({ ok: true, status: 200, json: async () => ({ club_directory: true }) })
  await pending; await live
  assert.equal(directory, true)
  await APIService.getFeatures(); await APIService.getFeaturesLive()
  assert.equal(calls, 1)
})

for (const bodyHeld of [false, true]) test(`MyClub expiry/retry releases shared ${bodyHeld ? 'body' : 'fetch'} without rejecting other consumers`, async t => {
  resetFeatures()
  t.after(resetFeatures)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const old = deferred()
  let calls = 0
  const flags = { club_staff_access: true }
  t.mock.method(globalThis, 'fetch', async () => {
    calls++
    if (calls === 1) {
      if (bodyHeld) return { ok: true, status: 200, json: () => old.promise }
      return old.promise
    }
    return { ok: true, status: 200, json: async () => flags }
  })
  const directoryConsumer = APIService.getFeatures()
  const local = readWithDeadline(() => APIService.getFeatures())
  const rejection = assert.rejects(local, { name: 'TimeoutError' })
  await drain()
  assert.equal(calls, 1)
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS)
  await rejection
  assert.equal(peekFeatures(), null)
  abandonMyClubFeatureRead()
  const stale = { club_staff_access: false }
  if (bodyHeld) {
    old.resolve(stale)
    assert.deepEqual(await directoryConsumer, stale)
    assert.equal(peekFeatures(), null)
  }
  assert.equal(await APIService.getFeatures(), flags)
  if (!bodyHeld) old.resolve({ ok: true, status: 200, json: async () => stale })
  assert.deepEqual(await directoryConsumer, stale)
  await drain()
  assert.equal(peekFeatures(), flags)
  assert.equal(await APIService.getFeaturesLive(), flags)
  assert.equal(calls, 2)
})
