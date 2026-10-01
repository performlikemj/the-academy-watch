import test from 'node:test'
import assert from 'node:assert/strict'
import { APIService } from '../src/lib/api.js'

test('feature bootstrap is shared across simultaneous and later consumers, failures retry', async () => {
  const original = APIService.request
  try {
    let calls = 0
    APIService.featuresPromise = null
    APIService.request = async () => { calls++; return { highlights: true } }
    const flags = await Promise.all([APIService.getFeatures(), APIService.getFeatures(), APIService.getFeatures()])
    assert.equal(calls, 1)
    assert.equal(flags[0], flags[2])
    await APIService.getFeatures()
    assert.equal(calls, 1)
    APIService.featuresPromise = null
    APIService.request = async () => { throw new Error('offline') }
    await assert.rejects(APIService.getFeatures())
    APIService.request = async () => { calls++; return {} }
    assert.deepEqual(await APIService.getFeatures(), {})
    assert.equal(calls, 2)
  } finally { APIService.request = original; APIService.featuresPromise = null }
})

test('private preview authenticates only to API and returns native media URL', async () => {
  const original = APIService.request
  const id = '00000000-0000-4000-8000-000000000001'
  try {
    let endpoint
    APIService.request = async path => { endpoint = path; return { url: 'https://private-storage.test/highlights/clip.mp4?read=60' } }
    assert.equal(await APIService.highlightPreviewUrl(`/api/me/highlight-requests/${id}/preview`), 'https://private-storage.test/highlights/clip.mp4?read=60')
    assert.equal(endpoint, `/me/highlight-requests/${id}/preview?transport=url`)
    await assert.rejects(APIService.highlightPreviewUrl('/api/video/1/footage'))
    APIService.request = async () => ({ url: 'javascript:alert(1)' })
    await assert.rejects(APIService.highlightPreviewUrl(`/api/me/highlight-requests/${id}/preview`))
  } finally { APIService.request = original }
})
