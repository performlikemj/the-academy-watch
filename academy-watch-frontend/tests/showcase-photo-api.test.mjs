import test from 'node:test'
import assert from 'node:assert/strict'
import { APIService } from '../src/lib/api.js'

for (const admin of [false, true]) {
  test(`private showcase photo sends ${admin ? 'dual admin' : 'owner'} credentials only to the app`, async t => {
    const original = [APIService.userToken, APIService.adminKey]
    APIService.userToken = 'synthetic-user-token'
    APIService.adminKey = 'synthetic-admin-key'
    t.after(() => { [APIService.userToken, APIService.adminKey] = original })
    const expected = new Blob(['jpeg'], { type: 'image/jpeg' })
    const fetch = t.mock.method(globalThis, 'fetch', async () => ({ ok: true, blob: async () => expected }))
    const path = `/api/${admin ? 'admin/' : ''}showcase/media/42/preview`
    assert.equal(await APIService.showcasePhotoBlob(path), expected)
    const [url, options] = fetch.mock.calls[0].arguments
    assert.equal(url, path)
    assert.equal(options.cache, 'no-store')
    assert.equal(options.headers.Authorization, 'Bearer synthetic-user-token')
    assert.equal(options.headers['X-API-Key'], admin ? 'synthetic-admin-key' : undefined)
  })
}

test('private preview refuses external, traversal and unrelated URLs before sending credentials', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', () => { throw new Error('Unexpected request') })
  for (const url of ['https://untrusted.example/api/showcase/media/42/preview', '//untrusted.example/x', '/api/showcase/media/../preview', '/api/club/1/roster/2/photo']) {
    await assert.rejects(APIService.showcasePhotoBlob(url), /Invalid showcase preview URL/)
  }
  assert.equal(fetch.mock.callCount(), 0)
})
