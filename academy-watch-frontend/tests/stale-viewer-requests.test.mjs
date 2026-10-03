import test from 'node:test'
import assert from 'node:assert/strict'

// api.js persists credentials; give it an in-memory store before it loads.
const store = new Map()
globalThis.localStorage = {
  getItem: (key) => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => { store.set(key, String(value)) },
  removeItem: (key) => { store.delete(key) },
}
const { APIService } = await import('../src/lib/api.js')
const { StaleViewerError, createViewerLifetime, isStaleViewerError } = await import('../src/lib/viewer-lifetime.js')

// A fetch whose answers the test releases by hand, recording what was sent.
function heldFetch() {
  const calls = []
  globalThis.fetch = (url, init = {}) => new Promise((resolve, reject) => {
    calls.push({
      url: String(url),
      authorization: init.headers?.Authorization || null,
      answer: (status, body = {}) => resolve(new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })),
      fail: (error = new TypeError('network down')) => reject(error),
    })
  })
  return calls
}
const quiet = async (work) => {
  const original = console.error
  console.error = () => {}
  try { return await work() } finally { console.error = original }
}
const signIn = (token) => { APIService.setUserToken(token) }

test.beforeEach(() => { APIService.setUserToken(''); APIService.setAdminKey('') })

// ---- The shared request layer (PCF5: narrowed) -----------------------------
// Data is delivered to its caller even if the credential changed meanwhile
// (pages outside the keyed boundaries do not re-read on a sign-in change). The
// one global rule: a 401 for a credential that is no longer current is a plain
// failure — no status — so nothing signs the current session out because of it.

test('request() delivers data across a credential change: success, anonymous answer after sign-in, network failure', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const created = APIService.request('/local-clubs', { method: 'POST', body: '{}' })
  APIService.setUserToken('')
  const anonymousFirst = APIService.request('/programs/demo-club')
  const failing = APIService.request('/players/1/showcase')
  signIn('token-b')
  assert.equal(calls[0].authorization, 'Bearer token-a')
  assert.equal(calls[1].authorization, null)
  calls[0].answer(201, { club: { id: 7 } })
  calls[1].answer(200, { program: { slug: 'demo-club' } })
  calls[2].fail()

  assert.deepEqual(await created, { club: { id: 7 } })
  assert.deepEqual(await anonymousFirst, { program: { slug: 'demo-club' } })
  await quiet(() => assert.rejects(failing, (error) => error instanceof TypeError && !isStaleViewerError(error)))
})

test('an expired saved sign-in at start-up: the profile 401 signs out, a public read sent with the old token is still delivered', async () => {
  const calls = heldFetch()
  signIn('expired-token')
  const refresh = APIService.refreshProfile()
  const club = APIService.request('/programs/demo-club')
  calls[0].answer(401, { error: 'expired' })
  await quiet(() => assert.rejects(refresh, (error) => error.status === 401))
  assert.equal(APIService.userToken, null)
  calls[1].answer(200, { program: { slug: 'demo-club' } })
  assert.deepEqual(await club, { program: { slug: 'demo-club' } })
})

test('a late 401 for a credential that is no longer current is a plain failure and signs nobody out', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const refresh = APIService.refreshProfile()
  const save = APIService.request('/players/1/matches', { method: 'POST', body: '{}' })
  signIn('token-b')
  calls[0].answer(401, { error: 'expired' })
  calls[1].answer(401, { error: 'expired' })

  for (const pending of [refresh, save]) {
    await quiet(() => assert.rejects(pending, (error) => error.status === undefined && error.staleCredential === true && !isStaleViewerError(error)))
  }
  assert.equal(APIService.userToken, 'token-b')
})

test('a late 401 after logout and another sign-in does not act either; a genuine 401 still signs out', async () => {
  let calls = heldFetch()
  signIn('token-a')
  const refresh = APIService.refreshProfile()
  APIService.logout()
  signIn('token-c')
  calls[0].answer(401, { error: 'expired' })
  await quiet(() => assert.rejects(refresh, (error) => error.status === undefined))
  assert.equal(APIService.userToken, 'token-c')

  calls = heldFetch()
  const genuine = APIService.refreshProfile()
  calls[0].answer(401, { error: 'expired' })
  await quiet(() => assert.rejects(genuine, (error) => error.status === 401 && !error.staleCredential))
  assert.equal(APIService.userToken, null)
})

test('the same credential gets its ordinary answers: success, null on 204, and failures with their status', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const ok = APIService.request('/x')
  const empty = APIService.request('/y', { method: 'DELETE' })
  const denied = APIService.request('/z')
  calls[0].answer(200, { fine: true })
  calls[1].answer(204)
  calls[2].answer(403, { error: 'no' })

  assert.deepEqual(await ok, { fine: true })
  assert.equal(await empty, null)
  await quiet(() => assert.rejects(denied, (error) => error.status === 403 && error.message === 'no'))
})

test('a non-401 failure across a credential change keeps its status (it is not a session answer)', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const pending = APIService.request('/z')
  signIn('token-b')
  calls[0].answer(503, { error: 'busy' })
  await quiet(() => assert.rejects(pending, (error) => error.status === 503))
})

