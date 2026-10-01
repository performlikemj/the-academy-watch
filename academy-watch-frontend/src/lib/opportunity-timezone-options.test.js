import { test } from 'node:test'
import assert from 'node:assert/strict'
import { defaultOpportunityTimezone, timezoneGroups, timezoneOffset } from './opportunity-timezone-options.js'

test('saved club zone takes precedence; browser aliases canonicalize; unknowns fall back', () => {
  assert.equal(defaultOpportunityTimezone('Europe/London', 'Asia/Tokyo'), 'Europe/London')
  assert.equal(defaultOpportunityTimezone('Asia/Calcutta', 'Europe/London'), 'Asia/Kolkata')
  assert.equal(defaultOpportunityTimezone(undefined, 'Asia/Calcutta'), 'Asia/Kolkata')
  assert.equal(defaultOpportunityTimezone('Factory', 'Asia/Tokyo'), 'Asia/Tokyo')
  assert.equal(defaultOpportunityTimezone(null, 'invalid'), 'UTC')
})

test('offset labels handle DST, half/quarter hours, negatives and UTC', () => {
  assert.equal(timezoneOffset('Europe/London', new Date('2026-07-01')), 'UTC+01:00')
  assert.equal(timezoneOffset('Europe/London', new Date('2026-12-01')), 'UTC+00:00')
  assert.equal(timezoneOffset('Asia/Kolkata'), 'UTC+05:30')
  assert.equal(timezoneOffset('Asia/Kathmandu'), 'UTC+05:45')
  assert.equal(timezoneOffset('America/St_Johns', new Date('2026-12-01')), 'UTC-03:30')
  assert.equal(timezoneOffset('UTC'), 'UTC+00:00')
})

test('picker deduplicates canonical zones by region and retains searchable aliases', () => {
  const groups = timezoneGroups(new Date('2026-07-01'))
  const all = groups.flatMap(group => group.options)
  assert.equal(new Set(all.map(option => option.zone)).size, all.length)
  assert.ok(groups.some(group => group.region === 'Europe'))
  assert.equal(all.find(option => option.zone === 'Europe/London').label, 'London — UTC+01:00 (now)')
  assert.ok(all.find(option => option.zone === 'Asia/Kolkata').keywords.includes('Asia/Calcutta'))
  assert.ok(all.every(option => / — UTC[+-]\d\d:\d\d \(now\)$/.test(option.label)))
})
