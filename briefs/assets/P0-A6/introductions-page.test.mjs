import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { statusLabel, counterpartName, canWithdraw, canRespond, previewText, upsertRequest } from '../src/lib/introductions.js'

const pageFile = new URL('../src/pages/IntroductionsPage.jsx', import.meta.url)
const appFile = new URL('../src/App.jsx', import.meta.url)

test('row helpers follow box and status', () => {
  const req = { id: 'r1', status: 'pending', player_api_id: 42, participants: { scout: { display_name: 'Alex' }, player: { display_name: null } } }
  assert.equal(counterpartName(req, 'inbox'), 'Alex')
  assert.equal(counterpartName(req, 'sent'), 'Player 42')
  assert.equal(canWithdraw(req, 'sent'), true)
  assert.equal(canWithdraw(req, 'inbox'), false)
  assert.equal(canRespond(req, 'inbox'), true)
  assert.equal(canRespond({ ...req, status: 'accepted' }, 'inbox'), false)
  assert.equal(statusLabel('no_such'), 'no_such')
  assert.equal(statusLabel('accepted'), 'Accepted')
  assert.equal(previewText('  hello\n\nworld  '), 'hello world')
  assert.equal(previewText('x'.repeat(200)).length, 120)
})

test('upsertRequest replaces by id or prepends', () => {
  const list = [{ id: 'a', status: 'pending' }, { id: 'b', status: 'pending' }]
  assert.deepEqual(upsertRequest(list, { id: 'b', status: 'accepted' }).map((r) => r.status), ['pending', 'accepted'])
  assert.equal(upsertRequest(list, { id: 'c' }).length, 3)
  assert.equal(upsertRequest(list, null), list)
})

test('the page lists both boxes, acts through APIService, mounts ContactThread, and is routed', async () => {
  const page = await fs.readFile(pageFile, 'utf8')
  assert.ok(page.includes("APIService.listContactRequests({ box: which, limit: 100 })"))
  assert.ok(page.includes('APIService.acceptContactRequest(request.id)'))
  assert.ok(page.includes('APIService.declineContactRequest(request.id)'))
  assert.ok(page.includes('APIService.withdrawContactRequest(request.id)'))
  assert.ok(page.includes('<ContactThread request={selected} onRequestChange={applyUpdate} />'))
  const app = await fs.readFile(appFile, 'utf8')
  assert.ok(app.includes('<Route path="/introductions" element={<IntroductionsPage />} />'))
  assert.ok(app.includes("import { IntroductionsPage } from '@/pages/IntroductionsPage'"))
})
