import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { Star, Download, StickyNote, X, Loader2, Search } from 'lucide-react'
import { FormIndicator, StatusBadge, PlayerCell } from './ScoutPage'

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
          className={`inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${entry.note ? 'text-primary' : 'text-muted-foreground/60 hover:text-muted-foreground'}`}
          aria-label={`Edit note for ${playerName}`}
          title={entry.note ? 'Edit note' : 'Add note'}
        >
          <StickyNote className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <div className="space-y-3">
          <p className="text-sm font-semibold text-foreground">Scouting note</p>
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

  // Signed out
  if (!auth?.token) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
        <div className="mx-auto flex max-w-7xl items-center justify-center px-4 py-24 sm:px-6 lg:px-8">
          <Card className="w-full max-w-md overflow-hidden border-border/80">
            <CardContent className="flex flex-col items-center gap-4 px-8 py-12 text-center">
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <Star className="h-6 w-6 text-primary" />
              </span>
              <h1 className="text-xl font-bold tracking-tight text-foreground">Sign in to build your watchlist</h1>
              <p className="text-sm text-muted-foreground">
                Star players across the Scout Desk and keep their form, stats and availability one click away.
              </p>
              <Button onClick={openLoginModal}>Sign in</Button>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <header className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="mb-2 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              <Star className="h-3.5 w-3.5" />
              Scout Pro — free during beta
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Your Watchlist
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
              Every player you are tracking, with live form, season output and your own scouting notes.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 lg:shrink-0 lg:pt-7">
            <label className="flex items-center gap-2 text-sm text-foreground/80">
              <Switch
                checked={digestOptIn}
                onCheckedChange={handleDigestToggle}
                disabled={savingDigest}
                aria-label="Weekly digest email"
              />
              Weekly digest
            </label>
            <Button variant="outline" size="sm" onClick={handleExportCsv} disabled={exporting || !entries.length}>
              {exporting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
              Export CSV
            </Button>
            <Button size="sm" asChild>
              <Link to="/scout" className="no-underline hover:no-underline">
                <Search className="mr-1.5 h-4 w-4" />
                Find players
              </Link>
            </Button>
          </div>
        </header>

        {error && (
          <p className="mb-4 text-sm text-destructive">{error}</p>
        )}

        {/* Empty state */}
        {!loading && !entries.length ? (
          <Card className="overflow-hidden border-border/80">
            <CardContent className="flex flex-col items-center gap-4 px-8 py-16 text-center">
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <Star className="h-6 w-6 text-primary" />
              </span>
              <h2 className="text-lg font-bold tracking-tight text-foreground">Nothing watched yet</h2>
              <p className="max-w-md text-sm text-muted-foreground">
                Star players on the Scout Desk and they&apos;ll show up here with live form, stats and availability.
              </p>
              <Button asChild>
                <Link to="/scout" className="no-underline hover:no-underline">Open the Scout Desk</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card className="overflow-hidden border-border/80">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse">
                <thead>
                  <tr className="border-b border-border/60 bg-secondary/60">
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Player</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pos</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Club</th>
                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Form</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Apps</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">G</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">A</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Mins</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rating</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">G+A/90</th>
                    <th className="w-20 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {loading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        <td colSpan={12} className="px-3 py-2.5"><Skeleton className="h-9 w-full" /></td>
                      </tr>
                    ))
                  ) : (
                    entries.map((entry) => {
                      const player = entry.player
                      const playerName = player?.player_name || `Player ${entry.player_api_id}`
                      return (
                        <tr key={entry.player_api_id} className="transition-colors hover:bg-secondary/40">
                          {player ? (
                            <>
                              <td className="px-3 py-2.5"><PlayerCell player={player} /></td>
                              <td className="px-3 py-2.5 text-sm text-foreground/80 whitespace-nowrap">{player.position?.slice(0, 3) || '—'}</td>
                              <td className="px-3 py-2.5"><StatusBadge status={player.status} /></td>
                              <td className="px-3 py-2.5 max-w-44">
                                <span className="block truncate text-sm text-foreground/90">{player.loan_team_name || player.primary_team_name || '—'}</span>
                                {player.loan_team_name && (player.owner_team_name || player.primary_team_name) && (
                                  <span className="block truncate text-xs text-muted-foreground">from {player.owner_team_name || player.primary_team_name}</span>
                                )}
                                {entry.note && (
                                  <span className="block max-w-44 truncate text-xs italic text-primary/80" title={entry.note}>
                                    “{entry.note}”
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-2.5"><FormIndicator form={player.recent_form} /></td>
                              <td className="px-3 py-2.5 text-right text-sm tabular-nums">{player.appearances}</td>
                              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums text-emerald-700">{player.goals}</td>
                              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums text-amber-700">{player.assists}</td>
                              <td className="px-3 py-2.5 text-right text-sm tabular-nums">{player.minutes_played?.toLocaleString()}</td>
                              <td className="px-3 py-2.5 text-right text-sm tabular-nums">{player.avg_rating ?? '—'}</td>
                              <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums text-primary">{player.contributions_per90 ?? '—'}</td>
                            </>
                          ) : (
                            <>
                              <td className="px-3 py-2.5">
                                <span className="block text-sm font-semibold text-foreground">{playerName}</span>
                                <span className="block text-xs text-muted-foreground">No longer tracked</span>
                                {entry.note && (
                                  <span className="block max-w-44 truncate text-xs italic text-primary/80" title={entry.note}>
                                    “{entry.note}”
                                  </span>
                                )}
                              </td>
                              <td colSpan={10} className="px-3 py-2.5 text-sm text-muted-foreground">—</td>
                            </>
                          )}
                          <td className="px-3 py-2.5">
                            <div className="flex items-center justify-end gap-1">
                              <NoteEditor entry={entry} onSaved={handleNoteSaved} />
                              <button
                                type="button"
                                onClick={() => handleRemove(entry.player_api_id)}
                                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground/60 transition-colors hover:bg-secondary hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
          </Card>
        )}
      </div>
    </div>
  )
}
