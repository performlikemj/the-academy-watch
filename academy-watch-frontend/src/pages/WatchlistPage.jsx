import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Star, X, Loader2 } from 'lucide-react'
import { IntroduceDialog } from '@/components/contact/IntroduceDialog'
import { PlayerTile } from '@/components/player-card/PlayerCard'
import { ScoutSurface, ScoutHeader, deskPillClass } from '@/components/scout/ScoutDesk'
import { useContactRail } from '@/hooks/useContactRail.js'
import { useGuarded, useViewerKey, useViewerLifetime, useViewerState } from '@/hooks/useViewerState'
import { saveBlobAs } from '@/lib/download'
import { NO_MATCHES, deskFigures, deskPhotos, introductionView, watchClub, watchRole } from '@/lib/scout-desk'
import { cn } from '@/lib/utils'
import { isStaleViewerError } from '@/lib/viewer-lifetime'

const NOTE_MAX = 2000
// Stable identity: useViewerState's setter is keyed on its initial value.
const NO_ENTRIES = Object.freeze([])
const TONE_DOT = { good: 'bg-[#6FBF95]', wait: 'bg-gold', quiet: 'bg-[#7B8580]' }
const labelClass = 'font-mono text-[11px] uppercase tracking-[0.16em]'
const quietLinkClass = 'inline-flex h-11 items-center border-0 bg-transparent px-0.5 text-sm text-[#C9C5BA] underline underline-offset-4 hover:text-chalk focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
const rowPillClass = 'inline-flex h-11 items-center rounded-full border border-chalk/25 bg-transparent px-4 text-sm text-chalk no-underline transition-colors hover:border-chalk/60 hover:bg-chalk/[0.04] hover:text-chalk hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

// Stable identity, so the guarded saver is made once per lifetime.
const saveWatchlistCsv = (blob) => saveBlobAs(blob, 'academy-watch-scout-export.csv')

