import { useMemo } from 'react'
import { NewsletterHeader } from './NewsletterHeader'
import { EditorsNote } from './EditorsNote'
import { KeyHighlightsList } from './KeyHighlightsList'
import { ByTheNumbersGrid } from './ByTheNumbersGrid'
import { SectionGroup } from './SectionGroup'
import { TeamTwitterSection } from './TeamTwitterSection'
import { CommunityTakesList } from './CommunityTakesList'
import { NewsletterFooter } from './NewsletterFooter'

/**
 * The Academy Watch newsletter — Tactical Lens edition.
 *
 * Replaces the legacy 360-line inline JSX block in `App.jsx` (lines
 * 9012-9372) with a properly componentised, mobile-first responsive
 * editorial layout that pulls from the existing newsletter JSON shape.
 *
 * Theming is scoped to the `.newsletter-tactical-lens` wrapper — the rest
 * of the app keeps its warm burgundy palette unchanged.
 *
 * Props:
 *   - newsletter: full newsletter record from /api/newsletters/:id
 *     (used for top-level metadata: title, team, dates)
 *   - enrichedContent: parsed structured_content JSON
 *   - twitterTakesByPlayer: { [player_api_id]: tweet[] } from API
 *   - twitterTakes: full tweet list (for team-level section)
 *   - communityTakes: full community-takes list (for non-twitter section)
 *   - publicBaseUrl: base URL for "view player" links (passed through)
 */
export function NewsletterView({
  newsletter,
  enrichedContent,
  twitterTakesByPlayer = {},
  twitterTakes = [],
  communityTakes = [],
  publicBaseUrl,
}) {
  const obj = enrichedContent || {}

  // Filter out the legacy "what the internet is saying" section — surfaced
  // separately by Twitter / Community Takes sections.
  const detailedSections = useMemo(() => {
    if (!Array.isArray(obj.sections)) return []
    return obj.sections.filter(
      (section) => ((section?.title || '').trim().toLowerCase()) !== 'what the internet is saying'
    )
  }, [obj.sections])

  const teamLogo = obj.team_logo || newsletter?.team_logo
  const teamName = obj.team_name || newsletter?.team?.name || newsletter?.team_name

  return (
    <div className="newsletter-tactical-lens min-h-full">
      <div className="max-w-[820px] mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
        <NewsletterHeader
          title={obj.title || newsletter?.title}
          range={obj.range}
          teamName={teamName}
          teamLogo={teamLogo}
        />

        <EditorsNote summary={obj.summary} />

        <KeyHighlightsList highlights={obj.highlights} />

        <ByTheNumbersGrid byNumbers={obj.by_numbers} />

        {detailedSections.length > 0 &&
          detailedSections.map((section, idx) => (
            <SectionGroup
              key={idx}
              section={section}
              twitterTakesByPlayer={twitterTakesByPlayer}
              publicBaseUrl={publicBaseUrl}
            />
          ))}

        <TeamTwitterSection twitterTakes={twitterTakes} />

        <CommunityTakesList communityTakes={communityTakes} />

        <NewsletterFooter
          webUrl={obj.web_url || newsletter?.web_url}
          submitTakeUrl={obj.submit_take_url || newsletter?.submit_take_url}
          flagBaseUrl={obj.flag_base_url || newsletter?.flag_base_url}
          teamName={teamName}
          newsletterId={newsletter?.id}
        />
      </div>
    </div>
  )
}

export default NewsletterView
