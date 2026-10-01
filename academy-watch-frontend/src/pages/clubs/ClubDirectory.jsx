import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowUpRight, Check, Loader2, LocateFixed, X } from 'lucide-react'

import { APIService } from '@/lib/api'
import { InterestSignup } from '@/components/interest/InterestSignup'
import {
  LEVEL_LABELS,
  LEVELS,
  DIRECTORY_URL_PARAMS,
  OFFERING_FILTERS,
  RADIUS_OPTIONS_KM,
  clubMeta,
  clubPlace,
  directorySearchRequest,
  distanceUnit,
  hasPin,
  initials,
  osmLink,
  projectPins,
  radiusLabel,
  scaleBar,
} from '@/lib/club-directory'

const PER_PAGE = 20
const DEFAULT_PRIMARY = '#0F3D2E'
const CHALK = '#F3F0E8'
const INK = '#0E1311'

function safeColor(value) {
  return /^#[0-9a-fA-F]{6}$/.test(String(value || '')) ? value : DEFAULT_PRIMARY
}

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

// Chalk on the club's colour when it is readable there, ink otherwise.
function tileInk(primary) {
  const [hi, lo] = [luminance(CHALK), luminance(primary)].sort((a, b) => b - a)
  return (hi + 0.05) / (lo + 0.05) >= 4.5 ? CHALK : INK
}

function ClubTile({ club, size = 'h-14 w-14 rounded-xl text-[24px]' }) {
  const primary = safeColor(club.brand?.primary_color)
  return (
    <span
      className={`display flex shrink-0 items-center justify-center overflow-hidden border border-chalk/15 ${size}`}
      style={{ backgroundColor: primary, color: tileInk(primary) }}
      aria-hidden="true"
    >
      {club.crest_url
        ? <img src={club.crest_url} alt="" className="h-full w-full object-contain p-1.5" loading="lazy" />
        : initials(club.name)}
    </span>
  )
}

