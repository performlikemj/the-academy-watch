import { test } from 'node:test'
import assert from 'node:assert/strict'
import { defaultOpportunityTimezone, timezoneGroups, timezoneOffset, timezoneSearch } from './opportunity-timezone-options.js'

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

test('unknown zone, unsupported shortOffset and missing offset parts never throw', () => {
  const original = Intl.DateTimeFormat
  try {
    Intl.DateTimeFormat = function (locale, options) {
      if (options?.timeZone === 'America/Coyhaique') throw new RangeError('unsupported zone')
      if (options?.timeZoneName === 'shortOffset') throw new RangeError('unsupported offset')
      return new original(locale, options)
    }
    assert.equal(timezoneOffset('America/Coyhaique'), null)
    assert.equal(timezoneOffset('Europe/London'), null)
    const all = timezoneGroups(new Date('2031-07-01')).flatMap(group => group.options)
    assert.ok(!all.some(option => option.zone === 'America/Coyhaique'))
    assert.equal(all.find(option => option.zone === 'Europe/London').label, 'London')
    Intl.DateTimeFormat = function () { return { formatToParts: () => [] } }
    assert.equal(timezoneOffset('Europe/London'), null)
  } finally { Intl.DateTimeFormat = original }
})

test('group offsets are reused within a minute and refreshed at the next minute', () => {
  const original = Intl.DateTimeFormat
  let calls = 0
  try {
    Intl.DateTimeFormat = function (locale, options) {
      calls += 1
      return new original(locale, options)
    }
    const first = timezoneGroups(new Date('2032-01-01T00:00:00Z'))
    const initial = calls
    assert.ok(initial > 300)
    assert.equal(timezoneGroups(new Date('2032-01-01T00:00:59Z')), first)
    assert.equal(calls, initial)
    assert.notEqual(timezoneGroups(new Date('2032-01-01T00:01:00Z')), first)
    assert.ok(calls > initial)
  } finally { Intl.DateTimeFormat = original }
})


test('search distinguishes UTC from offset labels while retaining aliases and signed offsets', () => {
  const options = timezoneGroups(new Date('2026-07-01')).flatMap(group => group.options)
  const matches = search => options.filter(option => timezoneSearch(option.zone, search, option.keywords))
  assert.deepEqual(matches('UTC').map(option => option.zone), ['UTC'])
  assert.deepEqual(matches('Calcutta').map(option => option.zone), ['Asia/Kolkata'])
  assert.ok(matches('+05:30').some(option => option.zone === 'Asia/Kolkata'))
  assert.ok(matches('UTC+05:30').some(option => option.zone === 'Asia/Kolkata'))
  assert.equal(timezoneSearch('Europe/London', 'London', ['London']), 2)
  assert.equal(timezoneSearch('Europe/London', 'not-a-zone', ['London']), 0)
})
