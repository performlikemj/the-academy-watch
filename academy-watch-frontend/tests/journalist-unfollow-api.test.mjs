import assert from 'node:assert/strict'
import { test } from 'node:test'
import { APIService } from '../src/lib/api.js'

test('writer unfollow uses the existing POST endpoint and returns success', async (t) => {
  const request = t.mock.method(APIService, 'request', async () => ({ message: 'Unsubscribed successfully' }))
  const result = await APIService.unsubscribeFromJournalist(7)
  assert.deepEqual(request.mock.calls[0].arguments, ['/journalists/7/unsubscribe', { method: 'POST' }])
  assert.equal(result.message, 'Unsubscribed successfully')
})

test('writer unfollow propagates API errors so Settings can retain the card', async (t) => {
  const error = new Error('Unable to unfollow. Please try again.')
  t.mock.method(APIService, 'request', async () => { throw error })
  await assert.rejects(APIService.unsubscribeFromJournalist(7), (received) => received === error)
})
