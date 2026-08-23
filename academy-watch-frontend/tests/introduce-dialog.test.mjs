import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { describeIntroduceError, canSend, MESSAGE_MAX } from '../src/lib/introduce.js'

const dialogFile = new URL('../src/components/contact/IntroduceDialog.jsx', import.meta.url)
const scoutFile = new URL('../src/pages/ScoutPage.jsx', import.meta.url)

test('describeIntroduceError maps every server code the rail returns', () => {
  assert.equal(describeIntroduceError({ status: 400, body: { code: 'attestation_required', error: 'rules' } }).kind, 'attestation')
  assert.deepEqual(describeIntroduceError({ status: 403, body: { code: 'scout_not_verified' } }), { kind: 'verify', message: 'Only verified scouts can introduce themselves.', href: '/scout/verification' })
  assert.equal(describeIntroduceError({ status: 403, body: { code: 'player_not_claimable' } }).kind, 'blocked')
  assert.equal(describeIntroduceError({ status: 409, body: { code: 'active_request_exists' } }).kind, 'blocked')
  assert.match(describeIntroduceError({ status: 409, body: { code: 'decline_cooldown_active', cooldown_days: 30 } }).message, /30 days/)
  assert.equal(describeIntroduceError({ status: 500, body: { error: 'boom' } }).message, 'boom')
  assert.equal(describeIntroduceError(new Error('offline')).message, 'offline')
})

test('canSend needs a non-empty message within the limit and the attestation when required', () => {
  assert.equal(canSend('hello', false, false), true)
  assert.equal(canSend('   ', false, false), false)
  assert.equal(canSend('x'.repeat(MESSAGE_MAX + 1), false, false), false)
  assert.equal(canSend('hello', true, false), false)
  assert.equal(canSend('hello', true, true), true)
})

test('the dialog posts through APIService and the desk mounts it only for contactable rows', async () => {
  const dialog = await fs.readFile(dialogFile, 'utf8')
  assert.ok(dialog.includes('APIService.createContactRequest({'))
  assert.ok(dialog.includes('permission_attestation: attestationRequired && attested'))
  const scout = await fs.readFile(scoutFile, 'utf8')
  assert.ok(scout.includes("import { IntroduceDialog } from '@/components/contact/IntroduceDialog'"))
  assert.ok(scout.includes('{contactRail === true && player.contactable ? ('))
  assert.ok(scout.includes('<IntroduceDialog'))
  assert.ok(scout.includes('const [introducePlayer, setIntroducePlayer] = useState(null)'))
})

test('a send that lands after the dialog closed or moved to another player is ignored', async () => {
  const dialog = await fs.readFile(dialogFile, 'utf8')
  assert.ok(dialog.includes('const opSeq = useRef(0)'), 'the dialog keeps an epoch')
  assert.ok(dialog.includes('opSeq.current += 1'), 'the epoch moves on open/close/player change')
  assert.ok(dialog.includes('if (seq !== opSeq.current) return'), 'stale results are discarded')
  assert.ok(dialog.includes('if (seq === opSeq.current) setSending(false)'), 'a stale send does not clear the new form\'s sending flag')
})
