import zones from './opportunity-timezones.json' with { type: 'json' }
import aliases from './opportunity-timezone-aliases.json' with { type: 'json' }
import { canonicalTimezone } from './opportunity-time.js'

export function defaultOpportunityTimezone(saved, browser = Intl.DateTimeFormat().resolvedOptions().timeZone) {
  return canonicalTimezone(zones.includes(saved) ? saved : browser)
}

export function timezoneOffset(zone, now = new Date()) {
  const offset = new Intl.DateTimeFormat('en-GB', { timeZone: zone, timeZoneName: 'shortOffset' })
    .formatToParts(now).find(part => part.type === 'timeZoneName').value
  const match = offset.match(/GMT([+-])(\d{1,2})(?::(\d{2}))?$/)
  return match ? `UTC${match[1]}${match[2].padStart(2, '0')}:${match[3] || '00'}` : 'UTC+00:00'
}

export function timezoneGroups(now = new Date()) {
  const groups = new Map()
  const canonical = [...new Set(zones.map(canonicalTimezone))]
  for (const zone of canonical.sort()) {
    const region = zone.includes('/') ? zone.split('/')[0] : 'UTC'
    const city = zone.split('/').at(-1).replaceAll('_', ' ')
    const option = { zone, label: `${city} — ${timezoneOffset(zone, now)} (now)`, keywords: Object.keys(aliases).filter(alias => aliases[alias] === zone).map(alias => alias.replaceAll('_', ' ')) }
    if (!groups.has(region)) groups.set(region, [])
    groups.get(region).push(option)
  }
  return [...groups].map(([region, options]) => ({ region, options }))
}