function Pill({ active, onClick, children }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex h-10 shrink-0 items-center rounded-full border px-4 text-sm transition-colors duration-200 ${active
        ? 'border-chalk bg-chalk text-ink'
        : 'border-chalk/25 text-chalk/80 hover:border-chalk/60 hover:text-chalk'}`}
    >
      {children}
    </button>
  )
}

function ClubRow({ club, selected, located, unit, onSelect }) {
  const meta = clubMeta(club, { unit, located })
  const place = clubPlace(club)
  return (
    <li>
      <Link
        to={`/programs/${club.slug}`}
        onMouseEnter={onSelect}
        onFocus={onSelect}
        data-testid="club-row"
        className={`grid grid-cols-[56px_minmax(0,1fr)] gap-4 border-b border-border px-2 py-5 transition-colors duration-200 hover:bg-chalk/[0.04] sm:gap-[18px] sm:px-3 ${selected ? 'bg-gold/[0.08]' : ''}`}
      >
        <ClubTile club={club} />
        <span className="flex min-w-0 flex-col gap-1.5">
          <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="display min-w-0 text-[26px] leading-none [overflow-wrap:anywhere] sm:text-[30px]">{club.name}</span>
            <span className="inline-flex items-center gap-1 text-xs text-muted-dark"><Check className="h-3 w-3" aria-hidden="true" />Verified</span>
          </span>
          {meta.length ? <span className="eyebrow text-muted-dark!">{meta.join(' · ')}</span> : null}
          {place ? <span className="text-[14.5px] text-chalk/75 [overflow-wrap:anywhere]">{place}</span> : null}
          {typeof club.open_opportunities === 'number' ? (
            <span className={`text-[14.5px] ${club.open_opportunities ? 'text-gold' : 'text-muted-dark'}`}>
              {club.open_opportunities
                ? `${club.open_opportunities} ${club.open_opportunities === 1 ? 'opportunity' : 'opportunities'} open`
                : 'No openings right now'}
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  )
}

/** North-up plot of real club coordinates. No tiles and no map provider: only relative positions. */
function PinPlot({ clubs, position, selectedId, onSelect, unit }) {
  const { pins, you, spanKm } = useMemo(() => projectPins(clubs, position), [clubs, position])
  const bar = scaleBar(spanKm, unit)
  const byId = useMemo(() => new Map(clubs.map((club) => [club.id, club])), [clubs])
  return (
    <div
      className="relative aspect-square w-full overflow-hidden rounded-lg border border-border bg-ink"
      style={{
        backgroundImage: 'linear-gradient(to right, rgba(243,240,232,.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(243,240,232,.05) 1px, transparent 1px)',
        backgroundSize: '12.5% 12.5%',
      }}
      role="group"
      aria-label="Club positions"
      data-testid="club-plot"
    >
      <span className="eyebrow absolute left-4 top-4 text-muted-dark!">N ↑</span>
      {you ? (
        <span
          className="absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-gold"
          style={{ left: `${you.x * 100}%`, top: `${you.y * 100}%` }}
          title="About where you are"
        >
          <span className="sr-only">About where you are</span>
        </span>
      ) : null}
      {pins.map((pin) => {
        const club = byId.get(pin.id)
        const active = pin.id === selectedId
        return (
          <button
            key={pin.id}
            type="button"
            aria-label={club?.name}
            aria-pressed={active}
            onClick={() => onSelect(pin.id)}
            className="absolute flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full"
            style={{ left: `${pin.x * 100}%`, top: `${pin.y * 100}%`, zIndex: active ? 2 : 1 }}
          >
            <span className={`block rounded-full border-2 border-night transition-all duration-200 ${active ? 'h-[22px] w-[22px] bg-gold' : 'h-3 w-3 bg-chalk'}`} />
          </button>
        )
      })}
      {bar ? (
        <span className="pointer-events-none absolute inset-x-0 bottom-4 flex flex-col gap-1.5" aria-hidden="true">
          <span className="ml-4 block h-px bg-chalk/60" style={{ width: `${bar.fraction * 100}%` }} />
          <span className="eyebrow ml-4 text-muted-dark!">{bar.label}</span>
        </span>
      ) : null}
      <span className="eyebrow absolute bottom-4 right-4 max-w-[55%] text-right text-muted-dark!">Positions only · not a street map</span>
    </div>
  )
}

function SelectedClub({ club, located, unit }) {
  if (!club) return null
  const meta = clubMeta(club, { unit, located })
  return (
    <div className="mt-4 flex flex-col gap-4 rounded-lg border border-chalk/15 bg-ink p-5 sm:flex-row sm:items-center sm:gap-5 sm:p-6" data-testid="selected-club">
      <ClubTile club={club} size="h-16 w-16 rounded-[14px] text-[28px]" />
      <span className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="display text-[28px] leading-none [overflow-wrap:anywhere] sm:text-[34px]">{club.name}</span>
        <span className="text-[14.5px] text-chalk/75 [overflow-wrap:anywhere]">{[clubPlace(club), ...meta].filter(Boolean).join(' · ')}</span>
      </span>
      <span className="flex shrink-0 flex-wrap gap-2.5">
        {hasPin(club) ? (
          <a
            href={osmLink(club.venue.latitude, club.venue.longitude)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-11 items-center gap-2 rounded-full border border-chalk/40 px-5 text-sm transition-colors hover:bg-chalk/10"
          >
            Open map <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
          </a>
        ) : null}
        <Link to={`/programs/${club.slug}`} className="inline-flex h-11 items-center rounded-full bg-chalk px-5 text-sm font-medium text-ink transition-colors hover:bg-chalk-2">
          View club
        </Link>
      </span>
    </div>
  )
}

function NoPinsPanel() {
  return (
    <div className="relative min-h-[320px] overflow-hidden rounded-lg bg-ink lg:min-h-[520px]">
      <img src="/media/city-pitch.webp" alt="" className="absolute inset-0 h-full w-full object-cover opacity-85" />
      <div className="absolute inset-0 bg-night/45" />
      <div className="absolute inset-x-4 bottom-4 flex flex-col gap-4 rounded-lg border border-chalk/15 bg-night/85 p-5 sm:inset-x-7 sm:bottom-7 sm:flex-row sm:items-center sm:gap-6 sm:p-6">
        <span className="flex-1">
          <span className="display block text-[26px] leading-tight">No grounds pinned here yet.</span>
          <span className="mt-1 block text-sm text-chalk/75">Clubs add their ground when they’re ready. Run a club? Claim its page and put it on the map.</span>
        </span>
        <Link to="/programs/claim" className="inline-flex h-11 shrink-0 items-center gap-2 self-start rounded-full border border-chalk/40 px-5 text-sm transition-colors hover:bg-chalk/10 sm:self-auto">
          Claim your club <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </div>
  )
}

export function ClubDirectory() {
  const [searchParams, setSearchParams] = useSearchParams()
  const offering = OFFERING_FILTERS.some((item) => item.id === searchParams.get('for')) ? searchParams.get('for') : ''
  const level = LEVELS.includes(searchParams.get('level')) ? searchParams.get('level') : ''

  // What the visitor typed (often a home postcode) and where they are live in memory only:
  // never in the page URL, a request URL, storage, analytics or our database.
  const [q, setQ] = useState('')
  const [draft, setDraft] = useState('')
  const [position, setPosition] = useState(null)
  const [locating, setLocating] = useState('idle')
  const [radiusKm, setRadiusKm] = useState(0)
  const [state, setState] = useState({ status: 'loading', clubs: [], total: 0, hasMore: false, page: 1 })
  const [selectedId, setSelectedId] = useState(null)
  const requestRef = useRef(0)
  const unit = useMemo(() => distanceUnit(typeof navigator === 'undefined' ? '' : navigator.language), [])

  const load = useCallback(async (page) => {
    const request = ++requestRef.current
    setState((current) => (page === 1
      ? { ...current, status: 'loading' }
      : { ...current, status: 'loading-more' }))
    try {
      const data = await APIService.request(...directorySearchRequest({ q, offering, level, position, radiusKm, page, perPage: PER_PAGE }))
      if (request !== requestRef.current) return
      setState((current) => ({
        status: 'ready',
        clubs: page === 1 ? data.clubs || [] : [...current.clubs, ...(data.clubs || [])],
        total: data.total || 0,
        hasMore: Boolean(data.has_more),
        page,
      }))
    } catch {
      if (request !== requestRef.current) return
      setState((current) => ({ ...current, status: page === 1 ? 'failed' : 'more-failed' }))
    }
  }, [q, offering, level, position, radiusKm])

  useEffect(() => {
    const timer = setTimeout(() => load(1), 0)
    return () => clearTimeout(timer)
  }, [load])

  // An old or hand-made link may carry a search in the URL: take it out of the address bar.
  useEffect(() => {
    const kept = new URLSearchParams()
    for (const name of DIRECTORY_URL_PARAMS) if (searchParams.get(name)) kept.set(name, searchParams.get(name))
    if (kept.toString() !== searchParams.toString()) setSearchParams(kept, { replace: true })
  }, [searchParams, setSearchParams])

  const { clubs } = state
  const pinned = useMemo(() => clubs.filter(hasPin), [clubs])
  const selected = clubs.find((club) => club.id === selectedId) || pinned[0] || null

  const setParam = (key, value) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const submit = (event) => {
    event.preventDefault()
    setQ(draft.trim())
  }

  const locate = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocating('unavailable')
      return
    }
    setLocating('asking')
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({ latitude: result.coords.latitude, longitude: result.coords.longitude })
        setLocating('on')
      },
      () => setLocating('denied'),
      { enableHighAccuracy: false, maximumAge: 600000, timeout: 10000 },
    )
  }

  const stopLocating = () => {
    setPosition(null)
    setRadiusKm(0)
    setLocating('idle')
  }

  const filtered = Boolean(q || offering || level || radiusKm)
  const clearAll = () => {
    setRadiusKm(0)
    setDraft('')
    setQ('')
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  const loading = state.status === 'loading'
  const countLabel = loading && !clubs.length
    ? 'Looking for clubs'
    : `${state.total} verified ${state.total === 1 ? 'club' : 'clubs'}`

  return (
    <div className="dark min-h-screen bg-night text-chalk">
      <div className="floodlight-container pb-20 pt-10 sm:pb-24 sm:pt-12">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between lg:gap-10">
          <div className="min-w-0">
            <p className="eyebrow">Find a club</p>
            <h1 className="display mt-3.5 text-[48px] sm:text-[76px]">Clubs near <em className="text-gold">you</em></h1>
          </div>
          <form onSubmit={submit} role="search" className="flex h-14 w-full items-center rounded-full border border-chalk/25 pl-5 pr-2 focus-within:border-chalk/60 lg:w-[460px] lg:shrink-0">
            <label htmlFor="club-search" className="eyebrow shrink-0 text-muted-dark!">Near</label>
            <input
              id="club-search"
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Town, postcode or club"
              maxLength={80}
              autoComplete="off"
              className="ml-3 min-w-0 flex-1 border-0 bg-transparent text-base text-chalk outline-none placeholder:text-muted-dark"
            />
            <button type="submit" className="h-[42px] shrink-0 rounded-full bg-chalk px-5 text-[14.5px] font-medium text-ink transition-colors hover:bg-chalk-2">Search</button>
          </form>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-3 text-sm text-chalk/80">
          {position ? (
            <>
              <span className="inline-flex items-center gap-2"><LocateFixed className="h-4 w-4 text-gold" aria-hidden="true" />Nearest first, from roughly where you are.</span>
              <label className="inline-flex items-center gap-2">
                <span className="text-muted-dark">Within</span>
                <select
                  value={radiusKm}
                  onChange={(event) => setRadiusKm(Number(event.target.value))}
                  className="h-10 rounded-full border border-chalk/25 bg-night px-3 text-sm text-chalk"
                  aria-label="Distance"
                >
                  <option value={0}>any distance</option>
                  {RADIUS_OPTIONS_KM[unit].map((km) => <option key={km} value={km}>{radiusLabel(km, unit)}</option>)}
                </select>
              </label>
              <button type="button" onClick={stopLocating} className="inline-flex h-10 items-center gap-1.5 rounded-full px-2 text-muted-dark underline-offset-4 hover:text-chalk hover:underline">
                <X className="h-3.5 w-3.5" aria-hidden="true" />Stop using my location
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={locate} disabled={locating === 'asking'} className="inline-flex h-10 items-center gap-2 rounded-full border border-chalk/40 px-4 transition-colors hover:bg-chalk/10 disabled:opacity-60">
                {locating === 'asking' ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <LocateFixed className="h-4 w-4" aria-hidden="true" />}
                Use my location
              </button>
              <span className="text-muted-dark" role="status">
                {locating === 'denied' ? 'We couldn’t get your location. Search by town or postcode instead.'
                  : locating === 'unavailable' ? 'This browser can’t share a location. Search by town or postcode instead.'
                    : 'Only used to sort this list. Rounded to about a kilometre, never saved.'}
              </span>
            </>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-2.5">
          <div className="flex flex-wrap gap-2.5" role="group" aria-label="Who it’s for">
            {OFFERING_FILTERS.map((item) => (
              <Pill key={item.id} active={offering === item.id} onClick={() => setParam('for', offering === item.id ? '' : item.id)}>{item.label}</Pill>
            ))}
          </div>
          <span className="mx-1 hidden h-6 w-px bg-chalk/15 sm:block" aria-hidden="true" />
          <div className="flex flex-wrap gap-2.5" role="group" aria-label="Level">
            {LEVELS.map((code) => (
              <Pill key={code} active={level === code} onClick={() => setParam('level', level === code ? '' : code)}>{LEVEL_LABELS[code]}</Pill>
            ))}
          </div>
          <span className="eyebrow ml-auto w-full pt-2 text-muted-dark! sm:w-auto sm:pt-0" role="status" aria-live="polite" data-testid="club-count">{countLabel}</span>
        </div>

        <div className="mt-6 grid gap-10 lg:grid-cols-[minmax(0,560px)_minmax(0,1fr)] lg:gap-8">
          <div className="min-w-0">
            {state.status === 'failed' ? (
              <div className="border-y border-border py-10">
                <p className="display text-[28px]">We couldn’t load the clubs.</p>
                <p className="mt-2 text-sm text-muted-dark">Nothing is wrong on your side. Try again in a moment.</p>
                <button type="button" onClick={() => load(1)} className="mt-6 inline-flex h-11 items-center rounded-full border border-chalk/40 px-5 text-sm transition-colors hover:bg-chalk/10">Try again</button>
              </div>
            ) : loading && !clubs.length ? (
              <div className="flex items-center gap-3 border-y border-border py-10 text-muted-dark" role="status">
                <Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                <span className="eyebrow text-muted-dark!">Loading clubs</span>
              </div>
            ) : clubs.length ? (
              <>
                <ul className={`border-t border-border transition-opacity duration-200 ${loading ? 'opacity-60' : ''}`} aria-label="Verified clubs">
                  {clubs.map((club) => (
                    <ClubRow
                      key={club.id}
                      club={club}
                      unit={unit}
                      located={Boolean(position)}
                      selected={selectedId === club.id}
                      onSelect={() => setSelectedId(club.id)}
                    />
                  ))}
                </ul>
                {state.hasMore || state.status === 'more-failed' ? (
                  <div className="mt-6 flex flex-wrap items-center gap-4">
                    <button type="button" onClick={() => load(state.page + 1)} disabled={state.status === 'loading-more'} className="inline-flex h-11 items-center gap-2 rounded-full border border-chalk/40 px-5 text-sm transition-colors hover:bg-chalk/10 disabled:opacity-60">
                      {state.status === 'loading-more' ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
                      Show more clubs
                    </button>
                    {state.status === 'more-failed' ? <span className="text-sm text-muted-dark" role="status">That didn’t load. Try again.</span> : null}
                  </div>
                ) : null}
                <p className="mt-6 text-[13px] leading-relaxed text-muted-dark">
                  Every club here has been checked by The Academy Watch and is looked after by an adult club manager.
                  Clubs are listed, never young players: no names, photos or squad lists appear on this page.
                </p>
              </>
            ) : (
              <div className="border-y border-border py-10" data-testid="club-empty">
                <p className="display text-[30px] leading-tight sm:text-[34px]">{filtered ? 'No verified clubs match that yet.' : 'No verified clubs are listed yet.'}</p>
                <p className="mt-3 max-w-md text-[15px] leading-relaxed text-muted-dark">
                  {filtered
                    ? 'Try a nearby town, a wider distance or fewer filters. New clubs join as they are checked.'
                    : 'Clubs appear here once they have been checked. Leave your email and we’ll tell you when clubs near you join.'}
                </p>
                {filtered ? (
                  <button type="button" onClick={clearAll} className="mt-6 inline-flex h-11 items-center rounded-full border border-chalk/40 px-5 text-sm transition-colors hover:bg-chalk/10">Clear search and filters</button>
                ) : null}
                <p className="display mt-10 text-[24px] leading-tight">Tell me when clubs near me join.</p>
                <InterestSignup feature="clubs_near_you" showRole className="mt-4" />
              </div>
            )}
          </div>

          <div className="min-w-0 lg:sticky lg:top-6 lg:self-start">
            {pinned.length ? (
              <>
                <PinPlot clubs={pinned} position={position} selectedId={selected?.id} onSelect={setSelectedId} unit={unit} />
                <SelectedClub club={selected} located={Boolean(position)} unit={unit} />
                {clubs.length > pinned.length ? (
                  <p className="mt-4 text-[13px] text-muted-dark">
                    {clubs.length - pinned.length} {clubs.length - pinned.length === 1 ? 'club in this list hasn’t' : 'clubs in this list haven’t'} pinned a ground yet, so {clubs.length - pinned.length === 1 ? 'it isn’t' : 'they aren’t'} plotted.
                  </p>
                ) : null}
              </>
            ) : <NoPinsPanel />}
          </div>
        </div>
      </div>
    </div>
  )
}