test('sign-in keeps working: the verify answer is delivered and establishes the credential', async () => {
  let calls = heldFetch()
  const signedIn = APIService.verifyLoginCode('a@example.test', '123456')
  calls[0].answer(200, { token: 'fresh-token', role: 'user' })
  assert.equal((await signedIn).token, 'fresh-token')
  assert.equal(APIService.userToken, 'fresh-token')

  // An expired stored session is cleared while the email-link verify is in flight.
  calls = heldFetch()
  signIn('expired-stored-token')
  const verify = APIService.verifyLoginCode('a@example.test', '654321')
  APIService.logout()
  calls[0].answer(200, { token: 'new-token', role: 'user' })
  await verify
  assert.equal(APIService.userToken, 'new-token')
})

test('admin requests: a 401 after the admin key changed is a plain failure too', async () => {
  const calls = heldFetch()
  signIn('admin-token')
  APIService.setAdminKey('key-1')
  const data = APIService.request('/admin/x', {}, { admin: true })
  const denied = APIService.request('/admin/y', {}, { admin: true })
  APIService.setAdminKey('key-2')
  calls[0].answer(200, { ok: true })
  calls[1].answer(401, { error: 'bad key' })

  assert.deepEqual(await data, { ok: true })
  await quiet(() => assert.rejects(denied, (error) => error.status === undefined))
  assert.equal(APIService.userToken, 'admin-token')
})

test('fetchScoutCsv returns the fully read body and has no side effect', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const pending = APIService.fetchScoutCsv({ sort: 'name' })
  assert.match(calls[0].url, /\/scout\/export\.csv\?sort=name$/)
  calls[0].answer(200, 'a,b')
  const blob = await pending
  assert.equal(await blob.text(), '"a,b"')
})

// ---- Inside the keyed pages: strict binding through the viewer lifetime -----

test('viewer lifetime: a data answer that lands after the viewer changed is a StaleViewerError', async () => {
  let current = 'user:a'
  let release
  const life = createViewerLifetime({ viewer: 'user:a', currentViewer: () => current })
  life.mount()
  const api = life.api({ read: () => new Promise((resolve) => { release = resolve }) })
  const pending = api.read()
  current = 'user:b'
  release({ profile: 'A only' })
  await assert.rejects(pending, (error) => error instanceof StaleViewerError && error.status === undefined)
})

test('viewer lifetime: after a viewer change no new request is started and late results are stale', async () => {
  let current = 'user:a'
  const sent = []
  const client = {
    create: (name) => { sent.push(['create', name]); return new Promise((resolve) => { client.release = () => resolve({ id: 7 }) }) },
    affiliate: (id) => { sent.push(['affiliate', id]); return Promise.resolve({ ok: true }) },
    plain: () => 'sync',
  }
  const life = createViewerLifetime({ viewer: 'user:a', currentViewer: () => current })
  life.mount()
  const api = life.api(client)
  assert.equal(life.api(client), api)
  assert.equal(api.plain(), 'sync')

  // The reviewer's case: create is held, the viewer changes, the handler carries on.
  const handler = (async () => {
    const club = await api.create('New club')
    await api.affiliate(club.id)
  })()
  current = 'user:b'
  client.release()

  await assert.rejects(handler, isStaleViewerError)
  assert.deepEqual(sent, [['create', 'New club']])
  // Refused without sending — as a rejection, so `.catch` chains handle it
  // (a synchronous throw inside a `.then` escaped them: RPCV5-O Small).
  await assert.rejects(api.affiliate(7), StaleViewerError)
  assert.equal(await api.create('x').then(() => 'sent', () => null), null)
  assert.deepEqual(sent, [['create', 'New club']])
})

test('viewer lifetime: guarded side effects run only while mounted under the same viewer', () => {
  let current = 'user:a'
  const ran = []
  const life = createViewerLifetime({ viewer: 'user:a', currentViewer: () => current })
  const navigate = life.guard((to) => { ran.push(to); return 'went' })

  assert.equal(navigate('/before-mount'), undefined)
  life.mount()
  assert.equal(navigate('/scout/verification'), 'went')
  life.unmount()
  assert.equal(navigate('/after-unmount'), undefined)
  life.mount()
  current = 'user:b'
  assert.equal(navigate('/after-switch'), undefined)
  assert.deepEqual(ran, ['/scout/verification'])
  assert.equal(life.alive(), false)
})

test('viewer lifetime: unmounting alone does not abort a same-viewer write; a failure keeps its own error', async () => {
  const life = createViewerLifetime({ viewer: 'user:a', currentViewer: () => 'user:a' })
  life.mount()
  const api = life.api({
    save: () => Promise.resolve('saved'),
    fail: () => Promise.reject(Object.assign(new Error('nope'), { status: 422 })),
  })
  life.unmount()

  assert.equal(await api.save(), 'saved')
  await assert.rejects(api.fail(), (error) => error.status === 422 && !isStaleViewerError(error))
})
