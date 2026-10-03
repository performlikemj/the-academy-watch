import './player-card.css'
import { useEffect, useId, useRef, useState } from 'react'
import { ConfirmedTick, NoPhoto, clubColorStyle } from '@/components/player-card/PlayerCard'

function PhotoThumbs({ photos, name, activeIndex, onPick }) {
  return (
    <ul className="pc-thumbs" aria-label={`Photos of ${name}`}>
      {photos.map((photo, index) => (
        <li key={photo.id ?? photo.public_url}>
          <button
            type="button"
            className="pc-thumb"
            aria-pressed={index === activeIndex}
            aria-label={`Show photo ${index + 1} of ${photos.length}`}
            onClick={() => onPick(index)}
          >
            <img src={photo.public_url} alt="" loading="lazy" width={56} height={56} />
          </button>
        </li>
      ))}
    </ul>
  )
}

/**
 * Top of a player's page. Desktop: the A-style photo panel beside the name.
 * Phone: card C — the photo full-bleed with the name over a night scrim.
 * With no approved photo both become state D (initials in the club colours).
 *
 * `photos` must already be the approved, public ones (see publicPhotos()).
 */
export function PlayerHero({
  name,
  photos = [],
  faceUrl = null,
  clubName = null,
  role = null,
  confirmedBy = null,
  eyebrow = null,
  line = null,
  quote = null,
  clubColors,
  bar = null,
  actions = null,
  children = null,
}) {
  const [picked, setPicked] = useState(0)
  const [quoteOpen, setQuoteOpen] = useState(false)
  const [quoteClamped, setQuoteClamped] = useState(false)
  const quoteRef = useRef(null)
  const quoteId = useId()
  const activeIndex = picked < photos.length ? picked : 0
  const photo = photos[activeIndex] || null

  useEffect(() => {
    const element = quoteRef.current
    if (!element || quoteOpen) return undefined
    const measure = () => setQuoteClamped(element.scrollHeight > element.clientHeight + 1)
    measure()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [quote, quoteOpen])

  return (
    <section className="pc pc-hero-wrap" style={clubColorStyle(clubColors)} aria-label={`${name} — profile`} data-testid="player-hero" data-photo={photo ? 'yes' : 'no'}>
      {bar ? <div className="pc-hero-bar">{bar}</div> : null}
      <div className="pc-hero">
        <div className="pc-hero-panel">
          <div className="pc-hero-photo">
            {photo
              ? <img src={photo.public_url} alt={name} width={600} height={768} data-testid="player-hero-photo" />
              : <NoPhoto name={name} clubName={clubName} role={role} faceUrl={faceUrl} />}
            {photo && role ? <span className="pc-role-chip">{role}</span> : null}
          </div>
          {photos.length > 1 ? <PhotoThumbs photos={photos} name={name} activeIndex={activeIndex} onPick={setPicked} /> : null}
        </div>
        <div className="pc-hero-text">
          <div className="pc-hero-copy" data-testid="player-hero-copy">
            {confirmedBy ? (
              <p className="pc-hero-confirmed">
                <ConfirmedTick size={20} />
                <ConfirmedTick size={18} tone="chalk" />
                <span>Confirmed by {confirmedBy}</span>
              </p>
            ) : null}
            {eyebrow ? <div className="pc-hero-eyebrow">{eyebrow}</div> : null}
            <h1 className="pc-hero-name">{name}</h1>
            {line ? <p className="pc-hero-line">{line}</p> : null}
            {actions ? <div className="pc-hero-actions">{actions}</div> : null}
          </div>
          <div className="pc-hero-rest">
            {quote ? (
              <p className="pc-hero-quote" id={quoteId} ref={quoteRef} data-open={quoteOpen}>“{quote}”</p>
            ) : null}
            {quote && (quoteClamped || quoteOpen) ? (
              <button type="button" className="pc-hero-more" aria-expanded={quoteOpen} aria-controls={quoteId} onClick={() => setQuoteOpen((open) => !open)}>
                {quoteOpen ? 'Show less' : 'Read more'}
              </button>
            ) : null}
            {photos.length > 1 ? <PhotoThumbs photos={photos} name={name} activeIndex={activeIndex} onPick={setPicked} /> : null}
            {children ? <div className="pc-hero-extra">{children}</div> : null}
          </div>
        </div>
      </div>
    </section>
  )
}

export default PlayerHero
