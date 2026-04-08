import { PlayerCommentaryCard } from './PlayerCommentaryCard'

/**
 * One section in the detailed report — title + count + a list of player
 * commentary cards. Each section corresponds to "Loanees", "First Team",
 * "Academy", etc.
 */
export function SectionGroup({ section, twitterTakesByPlayer = {}, publicBaseUrl }) {
  if (!section || typeof section !== 'object') return null

  const items = Array.isArray(section.items) ? section.items : []
  if (items.length === 0) return null

  return (
    <section className="mb-12 sm:mb-16">
      <div className="flex items-baseline gap-3 mb-5 sm:mb-6">
        <h2 className="tl-eyebrow m-0">{section.title}</h2>
        <span className="text-[11px] font-extrabold text-[var(--tl-text-faint)]">
          ({items.length})
        </span>
      </div>

      {section.content && (
        <p className="text-[14px] text-[var(--tl-text-muted)] leading-relaxed mb-5">
          {section.content}
        </p>
      )}

      <div>
        {items.map((item, idx) => {
          const playerKey = item.player_api_id || item.player_id
          const tweets = playerKey ? twitterTakesByPlayer[playerKey] || [] : []
          return (
            <PlayerCommentaryCard
              key={playerKey || idx}
              item={item}
              twitterTakes={tweets}
              publicBaseUrl={publicBaseUrl}
            />
          )
        })}
      </div>
    </section>
  )
}

export default SectionGroup
