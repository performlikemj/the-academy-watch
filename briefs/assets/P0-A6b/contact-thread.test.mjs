import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { describeThreadState, participantName, canSendMessage, outcomeLabel, OUTCOME_STAGES, MESSAGE_MAX } from '../src/lib/contact-thread.js'

const componentFile = new URL('../src/components/contact/ContactThread.jsx', import.meta.url)

test('describeThreadState explains every closed state and opens only when the API says so', () => {
  assert.equal(describeThreadState(null).open, false)
  assert.deepEqual(describeThreadState({ messaging_open: true, status: 'accepted' }), { open: true, note: null })
  assert.match(describeThreadState({ messaging_open: false, status: 'pending', routing_mode: 'direct' }).note, /Waiting for the player to accept/)
  assert.match(describeThreadState({ messaging_open: false, status: 'pending', routing_mode: 'club_included', club_consent_status: 'pending' }).note, /club to allow/)
  assert.match(describeThreadState({ messaging_open: false, status: 'accepted', routing_mode: 'club_included', club_consent_status: 'pending' }).note, /Messaging opens once the club allows/)
  assert.match(describeThreadState({ messaging_open: false, status: 'declined', club_consent_status: 'declined' }).note, /club declined/)
  assert.match(describeThreadState({ messaging_open: false, status: 'declined' }).note, /player declined/)
  assert.match(describeThreadState({ messaging_open: false, status: 'withdrawn' }).note, /withdrawn/)
  assert.match(describeThreadState({ messaging_open: false, status: 'expired' }).note, /expired/)
})

test('participantName, canSendMessage and outcome labels', () => {
  const req = { participants: { scout: { display_name: 'Alex' }, player: { display_name: null }, club: { display_name: 'Club A' } } }
  assert.equal(participantName(req, 'scout'), 'Alex')
  assert.equal(participantName(req, 'player'), 'Player')
  assert.equal(participantName(req, 'club'), 'Club A')
  assert.equal(canSendMessage('  hi '), true)
  assert.equal(canSendMessage('   '), false)
  assert.equal(canSendMessage('x'.repeat(MESSAGE_MAX + 1)), false)
  assert.equal(outcomeLabel('trial_scheduled'), 'Trial scheduled')
  assert.deepEqual(OUTCOME_STAGES.map((s) => s.value), ['contacted', 'trial_scheduled', 'trial_completed', 'signed', 'no_fit'])
})

test('the component talks to the three thread endpoints through APIService', async () => {
  const src = await fs.readFile(componentFile, 'utf8')
  assert.ok(src.includes('APIService.getContactMessages(requestId)'))
  assert.ok(src.includes('APIService.sendContactMessage(requestId, draft.trim())'))
  assert.ok(src.includes('APIService.reportContactOutcome(requestId, { stage, notes: notes.trim() || null })'))
  assert.ok(src.includes('data-testid="contact-thread"'))
})
