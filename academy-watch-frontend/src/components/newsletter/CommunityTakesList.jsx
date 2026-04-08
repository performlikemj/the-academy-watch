import { ExternalLink, Quote } from 'lucide-react'

/**
 * Non-Twitter community takes — reddit, submission, editor sources. Tweets
 * are rendered separately by `TeamTwitterSection` (team-level) and inline
 * within `PlayerCommentaryCard` (per-player). This section is the catch-all
 * for everything else, with a generic editorial-quote aesthetic.
 */
export function CommunityTakesList({ communityTakes }) {
  if (!communityTakes || !Array.isArray(communityTakes)) return null

  const nonTwitter = communityTakes.filter((t) => t.source_type !== 'twitter')
  if (nonTwitter.length === 0) return null

  return (
    <section className="mb-12 sm:mb-16">
      <h2 className="tl-eyebrow m-0 mb-5">Community Takes</h2>
      <div className="space-y-4">
        {nonTwitter.map((take, idx) => (
          <div
            key={take.id || idx}
            className="rounded-lg p-5 sm:p-6"
            style={{ background: 'var(--tl-section)' }}
          >
            <div className="flex items-start gap-3">
              <Quote className="h-4 w-4 text-[var(--tl-primary)] flex-shrink-0 mt-1" />
              <div className="flex-1 min-w-0">
                <p className="text-[14px] sm:text-[15px] leading-[1.7] text-[var(--tl-text-body)] m-0 mb-3">
                  {take.content}
                </p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--tl-text-muted)] font-medium">
                  <span>&mdash; {take.source_author || 'Anonymous'}</span>
                  {take.source_platform && <span>&middot; {take.source_platform}</span>}
                  {take.player_name && (
                    <span
                      className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider"
                      style={{
                        background: 'var(--tl-neutral-soft)',
                        color: 'var(--tl-text-body)',
                      }}
                    >
                      {take.player_name}
                    </span>
                  )}
                  {take.source_url && (
                    <a
                      href={take.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-auto inline-flex items-center gap-1 text-[var(--tl-primary)] no-underline hover:underline"
                    >
                      Source <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default CommunityTakesList
