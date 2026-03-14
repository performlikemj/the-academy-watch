import { useMemo } from 'react'
import { motion } from 'framer-motion' // eslint-disable-line no-unused-vars

/**
 * Format a season range pair [startYear, endYear] into display format.
 * e.g. [2022, 2026] -> "2022/23 – 2025/26"
 */
function formatSeasonRange(range) {
    if (!range || range.length < 2) return null
    const [start, end] = range
    const fmtSeason = (yr) => `${yr}/${String(yr + 1).slice(-2)}`
    return `${fmtSeason(start)} \u2013 ${fmtSeason(end - 1)}`
}

function StatItem({ value, label, color = 'text-white', dot, delay = 0 }) {
    return (
        <div className="flex flex-col items-center gap-0.5 min-w-[4rem]">
            <motion.span
                className={`text-2xl font-bold tabular-nums ${color}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay }}
            >
                {value}
            </motion.span>
            <motion.span
                className="flex items-center gap-1 text-xs text-slate-400"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: delay + 0.05 }}
            >
                {dot && (
                    <span
                        className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: dot }}
                    />
                )}
                {label}
            </motion.span>
        </div>
    )
}

export function NetworkMapHeader({ data }) {
    const countryCount = useMemo(() => {
        if (!data?.nodes) return 0
        const countries = new Set()
        for (const node of data.nodes) {
            if (!node.is_parent && node.country) {
                countries.add(node.country)
            }
        }
        return countries.size
    }, [data?.nodes])

    if (!data) return null

    const { total_academy_players, summary, season_range } = data
    const onLoan = summary?.on_loan ?? 0
    const firstTeam = summary?.first_team ?? 0
    const seasonLabel = formatSeasonRange(season_range)

    return (
        <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8 py-3 px-4">
            <StatItem
                value={total_academy_players ?? 0}
                label="Academy Players"
                color="text-white"
                delay={0}
            />
            <StatItem
                value={onLoan}
                label="On Loan"
                color="text-amber-400"
                dot="#d97706"
                delay={0.08}
            />
            <StatItem
                value={firstTeam}
                label="First Team"
                color="text-emerald-400"
                dot="#059669"
                delay={0.16}
            />
            <StatItem
                value={countryCount}
                label="Countries"
                color="text-sky-400"
                delay={0.24}
            />
            {seasonLabel && (
                <motion.div
                    className="flex flex-col items-center gap-0.5 min-w-[4rem]"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.32 }}
                >
                    <span className="text-sm font-medium text-slate-400">
                        {seasonLabel}
                    </span>
                    <span className="text-xs text-slate-500">Season Range</span>
                </motion.div>
            )}
        </div>
    )
}

export default NetworkMapHeader
