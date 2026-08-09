export function formatSeasonLabel(season) {
    const startYear = Number.parseInt(String(season ?? ''), 10)
    if (!Number.isInteger(startYear)) return 'Season'
    return `${startYear}/${String(startYear + 1).slice(-2)}`
}
