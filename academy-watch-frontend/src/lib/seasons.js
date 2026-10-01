export function formatSeasonLabel(season) {
    const startYear = Number.parseInt(String(season ?? ''), 10)
    if (!Number.isInteger(startYear)) return 'Season'
    return `${startYear}/${String(startYear + 1).slice(-2)}`
}

export function withSeasonParam(path, season) {
    if (season == null) return path
    const separator = path.includes('?') ? '&' : '?'
    return `${path}${separator}season=${encodeURIComponent(season)}`
}

// The display default follows available fixtures; the calendar is a last resort.
export function displaySeasonFromDirectory(directory) {
    for (const value of [directory?.display_season, directory?.current_season]) {
        if (value != null && Number.isInteger(Number(value))) return Number(value)
    }
    return undefined
}
