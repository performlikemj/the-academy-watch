// Clubs near you (dark behind the backend's CLUB_DIRECTORY_ENABLED). Pure helpers — no React, no network.
// The hook in src/hooks/useClubDirectory.js wires the flag to GET /api/features.

export const LEVEL_LABELS = {
  grassroots: 'Grassroots',
  amateur: 'Amateur',
  semi_pro: 'Semi-pro',
  professional: 'Professional',
}

export const PROGRAMME_LABELS = {
  men: 'Men',
  women: 'Women',
  boys: 'Boys',
  girls: 'Girls',
}

export const LEVELS = Object.keys(LEVEL_LABELS)
export const PROGRAMMES = Object.keys(PROGRAMME_LABELS)

// One offering filter at a time: each maps to "a club that runs any of these".
export const OFFERING_FILTERS = [
  { id: 'girls_women', label: 'Girls & women', programmes: ['women', 'girls'] },
  { id: 'adults', label: 'Adults', programmes: ['men', 'women'] },
  { id: 'youth', label: 'Youth', programmes: ['boys', 'girls'] },
]

export const RADIUS_OPTIONS_KM = { mi: [16, 40, 80, 160], km: [10, 25, 50, 100] }

let cached = null
let inflight = null

export function clubDirectoryFromFeatures(res) {
  return Boolean(res && res.club_directory === true)
}

// Resolves true/false; a successful answer is cached for the session, a failure answers false without caching.
export function loadClubDirectoryFlag(fetchFeatures) {
  if (cached !== null) return Promise.resolve(cached)
  if (!inflight) {
    inflight = Promise.resolve()
      .then(() => fetchFeatures())
      .then((res) => {
        cached = clubDirectoryFromFeatures(res)
        return cached
      }, () => false)
      .finally(() => { inflight = null })
  }
  return inflight
}

export function peekClubDirectoryFlag() {
  return cached
}

export function resetClubDirectoryFlag() {
  cached = null
  inflight = null
}

// A visitor's position is only ever sent rounded to about a kilometre, and is never stored.
export function coarseCoordinate(value) {
  return Math.round(Number(value) * 100) / 100
}

export function buildDirectoryQuery({ q, offering, level, position, radiusKm, page, perPage } = {}) {
  const params = new URLSearchParams()
  const term = String(q || '').trim()
  if (term.length >= 2) params.set('q', term.slice(0, 80))
  const filter = OFFERING_FILTERS.find((item) => item.id === offering)
  if (filter) params.set('programme', filter.programmes.join(','))
  if (LEVELS.includes(level)) params.set('level', level)
  if (position && Number.isFinite(position.latitude) && Number.isFinite(position.longitude)) {
    params.set('lat', String(coarseCoordinate(position.latitude)))
    params.set('lng', String(coarseCoordinate(position.longitude)))
    if (Number.isFinite(radiusKm) && radiusKm > 0) params.set('radius_km', String(radiusKm))
  }
  if (page > 1) params.set('page', String(page))
  if (perPage) params.set('per_page', String(perPage))
  return params.toString()
}

// Miles where people measure a drive to training in miles; kilometres everywhere else.
export function distanceUnit(locale) {
  const region = String(locale || '').split(/[-_]/)[1]
  return ['US', 'GB', 'LR', 'MM'].includes(String(region || '').toUpperCase()) ? 'mi' : 'km'
}

export function distanceLabel(km, unit = 'km') {
  if (km === null || km === undefined || !Number.isFinite(Number(km))) return null
  const value = unit === 'mi' ? Number(km) / 1.609344 : Number(km)
  if (value < 0.1) return `Under 0.1 ${unit}`
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${unit}`
}

export function radiusLabel(km, unit = 'km') {
  return `${Math.round(unit === 'mi' ? km / 1.609344 : km)} ${unit}`
}

export function initials(name) {
  return String(name || 'Club').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
}

export function programmeList(codes) {
  return PROGRAMMES.filter((code) => (codes || []).includes(code)).map((code) => PROGRAMME_LABELS[code])
}

/** The mono meta line under a club's name: level · distance · squads · who it's for. */
export function clubMeta(club, { unit = 'km', located = false } = {}) {
  const parts = []
  if (LEVEL_LABELS[club.club_level]) parts.push(LEVEL_LABELS[club.club_level])
  const distance = distanceLabel(club.distance_km, unit)
  if (distance) parts.push(distance)
  else if (located) parts.push('Distance unavailable')
  if (club.squad_count > 0) parts.push(`${club.squad_count} ${club.squad_count === 1 ? 'squad' : 'squads'}`)
  const programmes = programmeList(club.gender_programs)
  if (programmes.length) parts.push(programmes.join(', ').toLowerCase())
  return parts
}

export function clubPlace(club) {
  return [club.venue?.name, club.city || club.region, club.venue?.postcode].filter(Boolean).join(' · ')
}

export function hasPin(club) {
  return Number.isFinite(club?.venue?.latitude) && Number.isFinite(club?.venue?.longitude)
}

export function osmLink(latitude, longitude) {
  const lat = Number(latitude).toFixed(5)
  const lng = Number(longitude).toFixed(5)
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=15/${lat}/${lng}`
}

function unwrapLongitude(longitude, reference) {
  let value = longitude
  while (value - reference > 180) value -= 360
  while (value - reference < -180) value += 360
  return value
}

/**
 * Place real coordinates on a north-up plot (no tiles, no map provider): x/y are 0–1 fractions of a square
 * panel, to one shared scale so relative distances are true. `position` is the visitor, when shared.
 */