/** The scout's own note, in full. It is private: only this scout ever receives it. */
function NoteBlock({ entry, playerName, api, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const startEditing = () => {
    setDraft(entry.note || '')
    setError(null)
    setEditing(true)
  }

  const save = async (value) => {
    setSaving(true)
    setError(null)
    try {
      const res = await api.updateScoutWatchlistNote(entry.player_api_id, value)
      onSaved(res?.entry || { ...entry, note: value.trim() || null })
      setEditing(false)
    } catch (err) {
      if (!isStaleViewerError(err)) setError(err.message || 'The note could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-2.5" data-testid="watchlist-note">
      <p className={cn(labelClass, 'text-gold')}>Your private note</p>
      {editing ? (
        <>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value.slice(0, NOTE_MAX))}
            placeholder="What stands out about this player…"
            rows={6}
            maxLength={NOTE_MAX}
            aria-label={`Note for ${playerName}`}
            className="border-chalk/25 bg-transparent text-[15px] leading-relaxed text-chalk placeholder:text-[#8C9791]"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs tabular-nums text-muted-dark">{draft.length}/{NOTE_MAX}</span>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={quietLinkClass} disabled={saving} onClick={() => setEditing(false)}>Cancel</button>
              {entry.note ? (
                <button type="button" className={quietLinkClass} disabled={saving} onClick={() => save('')}>Clear</button>
              ) : null}
              <Button variant="on-dark" className="h-11 rounded-full px-5" disabled={saving} onClick={() => save(draft)}>
                {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                Save
              </Button>
            </div>
          </div>
          {error ? <p className="text-sm text-[#E9967A]" role="alert">{error}</p> : null}
        </>
      ) : (
        <>
          {entry.note ? (
            <p className="whitespace-pre-wrap font-serif text-[21px] leading-[1.3] text-chalk [overflow-wrap:anywhere]">{entry.note}</p>
          ) : (
            <p className="text-sm text-muted-dark">No note yet.</p>
          )}
          <div>
            <button type="button" className={quietLinkClass} onClick={startEditing} aria-label={`${entry.note ? 'Edit' : 'Add a'} note for ${playerName}`}>
              {entry.note ? 'Edit note' : 'Add a note'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

/** Where this scout's introduction to this player stands, with the one next step. */
function IntroductionBlock({ view, playerName, onAsk, children }) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5" data-testid="watchlist-introduction">
      {view ? (
        <>
          <p className={cn(labelClass, 'text-muted-dark')}>Introduction</p>
          <p className="flex items-center gap-2 text-base font-medium text-chalk">
            <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', TONE_DOT[view.tone])} aria-hidden="true" />
            {view.label}
          </p>
          <p className="text-[13px] leading-[1.4] text-muted-dark">{view.detail}</p>
        </>
      ) : null}
      <div className={cn('flex flex-wrap gap-2', view ? 'mt-1' : 'lg:justify-end')}>
        {view?.action?.kind === 'ask' ? (
          <button type="button" className={rowPillClass} onClick={onAsk} aria-label={`${view.action.label}: introduction to ${playerName}`}>
            {view.action.label}
          </button>
        ) : view?.action ? (
          <Link to={view.action.to} className={rowPillClass} aria-label={`${view.action.label}: ${playerName}`}>{view.action.label}</Link>
        ) : null}
        {children}
      </div>
    </div>
  )
}

function SeasonFigures({ player }) {
  const figures = deskFigures(player)
  if (figures.kind === 'withheld') return null
  if (figures.kind === 'none') return <p className="mt-1.5 text-[13px] text-muted-dark">{NO_MATCHES}</p>
  const items = [
    [figures.appearances.toLocaleString('en-GB'), figures.appearances === 1 ? 'app' : 'apps'],
    [figures.minutes.toLocaleString('en-GB'), 'min'],
    [String(figures.contributions), 'G+A'],
  ]
  if (figures.source === 'provider' && figures.rating != null) items.push([String(figures.rating), 'rating'])
  return (
    <>
      <p className="mt-1.5 flex flex-wrap gap-x-3.5 gap-y-1 text-sm text-chalk">
        {items.map(([value, unit]) => (
          <span key={unit}><span className="font-semibold tabular-nums">{value}</span> <span className="text-muted-dark">{unit}</span></span>
        ))}
      </p>
      {figures.sourceSentence ? <p className="text-[13px] text-muted-dark">{figures.sourceSentence}</p> : null}
    </>
  )
}

// Viewer change = fresh screen. The watchlist is the scout's own: who they
// watch, their private notes, where their introductions stand. It is keyed on
// the viewer, so on logout, login or an account switch React remounts it and
// none of that survives. Keep viewer-bound state inside WatchlistBody — never
// in this wrapper.
export function WatchlistPage() {
  const viewer = useViewerKey()
  return <WatchlistBody key={viewer} />
}

function WatchlistBody() {
  // Requests and side effects go through this viewer's lifetime (see lib/viewer-lifetime.js).
  const life = useViewerLifetime()
  const api = life.api
  const auth = useAuth()
  const viewer = useViewerKey()
  const contactRail = useContactRail()
  const openLoginModal = useGuarded(life, useAuthUI().openLoginModal)
  const saveCsv = useGuarded(life, saveWatchlistCsv)

  const [entries, setEntries] = useViewerState(viewer, NO_ENTRIES)
  const [introducePlayer, setIntroducePlayer] = useViewerState(viewer, null)
  const [loading, setLoading] = useState(Boolean(auth?.token))
  const [digestOptIn, setDigestOptIn] = useState(true)
  const [savingDigest, setSavingDigest] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState(null)
  const [verification, setVerification] = useState('loading')

  // `quiet` re-reads the list without the loading state (after an introduction is sent).
  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) {
      setLoading(true)
      setError(null)
    }
    try {
      const data = await api.getScoutWatchlist()
      setEntries(data?.entries || [])
      setDigestOptIn(data?.digest_opt_in !== false)
    } catch (err) {
      if (isStaleViewerError(err)) return
      console.error('Failed to load watchlist', err)
      if (!quiet) setError(err.message || 'The watchlist could not be loaded.')
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [api, setEntries])

  useEffect(() => {
    if (auth?.token) load()
  }, [auth?.token, load])

  // Asking for an introduction is for verified scouts (the server checks again).
  useEffect(() => {
    if (!auth?.token || contactRail !== true) return undefined
    let live = true
    api.getScoutVerification()
      .then((data) => { if (live) setVerification(data?.verification?.status === 'approved' ? 'approved' : 'unverified') })
      .catch(() => { if (live) setVerification('unavailable') })
    return () => { live = false }
  }, [api, auth?.token, contactRail])

  const handleDigestToggle = useCallback(async (checked) => {
    setDigestOptIn(checked)
    setSavingDigest(true)
    try {
      await api.updateScoutWatchlistSettings({ digest_opt_in: checked })
    } catch (err) {
      if (isStaleViewerError(err)) return
      console.error('Failed to update digest setting', err)
      setDigestOptIn(!checked)
    } finally {
      setSavingDigest(false)
    }
  }, [api])

  const handleRemove = useCallback((playerApiId) => {
    let removed = null
    let removedIndex = -1
    setEntries((current) => {
      removedIndex = current.findIndex((e) => e.player_api_id === playerApiId)
      removed = removedIndex >= 0 ? current[removedIndex] : null
      return current.filter((e) => e.player_api_id !== playerApiId)
    })
    api.removeFromScoutWatchlist(playerApiId).catch((err) => {
      if (isStaleViewerError(err)) return
      console.error('Failed to remove from watchlist', err)
      // Revert optimistic removal
      setEntries((current) => {
        if (!removed || current.some((e) => e.player_api_id === playerApiId)) return current
        const next = [...current]
        next.splice(Math.min(Math.max(removedIndex, 0), next.length), 0, removed)
        return next
      })
    })
  }, [api, setEntries])

  const handleNoteSaved = useCallback((updatedEntry) => {
    setEntries((current) => current.map((e) => (
      e.player_api_id === updatedEntry.player_api_id ? { ...e, ...updatedEntry, player: e.player } : e
    )))
  }, [setEntries])

  const handleExportCsv = useCallback(async () => {
    if (!entries.length) return
    setExporting(true)
    try {
      // The whole body is read and the viewer re-checked (life.api) before the guarded save.
      const blob = await api.fetchScoutCsv({ ids: entries.map((e) => e.player_api_id).join(',') })
      saveCsv(blob)
    } catch (err) {
      if (!isStaleViewerError(err)) console.error('CSV export failed', err)
    } finally {
      setExporting(false)
    }
  }, [api, entries, saveCsv])

  // Signed out
  if (!auth?.token) {
    return (
      <ScoutSurface>
        <div className="floodlight-container flex justify-center py-24">
          <div className="flex w-full max-w-md flex-col items-center gap-5 text-center">
            <span className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-gold/60">
              <Star className="h-6 w-6 text-gold" />
            </span>
            <h1 className="display text-4xl text-chalk sm:text-5xl">Sign in to build your watchlist</h1>
            <p className="text-[15px] leading-relaxed text-muted-dark">
              Watch players from the scout desk and keep your own notes on each of them in one place.
            </p>
            <Button variant="on-dark" onClick={openLoginModal}>Sign in</Button>
          </div>
        </div>
      </ScoutSurface>
    )
  }

  const count = entries.length
  return (
    <ScoutSurface>
      <div className="floodlight-container pb-24">
        <ScoutHeader
          eyebrow={`Watchlist${!loading && !error ? ` · ${count} player${count === 1 ? '' : 's'}` : ''}`}
          title="Players you’re"
          accent="watching"
          lede={contactRail === true
            ? 'Your notes first. Numbers when there are numbers. Where each introduction stands.'
            : 'Your notes first. Numbers when there are numbers.'}
          actions={(
            <>
              <label className="mr-1 flex h-11 items-center gap-2.5 text-sm text-chalk">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-gold"
                  checked={digestOptIn}
                  onChange={(e) => handleDigestToggle(e.target.checked)}
                  disabled={savingDigest}
                  aria-label="Weekly digest email"
                />
                Weekly digest
              </label>
              <Button variant="outline" size="sm" className={cn(deskPillClass, 'h-[46px] px-[18px] text-sm')} onClick={handleExportCsv} disabled={exporting || !count}>
                {exporting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                Export CSV
              </Button>
              <Button variant="on-dark" asChild className="h-[46px] rounded-full px-5 text-sm">
                <Link to="/scout" className="no-underline hover:no-underline">Find players</Link>
              </Button>
            </>
          )}
        />

        {error ? (
          <div className="flex flex-col items-start gap-3 border-t border-hairline-dark py-10" role="alert">
            <p className="text-[15px] text-[#E9967A]">{error}</p>
            <Button variant="outline" size="sm" className={cn(deskPillClass, 'h-11')} onClick={() => load()}>Try again</Button>
          </div>
        ) : loading ? (
          <ul className="flex flex-col gap-4" aria-busy="true" aria-label="Loading your watchlist" data-testid="watchlist-skeletons">
            {[0, 1, 2].map((i) => <li key={i} className="h-[162px] rounded-[22px] border border-hairline-dark bg-[#111514]" />)}
          </ul>
        ) : !count ? (
          <div className="flex flex-col items-center gap-5 border-t border-hairline-dark px-6 py-20 text-center">
            <span className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-gold/60">
              <Star className="h-6 w-6 text-gold" />
            </span>
            <h2 className="display text-4xl text-chalk">Nothing watched yet</h2>
            <p className="max-w-md text-[15px] leading-relaxed text-muted-dark">
              Press Watch on a player and they appear here with your notes{contactRail === true ? ', their numbers and where your introduction stands' : ' and their numbers'}.
            </p>
            <Button variant="on-dark" asChild className="h-11 rounded-full px-5">
              <Link to="/scout" className="no-underline hover:no-underline">Find players</Link>
            </Button>
          </div>
        ) : (
          <ul className="flex flex-col gap-4" aria-label="Watched players" data-testid="watchlist-rows">
            {entries.map((entry) => {
              const player = entry.player
              const playerName = player?.player_name || `Player ${entry.player_api_id}`
              const view = player && contactRail === true ? introductionView(entry.introduction, { verification }) : null
              const role = player ? watchRole(player) : ''
              const club = player ? watchClub(player) : ''
              return (
                <li
                  key={entry.player_api_id}
                  data-testid="watchlist-row"
                  className="grid grid-cols-[96px_minmax(0,1fr)] items-start gap-x-5 gap-y-6 rounded-[22px] border border-hairline-dark bg-[#111514] p-5 lg:grid-cols-[96px_minmax(0,1.25fr)_minmax(0,2.2fr)_minmax(0,1.1fr)] lg:gap-6"
                >
                  <PlayerTile name={player ? playerName : null} {...(player ? deskPhotos(player) : {})} />

                  <div className="flex min-w-0 flex-col gap-2">
                    {player ? (
                      <>
                        <Link to={`/players/${entry.player_api_id}`} className="font-serif text-[30px] leading-[1.02] text-chalk no-underline [overflow-wrap:anywhere] hover:text-gold hover:no-underline">
                          {playerName}
                        </Link>
                        {role ? <p className="text-sm text-[#C9C5BA]">{role}</p> : null}
                        {club ? <p className="text-sm text-[#C9C5BA] [overflow-wrap:anywhere]">{club}</p> : null}
                        <SeasonFigures player={player} />
                      </>
                    ) : (
                      <>
                        <p className="font-serif text-[30px] leading-[1.02] text-chalk [overflow-wrap:anywhere]">{playerName}</p>
                        <p className="text-sm text-muted-dark">No longer tracked</p>
                      </>
                    )}
                  </div>

                  <div className="col-span-2 min-w-0 lg:col-span-1">
                    <NoteBlock entry={entry} playerName={playerName} api={api} onSaved={handleNoteSaved} />
                  </div>

                  <div className="col-span-2 min-w-0 lg:col-span-1">
                    <IntroductionBlock
                      view={view}
                      playerName={playerName}
                      onAsk={() => setIntroducePlayer({ player_id: entry.player_api_id, player_name: playerName })}
                    >
                      <button
                        type="button"
                        onClick={() => handleRemove(entry.player_api_id)}
                        className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-chalk/25 text-chalk transition-colors hover:border-chalk/60 hover:bg-chalk/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label={`Stop watching ${playerName}`}
                        title="Stop watching"
                      >
                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </IntroductionBlock>
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        <IntroduceDialog
          open={!!introducePlayer}
          onOpenChange={(next) => { if (!next) setIntroducePlayer(null) }}
          player={introducePlayer}
          onSent={() => load({ quiet: true })}
        />
      </div>
    </ScoutSurface>
  )
}
