import { Link } from 'react-router-dom'
import { ArrowRight, Maximize2 } from 'lucide-react'
import { InlinePlayerWriteups } from '@/components/NewsletterWriterOverlay'
import { MatchCardsStrip } from './MatchCardsStrip'
import { UpcomingFixturesList } from './UpcomingFixturesList'
import { TweetCard } from './TweetCard'

/**
 * Player commentary card — the unit of value in the newsletter.
 *
 * Layout:
 *   - Mobile: stacked single column
 *   - md+:   2-column inside the card (info left / charts right)
 *
 * Inline view shows a slim chart set (radar + trend) so the card stays
 * scannable. The full chart set (match summary + stat table + radar +
 * trend + rating + minutes) lives in the expanded drawer.
 *
 * Click affordances:
 *   - "Expand" button (top right) → opens PlayerCardDrawer with full data
 *     at 1.5–2× scale.
 *   - Click on any inline chart → opens ChartLightbox at native resolution.
 *
 * Both callbacks (`onExpand`, `onZoomChart`) are owned by NewsletterView
 * so the drawer/lightbox can be controlled centrally.
 */

function StatPill({ label, value }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="flex flex-col items-center justify-center px-3 py-2.5 min-w-[60px] flex-1">
      <div className="text-[10px] uppercase tracking-wide text-[var(--tl-text-muted)] font-semibold">
        {label}
      </div>
      <div className="text-sm sm:text-[15px] font-bold text-[var(--tl-text)] mt-0.5">{value}</div>
    </div>
  )
}

function StatRibbon({ stats }) {
  if (!stats || typeof stats !== 'object') return null
  const cells = [
    { label: 'Mins', value: stats.minutes != null ? `${stats.minutes}'` : null },
    { label: 'Goals', value: stats.goals != null ? stats.goals : null },
    { label: 'Assists', value: stats.assists != null ? stats.assists : null },
    {
      label: 'Key Passes',
      value: stats.passes_key != null ? stats.passes_key : null,
    },
    {
      label: 'Rating',
      value:
        stats.rating != null && Number(stats.rating) > 0
          ? Number(stats.rating).toFixed(1)
          : null,
    },
  ].filter((c) => c.value !== null)

  if (cells.length === 0) return null

  return (
    <div
      className="flex flex-wrap rounded-md mb-4 divide-x divide-[var(--tl-divider)]"
      style={{ background: 'var(--tl-inner)' }}
    >
      {cells.map((c, i) => (
        <StatPill key={i} {...c} />
      ))}
    </div>
  )
}

function StatusPill({ status, level, loanTeam }) {
  if (!status && !loanTeam) return null
  const labelMap = {
    on_loan: 'On Loan',
    first_team: 'First Team',
    academy: level || 'Academy',
    released: 'Released',
    sold: 'Sold',
  }
  const label = labelMap[status] || (loanTeam ? 'On Loan' : null)
  if (!label) return null
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wide"
      style={{
        background: 'var(--tl-primary-soft)',
        color: 'var(--tl-primary)',
      }}
    >
      {label}
    </span>
  )
}

