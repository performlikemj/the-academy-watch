import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { statusLabel, counterpartName, canWithdraw, canRespond, previewText, upsertRequest, canDecideConsent, fetchAllRequests } from '../src/lib/introductions.js'

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
  assert.ok(page.includes("APIService.listContactRequests({ box: which, limit, offset })"))
  assert.ok(page.includes('fetchAllRequests('), 'both boxes are paged through, not cut at the first page')
  assert.ok(page.includes('APIService.acceptContactRequest(request.id)'))
  assert.ok(page.includes('APIService.declineContactRequest(request.id)'))
  assert.ok(page.includes('APIService.withdrawContactRequest(request.id)'))
  assert.ok(page.includes('<ContactThread request={selected} onRequestChange={applyUpdate} />'))
  const app = await fs.readFile(appFile, 'utf8')
  assert.ok(app.includes('<Route path="/introductions" element={<IntroductionsPage />} />'))
  assert.ok(app.includes("import { IntroductionsPage } from '@/pages/IntroductionsPage'"))
})

test('canDecideConsent needs a pending consent on a request that can still change', () => {
  assert.equal(canDecideConsent({ club_consent_status: 'pending', status: 'pending' }), true)
  assert.equal(canDecideConsent({ club_consent_status: 'pending', status: 'accepted' }), true)
  assert.equal(canDecideConsent({ club_consent_status: 'pending', status: 'withdrawn' }), false)
  assert.equal(canDecideConsent({ club_consent_status: 'pending', status: 'expired' }), false)
  assert.equal(canDecideConsent({ club_consent_status: 'granted', status: 'pending' }), false)
  assert.equal(canDecideConsent(null), false)
})

test('fetchAllRequests pages until a short page and concatenates in order', async () => {
  const calls = []
  const pager = async (limit, offset) => {
    calls.push([limit, offset])
    const total = 240
    const n = Math.max(0, Math.min(limit, total - offset))
    return { requests: Array.from({ length: n }, (_, i) => ({ id: offset + i + 1 })), total }
  }
  const rows = await fetchAllRequests(pager)
  assert.equal(rows.length, 240)
  assert.deepEqual(calls, [[100, 0], [100, 100], [100, 200]])
  assert.equal(rows[0].id, 1)
  assert.equal(rows[239].id, 240)
  const single = await fetchAllRequests(async () => ({ requests: [{ id: 1 }], total: 1 }))
  assert.equal(single.length, 1)
  const empty = await fetchAllRequests(async () => ({ requests: [] }))
  assert.equal(empty.length, 0)
})

test('a late load for the other box never overwrites the current box', async () => {
  const page = await fs.readFile(pageFile, 'utf8')
  assert.ok(page.includes('const loadSeq = useRef(0)'), 'loads are sequenced')
  assert.ok(page.includes('if (seq !== loadSeq.current) return'), 'stale load results are discarded')
  assert.ok(page.includes('if (seq === loadSeq.current) setLoading(false)'), 'a stale load does not clear the newer load\'s spinner')
})

test('an action that finishes after switching boxes never writes its error or clears the busy flag there', async () => {
  const page = await fs.readFile(pageFile, 'utf8')
  assert.ok(page.includes('const actionSeq = useRef(0)'), 'actions are sequenced')
  assert.ok(page.includes('if (seq !== actionSeq.current) return'), 'a stale action error is discarded')
  assert.ok(page.includes('if (seq === actionSeq.current) setBusyId(null)'), 'a stale action does not clear the new box\'s busy flag')
  assert.ok(page.includes('    actionSeq.current += 1\n    setSelectedId(null)\n    setActionError(null)\n    setBusyId(null)\n    load(box)'), 'switching boxes resets action state')
})
