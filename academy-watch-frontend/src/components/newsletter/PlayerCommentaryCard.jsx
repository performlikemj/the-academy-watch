import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { InlinePlayerWriteups } from '@/components/NewsletterWriterOverlay'
import { MatchCardsStrip } from './MatchCardsStrip'
import { UpcomingFixturesList } from './UpcomingFixturesList'
import { TweetCard } from './TweetCard'

/**
 * Player commentary card — the unit of value in the newsletter. Renders one
 * loanee/first-team/academy player with all of their data slots:
 *   - photo + name + status pill + parent/current club
 *   - stat ribbon (mins, G, A, KP, rating)
 *   - chart images (radar, trend, stat table, match card)
 *   - week summary text
 *   - this-week's-matches strip
 *   - coming-up fixtures
 *   - inline curator commentary via InlinePlayerWriteups
 *   - inline tweets about this player (twitter_takes_by_player[player_id])
 *   - "View full player profile" CTA
 *
 * Layout:
 *   - Mobile: stacked single column
 *   - md+:   2-column inside the card (info left / charts right)
 */

function StatPill({ label, value }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="flex flex-col items-center justify-center px-3 py-2 min-w-[60px] flex-1">
      <div className="text-[10px] uppercase tracking-wide text-[var(--tl-text-muted)] font-semibold">
        {label}
      </div>
      <div className="text-sm font-bold text-[var(--tl-text)] mt-0.5">{value}</div>
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

export function PlayerCommentaryCard({ item, twitterTakes = [], publicBaseUrl }) {
  if (!item) return null

  const playerLinkId = item.player_api_id || item.player_id
  const loanTeam = item.loan_team || item.loan_team_name
  const photo = item.player_photo
  const charts = [
    { url: item.match_card_url, alt: 'Match Performance Summary' },
    { url: item.stat_table_url, alt: 'Recent Match Stats' },
    { url: item.radar_chart_url, alt: 'Performance Radar' },
    { url: item.trend_chart_url, alt: 'Season Rating Trend' },
    { url: item.rating_graph_url, alt: 'Rating Graph' },
    { url: item.minutes_graph_url, alt: 'Minutes Graph' },
  ].filter((c) => c.url)

  return (
    <article
      className="tl-card-hover rounded-xl mb-5 sm:mb-6"
      style={{ background: 'var(--tl-section)' }}
    >
      <div className="grid grid-cols-1 md:grid-cols-12 gap-0">
        {/* LEFT — identity, stats, narrative, tweets, CTA */}
        <div className="md:col-span-7 p-5 sm:p-6 md:p-7">
          <div className="flex items-start gap-4 mb-4">
            {photo ? (
              <img
                src={photo}
                alt={item.player_name || 'Player'}
                className="h-14 w-14 sm:h-16 sm:w-16 rounded-full object-cover bg-[var(--tl-card)] flex-shrink-0"
              />
            ) : (
              <div className="h-14 w-14 sm:h-16 sm:w-16 rounded-full bg-[var(--tl-card)] flex items-center justify-center text-[var(--tl-text-muted)] text-xs font-bold flex-shrink-0">
                {(item.player_name || '?').slice(0, 1)}
              </div>
            )}
            <div className="flex-1 min-w-0">
              {playerLinkId && publicBaseUrl ? (
                <Link
                  to={`/players/${playerLinkId}`}
                  className="block"
                >
                  <h3 className="tl-headline text-lg sm:text-xl text-[var(--tl-text)] m-0 break-words hover:text-[var(--tl-primary)] transition-colors">
                    {item.player_name}
                  </h3>
                </Link>
              ) : (
                <h3 className="tl-headline text-lg sm:text-xl text-[var(--tl-text)] m-0 break-words">
                  {item.player_name}
                </h3>
              )}
              <div className="flex flex-wrap items-center gap-2 mt-1.5">
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

          {/* Inline tweets about this player */}
          {twitterTakes && twitterTakes.length > 0 && (
            <div className="mb-4">
              <p className="tl-eyebrow m-0 mb-2">
                Twitter &middot; about {item.player_name}
              </p>
              <div className="space-y-3">
                {twitterTakes.slice(0, 3).map((tweet, idx) => (
                  <TweetCard key={tweet.id || idx} tweet={tweet} />
                ))}
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

        {/* RIGHT — chart images stack. Hidden on mobile if charts are absent. */}
        {charts.length > 0 && (
          <div
            className="md:col-span-5 p-5 sm:p-6 md:p-7 space-y-4 border-t md:border-t-0 md:border-l border-[var(--tl-divider)]"
            style={{ background: 'var(--tl-card)' }}
          >
            {charts.map((c, idx) => (
              <img
                key={idx}
                src={c.url}
                alt={c.alt}
                loading="lazy"
                className="block w-full h-auto rounded-md"
              />
            ))}
          </div>
        )}
      </div>
    </article>
  )
}

export default PlayerCommentaryCard
