import test from 'node:test'
import assert from 'node:assert/strict'
import { buildAdminPreviewSendOptions } from '../src/lib/newsletter-admin.js'

test('buildAdminPreviewSendOptions defaults to web render with no simulation', () => {
  const payload = buildAdminPreviewSendOptions()

  assert.equal(payload.render_mode, 'web')
  assert.equal(payload.use_snippets, false)
  assert.equal(payload.journalist_ids, null)
})

test('buildAdminPreviewSendOptions enables snippets only for email mode', () => {
  const emailPayload = buildAdminPreviewSendOptions({ renderMode: 'email', useSnippets: true })
  const webPayload = buildAdminPreviewSendOptions({ renderMode: 'web', useSnippets: true })

  assert.equal(emailPayload.render_mode, 'email')
  assert.equal(emailPayload.use_snippets, true)
  assert.equal(webPayload.render_mode, 'web')
  assert.equal(webPayload.use_snippets, false)
})

test('buildAdminPreviewSendOptions includes unique simulated journalist ids', () => {
  const payload = buildAdminPreviewSendOptions({
    renderMode: 'email',
    useSnippets: true,
    simulateSubscription: true,
    selectedJournalists: [3, '4', 4, 0, -1, 'abc'],
  })

  assert.deepEqual(payload.journalist_ids, [3, 4])
  assert.equal(payload.use_snippets, true)
})
