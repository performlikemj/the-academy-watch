import zones from './opportunity-timezones.json' with { type: 'json' }
import aliases from './opportunity-timezone-aliases.json' with { type: 'json' }
const TIMEZONES = new Set(zones)

export function canonicalTimezone(zone) {
  return TIMEZONES.has(zone) ? aliases[zone] || zone : 'UTC'
}

// Every opportunity/application date uses this formatter, including defensive legacy-zone fallback.
export function when(value, timezone = 'UTC') {
  if (!value) return 'Date to be arranged'
  timezone = canonicalTimezone(timezone)
  let date
  try { date = new Date(value) } catch { return 'Date to be arranged' }
  if (!Number.isFinite(date.getTime())) return 'Date to be arranged'
  const options = { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short' }
  try {
    return `${new Intl.DateTimeFormat('en-GB', { ...options, timeZone: timezone }).format(date)} (${timezone})`
  } catch {
    return `${new Intl.DateTimeFormat('en-GB', { ...options, timeZone: 'UTC' }).format(date)} (UTC)`
  }
}

// Collapse local same-day ranges only when both endpoints share the same UTC offset.
// Across DST changes, show both zone labels so an ambiguous wall time stays explicit.
export function whenRange(start, end, timezone = 'UTC') {
  if (!end) return when(start, timezone)
  const zone = canonicalTimezone(timezone)
  let first, last
  try { first = new Date(start); last = new Date(end) } catch { return `${when(start, zone)} – ${when(end, zone)}` }
  if (!start || !Number.isFinite(first.getTime()) || !Number.isFinite(last.getTime())) return `${when(start, zone)} – ${when(end, zone)}`
  try {
    const parts = date => Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
      timeZone: zone, year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset',
    }).formatToParts(date).map(part => [part.type, part.value]))
    const a = parts(first), b = parts(last)
    if (a.timeZoneName !== b.timeZoneName) return `${when(start, zone)} – ${when(end, zone)}`
    const label = new Intl.DateTimeFormat('en-GB', { timeZone: zone, timeZoneName: 'short' }).formatToParts(last).find(part => part.type === 'timeZoneName').value
    const date = p => `${p.day} ${p.month} ${p.year}`
    const time = p => `${p.hour}:${p.minute}`
    const sameDay = date(a) === date(b)
    return `${date(a)}, ${time(a)}${sameDay ? '–' : ' – ' + date(b) + ', '}${time(b)} ${label} (${zone})`
  } catch { return `${when(start, zone)} – ${when(end, zone)}` }
}

export function localInput(value, timezone) {
  if (!value || !TIMEZONES.has(timezone)) return ''
  timezone = canonicalTimezone(timezone)
  try {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
      timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(value)).map(part => [part.type, part.value]))
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
  } catch { return '' }
}

export function fromLocalInput(value, timezone) {
  // Find every UTC instant matching this wall time: refuse skipped or repeated DST hours.
  const nominal = Date.parse(`${value}Z`)
  if (!Number.isFinite(nominal)) throw new Error('Enter a valid date and time.')
  const offsets = new Set()
  for (let hours = -36; hours <= 36; hours += 6) {
    const instant = nominal + hours * 3600000
    const local = localInput(new Date(instant).toISOString(), timezone)
    if (!local) throw new Error('Enter a valid IANA time zone.')
    offsets.add(Date.parse(`${local}Z`) - instant)
  }
  const matches = [...offsets].map(offset => new Date(nominal - offset).toISOString())
    .filter(instant => localInput(instant, timezone) === value)
  if (matches.length !== 1) throw new Error(matches.length ? `This time occurs twice in ${timezone}. Choose an unambiguous time.` : `This time does not exist in ${timezone}. Choose another time.`)
  return matches[0]
}
