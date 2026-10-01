import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildDirectoryQuery,
  clubDirectoryFromFeatures,
  clubMeta,
  clubPlace,
  coarseCoordinate,
  directoryForm,
  directoryPayload,
  directorySummary,
  distanceLabel,
  distanceUnit,
  loadClubDirectoryFlag,
  osmLink,
  parseCoordinatePair,
  peekClubDirectoryFlag,
  projectPins,
  resetClubDirectoryFlag,
  scaleBar,
} from '../src/lib/club-directory.js'

test('the flag reads only an explicit true, caches success and never caches failure', async () => {
  assert.equal(clubDirectoryFromFeatures({ club_directory: true }), true)
  assert.equal(clubDirectoryFromFeatures({ club_directory: 'true' }), false)
  assert.equal(clubDirectoryFromFeatures({ contact_rail: true }), false)
  assert.equal(clubDirectoryFromFeatures(null), false)

  resetClubDirectoryFlag()
  let calls = 0
  assert.equal(await loadClubDirectoryFlag(async () => { calls += 1; throw new Error('offline') }), false)
  assert.equal(peekClubDirectoryFlag(), null)
  const on = async () => { calls += 1; return { club_directory: true } }
  const [a, b] = await Promise.all([loadClubDirectoryFlag(on), loadClubDirectoryFlag(on)])
  assert.deepEqual([a, b, calls], [true, true, 2])
  assert.equal(await loadClubDirectoryFlag(on), true)
  assert.equal(calls, 2)
  resetClubDirectoryFlag()
})

test('a visitor position is only ever sent rounded to two decimals', () => {
  assert.equal(coarseCoordinate(50.791234), 50.79)
  assert.equal(coarseCoordinate(-1.0667), -1.07)
  const query = buildDirectoryQuery({ position: { latitude: 50.791234, longitude: -1.062345 }, radiusKm: 40 })
  assert.equal(query, 'lat=50.79&lng=-1.06&radius_km=40')
  assert.equal(buildDirectoryQuery({ radiusKm: 40 }), '')
  assert.equal(buildDirectoryQuery({ position: { latitude: Number.NaN, longitude: 1 } }), '')
})

test('query building maps filters to API codes and ignores unknown values', () => {
  assert.equal(buildDirectoryQuery({ q: '  po16 ', offering: 'girls_women', level: 'semi_pro', page: 2, perPage: 20 }),
    'q=po16&programme=women%2Cgirls&level=semi_pro&page=2&per_page=20')
  assert.equal(buildDirectoryQuery({ q: 'a', offering: 'robots', level: 'galactic', page: 1 }), '')
  assert.equal(new URLSearchParams(buildDirectoryQuery({ q: 'x'.repeat(200) })).get('q').length, 80)
})

test('distances use miles only where people do, and say so when unknown', () => {
  assert.equal(distanceUnit('en-GB'), 'mi')
  assert.equal(distanceUnit('en-US'), 'mi')
  assert.equal(distanceUnit('ja-JP'), 'km')
  assert.equal(distanceUnit(''), 'km')
  assert.equal(distanceLabel(1.9, 'mi'), '1.2 mi')
  assert.equal(distanceLabel(42.4, 'km'), '42 km')
  assert.equal(distanceLabel(0.02, 'km'), 'Under 0.1 km')
  assert.equal(distanceLabel(null, 'km'), null)
  const club = { club_level: 'semi_pro', distance_km: null, squad_count: 1, gender_programs: ['girls', 'men'] }
  assert.deepEqual(clubMeta(club, { unit: 'mi', located: true }), ['Semi-pro', 'Distance unavailable', '1 squad', 'men, girls'])
  assert.deepEqual(clubMeta(club, { unit: 'mi' }), ['Semi-pro', '1 squad', 'men, girls'])
  assert.deepEqual(clubMeta({ squad_count: 0, gender_programs: [] }), [])
  assert.equal(clubPlace({ venue: { name: 'Ground', postcode: 'AB1' }, city: 'Town', region: 'Shire' }), 'Ground · Town · AB1')
  assert.equal(clubPlace({ venue: null, city: null, region: 'Shire' }), 'Shire')
})

