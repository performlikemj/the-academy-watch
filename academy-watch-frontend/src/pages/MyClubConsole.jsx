import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  CalendarDays,
  Check,
  ChevronRight,
  CircleDot,
  Clock3,
  FileChartColumn,
  Film,
  Loader2,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Shirt,
  Trash2,
  Upload,
  Users,
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

const MAX_TIMELINE_SECONDS = 21600
const MATCH_INDEX_VERSION = 'v1'
const EDITABLE_MATCH_STATUSES = new Set(['created', 'uploaded'])
const MATCH_STATUS = {
  created: { label: 'Awaiting upload', className: 'border-sky-200 bg-sky-50 text-sky-800' },
  uploaded: { label: 'Uploaded', className: 'border-amber-200 bg-amber-50 text-amber-800' },
  preflight: { label: 'Preflight', className: 'border-violet-200 bg-violet-50 text-violet-800' },
  queued: { label: 'Queued', className: 'border-indigo-200 bg-indigo-50 text-indigo-800' },
  processing: { label: 'Processing', className: 'border-indigo-200 bg-indigo-50 text-indigo-800' },
  needs_tagging: { label: 'Admin review', className: 'border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800' },
  finalized: { label: 'Finalized', className: 'border-emerald-200 bg-emerald-50 text-emerald-800' },
  failed: { label: 'Failed', className: 'border-rose-200 bg-rose-50 text-rose-800' },
  expired: { label: 'Expired', className: 'border-stone-200 bg-stone-100 text-stone-700' },
}
const EMPTY_MATCH_FORM = {
  opponent_name: '',
  competition: '',
  our_kit_color: '',
  opponent_kit_color: '',
  match_date: '',
}
const MATCH_FORM_FIELDS = [
  'opponent_name',
  'competition',
  'our_kit_color',
  'opponent_kit_color',
  'match_date',
  'kickoff_s',
  'halftime_s',
  'second_half_kickoff_s',
  'duration_s',
]
const TIMELINE_FIELDS = ['kickoff_s', 'halftime_s', 'second_half_kickoff_s', 'duration_s']

function errorText(error, fallback) {
  return error?.body?.error || error?.message || fallback
}

