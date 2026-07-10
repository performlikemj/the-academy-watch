import { Link } from 'react-router-dom'
import { Star, Check, GitCompareArrows } from 'lucide-react'
import { StatusBadge, FormIndicator } from '@/pages/ScoutPage'
import { getInitials } from '@/lib/name'

/**
 * Mobile-first player card for the Scout Desk (< sm). The wide ranked table
 * collapses to a list of these on phones. Identity + stats are one big tap
 * target → /players/:id; the watch star and compare toggle live outside that
 * link so nesting stays valid and each control keeps its own 44px hit area.
 *
 * `statColumns` are the phase-relevant STAT_COLUMNS entries from ScoutPage —
 * we surface the headline few so a card stays glanceable, values in
 * tabular-nums, dashes (never fake zeros) preserved by each column's render.
 */
export function PlayerScoutCard({
  player,
  statColumns,
  watched,
  selected,
  onToggleWatch,
  onToggleCompare,
  compareDisabled,
}) {
  const headlineStats = (statColumns || []).slice(0, 4)
  const club = player.loan_team_name || player.primary_team_name
  const fromClub = player.loan_team_name && (player.owner_team_name || player.primary_team_name)
  const meta = [player.position, player.age ? `${player.age} yrs` : null].filter(Boolean).join(' · ')
  const noCoverage = player.appearances === 0 && player.data_depth === 'profile_only'

  return (
    <div className={`relative overflow-hidden rounded-xl border bg-card shadow-sm transition-colors ${selected ? 'border-primary/60 bg-primary/5' : 'border-border/80'}`}>
      {/* Watch star — top-right, outside the identity link */}
      <button
        type="button"
        onClick={onToggleWatch}
        className="absolute right-1.5 top-1.5 z-10 inline-flex h-11 w-11 items-center justify-center rounded-full transition-colors hover:bg-secondary active:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={watched ? `Remove ${player.player_name} from watchlist` : `Watch ${player.player_name}`}
        aria-pressed={watched}
      >
        <Star className={`h-5 w-5 transition-colors ${watched ? 'fill-amber-400 text-amber-500' : 'text-muted-foreground/50'}`} />
      </button>

      <Link to={`/players/${player.player_id}`} className="block p-3 pr-12 no-underline hover:no-underline">
        <div className="flex items-center gap-3">
          {player.player_photo ? (
            <img src={player.player_photo} alt="" loading="lazy" className="h-12 w-12 shrink-0 rounded-full bg-secondary object-cover" />
          ) : (
            <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold text-muted-foreground">
              {getInitials(player.player_name)}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-semibold leading-tight text-foreground">{player.player_name}</p>
            {meta && <p className="mt-0.5 truncate text-xs text-muted-foreground">{meta}</p>}
            <div className="mt-1 flex items-center gap-1.5">
              <StatusBadge status={player.status} />
            </div>
          </div>
        </div>

        {/* Club / loan line */}
        {club && (
          <p className="mt-2 truncate text-xs text-foreground/80">
            {club}
            {fromClub && <span className="text-muted-foreground"> · from {fromClub}</span>}
          </p>
        )}

        {/* Headline phase stats */}
        {headlineStats.length > 0 && (
          <div className="mt-2.5 grid grid-cols-4 gap-1.5">
            {headlineStats.map((col) => (
              <div key={col.label} className="rounded-lg bg-secondary/60 px-1.5 py-1.5 text-center">
                <div className={`text-sm font-semibold tabular-nums ${col.cellClass || 'text-foreground'}`}>
                  {col.render(player)}
                </div>
                <div className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{col.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Form */}
        <div className="mt-2.5 flex items-center gap-2">
          <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Form</span>
          {noCoverage ? (
            <span className="text-[11px] text-muted-foreground">No coverage yet</span>
          ) : (
            <FormIndicator form={player.recent_form} />
          )}
        </div>
      </Link>

      {/* Compare toggle — full-width tappable row, clearly outside the link */}
      <button
        type="button"
        onClick={onToggleCompare}
        disabled={compareDisabled}
        className={`flex min-h-11 w-full items-center justify-center gap-1.5 border-t text-xs font-semibold transition-colors disabled:opacity-40 ${
          selected
            ? 'border-primary/30 bg-primary/10 text-primary'
            : 'border-border/60 text-muted-foreground hover:bg-secondary/60 active:bg-secondary'
        }`}
        aria-pressed={selected}
      >
        {selected ? <Check className="h-4 w-4" /> : <GitCompareArrows className="h-4 w-4" />}
        {selected ? 'Selected to compare' : 'Compare'}
      </button>
    </div>
  )
}

export default PlayerScoutCard
