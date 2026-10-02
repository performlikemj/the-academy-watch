import { positionAbbreviation } from '@/lib/positions'
import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { Star, Download, StickyNote, X, Loader2, Search, ListChecks } from 'lucide-react'
import { FormIndicator, StatusBadge, PlayerCell } from './ScoutPage'
import { ScoutSurface, ScoutHeader, deskPillClass } from '@/components/scout/ScoutDesk'

const NOTE_MAX = 2000

function NoteEditor({ entry, onSaved }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(entry.note || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (open) {
      setDraft(entry.note || '')
      setError(null)
    }
  }, [open, entry.note])

  const save = async (value) => {
    setSaving(true)
    setError(null)
    try {
      const res = await APIService.updateScoutWatchlistNote(entry.player_api_id, value)
      onSaved(res?.entry || { ...entry, note: value.trim() || null })
      setOpen(false)
    } catch (err) {
      setError(err.message || 'Failed to save note')
    } finally {
      setSaving(false)
    }
  }

  const playerName = entry.player?.player_name || `Player ${entry.player_api_id}`

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${entry.note ? 'text-gold' : 'text-muted-foreground/60 hover:text-muted-foreground'}`}
          aria-label={`Edit note for ${playerName}`}
          title={entry.note ? 'Edit note' : 'Add note'}
        >
          <StickyNote className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 border-hairline-dark bg-ink">
        <div className="space-y-3">
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">My private note</p>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value.slice(0, NOTE_MAX))}
            placeholder="What stands out about this player…"
            rows={5}
            maxLength={NOTE_MAX}
            aria-label={`Note for ${playerName}`}
          />
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground tabular-nums">{draft.length}/{NOTE_MAX}</span>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" disabled={saving || !entry.note} onClick={() => save('')}>
                Clear
              </Button>
              <Button size="sm" disabled={saving} onClick={() => save(draft)}>
                {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                Save
              </Button>
            </div>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export function WatchlistPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()

  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [digestOptIn, setDigestOptIn] = useState(true)
  const [savingDigest, setSavingDigest] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!auth?.token) {
      setEntries([])
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    APIService.getScoutWatchlist()
      .then((data) => {
        if (cancelled) return
        setEntries(data?.entries || [])
        setDigestOptIn(data?.digest_opt_in !== false)
      })
      .catch((err) => {
        console.error('Failed to load watchlist', err)
        if (!cancelled) setError(err.message || 'Failed to load watchlist')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [auth?.token])

  const handleDigestToggle = useCallback(async (checked) => {
    setDigestOptIn(checked)
    setSavingDigest(true)
    try {
      await APIService.updateScoutWatchlistSettings({ digest_opt_in: checked })
    } catch (err) {
      console.error('Failed to update digest setting', err)
      setDigestOptIn(!checked)
    } finally {
      setSavingDigest(false)
    }
  }, [])

  const handleRemove = useCallback((playerApiId) => {
    let removed = null
    let removedIndex = -1
    setEntries((current) => {
      removedIndex = current.findIndex((e) => e.player_api_id === playerApiId)
      removed = removedIndex >= 0 ? current[removedIndex] : null
      return current.filter((e) => e.player_api_id !== playerApiId)
    })
    APIService.removeFromScoutWatchlist(playerApiId).catch((err) => {
      console.error('Failed to remove from watchlist', err)
      // Revert optimistic removal
      setEntries((current) => {
        if (!removed || current.some((e) => e.player_api_id === playerApiId)) return current
        const next = [...current]
        next.splice(Math.min(Math.max(removedIndex, 0), next.length), 0, removed)
        return next
      })
    })
  }, [])

  const handleNoteSaved = useCallback((updatedEntry) => {
    setEntries((current) => current.map((e) => (
      e.player_api_id === updatedEntry.player_api_id ? { ...e, ...updatedEntry, player: e.player } : e
    )))
  }, [])

  const handleExportCsv = useCallback(async () => {
    if (!entries.length) return
    setExporting(true)
    try {
      await APIService.downloadScoutCsv({ ids: entries.map((e) => e.player_api_id).join(',') })
    } catch (err) {
      console.error('CSV export failed', err)
    } finally {
      setExporting(false)
    }
  }, [entries])

  const thClass = 'px-3 py-3 font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-[#8C9791]'
  const tdNum = 'px-3 py-3.5 text-right font-mono text-[13px] tabular-nums text-chalk/85'

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
              Star players across the Scout Desk and keep their form, stats and availability one click away.
            </p>
            <Button variant="on-dark" onClick={openLoginModal}>Sign in</Button>
          </div>
        </div>
      </ScoutSurface>
    )
  }

  return (
    <ScoutSurface>
      <div className="floodlight-container pb-24">
        <ScoutHeader
          eyebrow={<span className="inline-flex items-center gap-2"><Star className="h-3.5 w-3.5" aria-hidden="true" />Watchlist{!loading ? ` · ${entries.length} player${entries.length === 1 ? '' : 's'}` : ''} · Scout Pro — free during beta</span>}
          title="Players you’re"
          accent="watching"
          lede="Every player you are tracking, with live form, season output and your own scouting notes."
          actions={(
            <>
              <label className="mr-2 flex items-center gap-3 text-sm text-[#C9CFCB]">
                Weekly digest
                <Switch
                  checked={digestOptIn}
                  onCheckedChange={handleDigestToggle}
                  disabled={savingDigest}
                  aria-label="Weekly digest email"
                />
              </label>
              <Button variant="outline" size="sm" className={deskPillClass} onClick={handleExportCsv} disabled={exporting || !entries.length}>
                {exporting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
                Export CSV
              </Button>
              <Button size="sm" variant="on-dark" asChild>
                <Link to="/scout" className="no-underline hover:no-underline">
                  <Search className="mr-1.5 h-4 w-4" />
                  Find players
                </Link>
              </Button>
            </>
          )}
        />

        {/* Lists cross-link */}
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-hairline-dark px-5 py-4">
          <span className="flex items-start gap-3 text-[14px] leading-relaxed text-[#C9CFCB]">
            <ListChecks className="mt-0.5 h-4 w-4 shrink-0 text-gold" aria-hidden="true" />
            <span>Your watchlist is now also a <span className="text-chalk">List</span> — manage richer follows (clubs, countries, saved filters) in Lists.</span>
          </span>
          <Link to="/scout/lists" className="shrink-0 border-b border-chalk/40 pb-px text-sm text-chalk no-underline hover:border-gold hover:no-underline">Open Lists</Link>
        </div>

        {error && (
          <p className="mb-4 text-sm text-destructive">{error}</p>
        )}

        {/* Empty state */}
        {!loading && !entries.length ? (
          <div className="flex flex-col items-center gap-5 border-t border-hairline-dark px-6 py-20 text-center">
            <span className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-gold/60">
              <Star className="h-6 w-6 text-gold" />
            </span>
            <h2 className="display text-4xl text-chalk">Nothing watched yet</h2>
            <p className="max-w-md text-[15px] leading-relaxed text-muted-dark">
              Star players on the Scout Desk and they&apos;ll show up here with live form, stats and availability.
            </p>
            <Button variant="on-dark" asChild>
              <Link to="/scout" className="no-underline hover:no-underline">Open the Scout Desk</Link>
            </Button>
          </div>
        ) : (
          <section aria-label="Watched players" className="border-t border-hairline-dark">
            <div className="relative overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse">
                <thead>
                  <tr className="border-b border-hairline-dark">
                    <th className={`text-left ${thClass}`}>Player</th>
                    <th className={`text-left ${thClass}`}>Pos</th>
                    <th className={`text-left ${thClass}`}>Status</th>
                    <th className={`text-left ${thClass}`}>Club</th>
                    <th className={`text-left ${thClass}`}>Form</th>
                    <th className={`text-right ${thClass}`}>Apps</th>
                    <th className={`text-right ${thClass}`}>G</th>
                    <th className={`text-right ${thClass}`}>A</th>
                    <th className={`text-right ${thClass}`}>Mins</th>
                    <th className={`text-right ${thClass}`}>Rating</th>
                    <th className={`text-right ${thClass}`}>G+A/90</th>
                    <th className={`w-20 text-right ${thClass}`}>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline-dark">
                  {loading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        <td colSpan={12} className="px-3 py-3"><Skeleton className="h-10 w-full" /></td>
                      </tr>
                    ))
                  ) : (
                    entries.map((entry) => {
                      const player = entry.player
                      const playerName = player?.player_name || `Player ${entry.player_api_id}`
                      return (
                        <tr key={entry.player_api_id} className="transition-colors duration-150 hover:bg-chalk/[0.035]">
                          {player ? (
                            <>
                              <td className="px-3 py-3.5"><PlayerCell player={player} /></td>
                              <td className="px-3 py-3.5 font-mono text-[12px] text-muted-dark whitespace-nowrap">{positionAbbreviation(player.position)}</td>
                              <td className="px-3 py-3.5"><StatusBadge status={player.status} /></td>
                              <td className="px-3 py-3.5 max-w-44">
                                <span className="block truncate text-sm text-chalk/90">{player.loan_team_name || player.primary_team_name || '—'}</span>
                                {player.loan_team_name && (player.owner_team_name || player.primary_team_name) && (
                                  <span className="block truncate text-xs text-muted-dark">from {player.owner_team_name || player.primary_team_name}</span>
                                )}
                                {entry.note && (
                                  <span className="block max-w-44 truncate font-serif text-[15px] italic text-gold/90" title={entry.note}>
                                    “{entry.note}”
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-3.5"><FormIndicator form={player.recent_form} /></td>
                              <td className={tdNum}>{player.appearances}</td>
                              <td className={tdNum}>{player.goals}</td>
                              <td className={tdNum}>{player.assists}</td>
                              <td className={tdNum}>{player.minutes_played?.toLocaleString()}</td>
                              <td className={tdNum}>{player.avg_rating ?? '—'}</td>
                              <td className={`${tdNum} text-gold`}>{player.contributions_per90 ?? '—'}</td>
                            </>
                          ) : (
                            <>
                              <td className="px-3 py-3.5">
                                <span className="block text-[14.5px] font-medium text-chalk">{playerName}</span>
                                <span className="block text-xs text-muted-dark">No longer tracked</span>
                                {entry.note && (
                                  <span className="block max-w-44 truncate font-serif text-[15px] italic text-gold/90" title={entry.note}>
                                    “{entry.note}”
                                  </span>
                                )}
                              </td>
                              <td colSpan={10} className="px-3 py-3.5 text-sm text-muted-dark">—</td>
                            </>
                          )}
                          <td className="px-3 py-3.5">
                            <div className="flex items-center justify-end gap-1">
                              <NoteEditor entry={entry} onSaved={handleNoteSaved} />
                              <button
                                type="button"
                                onClick={() => handleRemove(entry.player_api_id)}
                                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-dark/70 transition-colors hover:bg-chalk/[0.06] hover:text-[#E9967A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                aria-label={`Remove ${playerName} from watchlist`}
                                title="Remove from watchlist"
                              >
                                <X className="h-4 w-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </ScoutSurface>
  )
}
