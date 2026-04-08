import { useCallback, useMemo, useState } from 'react'
import { NewsletterHeader } from './NewsletterHeader'
import { EditorsNote } from './EditorsNote'
import { KeyHighlightsList } from './KeyHighlightsList'
import { ByTheNumbersGrid } from './ByTheNumbersGrid'
import { SectionGroup } from './SectionGroup'
import { TeamTwitterSection } from './TeamTwitterSection'
import { CommunityTakesList } from './CommunityTakesList'
import { NewsletterFooter } from './NewsletterFooter'
import { PlayerCardDrawer } from './PlayerCardDrawer'
import { ChartLightbox } from './ChartLightbox'

/**
 * The Academy Watch newsletter — Tactical Lens edition.
 *
 * Replaces the legacy 360-line inline JSX block in `App.jsx` with a
 * componentised, mobile-first responsive editorial layout. The container
 * is wide (1280px max) so big monitors don't show acres of empty space,
 * but text-heavy reading blocks (editor's note, highlights) are capped
 * to ~68 characters wide for editorial readability.
 *
 * Two interactive primitives are owned at this top level:
 *   - `PlayerCardDrawer` — opens when a card's expand button fires; shows
 *     the same player content at 1.5–2× scale with all charts.
 *   - `ChartLightbox`    — opens when a chart image is clicked; shows that
 *     one chart at native resolution.
 *
 * Theming is scoped to `.newsletter-tactical-lens` — the rest of the app
 * keeps its warm burgundy palette unchanged.
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

  const detailedSections = useMemo(() => {
    if (!Array.isArray(obj.sections)) return []
    return obj.sections.filter(
      (section) => ((section?.title || '').trim().toLowerCase()) !== 'what the internet is saying'
    )
  }, [obj.sections])

  const teamLogo = obj.team_logo || newsletter?.team_logo
  const teamName = obj.team_name || newsletter?.team?.name || newsletter?.team_name

  // Drawer state — only one player drawer can be open at a time.
  const [drawerPlayer, setDrawerPlayer] = useState(null)
  const handleExpand = useCallback((payload) => {
    setDrawerPlayer(payload)
  }, [])
  const handleCloseDrawer = useCallback(() => setDrawerPlayer(null), [])

  // Chart lightbox state — receives a single chart at a time.
  const [lightboxChart, setLightboxChart] = useState(null)
  const handleZoomChart = useCallback((payload) => {
    setLightboxChart(payload)
  }, [])
  const handleCloseLightbox = useCallback(() => setLightboxChart(null), [])

  return (
    <div className="newsletter-tactical-lens min-h-full">
      {/* Wide canvas — uses up to 1280px on big monitors. The text-heavy
          editorial blocks below cap themselves at ~68ch internally for
          readability. */}
      <div className="max-w-[1280px] mx-auto px-4 sm:px-6 lg:px-10 py-8 sm:py-10 lg:py-12">
        <NewsletterHeader
          title={obj.title || newsletter?.title}
          range={obj.range}
          teamName={teamName}
          teamLogo={teamLogo}
        />

        {/* Editorial reading blocks — capped width inside the wide canvas. */}
        <div className="max-w-[68ch]">
          <EditorsNote summary={obj.summary} />
          <KeyHighlightsList highlights={obj.highlights} />
        </div>

        <ByTheNumbersGrid byNumbers={obj.by_numbers} />

        {detailedSections.length > 0 &&
          detailedSections.map((section, idx) => (
            <SectionGroup
              key={idx}
              section={section}
              twitterTakesByPlayer={twitterTakesByPlayer}
              publicBaseUrl={publicBaseUrl}
              onExpand={handleExpand}
              onZoomChart={handleZoomChart}
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

      {/* Player card drawer — full content of one player at 1.5–2× scale. */}
      <PlayerCardDrawer
        open={Boolean(drawerPlayer)}
        onOpenChange={(open) => !open && handleCloseDrawer()}
        item={drawerPlayer?.item || null}
        twitterTakes={drawerPlayer?.twitterTakes || []}
        publicBaseUrl={publicBaseUrl}
        onZoomChart={handleZoomChart}
      />

      {/* Chart lightbox — single chart at native resolution. */}
      <ChartLightbox
        open={Boolean(lightboxChart)}
        onOpenChange={(open) => !open && handleCloseLightbox()}
        url={lightboxChart?.url || ''}
        alt={lightboxChart?.alt || ''}
        caption={lightboxChart?.caption || ''}
      />
    </div>
  )
}

export default NewsletterView
