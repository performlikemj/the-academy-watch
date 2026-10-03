import './player-card.css'
import { Link } from 'react-router-dom'
import { cardCounters, initialsOf } from '@/lib/player-card'

/** The green club-confirmed tick. `tone="chalk"` is the version used over a photo. */
export function ConfirmedTick({ size = 18, tone = 'good', label, className = '' }) {
  const fill = tone === 'chalk' ? 'var(--color-chalk)' : 'var(--color-good)'
  const stroke = tone === 'chalk' ? 'var(--color-night)' : 'var(--color-chalk)'
  return (
    <svg
      viewBox="0 0 20 20"
      width={size}
      height={size}
      className={`pc-tick pc-tick--${tone} ${className}`}
      {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true })}
    >
      <circle cx="10" cy="10" r="10" fill={fill} />
      <path d="M5.5 10.5 L8.7 13.5 L14.5 7" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Club colours for a card or hero; falls back to club green + gold in CSS. */
export function clubColorStyle(colors) {
  const style = {}
  if (colors?.primary) style['--pc-club-primary'] = colors.primary
  if (colors?.accent) style['--pc-club-accent'] = colors.accent
  return style
}

/**
 * State D — no approved photo yet: large initials in the club's colours.
 * `faceUrl` is a small provider headshot; it is shown at its own size, never
 * stretched into a portrait.
 */
export function NoPhoto({ name, clubName, role, faceUrl }) {
  return (
    <div className="pc-noimg" {...(faceUrl ? {} : { role: 'img', 'aria-label': `${name} — no photo yet` })}>
      {faceUrl
        ? <img className="pc-noimg-face" src={faceUrl} alt={name} width={148} height={148} />
        : <span className="pc-noimg-initials" aria-hidden="true">{initialsOf(name)}</span>}
      {clubName ? <span className="pc-noimg-club">{clubName}</span> : null}
      {role ? <span className="pc-noimg-role">{role}</span> : null}
    </div>
  )
}

/**
 * The card's tile at row size (a watchlist row): the approved photo, the
 * provider's small headshot, or initials in the club's colours. With no `name`
 * (a player who is no longer tracked) it is an empty, quiet tile.
 */
export function PlayerTile({ name, photoUrl, faceUrl, clubColors }) {
  if (!name) return <div className="pc pc-mini pc-mini--empty" aria-hidden="true" />
  return (
    <div className="pc pc-mini" style={clubColorStyle(clubColors)} data-photo={photoUrl ? 'yes' : 'no'}>
      {photoUrl
        ? <img className="pc-mini-photo" src={photoUrl} alt={name} loading="lazy" width={96} height={120} />
        : faceUrl
          ? <img className="pc-mini-face" src={faceUrl} alt={name} loading="lazy" width={64} height={64} />
          : <span className="pc-mini-initials" role="img" aria-label={`${name} — no photo yet`}>{initialsOf(name)}</span>}
    </div>
  )
}

/**
 * The standard player card (A · portrait, or D when there is no photo).
 * The whole card opens the player; the action button stays its own target.
 *
 * `variant="desk"` is the same card at list density (the scout desk): a short
 * tile with the position `chip`, `meta` (club · age) under the name, the season
 * figures with the word that says where they come from (`source`) — or
 * `emptyNote` when nothing is recorded — and a `status` line beside the action.
 */
export function PlayerCard({
  to,
  name,
  photoUrl,
  faceUrl,
  line,
  clubName,
  role,
  confirmed = false,
  appearances,
  minutes,
  clubColors,
  action,
  // Small icon controls for the surface the card sits on (e.g. compare, introduce).
  extras = null,
  variant = 'standard',
  chip = null,
  meta = null,
  source = null,
  emptyNote = null,
  status = null,
}) {
  const desk = variant === 'desk'
  const counters = cardCounters({ appearances, minutes })
  const counts = counters.length ? (
    <div className="pc-card-counts">
      {counters.map((counter) => (
        <span key={counter.unit}><b>{counter.value}</b> {counter.unit}</span>
      ))}
      {desk && source ? <span className="pc-card-source">{source}</span> : null}
    </div>
  ) : null
  const controls = extras ? <div className="pc-card-extras">{extras}</div> : null
  return (
    <article className={`pc pc-card${desk ? ' pc-card--desk' : ''}`} style={clubColorStyle(clubColors)} data-testid="player-card" data-photo={photoUrl ? 'yes' : 'no'}>
      <div className="pc-card-media">
        {photoUrl
          ? <img src={photoUrl} alt={name} loading="lazy" width={256} height={300} />
          : <NoPhoto name={name} clubName={desk ? null : clubName} role={desk ? null : role} faceUrl={faceUrl} />}
        {desk && chip ? <span className="pc-card-chip">{chip}</span> : null}
        {desk ? controls : null}
      </div>
      <div className="pc-card-body">
        <div className="pc-card-name">
          <Link to={to}>{name}</Link>
          {confirmed ? <ConfirmedTick size={desk ? 16 : 18} label="Club-confirmed" /> : null}
        </div>
        {desk && meta ? <p className="pc-card-meta">{meta}</p> : null}
        {line ? <p className="pc-card-line">{line}</p> : null}
        {desk ? counts || (emptyNote ? <p className="pc-card-empty">{emptyNote}</p> : null) : null}
        <div className="pc-card-foot">
          <div className="pc-card-foot-start">
            {desk ? (status ? <span className="pc-card-status">{status}</span> : null) : counts}
            {desk ? null : controls}
          </div>
          {action ? (
            <button
              type="button"
              className="pc-pill"
              onClick={action.onClick}
              aria-pressed={Boolean(action.pressed)}
              aria-label={action.ariaLabel}
              disabled={action.disabled}
            >
              {action.label}
            </button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

export default PlayerCard
