/**
 * "Coming up next" — upcoming fixtures list with optional results overlay.
 * Some entries may be `status === 'completed'` (with `result`, `team_score`,
 * `opponent_score`); the rest are upcoming.
 */

function fixtureBadgeClasses(result) {
  if (result === 'W') return { bg: 'var(--tl-success-soft)', color: 'var(--tl-success)' }
  if (result === 'L') return { bg: 'var(--tl-danger-soft)', color: 'var(--tl-danger)' }
  if (result === 'D') return { bg: 'var(--tl-neutral-soft)', color: 'var(--tl-text-body)' }
  return null
}

export function UpcomingFixturesList({ fixtures }) {
  if (!fixtures || !Array.isArray(fixtures) || fixtures.length === 0) return null

  return (
    <div
      className="rounded-lg p-4 sm:p-5"
      style={{
        background: 'var(--tl-card)',
        borderLeft: '3px solid var(--tl-primary)',
      }}
    >
      <p className="tl-eyebrow m-0 mb-3">Coming Up Next</p>
      <div className="space-y-2">
        {fixtures.map((fixture, idx) => {
          const isCompleted = fixture.status === 'completed' && fixture.result
          const badge = isCompleted ? fixtureBadgeClasses(fixture.result) : null
          return (
            <div
              key={idx}
              className="flex items-center gap-3 py-2"
              style={{
                borderBottom: idx < fixtures.length - 1 ? '1px solid var(--tl-divider)' : 'none',
              }}
            >
              {fixture.opponent_logo && (
                <img
                  src={fixture.opponent_logo}
                  alt={fixture.opponent || ''}
                  className="h-7 w-7 rounded-full object-cover bg-[var(--tl-inner)] flex-shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-[13px] sm:text-sm font-semibold text-[var(--tl-text)] truncate">
                  {fixture.is_home ? 'vs' : '@'} {fixture.opponent || 'Unknown'}
                  {isCompleted && (
                    <span className="ml-2 font-bold">
                      {fixture.team_score}-{fixture.opponent_score}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-[var(--tl-text-muted)] truncate">
                  {fixture.competition}
                  {fixture.date && ` · ${String(fixture.date).slice(0, 10)}`}
                </div>
              </div>
              {badge && (
                <span
                  className="px-2 py-0.5 rounded text-[10px] font-extrabold tracking-wide flex-shrink-0"
                  style={{ background: badge.bg, color: badge.color }}
                >
                  {fixture.result}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default UpcomingFixturesList
