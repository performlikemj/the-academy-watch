import test from 'node:test'
import assert from 'node:assert/strict'
import { initials, positionGroup } from '../src/pages/club-console/presentation.js'

test('club squads group provider codes and natural-language positions consistently', () => {
  for (const position of ['Goalkeeper', 'GK', 'G']) assert.equal(positionGroup(position), 'Goalkeepers')
  for (const position of ['Right-back', 'Centre-back', 'Defender', 'CB', 'D']) assert.equal(positionGroup(position), 'Defenders')
  for (const position of ['Attacking midfielder', 'Defensive midfielder', 'M', 'CM']) assert.equal(positionGroup(position), 'Midfielders')
  for (const position of ['Striker', 'Winger', 'Forward', 'F', 'ST']) assert.equal(positionGroup(position), 'Forwards')
  for (const position of [null, '', 'Unknown']) assert.equal(positionGroup(position), 'Other')
})

test('initials avatars do not require a photo or a second name', () => {
  assert.equal(initials('Sample Club'), 'SC')
  assert.equal(initials('Fictional'), 'F')
  assert.equal(initials(null), '?')
})

test('year-only ages retain their uncertainty instead of inventing an exact age', async () => {
  const { ageDescription } = await import('../src/pages/club-console/presentation.js')
  assert.equal(ageDescription({ age: 17 }), 'Age 17')
  assert.equal(ageDescription({ age: null, age_label: '15–16' }), 'Age 15–16')
  assert.equal(ageDescription({ age: null }), null)
})
