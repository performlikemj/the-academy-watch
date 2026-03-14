import { useMemo } from 'react'

/**
 * Compact aggregate stats strip for placed players.
 * Shows once 7+ players are on the pitch.
 */
export function SquadSummaryStrip({ placements }) {
  const stats = useMemo(() => {
    const players = Object.values(placements).filter(Boolean)
    if (players.length < 7) return null

    const goals = players.reduce((sum, p) => sum + (p.goals || 0), 0)
    const assists = players.reduce((sum, p) => sum + (p.assists || 0), 0)
    const apps = players.reduce((sum, p) => sum + (p.appearances || 0), 0)
    const minutes = players.reduce((sum, p) => sum + (p.minutes_played || 0), 0)

    return { count: players.length, goals, assists, apps, minutes }
  }, [placements])

  if (!stats) return null

  return (
    <div className="flex items-center justify-center gap-4 sm:gap-6 py-2 px-4 bg-foreground text-primary-foreground rounded-lg text-sm max-w-[520px] mx-auto">
      <Stat value={stats.goals} label="goals" />
      <Sep />
      <Stat value={stats.assists} label="assists" />
      <Sep />
      <Stat value={stats.apps} label="apps" />
      <Sep />
      <Stat value={formatMinutes(stats.minutes)} label="mins" />
    </div>
  )
}

function Stat({ value, label }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-lg font-bold tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground/70">{label}</span>
    </div>
  )
}

function Sep() {
  return <span className="text-muted-foreground">·</span>
}

function formatMinutes(mins) {
  if (mins >= 1000) return `${(mins / 1000).toFixed(1)}k`
  return mins
}
