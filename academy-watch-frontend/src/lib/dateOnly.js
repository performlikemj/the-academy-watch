const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const DEFAULT_DATE_OPTIONS = { day: 'numeric', month: 'short', year: 'numeric' }

export function toLocalISODate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatDateOnly(value, options = DEFAULT_DATE_OPTIONS, locale = undefined) {
  if (value === null || typeof value === 'undefined' || value === '') return null
  const match = DATE_ONLY_PATTERN.exec(String(value).trim())
  if (!match) return null

  const year = Number(match[1])
  const monthIndex = Number(match[2]) - 1
  const day = Number(match[3])
  const date = new Date(year, monthIndex, day)
  if (date.getFullYear() !== year || date.getMonth() !== monthIndex || date.getDate() !== day) return null

  return date.toLocaleDateString(locale, options)
}
