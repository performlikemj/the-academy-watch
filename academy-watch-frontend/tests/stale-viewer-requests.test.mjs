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

test('an answer for a credential that is no longer current is a StaleViewerError, not a success', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const pending = APIService.request('/local-clubs', { method: 'POST', body: '{}' })
  assert.equal(calls[0].authorization, 'Bearer token-a')
  signIn('token-b')
  calls[0].answer(201, { club: { id: 7 } })

  await assert.rejects(pending, (error) => error instanceof StaleViewerError && isStaleViewerError(error) && error.status === undefined)
})

test('a late 401 for the old credential is not an ordinary failure and logs nobody out', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const refresh = APIService.refreshProfile()
  signIn('token-b')
  calls[0].answer(401, { error: 'expired' })

  await quiet(() => assert.rejects(refresh, (error) => isStaleViewerError(error) && error.status !== 401))
  assert.equal(APIService.userToken, 'token-b')
})

test('a late 401 after logout does not act on the signed-out session either; a genuine 401 still signs out', async () => {
  let calls = heldFetch()
  signIn('token-a')
  const refresh = APIService.refreshProfile()
  APIService.logout()
  signIn('token-c')
  calls[0].answer(401, { error: 'expired' })
  await quiet(() => assert.rejects(refresh, isStaleViewerError))
  assert.equal(APIService.userToken, 'token-c')

  calls = heldFetch()
  const genuine = APIService.refreshProfile()
  calls[0].answer(401, { error: 'expired' })
  await quiet(() => assert.rejects(genuine, (error) => error.status === 401 && !isStaleViewerError(error)))
  assert.equal(APIService.userToken, null)
})

test('a network failure or an anonymous answer that lands after the change is stale too', async () => {
  const calls = heldFetch()
  signIn('token-a')
  const failing = APIService.request('/players/1/showcase')
  const anonymousFirst = (APIService.setUserToken(''), APIService.request('/players/1/showcase'))
  signIn('token-b')
  calls[0].fail()
  calls[1].answer(200, { profile: null })

  await quiet(() => assert.rejects(failing, isStaleViewerError))
  await assert.rejects(anonymousFirst, isStaleViewerError)
  assert.equal(calls[1].authorization, null)
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
  await quiet(() => assert.rejects(denied, (error) => error.status === 403 && error.message === 'no' && !isStaleViewerError(error)))
})

test('sign-in keeps working: the verify answer is delivered whatever happened to the previous credential', async () => {
  // Ordinary sign-in: sent signed out, the answer establishes the credential.
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

  // Asking for a code is not bound to a viewer either.
  calls = heldFetch()
  const code = APIService.requestLoginCode('a@example.test')
  signIn('someone-else')
  calls[0].answer(200, { sent: true })
  assert.deepEqual(await code, { sent: true })
})

test('app-wide public configuration is delivered across a sign-in (it is the same for every viewer)', async () => {
  const calls = heldFetch()
  const mode = APIService.getDataMode()
  const seasons = APIService.getSeasons()
  signIn('token-a')
  calls[0].answer(200, { api_football_frozen: true })
  calls[1].answer(200, { current_season: 2026 })

  assert.deepEqual(await mode, { api_football_frozen: true })
  assert.deepEqual(await seasons, { current_season: 2026 })
})

test('admin requests are also bound to the admin key they were sent with', async () => {
  const calls = heldFetch()
  signIn('admin-token')
  APIService.setAdminKey('key-1')
  const pending = APIService.request('/admin/x', {}, { admin: true })
  APIService.setAdminKey('key-2')
  calls[0].answer(200, { ok: true })

  await assert.rejects(pending, isStaleViewerError)
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
  assert.throws(() => api.affiliate(7), StaleViewerError)
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