function formatDate(value, includeTime = false) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString(undefined, includeTime
    ? { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatBytes(value) {
  if (!Number.isFinite(Number(value))) return 'the upload limit'
  const bytes = Number(value)
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  return `${Math.ceil(bytes / 1024 ** 2)} MB`
}

function formatSeconds(value) {
  if (value === null || value === '' || typeof value === 'undefined' || !Number.isFinite(Number(value))) return 'Not marked'
  const seconds = Math.round(Number(value))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

function matchIndexKey(programId) {
  return `club-console:matches:${MATCH_INDEX_VERSION}:${programId}`
}

function loadMatchIds(programId) {
  try {
    const value = JSON.parse(localStorage.getItem(matchIndexKey(programId)) || '[]')
    if (!Array.isArray(value)) return []
    return [...new Set(value.filter((id) => Number.isInteger(id) && id > 0))].slice(0, 100)
  } catch {
    return []
  }
}

function saveMatchIds(programId, ids) {
  try {
    localStorage.setItem(matchIndexKey(programId), JSON.stringify([...new Set(ids)].slice(0, 100)))
  } catch {
    // The console remains usable when storage is disabled; the local match index
    // simply cannot survive a reload because C2 exposes no list endpoint.
  }
}

function isSasFresh(grant) {
  if (!grant?.upload_url || !grant?.expires_at) return false
  const expiry = new Date(grant.expires_at).getTime()
  return Number.isFinite(expiry) && expiry > Date.now() + 60_000
}

function matchFormValues(match) {
  return {
    opponent_name: match.opponent_name || '',
    competition: match.competition || '',
    our_kit_color: match.our_kit_color || '',
    opponent_kit_color: match.opponent_kit_color || '',
    match_date: match.match_date || '',
    kickoff_s: match.kickoff_s ?? '',
    halftime_s: match.halftime_s ?? '',
    second_half_kickoff_s: match.second_half_kickoff_s ?? '',
    duration_s: match.duration_s ?? '',
  }
}

function matchRosterValues(match) {
  return Array.isArray(match.roster) ? match.roster.map((entry) => ({
    club_roster_member_id: entry.club_roster_member_id,
    jersey_number: String(entry.jersey_number),
  })).filter((entry) => entry.club_roster_member_id) : []
}

function timelinePayload(values, { dirtyFields } = {}) {
  const payload = {}
  for (const field of TIMELINE_FIELDS) {
    const raw = values[field]
    if (raw === '' || raw === null || typeof raw === 'undefined') {
      if (dirtyFields?.has(field)) payload[field] = null
      continue
    }
    const parsed = Number(raw)
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > MAX_TIMELINE_SECONDS) {
      throw new Error('Timeline values must be numbers from 0 to 21,600 seconds.')
    }
    payload[field] = parsed
  }
  return payload
}

function MatchStatusBadge({ status }) {
  const badge = MATCH_STATUS[status] || {
    label: status || 'Unknown',
    className: 'border-stone-200 bg-stone-100 text-stone-700',
  }
  return <Badge className={badge.className}>{badge.label}</Badge>
}

function InlineError({ children }) {
  return children ? <p className="text-sm text-destructive" role="alert">{children}</p> : null
}

function EmptyState({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border bg-secondary/20 px-6 py-12 text-center">
      <span className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-full bg-background text-muted-foreground shadow-sm ring-1 ring-border">
        <Icon className="h-5 w-5" />
      </span>
      <p className="font-semibold text-foreground">{title}</p>
      <p className="mt-1 max-w-md text-sm leading-relaxed text-muted-foreground">{children}</p>
    </div>
  )
}

function AddRosterMemberDialog({ open, onOpenChange, programId, onAdded, onAccessDenied }) {
  const [mode, setMode] = useState('tracked')
  const [query, setQuery] = useState('')
  const [searchState, setSearchState] = useState({ query: '', loading: false, results: [], error: null })
  const [selectedPlayer, setSelectedPlayer] = useState(null)
  const [localPlayerId, setLocalPlayerId] = useState('')
  const [role, setRole] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const reset = useCallback(() => {
    setMode('tracked')
    setQuery('')
    setSearchState({ query: '', loading: false, results: [], error: null })
    setSelectedPlayer(null)
    setLocalPlayerId('')
    setRole('')
    setNote('')
    setBusy(false)
    setError(null)
  }, [])

  useEffect(() => {
    if (!open || mode !== 'tracked') return undefined
    const trimmed = query.trim()
    if (trimmed.length < 2) return undefined
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setSearchState({ query: trimmed, loading: true, results: [], error: null })
      try {
        const response = await APIService.getScoutPlayers({ search: trimmed, per_page: 8, sort: 'name', order: 'asc' })
        if (!cancelled) {
          setSearchState({
            query: trimmed,
            loading: false,
            results: Array.isArray(response?.players) ? response.players : [],
            error: null,
          })
        }
      } catch {
        if (!cancelled) setSearchState({ query: trimmed, loading: false, results: [], error: 'Player search is unavailable. Try again.' })
      }
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [mode, open, query])

  const submit = async () => {
    if (busy) return
    let subjectPayload
    if (mode === 'tracked') {
      const playerId = selectedPlayer?.player_api_id ?? selectedPlayer?.player_id
      if (!Number.isInteger(Number(playerId)) || Number(playerId) <= 0) {
        setError('Search for and select a tracked player.')
        return
      }
      subjectPayload = { player_api_id: Number(playerId) }
    } else {
      const parsedId = Number(localPlayerId)
      if (!Number.isInteger(parsedId) || parsedId <= 0) {
        setError('Enter a valid local player ID.')
        return
      }
      subjectPayload = { local_player_id: parsedId }
    }

    setBusy(true)
    setError(null)
    try {
      const response = await APIService.addRosterMember(programId, {
        ...subjectPayload,
        role: role.trim() || undefined,
        note: note.trim() || undefined,
      })
      onAdded(response?.member)
      onOpenChange(false)
      reset()
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      if (requestError?.status === 409) {
        setError(requestError.body?.error || 'This player is already on the roster.')
      } else if (requestError?.status === 404) {
        setError('That player is not available to add. Check the player and try again.')
      } else {
        setError(errorText(requestError, 'Could not add this roster member.'))
      }
    } finally {
      setBusy(false)
    }
  }

  const activeResults = searchState.query === query.trim() ? searchState.results : []

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      if (busy) return
      onOpenChange(nextOpen)
      if (!nextOpen) reset()
    }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a roster member</DialogTitle>
          <DialogDescription>Roster membership is private and only scopes this club&apos;s match footage and reports.</DialogDescription>
        </DialogHeader>

        <Tabs value={mode} onValueChange={(value) => { setMode(value); setError(null) }}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="tracked">Tracked player</TabsTrigger>
            <TabsTrigger value="local">Local player ID</TabsTrigger>
          </TabsList>
          <TabsContent value="tracked" className="space-y-3 pt-2">
            <div className="space-y-2">
              <Label htmlFor="club-roster-player-search">Player name</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="club-roster-player-search"
                  value={query}
                  onChange={(event) => { setQuery(event.target.value); setSelectedPlayer(null); setError(null) }}
                  placeholder="Search tracked players"
                  className="pl-9"
                  autoComplete="off"
                />
                {searchState.loading && searchState.query === query.trim() ? (
                  <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-primary" />
                ) : null}
              </div>
            </div>
            {searchState.error && searchState.query === query.trim() ? <InlineError>{searchState.error}</InlineError> : null}
            {activeResults.length > 0 ? (
              <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-border p-1" role="listbox" aria-label="Tracked player results">
                {activeResults.map((player) => {
                  const playerId = player.player_api_id ?? player.player_id
                  const selected = Number(selectedPlayer?.player_api_id ?? selectedPlayer?.player_id) === Number(playerId)
                  return (
                    <button
                      key={playerId}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onClick={() => { setSelectedPlayer(player); setError(null) }}
                      className={`flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left transition-colors ${selected ? 'bg-primary/10 text-primary' : 'hover:bg-muted'}`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{player.player_name || player.name || `Player #${playerId}`}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {[player.position, player.loan_team_name || player.owner_team_name].filter(Boolean).join(' · ') || 'Tracked player'}
                        </span>
                      </span>
                      {selected ? <Check className="h-4 w-4 shrink-0" /> : null}
                    </button>
                  )
                })}
              </div>
            ) : null}
          </TabsContent>
          <TabsContent value="local" className="space-y-2 pt-2">
            <Label htmlFor="club-roster-local-id">Local player ID</Label>
            <Input
              id="club-roster-local-id"
              type="number"
              inputMode="numeric"
              min="1"
              step="1"
              value={localPlayerId}
              onChange={(event) => { setLocalPlayerId(event.target.value); setError(null) }}
              placeholder="e.g. 42"
            />
            <p className="text-xs leading-relaxed text-muted-foreground">
              Use the numeric ID of a local player profile you created. Private minors stay private in this console.
            </p>
          </TabsContent>
        </Tabs>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="club-roster-role">Squad role (optional)</Label>
            <Input id="club-roster-role" value={role} onChange={(event) => setRole(event.target.value)} maxLength={80} placeholder="e.g. U16 midfielder" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="club-roster-note">Private note (optional)</Label>
            <Input id="club-roster-note" value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} placeholder="Manager-only context" />
          </div>
        </div>
        <InlineError>{error}</InlineError>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plus className="mr-1.5 h-4 w-4" />}
            {busy ? 'Adding…' : 'Add to roster'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RosterPanel({ programId, members, loading, error, onMembersChange, onReload, onAccessDenied }) {
  const [addOpen, setAddOpen] = useState(false)
  const [removeTarget, setRemoveTarget] = useState(null)
  const [removing, setRemoving] = useState(false)
  const [removeError, setRemoveError] = useState(null)

  const removeMember = async () => {
    if (!removeTarget || removing) return
    setRemoving(true)
    setRemoveError(null)
    try {
      await APIService.removeRosterMember(programId, removeTarget.id)
      onMembersChange((current) => current.filter((member) => member.id !== removeTarget.id))
      setRemoveTarget(null)
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      setRemoveError(errorText(requestError, 'Could not remove this roster member.'))
    } finally {
      setRemoving(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden border-border/80">
        <CardHeader className="flex flex-row items-start justify-between gap-4 border-b border-border/60 bg-card">
          <div>
            <CardTitle className="flex items-center gap-2"><Users className="h-5 w-5 text-primary" /> Private roster</CardTitle>
            <CardDescription className="mt-1">The squad available for this club&apos;s match sheets and private reports.</CardDescription>
          </div>
          <Button onClick={() => setAddOpen(true)} size="sm"><Plus className="mr-1.5 h-4 w-4" /> Add member</Button>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading roster…</div>
          ) : error ? (
            <div className="space-y-3 p-6 text-center">
              <InlineError>{error}</InlineError>
              <Button variant="outline" size="sm" onClick={onReload}><RefreshCw className="mr-1.5 h-4 w-4" /> Try again</Button>
            </div>
          ) : members.length === 0 ? (
            <div className="p-6"><EmptyState icon={Shirt} title="Build your first private roster">Add tracked players or a local player profile created by your club.</EmptyState></div>
          ) : (
            <div className="divide-y divide-border/70">
              {members.map((member) => (
                <div key={member.id} className="flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-muted/35 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-semibold text-foreground">{member.available ? member.display_name : 'Unavailable roster member'}</p>
                      {member.is_minor ? <Badge className="border-amber-200 bg-amber-50 text-amber-900"><LockKeyhole className="mr-1 h-3 w-3" /> Minor — private</Badge> : null}
                      {!member.available ? <Badge variant="outline">Unavailable</Badge> : null}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {[member.position, member.role, member.subject_type === 'local' ? `Local player #${member.local_player_id}` : null].filter(Boolean).join(' · ') || 'Squad member'}
                    </p>
                    {member.note ? <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{member.note}</p> : null}
                  </div>
                  <Button variant="ghost" size="sm" className="shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => { setRemoveTarget(member); setRemoveError(null) }}>
                    <Trash2 className="mr-1.5 h-4 w-4" /> Remove
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Alert className="border-amber-200 bg-amber-50/70">
        <LockKeyhole className="h-4 w-4 text-amber-800" />
        <AlertDescription className="text-amber-950">Minor identities stay inside this manager-only console and are never linked to a public player page.</AlertDescription>
      </Alert>

      <AddRosterMemberDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        programId={programId}
        onAdded={(member) => { if (member) onMembersChange((current) => [...current, member]) }}
        onAccessDenied={onAccessDenied}
      />

      <AlertDialog open={Boolean(removeTarget)} onOpenChange={(open) => { if (!open && !removing) setRemoveTarget(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {removeTarget?.display_name || 'this member'}?</AlertDialogTitle>
            <AlertDialogDescription>This removes them from future match-sheet selection. Existing finalized report snapshots are not changed.</AlertDialogDescription>
          </AlertDialogHeader>
          <InlineError>{removeError}</InlineError>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removing}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={(event) => { event.preventDefault(); removeMember() }} disabled={removing} className="bg-destructive text-white hover:bg-destructive/90">
              {removing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Trash2 className="mr-1.5 h-4 w-4" />}
              Remove member
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function CreateMatchDialog({ open, onOpenChange, programId, onCreated, onAccessDenied }) {
  const [form, setForm] = useState(EMPTY_MATCH_FORM)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }))
  const close = () => {
    if (busy) return
    setForm(EMPTY_MATCH_FORM)
    setError(null)
    onOpenChange(false)
  }
  const submit = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value.trim() || undefined]))
      const response = await APIService.createClubMatch(programId, payload)
      onCreated(response)
      setForm(EMPTY_MATCH_FORM)
      onOpenChange(false)
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      if (requestError?.status === 429) {
        const quota = requestError.body?.quota
        setError(requestError.body?.error || `This club has reached its match quota${quota ? ` of ${quota}` : ''}.`)
      } else {
        setError(errorText(requestError, 'Could not create this match.'))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) close() }}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create a match workspace</DialogTitle>
          <DialogDescription>Add the match details now, then upload an MP4 and mark its timeline.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2 sm:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="new-match-opponent">Opponent</Label><Input id="new-match-opponent" value={form.opponent_name} onChange={(event) => update('opponent_name', event.target.value)} maxLength={200} placeholder="Opponent name" /></div>
          <div className="space-y-2"><Label htmlFor="new-match-competition">Competition</Label><Input id="new-match-competition" value={form.competition} onChange={(event) => update('competition', event.target.value)} maxLength={200} placeholder="League or tournament" /></div>
          <div className="space-y-2"><Label htmlFor="new-match-date">Match date</Label><Input id="new-match-date" type="date" value={form.match_date} onChange={(event) => update('match_date', event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="new-match-our-kit">Our kit color</Label><Input id="new-match-our-kit" value={form.our_kit_color} onChange={(event) => update('our_kit_color', event.target.value)} maxLength={50} placeholder="e.g. Red" /></div>
          <div className="space-y-2 sm:col-span-2"><Label htmlFor="new-match-opponent-kit">Opponent kit color</Label><Input id="new-match-opponent-kit" value={form.opponent_kit_color} onChange={(event) => update('opponent_kit_color', event.target.value)} maxLength={50} placeholder="e.g. Navy" /></div>
        </div>
        <InlineError>{error}</InlineError>
        <DialogFooter>
          <Button variant="ghost" onClick={close} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy}>{busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Film className="mr-1.5 h-4 w-4" />}{busy ? 'Creating…' : 'Create match'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MatchReport({ programId, match, onAccessDenied }) {
  const [state, setState] = useState({ loading: false, loaded: false, notFinalized: false, report: null, error: null })

  const load = async () => {
    if (state.loading) return
    setState((current) => ({ ...current, loading: true, error: null }))
    try {
      const report = await APIService.getClubMatchReport(programId, match.id)
      setState({ loading: false, loaded: true, notFinalized: false, report, error: null })
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      if (requestError?.status === 409) {
        setState({ loading: false, loaded: true, notFinalized: true, report: null, error: null })
      } else {
        setState({ loading: false, loaded: false, notFinalized: false, report: null, error: errorText(requestError, 'Could not load this report.') })
      }
    }
  }

  if (match.status !== 'finalized') {
    return <EmptyState icon={FileChartColumn} title="Report available once processing is finalized">An admin runs the GPU analysis, reviews identities and finalizes the private report.</EmptyState>
  }
  if (!state.loaded) {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5 text-center">
        <p className="font-semibold text-emerald-950">Your finalized report is ready</p>
        <Button className="mt-3" onClick={load} disabled={state.loading}>{state.loading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <FileChartColumn className="mr-1.5 h-4 w-4" />}View report</Button>
        <InlineError>{state.error}</InlineError>
      </div>
    )
  }
  if (state.notFinalized) {
    return <EmptyState icon={FileChartColumn} title="Report available once processing is finalized">An admin still needs to complete review and finalize this report.</EmptyState>
  }

  const reports = Array.isArray(state.report?.reports) ? state.report.reports : []
  return reports.length === 0 ? (
    <EmptyState icon={FileChartColumn} title="No player reports were published">The match is finalized, but no club-roster report rows are available.</EmptyState>
  ) : (
    <div className="space-y-3">
      {reports.map((report) => {
        const metrics = Array.isArray(report.metrics) ? report.metrics.filter((metric) => !metric?.suppressed) : []
        return (
          <article key={report.id} className="rounded-xl border border-border bg-card p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="font-bold text-foreground">#{report.jersey_number ?? '—'} {report.player_name || 'Roster player'}</h4>
                  {report.subject?.is_minor ? <Badge className="border-amber-200 bg-amber-50 text-amber-900"><LockKeyhole className="mr-1 h-3 w-3" /> Minor — private</Badge> : null}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Identity: {report.identity_confidence || 'Not stated'} · Model {report.model_version || '—'}</p>
              </div>
              <Badge variant="outline" className="tabular-nums">{Number(report.minutes_visible || 0).toFixed(1)} min visible</Badge>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">Distance</p><p className="mt-1 font-bold tabular-nums">{report.distance_m !== null && Number.isFinite(Number(report.distance_m)) ? `${Math.round(Number(report.distance_m))} m` : '—'}</p></div>
              <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">Top speed</p><p className="mt-1 font-bold tabular-nums">{report.fastest_sustained_kmh !== null && Number.isFinite(Number(report.fastest_sustained_kmh)) ? `${Number(report.fastest_sustained_kmh).toFixed(1)} km/h` : '—'}</p></div>
              <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">Sprints</p><p className="mt-1 font-bold tabular-nums">{report.sprint_count ?? '—'}</p></div>
              <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">Touches</p><p className="mt-1 font-bold tabular-nums">{report.touches ?? '—'}{report.touches_is_beta ? ' beta' : ''}</p></div>
            </div>
            {metrics.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {metrics.map((metric, index) => <Badge key={`${metric.key || 'metric'}-${index}`} variant="outline">{metric.key || 'Metric'}: {String(metric.value ?? '—')} {metric.unit || ''}</Badge>)}
              </div>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}

function MatchDetail({ programId, match, uploadGrant, rosterMembers, onMatchChange, onUploadGrantChange, onAccessDenied, onRefresh }) {
  const editable = EDITABLE_MATCH_STATUSES.has(match.status)
  const [form, setForm] = useState(() => matchFormValues(match))
  const dirtyFieldsRef = useRef(new Set())
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [processError, setProcessError] = useState(null)
  const [matchRoster, setMatchRoster] = useState(() => matchRosterValues(match))
  const rosterDirtyRef = useRef(false)
  const [rosterSaving, setRosterSaving] = useState(false)
  const [rosterError, setRosterError] = useState(null)

  const availableMembers = useMemo(() => rosterMembers.filter((member) => member.available), [rosterMembers])
  const selectedMemberIds = useMemo(() => new Set(matchRoster.map((entry) => entry.club_roster_member_id)), [matchRoster])
  const updateForm = (field, value) => {
    dirtyFieldsRef.current.add(field)
    setForm((current) => ({ ...current, [field]: value }))
  }

  useEffect(() => {
    const refreshedForm = matchFormValues(match)
    setForm((current) => Object.fromEntries(MATCH_FORM_FIELDS.map((field) => [
      field,
      dirtyFieldsRef.current.has(field) ? current[field] : refreshedForm[field],
    ])))
    const validMemberIds = new Set(rosterMembers.map((member) => member.id))
    setMatchRoster((current) => {
      const refreshedRoster = rosterDirtyRef.current ? current : matchRosterValues(match)
      return refreshedRoster.filter((entry) => validMemberIds.has(entry.club_roster_member_id))
    })
  }, [match, rosterMembers])

  const handleConsoleError = (requestError, fallback, setter) => {
    if (requestError?.status === 403) {
      onAccessDenied()
      return
    }
    setter(errorText(requestError, fallback))
  }

  const saveDetails = async () => {
    if (!editable || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      const payload = {
        opponent_name: form.opponent_name.trim() || null,
        competition: form.competition.trim() || null,
        our_kit_color: form.our_kit_color.trim() || null,
        opponent_kit_color: form.opponent_kit_color.trim() || null,
        match_date: form.match_date || null,
        ...timelinePayload(form, { dirtyFields: dirtyFieldsRef.current }),
      }
      const updated = await APIService.patchClubMatch(programId, match.id, payload)
      dirtyFieldsRef.current.clear()
      onMatchChange({ ...match, ...updated, roster: match.roster, processing_request_status: match.processing_request_status })
    } catch (requestError) {
      handleConsoleError(requestError, 'Could not save match details.', setSaveError)
    } finally {
      setSaving(false)
    }
  }

  const freshGrant = async () => {
    if (isSasFresh(uploadGrant)) return uploadGrant
    const grant = await APIService.mintMatchSas(programId, match.id)
    onUploadGrantChange(grant)
    return grant
  }

  const upload = async () => {
    if (!editable || !file || uploading) return
    setUploading(true)
    setUploadProgress(0)
    setUploadError(null)
    try {
      let grant = await freshGrant()
      if (Number.isFinite(Number(grant.max_bytes)) && file.size > Number(grant.max_bytes)) {
        throw new Error(`This file is ${formatBytes(file.size)}. The maximum is ${formatBytes(grant.max_bytes)}.`)
      }
      try {
        await APIService.uploadVideoToBlob(grant.upload_url, file, setUploadProgress)
      } catch (storageError) {
        if (storageError?.status !== 403) throw storageError
        grant = await APIService.mintMatchSas(programId, match.id)
        onUploadGrantChange(grant)
        if (Number.isFinite(Number(grant.max_bytes)) && file.size > Number(grant.max_bytes)) {
          throw new Error(`This file is ${formatBytes(file.size)}. The maximum is ${formatBytes(grant.max_bytes)}.`, { cause: storageError })
        }
        await APIService.uploadVideoToBlob(grant.upload_url, file, setUploadProgress)
      }
      const completed = await APIService.completeMatchUpload(programId, match.id, timelinePayload(form))
      onMatchChange({ ...match, ...completed, roster: match.roster, processing_request_status: null })
      setUploadProgress(100)
      setFile(null)
    } catch (requestError) {
      if (requestError?.status === 403 && requestError?.body) {
        onAccessDenied()
      } else if (requestError?.status === 422) {
        setUploadError(requestError.body?.error || 'The uploaded blob is missing or exceeds the server limit.')
      } else {
        setUploadError(errorText(requestError, 'Could not upload this video.'))
      }
    } finally {
      setUploading(false)
    }
  }

  const toggleRosterMember = (memberId, checked) => {
    setRosterError(null)
    rosterDirtyRef.current = true
    setMatchRoster((current) => checked
      ? [...current, { club_roster_member_id: memberId, jersey_number: '' }]
      : current.filter((entry) => entry.club_roster_member_id !== memberId))
  }
  const setJersey = (memberId, value) => {
    rosterDirtyRef.current = true
    setMatchRoster((current) => current.map((entry) => entry.club_roster_member_id === memberId ? { ...entry, jersey_number: value } : entry))
  }

  const saveRoster = async () => {
    if (!editable || rosterSaving) return
    if (matchRoster.length === 0) {
      setRosterError('Select at least one roster member.')
      return
    }
    const entries = matchRoster.map((entry) => ({
      club_roster_member_id: entry.club_roster_member_id,
      jersey_number: Number(entry.jersey_number),
    }))
    const invalid = entries.some((entry) => !Number.isInteger(entry.jersey_number) || entry.jersey_number < 1 || entry.jersey_number > 99)
    const numbers = entries.map((entry) => entry.jersey_number)
    if (invalid || new Set(numbers).size !== numbers.length) {
      setRosterError('Every selected player needs a unique jersey number from 1 to 99.')
      return
    }
    setRosterSaving(true)
    setRosterError(null)
    try {
      const response = await APIService.setMatchRoster(programId, match.id, entries)
      rosterDirtyRef.current = false
      onMatchChange({ ...match, roster: Array.isArray(response?.roster) ? response.roster : [] })
    } catch (requestError) {
      handleConsoleError(requestError, 'Could not save the match roster.', setRosterError)
    } finally {
      setRosterSaving(false)
    }
  }

  const refreshMatch = async () => {
    if (refreshing) return
    setRefreshing(true)
    setRefreshError(null)
    try {
      await onRefresh()
    } catch (requestError) {
      setRefreshError(errorText(requestError, 'Could not refresh this match.'))
    } finally {
      setRefreshing(false)
    }
  }

  const requestProcessing = async () => {
    if (match.status !== 'uploaded' || match.kickoff_s === null || typeof match.kickoff_s === 'undefined' || processing) return
    setProcessing(true)
    setProcessError(null)
    try {
      const response = await APIService.requestMatchProcessing(programId, match.id)
      onMatchChange({ ...match, ...(response?.match || {}), roster: match.roster, processing_request_status: response?.processing_request_status || 'requested' })
    } catch (requestError) {
      handleConsoleError(requestError, 'Could not queue this processing request.', setProcessError)
    } finally {
      setProcessing(false)
    }
  }

  return (
    <Card className="overflow-hidden border-border/80 shadow-sm">
      <CardHeader className="border-b border-border/60 bg-slate-950 text-white">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-300">Match #{match.id}</p>
            <CardTitle className="mt-1 text-xl text-white">vs {match.opponent_name || 'Opponent TBD'}</CardTitle>
            <CardDescription className="mt-1 text-slate-300">{[match.competition, formatDate(match.match_date)].filter(Boolean).join(' · ') || 'Add match details below'}</CardDescription>
          </div>
          <MatchStatusBadge status={match.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-6 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-secondary/30 px-4 py-3">
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
            <span><Clock3 className="mr-1 inline h-3.5 w-3.5" /> Kickoff {formatSeconds(match.kickoff_s)}</span>
            <span><Users className="mr-1 inline h-3.5 w-3.5" /> {Array.isArray(match.roster) ? match.roster.length : 0} selected</span>
            <span><CircleDot className="mr-1 inline h-3.5 w-3.5" /> {match.processing_request_status === 'requested' ? 'Processing requested' : 'Not queued'}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={refreshMatch} disabled={refreshing}>{refreshing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1.5 h-4 w-4" />} Refresh</Button>
        </div>
        {refreshError ? <Alert className="border-amber-200 bg-amber-50"><AlertCircle className="h-4 w-4 text-amber-800" /><AlertDescription className="flex flex-wrap items-center gap-1 text-amber-950">{refreshError} <Button variant="link" className="h-auto p-0 text-amber-950 underline" onClick={refreshMatch}>Retry</Button></AlertDescription></Alert> : null}

        <section className="space-y-3" aria-labelledby={`match-${match.id}-details`}>
          <div><h3 id={`match-${match.id}-details`} className="font-bold text-foreground">Match details &amp; timeline</h3><p className="text-sm text-muted-foreground">Timeline values are raw seconds from the start of the video.</p></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label htmlFor={`opponent-${match.id}`}>Opponent</Label><Input id={`opponent-${match.id}`} value={form.opponent_name} onChange={(event) => updateForm('opponent_name', event.target.value)} disabled={!editable} maxLength={200} /></div>
            <div className="space-y-1.5"><Label htmlFor={`competition-${match.id}`}>Competition</Label><Input id={`competition-${match.id}`} value={form.competition} onChange={(event) => updateForm('competition', event.target.value)} disabled={!editable} maxLength={200} /></div>
            <div className="space-y-1.5"><Label htmlFor={`date-${match.id}`}>Match date</Label><Input id={`date-${match.id}`} type="date" value={form.match_date} onChange={(event) => updateForm('match_date', event.target.value)} disabled={!editable} /></div>
            <div className="space-y-1.5"><Label htmlFor={`our-kit-${match.id}`}>Our kit color</Label><Input id={`our-kit-${match.id}`} value={form.our_kit_color} onChange={(event) => updateForm('our_kit_color', event.target.value)} disabled={!editable} maxLength={50} /></div>
            <div className="space-y-1.5 sm:col-span-2"><Label htmlFor={`their-kit-${match.id}`}>Opponent kit color</Label><Input id={`their-kit-${match.id}`} value={form.opponent_kit_color} onChange={(event) => updateForm('opponent_kit_color', event.target.value)} disabled={!editable} maxLength={50} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ['kickoff_s', 'Kickoff'],
              ['halftime_s', 'Halftime'],
              ['second_half_kickoff_s', 'Second half'],
              ['duration_s', 'Duration'],
            ].map(([field, label]) => (
              <div key={field} className="space-y-1.5">
                <Label htmlFor={`${field}-${match.id}`}>{label} (s)</Label>
                <Input id={`${field}-${match.id}`} type="number" inputMode="decimal" min="0" max={MAX_TIMELINE_SECONDS} step="0.1" value={form[field]} onChange={(event) => updateForm(field, event.target.value)} disabled={!editable} placeholder="0" />
              </div>
            ))}
          </div>
          <InlineError>{saveError}</InlineError>
          {editable ? <Button variant="outline" onClick={saveDetails} disabled={saving}>{saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Check className="mr-1.5 h-4 w-4" />}{saving ? 'Saving…' : 'Save details'}</Button> : null}
        </section>

        {editable ? (
          <section className="space-y-3 border-t border-border pt-5" aria-labelledby={`match-${match.id}-upload`}>
            <div><h3 id={`match-${match.id}-upload`} className="font-bold text-foreground">Match video</h3><p className="text-sm text-muted-foreground">MP4 uploads go directly to private blob storage. The server verifies the blob afterward.</p></div>
            <Input type="file" accept="video/mp4,.mp4" onChange={(event) => { setFile(event.target.files?.[0] || null); setUploadError(null); setUploadProgress(0) }} disabled={uploading} aria-label="Choose match MP4" />
            {file ? <p className="text-xs text-muted-foreground">{file.name} · {formatBytes(file.size)}</p> : null}
            {uploading || uploadProgress > 0 ? <div className="space-y-1.5"><div className="flex justify-between text-xs text-muted-foreground"><span>{uploading ? 'Uploading to private storage…' : 'Upload complete'}</span><span>{uploadProgress}%</span></div><Progress value={uploadProgress} /></div> : null}
            <InlineError>{uploadError}</InlineError>
            <Button onClick={upload} disabled={!file || uploading}>{uploading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Upload className="mr-1.5 h-4 w-4" />}{uploading ? `Uploading ${uploadProgress}%` : match.status === 'uploaded' ? 'Replace MP4' : 'Upload MP4'}</Button>
          </section>
        ) : null}

        <section className="space-y-3 border-t border-border pt-5" aria-labelledby={`match-${match.id}-roster`}>
          <div><h3 id={`match-${match.id}-roster`} className="font-bold text-foreground">Match roster</h3><p className="text-sm text-muted-foreground">Select players from this club&apos;s private roster and assign unique shirt numbers.</p></div>
          {availableMembers.length === 0 ? (
            <EmptyState icon={Users} title="No available club roster members">Add players in the Roster tab before building this match sheet.</EmptyState>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {availableMembers.map((member) => {
                const selected = selectedMemberIds.has(member.id)
                const entry = matchRoster.find((row) => row.club_roster_member_id === member.id)
                return (
                  <div key={member.id} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 ${selected ? 'border-primary/30 bg-primary/5' : 'border-border'}`}>
                    <input type="checkbox" checked={selected} onChange={(event) => toggleRosterMember(member.id, event.target.checked)} disabled={!editable} aria-label={`Select ${member.display_name}`} className="h-4 w-4 accent-primary" />
                    <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{member.display_name}</p><p className="truncate text-xs text-muted-foreground">{member.position || member.role || 'Squad member'}{member.is_minor ? ' · Minor — private' : ''}</p></div>
                    {selected ? <Input type="number" inputMode="numeric" min="1" max="99" step="1" value={entry?.jersey_number || ''} onChange={(event) => setJersey(member.id, event.target.value)} disabled={!editable} placeholder="#" aria-label={`Jersey number for ${member.display_name}`} className="w-16" /> : null}
                  </div>
                )
              })}
            </div>
          )}
          <InlineError>{rosterError}</InlineError>
          {editable ? <Button variant="outline" onClick={saveRoster} disabled={rosterSaving || availableMembers.length === 0}>{rosterSaving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Shirt className="mr-1.5 h-4 w-4" />}{rosterSaving ? 'Saving…' : 'Save match roster'}</Button> : null}
        </section>

        <section className="space-y-3 border-t border-border pt-5" aria-labelledby={`match-${match.id}-processing`}>
          <div><h3 id={`match-${match.id}-processing`} className="font-bold text-foreground">Processing</h3><p className="text-sm text-muted-foreground">Your request only queues the work. An admin runs the GPU pipeline, reviews identities and finalizes the result.</p></div>
          {match.processing_request_status === 'requested' ? <Alert className="border-indigo-200 bg-indigo-50"><Clock3 className="h-4 w-4 text-indigo-700" /><AlertDescription className="text-indigo-950">Processing requested. Refresh this match later to see its admin-run status.</AlertDescription></Alert> : null}
          {match.status === 'uploaded' && (match.kickoff_s === null || typeof match.kickoff_s === 'undefined') ? <p className="text-sm text-amber-800">Mark and save kickoff before requesting processing.</p> : null}
          {match.job ? <p className="rounded-lg bg-secondary/60 px-3 py-2 text-sm text-muted-foreground">Admin job: {match.job.status || 'unknown'}{match.job.stage ? ` · ${match.job.stage}` : ''}{Number.isFinite(Number(match.job.progress)) ? ` · ${match.job.progress}%` : ''}</p> : null}
          <InlineError>{processError}</InlineError>
          {match.status === 'uploaded' ? (
            <Button onClick={requestProcessing} disabled={processing || match.kickoff_s === null || typeof match.kickoff_s === 'undefined' || match.processing_request_status === 'requested'}>
              {processing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <CircleDot className="mr-1.5 h-4 w-4" />}
              {match.processing_request_status === 'requested' ? 'Processing requested' : processing ? 'Queuing…' : 'Request processing'}
            </Button>
          ) : null}
        </section>

        <section className="space-y-3 border-t border-border pt-5" aria-labelledby={`match-${match.id}-report`}>
          <div><h3 id={`match-${match.id}-report`} className="font-bold text-foreground">Private player report</h3><p className="text-sm text-muted-foreground">Only reports scoped to this club program are shown here.</p></div>
          <MatchReport programId={programId} match={match} onAccessDenied={onAccessDenied} />
        </section>
      </CardContent>
    </Card>
  )
}

function MatchesPanel({ programId, rosterMembers, matches, loading, error, loadFailureCount, uploadGrants, onMatchesChange, onUploadGrantChange, onReload, onAccessDenied }) {
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedId, setSelectedId] = useState(() => matches[0]?.id || null)
  const selectedMatch = matches.find((match) => match.id === selectedId) || matches[0] || null

  const upsertMatch = useCallback((updated) => {
    onMatchesChange((current) => {
      const exists = current.some((match) => match.id === updated.id)
      return exists ? current.map((match) => match.id === updated.id ? updated : match) : [updated, ...current]
    })
  }, [onMatchesChange])

  const created = (response) => {
    if (!response?.id) return
    const { upload: grant, ...match } = response
    upsertMatch({ ...match, roster: [], processing_request_status: null })
    if (grant) onUploadGrantChange(match.id, grant)
    const ids = [match.id, ...loadMatchIds(programId).filter((id) => id !== match.id)]
    saveMatchIds(programId, ids)
    setSelectedId(match.id)
  }

  const refreshSelected = async () => {
    if (!selectedMatch) return
    try {
      const updated = await APIService.getClubMatch(programId, selectedMatch.id)
      upsertMatch(updated)
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      throw requestError
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 className="text-xl font-bold tracking-tight text-foreground">Matches &amp; reports</h2><p className="mt-1 text-sm text-muted-foreground">Create, upload and queue private match analysis.</p></div>
        <Button onClick={() => setCreateOpen(true)}><Plus className="mr-1.5 h-4 w-4" /> Create match</Button>
      </div>
      {loadFailureCount > 0 ? (
        <Alert className="border-amber-200 bg-amber-50">
          <AlertCircle className="h-4 w-4 text-amber-800" />
          <AlertDescription className="flex flex-wrap items-center gap-1 text-amber-950">
            {loadFailureCount} saved {loadFailureCount === 1 ? 'match' : 'matches'} could not be loaded —
            <Button variant="link" className="h-auto p-0 text-amber-950 underline" onClick={onReload}>Retry</Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {loading ? (
        <Card><CardContent className="flex items-center justify-center py-16 text-sm text-muted-foreground"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading saved matches…</CardContent></Card>
      ) : error ? (
        <Card><CardContent className="space-y-3 py-10 text-center"><InlineError>{error}</InlineError><Button variant="outline" onClick={onReload}><RefreshCw className="mr-1.5 h-4 w-4" /> Try again</Button></CardContent></Card>
      ) : matches.length === 0 ? (
        <EmptyState icon={Film} title="No matches in this browser yet">Create the first match workspace. Until a backend list endpoint exists, this browser remembers the match IDs it creates.</EmptyState>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="space-y-2 lg:sticky lg:top-20">
            {matches.map((match) => {
              const selected = selectedMatch?.id === match.id
              return (
                <button key={match.id} type="button" onClick={() => setSelectedId(match.id)} className={`w-full rounded-xl border p-4 text-left transition-all ${selected ? 'border-primary/40 bg-primary/5 shadow-sm' : 'border-border bg-card hover:border-primary/25 hover:bg-muted/30'}`}>
                  <div className="flex items-start justify-between gap-3"><p className="truncate font-bold text-foreground">vs {match.opponent_name || 'Opponent TBD'}</p><ChevronRight className={`h-4 w-4 shrink-0 ${selected ? 'text-primary' : 'text-muted-foreground'}`} /></div>
                  <p className="mt-1 truncate text-xs text-muted-foreground">{[match.competition, formatDate(match.match_date)].filter(Boolean).join(' · ') || `Match #${match.id}`}</p>
                  <div className="mt-3"><MatchStatusBadge status={match.status} /></div>
                </button>
              )
            })}
          </div>
          {selectedMatch ? (
            <MatchDetail
              key={selectedMatch.id}
              programId={programId}
              match={selectedMatch}
              uploadGrant={uploadGrants[selectedMatch.id]}
              rosterMembers={rosterMembers}
              onMatchChange={upsertMatch}
              onUploadGrantChange={(grant) => onUploadGrantChange(selectedMatch.id, grant)}
              onAccessDenied={onAccessDenied}
              onRefresh={refreshSelected}
            />
          ) : null}
        </div>
      )}
      <CreateMatchDialog open={createOpen} onOpenChange={setCreateOpen} programId={programId} onCreated={created} onAccessDenied={onAccessDenied} />
    </div>
  )
}

function ClubProfile({ program, claim }) {
  const location = [program.city, program.region, program.country].filter(Boolean).join(', ')
  return (
    <Card className="overflow-hidden border-border/80">
      <CardHeader className="border-b border-border/60 bg-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          {program.crest_url ? <img src={program.crest_url} alt="" className="h-16 w-16 rounded-xl border border-border bg-white object-contain p-2" /> : <span className="inline-flex h-16 w-16 items-center justify-center rounded-xl bg-primary/10 text-primary"><ShieldCheck className="h-7 w-7" /></span>}
          <div><CardTitle className="text-2xl">{program.name || 'Verified club program'}</CardTitle><CardDescription className="mt-1">Read-only verified program record</CardDescription></div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ['Program ID', program.id],
          ['Program status', program.platform_status],
          ['Manager claim', claim?.status],
          ['Location', location],
          ['League', program.league?.name],
          ['Age groups', Array.isArray(program.league?.age_bands) ? program.league.age_bands.join(', ') : null],
          ['Data tier', program.league?.data_tier],
          ['Provenance', program.provenance?.label],
          ['Verified', formatDate(program.verified_at)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-secondary/25 p-4"><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p><p className="mt-1.5 font-semibold capitalize text-foreground">{value || '—'}</p></div>
        ))}
      </CardContent>
    </Card>
  )
}

export function MyClubConsole({ programClaim, initialRoster, programOptions, onProgramChange, onAccessDenied }) {
  const program = programClaim.program
  const programId = program.id
  const [members, setMembers] = useState(() => (Array.isArray(initialRoster?.members) ? initialRoster.members : []))
  const [rosterLoading, setRosterLoading] = useState(false)
  const [rosterError, setRosterError] = useState(null)
  const [matches, setMatches] = useState([])
  const [matchesLoading, setMatchesLoading] = useState(true)
  const [matchesError, setMatchesError] = useState(null)
  const [matchesLoadFailureCount, setMatchesLoadFailureCount] = useState(0)
  const [uploadGrants, setUploadGrants] = useState({})
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const loadRoster = useCallback(async () => {
    setRosterLoading(true)
    setRosterError(null)
    try {
      const response = await APIService.getClubRoster(programId)
      if (mountedRef.current) setMembers(Array.isArray(response?.members) ? response.members : [])
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      if (mountedRef.current) setRosterError(errorText(requestError, 'Could not load the club roster.'))
    } finally {
      if (mountedRef.current) setRosterLoading(false)
    }
  }, [onAccessDenied, programId])

  const loadMatches = useCallback(async () => {
    setMatchesLoading(true)
    setMatchesError(null)
    setMatchesLoadFailureCount(0)
    const ids = loadMatchIds(programId)
    if (ids.length === 0) {
      setMatches([])
      setMatchesLoading(false)
      return
    }
    const results = await Promise.allSettled(ids.map((id) => APIService.getClubMatch(programId, id)))
    if (!mountedRef.current) return
    const denied = results.some((result) => result.status === 'rejected' && result.reason?.status === 403)
    if (denied) {
      onAccessDenied()
      return
    }
    const loaded = results.flatMap((result) => result.status === 'fulfilled' ? [result.value] : [])
    const retainedIds = results.flatMap((result, index) => result.status === 'fulfilled' || result.reason?.status !== 404 ? [ids[index]] : [])
    const failureCount = results.filter((result) => result.status === 'rejected' && result.reason?.status !== 404).length
    saveMatchIds(programId, retainedIds)
    setMatches(loaded)
    setMatchesLoadFailureCount(failureCount)
    if (loaded.length === 0 && results.some((result) => result.status === 'rejected' && result.reason?.status !== 404)) {
      setMatchesError('Saved match details could not be loaded. Try again.')
    }
    setMatchesLoading(false)
  }, [onAccessDenied, programId])

  useEffect(() => {
    const timer = setTimeout(() => {
      loadMatches()
    }, 0)
    return () => clearTimeout(timer)
  }, [loadMatches])

  const setGrant = useCallback((matchId, grant) => setUploadGrants((current) => ({ ...current, [matchId]: grant })), [])

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-100 via-background to-secondary/50">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <header className="relative overflow-hidden rounded-2xl bg-slate-950 px-6 py-7 text-white shadow-xl sm:px-8 sm:py-9">
          <div className="pointer-events-none absolute -right-20 -top-28 h-72 w-72 rounded-full border-[42px] border-amber-300/10" />
          <div className="pointer-events-none absolute -bottom-20 right-24 h-48 w-48 rounded-full border border-white/10" />
          <div className="relative flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-amber-300"><ShieldCheck className="h-4 w-4" /> Verified manager console</p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">{program.name}</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-300">Run your private squad and match-analysis workflow from upload through finalized player reports.</p>
            </div>
            <div className="flex w-full flex-col items-start gap-3 sm:w-auto sm:items-end">
              <Badge className="w-fit border-emerald-300/30 bg-emerald-300/10 px-3 py-1.5 text-emerald-200"><CircleDot className="mr-1.5 h-3.5 w-3.5" /> Program active</Badge>
              {programOptions.length > 1 ? (
                <Select value={String(programId)} onValueChange={(value) => onProgramChange(Number(value))}>
                  <SelectTrigger className="w-full border-white/20 bg-white/10 text-white sm:w-64" aria-label="Switch club program">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {programOptions.map((option) => <SelectItem key={option.program.id} value={String(option.program.id)}>{option.program.name || `Program #${option.program.id}`}</SelectItem>)}
                  </SelectContent>
                </Select>
              ) : null}
            </div>
          </div>
        </header>

        <Tabs defaultValue="roster" className="gap-5">
          <TabsList className="grid h-auto w-full grid-cols-3 bg-slate-200/70 p-1 sm:w-fit sm:min-w-[32rem]">
            <TabsTrigger value="roster" className="py-2"><Users className="h-4 w-4" /> Roster</TabsTrigger>
            <TabsTrigger value="matches" className="py-2"><Film className="h-4 w-4" /> Matches &amp; reports</TabsTrigger>
            <TabsTrigger value="profile" className="py-2"><ShieldCheck className="h-4 w-4" /> Club profile</TabsTrigger>
          </TabsList>
          <TabsContent value="roster">
            <RosterPanel programId={programId} members={members} loading={rosterLoading} error={rosterError} onMembersChange={setMembers} onReload={loadRoster} onAccessDenied={onAccessDenied} />
          </TabsContent>
          <TabsContent value="matches">
            <MatchesPanel programId={programId} rosterMembers={members} matches={matches} loading={matchesLoading} error={matchesError} loadFailureCount={matchesLoadFailureCount} uploadGrants={uploadGrants} onMatchesChange={setMatches} onUploadGrantChange={setGrant} onReload={loadMatches} onAccessDenied={onAccessDenied} />
          </TabsContent>
          <TabsContent value="profile"><ClubProfile program={program} claim={programClaim} /></TabsContent>
        </Tabs>

        <p className="flex items-center justify-center gap-2 text-center text-xs text-muted-foreground"><LockKeyhole className="h-3.5 w-3.5" /> Club-console data is manager-only. Opposition players remain anonymous.</p>
      </div>
    </div>
  )
}

export default MyClubConsole
