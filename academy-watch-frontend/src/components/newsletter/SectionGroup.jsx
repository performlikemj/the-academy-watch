import { PlayerCommentaryCard } from './PlayerCommentaryCard'

/**
 * One section in the detailed report — title + count + a list of player
 * commentary cards.
 *
 * Two backend shapes are supported:
 *   1. Flat:        { title, items: [...] }
 *   2. Subsectioned: { title, subsections: [{ label, items: [...] }, ...] }
 *
 * The subsectioned shape is emitted when players span multiple loan
 * leagues or academy levels (see weekly_newsletter_agent._group_items_by).
 * If we ignore subsections we silently drop entire sections of players —
 * exactly what was happening before this fix.
 *
 * Layout: when a (sub)section has 2+ players, render the cards in a
 * 2-column grid at lg+ (1024px+) so wide monitors don't show lonely
 * single cards with empty space on either side.
 *
 * Props:
 *   - onExpand({ item, twitterTakes }) — fired when a card's expand button
 *     is clicked. Owned by NewsletterView.
 *   - onZoomChart({ url, alt, caption }) — fired when a chart image inside
 *     a card is clicked. Also owned by NewsletterView.
 */
function PlayerGrid({ items, twitterTakesByPlayer, publicBaseUrl, onExpand, onZoomChart }) {
  const gridClass =
    items.length > 1
      ? 'grid grid-cols-1 lg:grid-cols-2 gap-5 lg:gap-6'
      : 'grid grid-cols-1'
  return (
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
  )
}

export function SectionGroup({
  section,
  twitterTakesByPlayer = {},
  publicBaseUrl,
  onExpand,
  onZoomChart,
}) {
  if (!section || typeof section !== 'object') return null

  const subsections = Array.isArray(section.subsections)
    ? section.subsections.filter((s) => Array.isArray(s?.items) && s.items.length > 0)
    : []
  const flatItems = Array.isArray(section.items) ? section.items : []

  const totalItems =
    subsections.length > 0
      ? subsections.reduce((sum, s) => sum + s.items.length, 0)
      : flatItems.length

  if (totalItems === 0) return null

  return (
    <section className="mb-12 sm:mb-14 lg:mb-16">
      <div className="flex items-baseline gap-3 mb-5 sm:mb-6">
        <h2 className="tl-eyebrow m-0">{section.title}</h2>
        <span className="text-[11px] font-extrabold text-[var(--tl-text-faint)]">
          ({totalItems})
        </span>
      </div>

      {section.content && (
        <p className="text-[14px] text-[var(--tl-text-muted)] leading-relaxed mb-5 max-w-[68ch]">
          {section.content}
        </p>
      )}

      {subsections.length > 0 ? (
        <div className="space-y-8 sm:space-y-10">
          {subsections.map((sub, subIdx) => (
            <div key={sub.label || subIdx}>
              <h3 className="text-[13px] sm:text-sm font-bold text-[var(--tl-text)] m-0 mb-4 flex items-baseline gap-2">
                <span>{sub.label}</span>
                <span className="text-[11px] font-extrabold text-[var(--tl-text-faint)]">
                  ({sub.items.length})
                </span>
              </h3>
              <PlayerGrid
                items={sub.items}
                twitterTakesByPlayer={twitterTakesByPlayer}
                publicBaseUrl={publicBaseUrl}
                onExpand={onExpand}
                onZoomChart={onZoomChart}
              />
            </div>
          ))}
        </div>
      ) : (
        <PlayerGrid
          items={flatItems}
          twitterTakesByPlayer={twitterTakesByPlayer}
          publicBaseUrl={publicBaseUrl}
          onExpand={onExpand}
          onZoomChart={onZoomChart}
        />
      )}
    </section>
  )
}

export default SectionGroup