export function projectPins(clubs, position = null, padding = 0.12) {
  const pinned = (clubs || []).filter(hasPin)
  const points = pinned.map((club) => ({ id: club.id, latitude: club.venue.latitude, longitude: club.venue.longitude }))
  if (position && Number.isFinite(position.latitude) && Number.isFinite(position.longitude)) {
    points.push({ id: 'you', latitude: coarseCoordinate(position.latitude), longitude: coarseCoordinate(position.longitude) })
  }
  if (!points.length) return { pins: [], you: null, spanKm: 0 }
  const reference = points[0].longitude
  const midLatitude = points.reduce((sum, point) => sum + point.latitude, 0) / points.length
  const shrink = Math.max(0.05, Math.cos((midLatitude * Math.PI) / 180))
  const flat = points.map((point) => ({
    id: point.id,
    east: unwrapLongitude(point.longitude, reference) * shrink,
    north: point.latitude,
  }))
  const easts = flat.map((point) => point.east)
  const norths = flat.map((point) => point.north)
  const centreEast = (Math.min(...easts) + Math.max(...easts)) / 2
  const centreNorth = (Math.min(...norths) + Math.max(...norths)) / 2
  // Never zoom in closer than about 2 km across, so one pin sits calmly in the middle.
  const span = Math.max(Math.max(...easts) - Math.min(...easts), Math.max(...norths) - Math.min(...norths), 0.018)
  const usable = 1 - padding * 2
  const placed = flat.map((point) => ({
    id: point.id,
    x: 0.5 + ((point.east - centreEast) / span) * usable,
    y: 0.5 - ((point.north - centreNorth) / span) * usable,
  }))
  return {
    pins: placed.filter((point) => point.id !== 'you'),
    you: placed.find((point) => point.id === 'you') || null,
    spanKm: (span / usable) * 111.195,
  }
}

/** A round scale-bar length (in the visitor's unit) that fits about a quarter of the panel. */
export function scaleBar(spanKm, unit = 'km') {
  const span = unit === 'mi' ? spanKm / 1.609344 : spanKm
  if (!(span > 0)) return null
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
  const length = [...steps].reverse().find((step) => step <= span / 4) || steps[0]
  return { label: `${length} ${unit}`, fraction: Math.min(1, length / span) }
}

// ---- Club Home: the moderated "find us" fields on the club profile form ----

export const EMPTY_DIRECTORY_FORM = { venue_name: '', postcode: '', latitude: '', longitude: '', club_level: '', gender_programs: [] }

export function directoryForm(directory) {
  if (!directory) return EMPTY_DIRECTORY_FORM
  return {
    venue_name: directory.venue_name || '',
    postcode: directory.postcode || '',
    latitude: directory.latitude === null || directory.latitude === undefined ? '' : String(directory.latitude),
    longitude: directory.longitude === null || directory.longitude === undefined ? '' : String(directory.longitude),
    club_level: directory.club_level || '',
    gender_programs: PROGRAMMES.filter((code) => (directory.gender_programs || []).includes(code)),
  }
}

/** "51.5010, -0.1416" pasted from a maps app → both numbers; anything else → null. */
export function parseCoordinatePair(text) {
  const match = /^\s*\(?\s*(-?\d{1,2}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*\)?\s*$/.exec(String(text || ''))
  if (!match) return null
  const latitude = Number(match[1])
  const longitude = Number(match[2])
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null
  return { latitude, longitude }
}

function coordinateValue(text) {
  const trimmed = String(text ?? '').trim()
  if (!trimmed) return null
  return /^-?\d+(\.\d+)?$/.test(trimmed) ? Number(trimmed) : Number.NaN
}

/** The `directory` object of PUT /club/<id>/profile, plus client-side field errors. */
export function directoryPayload(form) {
  const errors = {}
  const latitude = coordinateValue(form.latitude)
  const longitude = coordinateValue(form.longitude)
  if (Number.isNaN(latitude) || (latitude !== null && Math.abs(latitude) > 90)) errors.latitude = 'Latitude is a number between -90 and 90.'
  if (Number.isNaN(longitude) || (longitude !== null && Math.abs(longitude) > 180)) errors.longitude = 'Longitude is a number between -180 and 180.'
  if (!errors.latitude && !errors.longitude && (latitude === null) !== (longitude === null)) {
    errors.latitude = 'Add both latitude and longitude, or leave both empty.'
  }
  return {
    errors,
    directory: {
      venue_name: form.venue_name.trim() || null,
      postcode: form.postcode.trim() || null,
      latitude,
      longitude,
      club_level: form.club_level || null,
      gender_programs: PROGRAMMES.filter((code) => form.gender_programs.includes(code)),
    },
  }
}

export function directorySummary(directory) {
  if (!directory) return []
  const lines = []
  const place = [directory.venue_name, directory.postcode].filter(Boolean).join(' · ')
  if (place) lines.push(place)
  if (directory.latitude !== null && directory.latitude !== undefined && directory.longitude !== null && directory.longitude !== undefined) {
    lines.push(`Pin ${Number(directory.latitude).toFixed(5)}, ${Number(directory.longitude).toFixed(5)}`)
  }
  if (LEVEL_LABELS[directory.club_level]) lines.push(LEVEL_LABELS[directory.club_level])
  const programmes = programmeList(directory.gender_programs)
  if (programmes.length) lines.push(programmes.join(', '))
  return lines
}
