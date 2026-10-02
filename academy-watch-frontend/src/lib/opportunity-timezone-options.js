import zones from './opportunity-timezones.json' with { type: 'json' }
import aliases from './opportunity-timezone-aliases.json' with { type: 'json' }
import { canonicalTimezone } from './opportunity-time.js'

export function defaultOpportunityTimezone(saved, browser = Intl.DateTimeFormat().resolvedOptions().timeZone) {
  return canonicalTimezone(zones.includes(saved) ? saved : browser)
}

// One bounded cache per browser session. Refresh current labels at most once a minute.
let cachedMinute, cachedFormatter, cachedGroups

export function timezoneOffset(zone, now = new Date()) {
  try {
    const offset = new Intl.DateTimeFormat('en-GB', { timeZone: zone, timeZoneName: 'shortOffset' })
      .formatToParts(now).find(part => part.type === 'timeZoneName')?.value
    if (offset === 'GMT' || offset === 'UTC') return 'UTC+00:00'
    const match = offset?.match(/GMT([+-])(\d{1,2})(?::(\d{2}))?$/)
    return match ? `UTC${match[1]}${match[2].padStart(2, '0')}:${match[3] || '00'}` : null
  } catch { return null }
}

export function timezoneGroups(now = new Date()) {
  const minute = Math.floor(now.getTime() / 60000)
  if (cachedGroups && cachedMinute === minute && cachedFormatter === Intl.DateTimeFormat) return cachedGroups
  const groups = new Map()
  const canonical = [...new Set(zones.map(canonicalTimezone))]
  for (const zone of canonical.sort()) {
    const offset = timezoneOffset(zone, now)
    if (offset === null) {
      // Distinguish an unsupported zone from missing shortOffset support.
      try { new Intl.DateTimeFormat('en-GB', { timeZone: zone }).format(now) } catch { continue }
    }
    const region = zone.includes('/') ? zone.split('/')[0] : 'UTC'
    const city = zone.split('/').at(-1).replaceAll('_', ' ')
    const option = {
      zone,
      label: offset ? `${city} — ${offset} (now)` : city,
      // Do not index the universal UTC prefix; signed offsets remain searchable.
      keywords: [city, ...(offset ? [offset.replace('UTC', '')] : []), ...Object.keys(aliases).filter(alias => aliases[alias] === zone).map(alias => alias.replaceAll('_', ' '))],
    }
    if (!groups.has(region)) groups.set(region, [])
    groups.get(region).push(option)
  }
  cachedMinute = minute
  cachedFormatter = Intl.DateTimeFormat
  cachedGroups = [...groups].map(([region, options]) => ({ region, options }))
  return cachedGroups
}

export function timezoneSearch(candidate, search, keywords = []) {
  const normalize = text => text.toLowerCase().replaceAll('_', ' ').trim().replace(/^utc(?=[+-])/, '')
  const query = normalize(search)
  const terms = [candidate, ...keywords].map(normalize)
  return terms.some(text => text === query) ? 2 : terms.some(text => text.includes(query)) ? 1 : 0
}