test('pins keep true relative positions: north is up, east is right, one shared scale', () => {
  const clubs = [
    { id: 1, venue: { latitude: 50.0, longitude: -1.0 } },
    { id: 2, venue: { latitude: 50.1, longitude: -1.0 } },
    { id: 3, venue: { latitude: 50.0, longitude: -0.9 } },
    { id: 4, venue: null },
  ]
  const { pins, you, spanKm } = projectPins(clubs)
  assert.equal(pins.length, 3)
  assert.equal(you, null)
  const [a, north, east] = pins
  assert.ok(north.y < a.y && Math.abs(north.x - a.x) < 1e-9)
  assert.ok(east.x > a.x && Math.abs(east.y - a.y) < 1e-9)
  // 0.1° of longitude at 50°N is shorter on the ground than 0.1° of latitude.
  assert.ok((east.x - a.x) < (a.y - north.y))
  assert.ok(pins.every((pin) => pin.x >= 0 && pin.x <= 1 && pin.y >= 0 && pin.y <= 1))
  assert.ok(spanKm > 11 && spanKm < 16)
  const withYou = projectPins(clubs, { latitude: 50.05678, longitude: -0.95678 })
  assert.ok(withYou.you && withYou.pins.length === 3)
  assert.deepEqual(projectPins([]), { pins: [], you: null, spanKm: 0 })
  const single = projectPins([clubs[0]])
  assert.deepEqual([single.pins[0].x, single.pins[0].y], [0.5, 0.5])
  // Either side of the antimeridian stays close together.
  const wrapped = projectPins([{ id: 1, venue: { latitude: 0, longitude: 179.95 } }, { id: 2, venue: { latitude: 0, longitude: -179.95 } }])
  assert.ok(wrapped.spanKm < 30)
  assert.deepEqual(scaleBar(13.3, 'km'), { label: '2 km', fraction: 2 / 13.3 })
  assert.equal(scaleBar(0, 'km'), null)
  assert.equal(osmLink(50.78611, -1.06111), 'https://www.openstreetmap.org/?mlat=50.78611&mlon=-1.06111#map=15/50.78611/-1.06111')
})

test('club form: pasted pairs, validation and payload', () => {
  assert.deepEqual(parseCoordinatePair('50.7861, -1.0611'), { latitude: 50.7861, longitude: -1.0611 })
  assert.deepEqual(parseCoordinatePair('(50.7861 -1.0611)'), { latitude: 50.7861, longitude: -1.0611 })
  assert.equal(parseCoordinatePair('95, 10'), null)
  assert.equal(parseCoordinatePair('50.7861'), null)
  assert.equal(parseCoordinatePair('north, south'), null)

  const form = directoryForm({ venue_name: 'Ground', postcode: 'AB1 2CD', latitude: 50.5, longitude: -1.25, club_level: 'amateur', gender_programs: ['girls', 'men'] })
  assert.deepEqual(form, { venue_name: 'Ground', postcode: 'AB1 2CD', latitude: '50.5', longitude: '-1.25', club_level: 'amateur', gender_programs: ['men', 'girls'] })
  assert.deepEqual(directoryPayload(form), {
    errors: {},
    directory: { venue_name: 'Ground', postcode: 'AB1 2CD', latitude: 50.5, longitude: -1.25, club_level: 'amateur', gender_programs: ['men', 'girls'] },
  })
  const empty = directoryPayload(directoryForm(null))
  assert.deepEqual(empty, { errors: {}, directory: { venue_name: null, postcode: null, latitude: null, longitude: null, club_level: null, gender_programs: [] } })
  assert.ok(directoryPayload({ ...form, longitude: '' }).errors.latitude)
  assert.ok(directoryPayload({ ...form, latitude: 'abc' }).errors.latitude)
  assert.ok(directoryPayload({ ...form, longitude: '200' }).errors.longitude)
  assert.deepEqual(directorySummary({ venue_name: 'Ground', postcode: null, latitude: 50.5, longitude: -1.25, club_level: 'amateur', gender_programs: ['men'] }),
    ['Ground', 'Pin 50.50000, -1.25000', 'Amateur', 'Men'])
  assert.deepEqual(directorySummary(undefined), [])
})
