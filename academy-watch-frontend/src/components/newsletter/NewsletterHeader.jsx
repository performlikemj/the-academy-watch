/**
 * Newsletter header — masthead, edition title, date range, team identity.
 *
 * Reads:
 *   - title (string)            — newsletter title
 *   - range (array<string,2>)   — [startDate, endDate] human-formatted
 *   - teamName (string)
 *   - teamLogo (string|null)    — URL
 *   - editionLabel (string)     — small uppercase eyebrow above title
 */
export function NewsletterHeader({
  title,
  range,
  teamName,
  teamLogo,
  editionLabel = 'Pipeline Update',
}) {
  return (
    <header className="mb-8 sm:mb-10">
      <div className="flex items-start gap-4 sm:gap-5">
        {teamLogo && (
          <img
            src={teamLogo}
            alt={teamName ? `${teamName} crest` : 'Team crest'}
            className="h-14 w-14 sm:h-16 sm:w-16 rounded-full object-cover bg-[var(--tl-card)] flex-shrink-0"
          />
        )}
        <div className="flex-1 min-w-0 space-y-1.5">
          <p className="tl-eyebrow m-0 text-[var(--tl-primary)]">
            The Academy Watch &middot; {editionLabel}
          </p>
          <h1 className="tl-headline text-2xl sm:text-3xl md:text-4xl text-[var(--tl-text)] m-0 leading-[1.15] break-words">
            {title}
          </h1>
          {(range || teamName) && (
            <p className="text-[13px] sm:text-sm text-[var(--tl-text-muted)] font-medium m-0">
              {teamName && <span>{teamName}</span>}
              {teamName && range && <span> &middot; </span>}
              {range && Array.isArray(range) && range.length >= 2 && (
                <span>
                  {range[0]} – {range[1]}
                </span>
              )}
            </p>
          )}
        </div>
      </div>
    </header>
  )
}

export default NewsletterHeader