export function PlayerCommentaryCard({
  item,
  twitterTakes = [],
  publicBaseUrl,
  onExpand,
  onZoomChart,
}) {
  if (!item) return null

  const playerLinkId = item.player_api_id || item.player_id
  const loanTeam = item.loan_team || item.loan_team_name
  const photo = item.player_photo

  // Inline view shows a slim chart set so the card stays scannable. The
  // expanded drawer surfaces ALL the charts at full size.
  const inlineCharts = [
    { url: item.radar_chart_url, alt: 'Performance Radar' },
    { url: item.trend_chart_url, alt: 'Season Rating Trend' },
  ].filter((c) => c.url)
  const hasCharts = inlineCharts.length > 0

  const handleExpand = () => {
    if (onExpand) {
      onExpand({ item, twitterTakes })
    }
  }

  const handleChartClick = (chart) => {
    if (onZoomChart) {
      onZoomChart({
        url: chart.url,
        alt: chart.alt,
        caption: `${item.player_name} — ${chart.alt}`,
      })
    }
  }

  return (
    <article
      className="tl-card-hover rounded-xl mb-5 sm:mb-6 lg:mb-0 relative @container"
      style={{ background: 'var(--tl-section)' }}
    >
      {/* Expand affordance — top-right corner. Only renders when an
          onExpand handler is provided. */}
      {onExpand && (
        <button
          type="button"
          onClick={handleExpand}
          aria-label={`Expand ${item.player_name || 'player'} details`}
          className="absolute top-3 right-3 z-10 inline-flex items-center justify-center h-9 w-9 rounded-full text-[var(--tl-text-muted)] hover:text-[var(--tl-text)] hover:bg-[var(--tl-card)] transition-colors"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      )}

      {/* Internal split is container-query driven — at @[560px] of CARD
          width (not viewport width), narrative + charts go side-by-side
          7/5. Below that, charts stack below narrative full-width. This
          decouples the card from parent grid breakpoints so a 3-up grid
          on a 1536px viewport (each card ~460px) auto-stacks correctly. */}
      <div className={hasCharts ? 'grid grid-cols-1 @[560px]:grid-cols-12 gap-0' : ''}>
        {/* LEFT — identity, stats, narrative, tweets, CTA */}
        <div
          className={
            hasCharts
              ? '@[560px]:col-span-7 min-w-0 p-5 sm:p-6 md:p-7 lg:p-8'
              : 'min-w-0 p-5 sm:p-6 md:p-7 lg:p-8'
          }
        >
          <div className="flex items-start gap-4 mb-4 pr-10">
            {photo ? (
              <img
                src={photo}
                alt={item.player_name || 'Player'}
                className="h-16 w-16 sm:h-18 sm:w-18 lg:h-20 lg:w-20 rounded-full object-cover bg-[var(--tl-card)] flex-shrink-0"
              />
            ) : (
              <div className="h-16 w-16 sm:h-18 sm:w-18 lg:h-20 lg:w-20 rounded-full bg-[var(--tl-card)] flex items-center justify-center text-[var(--tl-text-muted)] text-sm font-bold flex-shrink-0">
                {(item.player_name || '?').slice(0, 1)}
              </div>
            )}
            <div className="flex-1 min-w-0">
              {playerLinkId && publicBaseUrl ? (
                <Link
                  to={`/players/${playerLinkId}`}
                  className="block"
                >
                  <h3 className="tl-headline text-lg sm:text-xl lg:text-2xl text-[var(--tl-text)] m-0 hover:text-[var(--tl-primary)] transition-colors">
                    {item.player_name}
                  </h3>
                </Link>
              ) : (
                <h3 className="tl-headline text-lg sm:text-xl lg:text-2xl text-[var(--tl-text)] m-0">
                  {item.player_name}
                </h3>
              )}
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <StatusPill
                  status={item.pathway_status}
                  level={item.current_level}
                  loanTeam={loanTeam}
                />
                {loanTeam && (
                  <div className="inline-flex items-center gap-1.5 text-[12px] text-[var(--tl-text-muted)] font-semibold">
                    {item.loan_team_logo && (
                      <img
                        src={item.loan_team_logo}
                        alt={loanTeam}
                        className="h-4 w-4 rounded-full object-cover bg-[var(--tl-card)]"
                      />
                    )}
                    <span>{loanTeam}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <StatRibbon stats={item.stats} />

          {item.week_summary && (
            <p className="text-[14px] sm:text-[15px] leading-[1.7] text-[var(--tl-text-body)] m-0 mb-4">
              {item.week_summary}
            </p>
          )}

          {item.matches && item.matches.length > 0 && (
            <div className="mb-4">
              <MatchCardsStrip matches={item.matches} />
            </div>
          )}

          {item.upcoming_fixtures && item.upcoming_fixtures.length > 0 && (
            <div className="mb-4">
              <UpcomingFixturesList fixtures={item.upcoming_fixtures} />
            </div>
          )}

          {/* Inline writer commentary (existing component) */}
          {playerLinkId && (
            <InlinePlayerWriteups
              playerId={playerLinkId}
              playerName={item.player_name}
              className="mb-4"
            />
          )}

          {/* Inline tweets about this player — capped at 2 in the inline
              view; the drawer surfaces the full list. */}
          {twitterTakes && twitterTakes.length > 0 && (
            <div className="mb-4">
              <p className="tl-eyebrow m-0 mb-2">
                Twitter &middot; about {item.player_name}
              </p>
              <div className="space-y-3">
                {twitterTakes.slice(0, 2).map((tweet, idx) => (
                  <TweetCard key={tweet.id || idx} tweet={tweet} />
                ))}
                {twitterTakes.length > 2 && (
                  <button
                    type="button"
                    onClick={handleExpand}
                    className="text-[11px] font-semibold text-[var(--tl-primary)] hover:underline"
                  >
                    + {twitterTakes.length - 2} more in expanded view
                  </button>
                )}
              </div>
            </div>
          )}

          {playerLinkId && publicBaseUrl && (
            <Link
              to={`/players/${playerLinkId}`}
              className="inline-flex items-center gap-1 text-[12px] uppercase tracking-wider font-bold text-[var(--tl-primary)] no-underline hover:gap-2 transition-all"
            >
              View full profile <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>

        {/* RIGHT — slim inline chart set (radar + trend). The full chart
            set lives in the expanded drawer. Each chart is clickable to
            open a lightbox at native resolution. */}
        {hasCharts && (
          <div
            className="@[560px]:col-span-5 p-5 sm:p-6 md:p-7 lg:p-8 space-y-4 border-t @[560px]:border-t-0 @[560px]:border-l border-[var(--tl-divider)]"
            style={{ background: 'var(--tl-card)' }}
          >
            {inlineCharts.map((c, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleChartClick(c)}
                aria-label={`Zoom ${c.alt}`}
                className="block w-full cursor-zoom-in p-0 border-0 bg-transparent hover:opacity-90 transition-opacity"
              >
                <img
                  src={c.url}
                  alt={c.alt}
                  loading="lazy"
                  className="block w-full h-auto rounded-md"
                />
              </button>
            ))}
            {/* Subtle hint that the card has more behind the expand button. */}
            {(item.match_card_url || item.stat_table_url || item.rating_graph_url) && (
              <button
                type="button"
                onClick={handleExpand}
                className="block w-full text-[11px] font-semibold text-[var(--tl-text-muted)] hover:text-[var(--tl-primary)] mt-2 text-center"
              >
                Click expand for match summary, stat table, and more &rarr;
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  )
}

export default PlayerCommentaryCard
