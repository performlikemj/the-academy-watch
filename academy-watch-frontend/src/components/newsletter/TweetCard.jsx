import { ExternalLink, Heart, Repeat2 } from 'lucide-react'

/**
 * Native X-style tweet card. Used in two places:
 *   - Inline within `PlayerCommentaryCard` when `twitter_takes_by_player[player_id]`
 *     has tweets about that player.
 *   - In the team-level `TeamTwitterSection` for tweets without a player_id.
 *
 * Renders a tweet that visually reads as a tweet (X branding, blue handle,
 * engagement metrics, "View on X" link) — explicitly NOT a generic 💬 quote.
 *
 * Source data is the existing `CommunityTake(source_type='twitter')` shape:
 *   { source_author, source_platform, content, source_url, upvotes,
 *     original_posted_at, player_id, player_name }
 */
export function TweetCard({ tweet }) {
  if (!tweet || !tweet.content) return null

  const author = tweet.source_author || 'Unknown'
  const handle = tweet.source_platform || ''
  const likes = tweet.upvotes || 0
  const date = tweet.original_posted_at ? tweet.original_posted_at.slice(0, 10) : null

  return (
    <div className="tl-tweet">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[13px] font-bold text-[var(--tl-text)]">{author}</span>
        {handle && (
          <span className="text-[12px] font-medium text-[var(--tl-primary)]">{handle}</span>
        )}
        <span className="ml-auto text-[15px] font-extrabold text-[var(--tl-text-muted)] leading-none">
          𝕏
        </span>
      </div>
      <p className="text-[14px] leading-[1.55] text-[var(--tl-text-body)] m-0 mb-3">
        {tweet.content}
      </p>
      <div className="flex items-center gap-4 text-[11px] text-[var(--tl-text-muted)]">
        {likes > 0 && (
          <span className="inline-flex items-center gap-1">
            <Heart className="h-3 w-3" />
            {likes}
          </span>
        )}
        {date && <span>{date}</span>}
        {tweet.source_url && (
          <a
            href={tweet.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-[var(--tl-primary)] font-semibold no-underline hover:underline"
          >
            View on X <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </div>
  )
}

export default TweetCard
