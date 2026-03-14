import test from 'node:test'
import assert from 'node:assert/strict'

test('buildLoanFetchParams includes supplemental loans by default', async () => {
  const { buildLoanFetchParams } = await import('../src/pages/writer/loanFetchParams.js')
  const params = buildLoanFetchParams()

  assert.equal(params.include_supplemental, 'true')
  assert.equal(params.active_only, 'true')
  assert.equal(params.dedupe, 'true')
  assert.equal(Object.prototype.hasOwnProperty.call(params, 'season'), false)
})

test('buildLoanFetchParams includes direction when provided', async () => {
  const { buildLoanFetchParams } = await import('../src/pages/writer/loanFetchParams.js')
  const params = buildLoanFetchParams({ direction: 'loaned_to' })

  assert.equal(params.direction, 'loaned_to')
})
