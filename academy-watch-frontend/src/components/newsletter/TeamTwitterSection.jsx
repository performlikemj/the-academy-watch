import { TweetCard } from './TweetCard'

/**
 * "Around the Squad — Twitter" — team-level tweets that aren't tied to a
 * specific player_id. Renders as a responsive grid of native X-style cards.
 */
export function TeamTwitterSection({ twitterTakes }) {
  if (!twitterTakes || !Array.isArray(twitterTakes)) return null

  // Only tweets without a player_id (per-player tweets are rendered inline
  // inside PlayerCommentaryCard).
  const teamTweets = twitterTakes.filter((t) => !t.player_id)
  if (teamTweets.length === 0) return null

  return (
    <section className="mb-12 sm:mb-16">
      <h2 className="tl-eyebrow m-0 mb-5">Around the Squad &middot; Twitter</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {teamTweets.map((tweet, idx) => (
          <TweetCard key={tweet.id || idx} tweet={tweet} />
        ))}
      </div>
    </section>
  )
}

export default TeamTwitterSection
