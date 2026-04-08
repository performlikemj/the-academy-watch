import { Link } from 'react-router-dom'
import { ArrowRight, ExternalLink } from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { InlinePlayerWriteups } from '@/components/NewsletterWriterOverlay'
import { MatchCardsStrip } from './MatchCardsStrip'
import { UpcomingFixturesList } from './UpcomingFixturesList'
import { TweetCard } from './TweetCard'

/**
 * PlayerCardDrawer — opens when a user clicks the expand button on a
 * PlayerCommentaryCard. Renders the SAME player content but at much
 * larger scale, with the FULL chart set (radar, trend, match summary,
 * stat table, rating graph, minutes graph) stacked vertically and the
 * full tweet list (no truncation cap).
 *
 * Uses a Sheet primitive sliding from the right on desktop. On mobile
 * the Sheet's default `w-3/4` becomes the bottom-most ~75% width — still
 * usable. (We chose Sheet over Drawer because Drawer's bottom-only
 * direction feels weird for a side panel of editorial content.)
 *
 * Wraps content in `.newsletter-tactical-lens` so the local CSS variables
 * cascade into the portal-rendered Sheet content (otherwise they'd live
 * in the React tree of the page but not in the actual DOM ancestor of
 * the Sheet content, since Radix portals append to <body>).
 */

function StatCell({ label, value }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="flex flex-col items-center justify-center px-4 py-3.5 min-w-[80px] flex-1">
      <div className="text-[11px] uppercase tracking-wide text-[var(--tl-text-muted)] font-semibold">
        {label}
      </div>
      <div className="text-lg sm:text-xl font-bold text-[var(--tl-text)] mt-1">{value}</div>
    </div>
  )
}

function StatRibbonLarge({ stats }) {
  if (!stats || typeof stats !== 'object') return null
  const cells = [
    { label: 'Mins', value: stats.minutes != null ? `${stats.minutes}'` : null },
    { label: 'Goals', value: stats.goals != null ? stats.goals : null },
    { label: 'Assists', value: stats.assists != null ? stats.assists : null },
    { label: 'Key Passes', value: stats.passes_key != null ? stats.passes_key : null },
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
      className="flex flex-wrap rounded-lg mb-6 divide-x divide-[var(--tl-divider)]"
      style={{ background: 'var(--tl-inner)' }}
    >
      {cells.map((c, i) => (
        <StatCell key={i} {...c} />
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
      className="inline-flex items-center px-2.5 py-1 rounded text-[11px] font-extrabold uppercase tracking-wide"
      style={{ background: 'var(--tl-primary-soft)', color: 'var(--tl-primary)' }}
    >
      {label}
    </span>
  )
}

export function PlayerCardDrawer({
  open,
  onOpenChange,
  item,
  twitterTakes = [],
  publicBaseUrl: _publicBaseUrl,
  onZoomChart,
}) {
  if (!item) return null

  const playerLinkId = item.player_api_id || item.player_id
  const loanTeam = item.loan_team || item.loan_team_name

  // Full chart set — every available image, in a sensible reading order.
  const allCharts = [
    { url: item.match_card_url, alt: 'Match Performance Summary' },
    { url: item.stat_table_url, alt: 'Recent Match Stats' },
    { url: item.radar_chart_url, alt: 'Performance Radar' },
    { url: item.trend_chart_url, alt: 'Season Rating Trend' },
    { url: item.rating_graph_url, alt: 'Rating Graph' },
    { url: item.minutes_graph_url, alt: 'Minutes Graph' },
  ].filter((c) => c.url)

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
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="newsletter-tactical-lens w-full sm:max-w-[640px] md:max-w-[760px] lg:max-w-[860px] !max-w-[100vw] sm:!max-w-[640px] md:!max-w-[760px] lg:!max-w-[860px] border-l-0 p-0 overflow-y-auto bg-[var(--tl-page)] text-[var(--tl-text-body)]"
      >
        <SheetHeader className="px-6 sm:px-8 pt-8 pb-4 text-left border-b border-[var(--tl-divider)]">
          <div className="flex items-start gap-4 sm:gap-5">
            {item.player_photo ? (
              <img
                src={item.player_photo}
                alt={item.player_name || 'Player'}
                className="h-20 w-20 sm:h-24 sm:w-24 rounded-full object-cover bg-[var(--tl-card)] flex-shrink-0"
              />
            ) : (
              <div className="h-20 w-20 sm:h-24 sm:w-24 rounded-full bg-[var(--tl-card)] flex items-center justify-center text-[var(--tl-text-muted)] text-base font-bold flex-shrink-0">
                {(item.player_name || '?').slice(0, 1)}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <SheetTitle className="tl-headline text-2xl sm:text-3xl text-[var(--tl-text)] m-0 break-words">
                {item.player_name}
              </SheetTitle>
              <SheetDescription className="text-[12px] text-[var(--tl-text-muted)] m-0 mt-1">
                Click any chart to zoom in.
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-2 mt-3">
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
        </SheetHeader>

        <div className="px-6 sm:px-8 py-6 sm:py-8 space-y-6">
          <StatRibbonLarge stats={item.stats} />

          {item.week_summary && (
            <div>
              <p className="tl-eyebrow m-0 mb-2">This Week</p>
              <p className="text-[15px] sm:text-base leading-[1.75] text-[var(--tl-text-body)] m-0">
                {item.week_summary}
              </p>
            </div>
          )}

          {item.matches && item.matches.length > 0 && (
            <div>
              <MatchCardsStrip matches={item.matches} />
            </div>
          )}

          {item.upcoming_fixtures && item.upcoming_fixtures.length > 0 && (
            <div>
              <UpcomingFixturesList fixtures={item.upcoming_fixtures} />
            </div>
          )}

          {/* Full chart set, stacked vertically at full width. Each chart
              is clickable to open the lightbox at native res. */}
          {allCharts.length > 0 && (
            <div className="space-y-5">
              <p className="tl-eyebrow m-0">Performance Visuals</p>
              {allCharts.map((c, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleChartClick(c)}
                  aria-label={`Zoom ${c.alt}`}
                  className="block w-full cursor-zoom-in p-0 border-0 bg-transparent rounded-lg overflow-hidden hover:opacity-95 transition-opacity"
                >
                  <img
                    src={c.url}
                    alt={c.alt}
                    loading="lazy"
                    className="block w-full h-auto"
                  />
                </button>
              ))}
            </div>
          )}

          {/* Inline writer commentary */}
          {playerLinkId && (
            <div>
              <InlinePlayerWriteups
                playerId={playerLinkId}
                playerName={item.player_name}
              />
            </div>
          )}

          {/* Full tweet list — no slice cap */}
          {twitterTakes && twitterTakes.length > 0 && (
            <div>
              <p className="tl-eyebrow m-0 mb-3">
                Twitter &middot; about {item.player_name} ({twitterTakes.length})
              </p>
              <div className="space-y-3">
                {twitterTakes.map((tweet, idx) => (
                  <TweetCard key={tweet.id || idx} tweet={tweet} />
                ))}
              </div>
            </div>
          )}

          {playerLinkId && (
            <div className="pt-4 border-t border-[var(--tl-divider)]">
              <Link
                to={`/players/${playerLinkId}`}
                onClick={() => onOpenChange?.(false)}
                className="inline-flex items-center gap-2 text-[12px] uppercase tracking-wider font-bold text-[var(--tl-primary)] no-underline hover:gap-3 transition-all"
              >
                View full player profile <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default PlayerCardDrawer
