import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { APIService, nextWindowIndex } = await import('../src/lib/api.js')

test('getVideoReel calls the admin reel endpoint', async () => {
  const originalRequest = APIService.request
  const calls = []
  APIService.request = async (...args) => {
    calls.push(args)
    return { players: [] }
  }

  try {
    const response = await APIService.getVideoReel(42)
    assert.deepEqual(response, { players: [] })
    assert.deepEqual(calls, [['/admin/video/matches/42/reel', {}, { admin: true }]])
  } finally {
    APIService.request = originalRequest
  }
})

test('nextWindowIndex stays live before the end and advances at the boundary', () => {
  const windows = [
    { start_s: 10, end_s: 12 },
    { start_s: 20, end_s: 24 },
  ]

  assert.equal(nextWindowIndex(11.99, windows, 0), 0)
  assert.equal(nextWindowIndex(12, windows, 0), 1)
  assert.equal(nextWindowIndex(24, windows, 1), -1)
})

test('nextWindowIndex handles empty and invalid playlist state', () => {
  const windows = [{ start_s: 5, end_s: 8 }]
  assert.equal(nextWindowIndex(5, [], 0), -1)
  assert.equal(nextWindowIndex(5, windows, -1), 0)
  assert.equal(nextWindowIndex(5, windows, 99), 0)
})
