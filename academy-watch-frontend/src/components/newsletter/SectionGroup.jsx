import { PlayerCommentaryCard } from './PlayerCommentaryCard'

/**
 * One section in the detailed report — title + count + a list of player
 * commentary cards.
 *
 * Layout: when a section has 2+ players, render the cards in a 2-column
 * grid at lg+ (1024px+) so wide monitors don't show lonely single cards
 * with empty space on either side. Sections with exactly one player keep
 * a single full-width card.
 *
 * Props:
 *   - onExpand({ item, twitterTakes }) — fired when a card's expand button
 *     is clicked. Owned by NewsletterView.
 *   - onZoomChart({ url, alt, caption }) — fired when a chart image inside
 *     a card is clicked. Also owned by NewsletterView.
 */
export function SectionGroup({
  section,
  twitterTakesByPlayer = {},
  publicBaseUrl,
  onExpand,
  onZoomChart,
}) {
  if (!section || typeof section !== 'object') return null

  const items = Array.isArray(section.items) ? section.items : []
  if (items.length === 0) return null

  // Multi-column grid for sections with 2+ players. Single-column otherwise.
  const gridClass =
    items.length > 1
      ? 'grid grid-cols-1 lg:grid-cols-2 gap-5 lg:gap-6'
      : 'grid grid-cols-1'

  return (
    <section className="mb-12 sm:mb-14 lg:mb-16">
      <div className="flex items-baseline gap-3 mb-5 sm:mb-6">
        <h2 className="tl-eyebrow m-0">{section.title}</h2>
        <span className="text-[11px] font-extrabold text-[var(--tl-text-faint)]">
          ({items.length})
        </span>
      </div>

      {section.content && (
        <p className="text-[14px] text-[var(--tl-text-muted)] leading-relaxed mb-5 max-w-[68ch]">
          {section.content}
        </p>
      )}

      <div className={gridClass}>
        {items.map((item, idx) => {
          const playerKey = item.player_api_id || item.player_id
          const tweets = playerKey ? twitterTakesByPlayer[playerKey] || [] : []
          return (
            <PlayerCommentaryCard
              key={playerKey || idx}
              item={item}
              twitterTakes={tweets}
              publicBaseUrl={publicBaseUrl}
              onExpand={onExpand}
              onZoomChart={onZoomChart}
            />
          )
        })}
      </div>
    </section>
  )
}

export default SectionGroup
