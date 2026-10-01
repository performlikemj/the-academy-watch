import { LEVEL_LABELS, osmLink, programmeList } from '@/lib/club-directory'

/** Clubs-near-you fields of a profile revision, for the admin approving it (p2-b1). */
export function DirectoryReview({ directory }) {
  const pinned = Number.isFinite(directory.latitude) && Number.isFinite(directory.longitude)
  const programmes = programmeList(directory.gender_programs)
  if (!directory.venue_name && !directory.postcode && !pinned && !directory.club_level && !programmes.length) return null
  return (
    <div className="space-y-2 border-t pt-2" data-testid="directory-review">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Clubs near you — public once approved</p>
      {directory.venue_name ? <p><strong>Venue:</strong> {directory.venue_name}</p> : null}
      {directory.postcode ? <p><strong>Postcode:</strong> {directory.postcode}</p> : null}
      {pinned ? (
        <p>
          <strong>Pin:</strong> {directory.latitude.toFixed(5)}, {directory.longitude.toFixed(5)}{' '}
          <a className="underline underline-offset-4" href={osmLink(directory.latitude, directory.longitude)} target="_blank" rel="noopener noreferrer">Check it on a map</a>
        </p>
      ) : null}
      {LEVEL_LABELS[directory.club_level] ? <p><strong>Level:</strong> {LEVEL_LABELS[directory.club_level]}</p> : null}
      {programmes.length ? <p><strong>Football for:</strong> {programmes.join(', ')}</p> : null}
    </div>
  )
}
