/**
 * Flatten club-grouped stops into chronological (season, club) ProgressionNodes.
 *
 * Each stop from the API groups all seasons at one club together.
 * We split them into individual nodes so the "time travel" feature can
 * focus on a single season at a time.
 */

import { JOURNEY_LEVEL_COLORS } from './theme-constants'

// Re-export from theme-constants so existing consumers don't break
export const LEVEL_COLORS = JOURNEY_LEVEL_COLORS

/**
 * Build an array of ProgressionNodes from the API stops.
 *
 * If a stop has `competitions` with per-season data we create one node per
 * season. Otherwise, we create a single node for the stop using its
 * aggregated stats.
 *
 * Each node:
 *   { id, season, clubId, clubName, clubLogo, lat, lng, city, country,
 *     levels, primaryLevel, stats: { apps, goals, assists },
 *     competitions, years, stopIndex }
 */
export function buildProgressionNodes(stops) {
    if (!stops || stops.length === 0) return []

    const nodes = []
    let id = 0

    stops.forEach((stop, stopIndex) => {
        // Group competitions by season
        const compsBySeason = {}
        if (stop.competitions && stop.competitions.length > 0) {
            stop.competitions.forEach(comp => {
                const season = comp.season ?? null
                if (season == null) return
                if (!compsBySeason[season]) compsBySeason[season] = []
                compsBySeason[season].push(comp)
            })
        }

        const seasonKeys = Object.keys(compsBySeason).sort((a, b) => Number(a) - Number(b))

        if (seasonKeys.length > 0) {
            // One node per season
            seasonKeys.forEach(seasonStr => {
                const season = Number(seasonStr)
                const comps = compsBySeason[season]
                const apps = comps.reduce((s, c) => s + (c.apps || 0), 0)
                const goals = comps.reduce((s, c) => s + (c.goals || 0), 0)
                const assists = comps.reduce((s, c) => s + (c.assists || 0), 0)

                nodes.push({
                    id: id++,
                    season,
                    clubId: stop.club_id,
                    clubName: stop.club_name,
                    clubLogo: stop.club_logo,
                    lat: stop.lat,
                    lng: stop.lng,
                    city: stop.city,
                    country: stop.country,
                    levels: stop.levels || [],
                    entryTypes: stop.entry_types || [],
                    primaryLevel: stop.levels?.[0] || 'First Team',
                    stats: { apps, goals, assists },
                    competitions: comps,
                    years: `${season}/${season + 1}`,
                    stopIndex,
                })
            })
        } else {
            // Fallback: single node per stop
            // Try to extract a season number from the years string (e.g. "2021-2023")
            const yearMatch = stop.years?.match(/(\d{4})/)
            const season = yearMatch ? Number(yearMatch[1]) : null

            nodes.push({
                id: id++,
                season,
                clubId: stop.club_id,
                clubName: stop.club_name,
                clubLogo: stop.club_logo,
                lat: stop.lat,
                lng: stop.lng,
                city: stop.city,
                country: stop.country,
                levels: stop.levels || [],
                entryTypes: stop.entry_types || [],
                primaryLevel: stop.levels?.[0] || 'First Team',
                stats: {
                    apps: stop.total_apps || 0,
                    goals: stop.total_goals || 0,
                    assists: stop.total_assists || 0,
                },
                competitions: stop.competitions || [],
                years: stop.years || '',
                stopIndex,
            })
        }
    })

    // Sort globally by season so international/youth entries appear in
    // chronological order rather than grouped after their parent stop.
    // Secondary sort by stopIndex preserves backend ordering within a season.
    nodes.sort((a, b) => {
        const sa = a.season ?? 0
        const sb = b.season ?? 0
        if (sa !== sb) return sa - sb
        return a.stopIndex - b.stopIndex
    })

    // Reassign sequential IDs after sorting (used for time-travel visited state)
    nodes.forEach((node, i) => { node.id = i })

    return nodes
}
