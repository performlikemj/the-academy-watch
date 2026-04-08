/**
 * "This week's matches" — horizontal strip of match score badges with
 * opponent name + competition. Renders the W/D/L color from `match.result`
 * (populated by the backend after the previous PR). Falls back to a neutral
 * pill when result is missing.
 *
 * Mobile: single-column stacked list. md+: horizontal grid wrap.
 */

function resultClasses(result) {
  if (result === 'W') {
    return {
      bg: 'var(--tl-success-soft)',
      color: 'var(--tl-success)',
    }
  }
  if (result === 'L') {
    return {
      bg: 'var(--tl-danger-soft)',
      color: 'var(--tl-danger)',
    }
  }
  return {
    bg: 'var(--tl-neutral-soft)',
    color: 'var(--tl-text-body)',
  }
}

export function MatchCardsStrip({ matches }) {
  if (!matches || !Array.isArray(matches) || matches.length === 0) return null

  return (
    <div
      className="rounded-lg p-4 sm:p-5"
      style={{ background: 'var(--tl-card)' }}
    >
      <p className="tl-eyebrow m-0 mb-3">This Week's Matches</p>
      <div className="space-y-2">
        {matches.map((match, idx) => {
          const colors = resultClasses(match.result)
          const homeGoals = match?.score?.home ?? 0
          const awayGoals = match?.score?.away ?? 0
          return (
            <div
              key={idx}
              className="flex items-center gap-3 py-2"
              style={{
                borderBottom: idx < matches.length - 1 ? '1px solid var(--tl-divider)' : 'none',
              }}
            >
              {match.opponent_logo && (
                <img
                  src={match.opponent_logo}
                  alt={match.opponent || ''}
                  className="h-7 w-7 rounded-full object-cover bg-[var(--tl-inner)] flex-shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-[13px] sm:text-sm font-semibold text-[var(--tl-text)] truncate">
                  {match.home ? 'vs' : '@'} {match.opponent || 'Unknown'}
                </div>
                {match.competition && (
                  <div className="text-[11px] text-[var(--tl-text-muted)] truncate">
                    {match.competition}
                  </div>
                )}
              </div>
              <span
                className="px-2.5 py-1 rounded text-[11px] font-extrabold tracking-wide flex-shrink-0"
                style={{ background: colors.bg, color: colors.color }}
              >
                {match.result || '–'} {homeGoals}-{awayGoals}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default MatchCardsStrip
