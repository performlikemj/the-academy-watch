// Shared UK display dates. Date-only values stay on their calendar day; Flask's
// naive ISO timestamps are UTC. Zoned timestamps are displayed in the viewer's zone.
export function formatDisplayDate(value, { withTime = false, fallback = null } = {}) {
  if (value == null || value === '') return fallback
  const text = typeof value === 'string' ? value.trim() : value
  const dateOnly = typeof text === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(text)
  const naive = typeof text === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(text) && !/(?:z|[+-]\d{2}:?\d{2})$/i.test(text)
  const date = new Date(dateOnly ? `${text}T00:00:00Z` : naive ? `${text}Z` : text)
  if (Number.isNaN(date.getTime())) return fallback
  if (dateOnly && date.toISOString().slice(0, 10) !== text) return fallback
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric',
    ...(withTime && !dateOnly ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
    ...(dateOnly ? { timeZone: 'UTC' } : {}),
  }).format(date)
}
