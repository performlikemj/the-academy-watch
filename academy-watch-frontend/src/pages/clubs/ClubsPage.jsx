import { useClubDirectory } from '@/hooks/useClubDirectory'
import { ClubsNearYouTeaser } from '@/pages/teasers/ClubsNearYouTeaser'
import { ClubDirectory } from './ClubDirectory'

/** /clubs: the real directory when CLUB_DIRECTORY_ENABLED is on, today's teaser otherwise. */
export function ClubsPage() {
  const enabled = useClubDirectory()
  if (enabled === null) return <div className="dark min-h-[70vh] bg-night" aria-busy="true" />
  return enabled ? <ClubDirectory /> : <ClubsNearYouTeaser />
}
