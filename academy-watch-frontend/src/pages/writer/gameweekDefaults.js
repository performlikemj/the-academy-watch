const isValidDate = (value) => value instanceof Date && !Number.isNaN(value.getTime())

const toDateKey = (value) => value.toISOString().slice(0, 10)

const compareDesc = (a, b) => {
  const aKey = typeof a?.start_date === 'string' ? a.start_date : ''
  const bKey = typeof b?.start_date === 'string' ? b.start_date : ''
  if (aKey === bKey) return 0
  return aKey < bKey ? 1 : -1
}

export function getDefaultWriteupWeek(gameweeks, referenceDate = new Date()) {
  if (!Array.isArray(gameweeks)) return null

  const normalized = gameweeks.filter(Boolean)
  if (normalized.length === 0) return null

  const weeks = [...normalized].sort(compareDesc)

  const currentIndex = weeks.findIndex((week) => week?.is_current)
  if (currentIndex !== -1) {
    return weeks[currentIndex + 1] || weeks[currentIndex]
  }

  const referenceKey = isValidDate(referenceDate) ? toDateKey(referenceDate) : null
  if (referenceKey) {
    const inferredIndex = weeks.findIndex((week) => {
      if (!week?.start_date || !week?.end_date) return false
      return week.start_date <= referenceKey && referenceKey <= week.end_date
    })

    if (inferredIndex !== -1) {
      return weeks[inferredIndex + 1] || weeks[inferredIndex]
    }

    let latestPast = null
    for (const week of weeks) {
      if (!week?.end_date || week.end_date >= referenceKey) continue
      if (!latestPast || week.end_date > latestPast.end_date) {
        latestPast = week
      }
    }

    if (latestPast) return latestPast
  }

  return weeks[0]
}
