import test from 'node:test'
import assert from 'node:assert/strict'
import { watchEntryRead, CLUB_ENTRY_DEADLINE_MS } from './entry-read.js'
import { APIService } from '../../lib/api.js'
import { resetFeatures, peekFeatures } from '../../lib/features.js'
import { loadClubDirectoryFlag, resetClubDirectoryFlag } from '../../lib/club-directory.js'

async function drain() { for (let i = 0; i < 20; i++) await Promise.resolve() }
function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('MyClub Retry threshold includes the body and preserves late successful read', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const body = deferred()
  let slow = 0
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, status: 200, json: () => body.promise }))
  const read = watchEntryRead(() => APIService.getMyClubClaims(), () => { slow++ })
  await drain()
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS - 1)
  assert.equal(slow, 0)
  t.mock.timers.tick(1)
  assert.equal(slow, 1)
  body.resolve({ claims: ['current late grant'] })
  assert.deepEqual(await read, { claims: ['current late grant'] })
})

for (const seconds of [20, 70]) test(`valid${seconds}-second features enables the directory and shares main's read`, async t => {
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
  t.mock.timers.tick(seconds * 1000)
  await drain()
  assert.equal(directory, undefined)
  assert.equal(calls, 1)
  response.resolve({ ok: true, status: 200, json: async () => ({ club_directory: true }) })
  await pending; await live
  assert.equal(directory, true)
  await APIService.getFeatures(); await APIService.getFeaturesLive()
  assert.equal(calls, 1)
})

test('MyClub fresh local retry leaves main bootstrap and its awaiting consumers intact', async t => {
  resetFeatures()
  t.after(resetFeatures)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const old = deferred()
  let calls = 0
  let slow = 0
  const fresh = { club_staff_access: true }
  t.mock.method(globalThis, 'fetch', async () => {
    calls++
    return calls === 1 ? old.promise : { ok: true, status: 200, json: async () => fresh }
  })
  const otherConsumer = APIService.getFeatures()
  const local = watchEntryRead(() => APIService.getFeatures(), () => { slow++ })
  await drain()
  assert.equal(calls, 1)
  t.mock.timers.tick(CLUB_ENTRY_DEADLINE_MS)
  assert.equal(slow, 1)
  assert.equal(peekFeatures(), null)
  assert.equal(await APIService.request('/features'), fresh)
  const late = { club_staff_access: false }
  old.resolve({ ok: true, status: 200, json: async () => late })
  assert.deepEqual(await otherConsumer, late)
  assert.deepEqual(await local, late)
  assert.equal(peekFeatures(), late)
  assert.equal(calls, 2)
})
