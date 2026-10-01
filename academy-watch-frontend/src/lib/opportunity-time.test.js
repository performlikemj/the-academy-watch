import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { when } from './opportunity-time.js'

for (const [zone, before, after, firstLabel, secondLabel] of [
  ['Europe/London', '2026-10-25T00:30:00Z', '2026-10-25T01:30:00Z', 'BST', 'GMT'],
  ['America/Los_Angeles', '2026-11-01T08:30:00Z', '2026-11-01T09:30:00Z', 'GMT-7', 'GMT-8'],
]) {
  test(`${zone}: the repeated hour keeps its explicit DST offset and IANA label`, () => {
    assert.match(when(before, zone), new RegExp(`01:30 ${firstLabel.replace('-', '\\-')}`))
    assert.match(when(after, zone), new RegExp(`01:30 ${secondLabel.replace('-', '\\-')}`))
    assert.ok(when(before, zone).endsWith(`(${zone})`))
    assert.ok(when(after, zone).endsWith(`(${zone})`))
  })
}

test('unsupported and malformed zones fall back to a labelled UTC without throwing', () => {
  for (const zone of ['Factory', 'posixrules', 'localtime', 'right/Europe/London', null, {}]) {
    assert.equal(when('2026-10-10T17:00:00Z', zone), when('2026-10-10T17:00:00Z', 'UTC'))
  }
  assert.equal(when(null), 'Date to be arranged')
  assert.equal(when('not-a-date'), 'Date to be arranged')
  assert.equal(when({ toString: 1 }), 'Date to be arranged')
  assert.equal(when(Symbol('invalid date')), 'Date to be arranged')
})

test('every backend canonical region-zone allowlist entry is accepted by browser Intl', () => {
  const zones = JSON.parse(fs.readFileSync(new URL('../../../academy-watch-backend/src/data/opportunity_timezones.json', import.meta.url), 'utf8'))
  assert.ok(zones.length > 350)
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL('./opportunity-timezones.json', import.meta.url), 'utf8')), zones)
  for (const zone of zones) {
    assert.match(zone, /^(UTC|(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific)\/)/)
    assert.doesNotThrow(() => new Intl.DateTimeFormat('en-GB', { timeZone: zone }).format(new Date()))
  }
  for (const invalid of ['Factory', 'posixrules', 'localtime', 'EST', 'Etc/GMT+1']) assert.ok(!zones.includes(invalid))
})

test('entry and editing use the opportunity zone, independently of browser timezone', async () => {
  const { localInput, fromLocalInput } = await import('./opportunity-time.js')
  assert.equal(localInput('2026-10-10T17:00:00Z', 'Europe/London'), '2026-10-10T18:00')
  assert.equal(fromLocalInput('2026-10-10T18:00', 'Europe/London'), '2026-10-10T17:00:00.000Z')
  assert.equal(fromLocalInput('2026-10-10T10:00', 'America/Los_Angeles'), '2026-10-10T17:00:00.000Z')
  assert.throws(() => fromLocalInput('2026-10-25T01:30', 'Europe/London'), /occurs twice/)
  assert.throws(() => fromLocalInput('2026-03-29T01:30', 'Europe/London'), /does not exist/)
  assert.throws(() => fromLocalInput('2026-11-01T01:30', 'America/Los_Angeles'), /occurs twice/)
  assert.throws(() => fromLocalInput('2026-03-08T02:30', 'America/Los_Angeles'), /does not exist/)
})
