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
  Send,
  ShieldCheck,
  Shirt,
  Trash2,
  Trophy,
  Upload,
  Users,
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { ClubIntroductionsPanel } from '@/components/contact/ClubIntroductionsPanel'
import { PlayerReels } from '@/components/video/PlayerReel'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { track } from '@/lib/track'
import { useContactRail } from '@/hooks/useContactRail.js'
import { formatDateOnly } from '@/lib/dateOnly'
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
const MAX_MATCH_MINUTES = 130
const MAX_MATCH_COUNT = 20
const MAX_RESULT_TEXT_LENGTH = 120
const MAX_RESULT_NOTE_LENGTH = 500
const MAX_BRIEF_CHARS = 2000
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
  camera_view: '',
  camera_motion: '',
  pitch_lines_visible: '',
}
const EMPTY_RESULT_FORM = {
  match_date: '',
  opponent: '',
  competition: '',
  home_away: 'home',
  result_for: '',
  result_against: '',
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
  'camera_view',
  'camera_motion',
  'pitch_lines_visible',
]
const PREFLIGHT_FIELDS = ['camera_view', 'camera_motion', 'pitch_lines_visible']
const PREFLIGHT_OPTIONS = {
  camera_view: [['panoramic', 'Panoramic'], ['wide_fixed', 'Wide fixed'], ['broadcast', 'Broadcast']],
  camera_motion: [['fixed', 'Fixed'], ['panning', 'Panning'], ['handheld', 'Handheld']],
  pitch_lines_visible: [['all', 'All'], ['partial', 'Partial'], ['none', 'None']],
}
const TIMELINE_FIELDS = ['kickoff_s', 'halftime_s', 'second_half_kickoff_s', 'duration_s']
const REEL_MATCH_STATUSES = new Set(['needs_tagging', 'finalized'])
const CLUB_REEL_MEDIA_SOURCE = {
  cacheKey: 'club',
  loadTrackletCrops: (matchId, trackletId, token) => APIService.getClubVideoTrackletCrops(matchId, trackletId, token),
  loadTrackletBbox: (matchId, trackletId, token) => APIService.getClubVideoTrackletBbox(matchId, trackletId, token),
  footageUrl: (matchId, token) => APIService.videoFootageUrl(matchId, token),
  cropUrl: (matchId, file, token) => APIService.videoCropUrl(matchId, file, token),
}

function errorText(error, fallback) {
  return error?.body?.error || error?.message || fallback
}

function formatTimestampDate(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatUpdatedTime(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
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
    camera_view: match.capture_meta?.camera_view || '',
    camera_motion: match.capture_meta?.camera_motion || '',
    pitch_lines_visible: match.capture_meta?.pitch_lines_visible || '',
  }
}

function matchRosterValues(match) {
  return Array.isArray(match.roster) ? match.roster.map((entry) => ({
    club_roster_member_id: entry.club_roster_member_id,
    jersey_number: String(entry.jersey_number),
  })).filter((entry) => entry.club_roster_member_id) : []
}

function isGoalkeeper(member) {
  const position = String(member?.position || member?.role || '').trim().toLowerCase()
  return position === 'g' || position === 'gk' || position === 'goalkeeper' || position === 'keeper'
}

function resultFormValues(match, savedResult) {
  const returned = savedResult?.result
  if (returned && typeof returned === 'object') {
    return {
      match_date: returned.match_date || '',
      opponent: returned.opponent || '',
      competition: returned.competition || '',
      home_away: returned.home_away || 'home',
      result_for: returned.result_for ?? '',
      result_against: returned.result_against ?? '',
    }
  }
  if (!match) return EMPTY_RESULT_FORM
  return {
    match_date: match.match_date || '',
    opponent: match.opponent_name || '',
    competition: match.competition || '',
    home_away: match.home_away || 'home',
    result_for: match.result_for ?? '',
    result_against: match.result_against ?? '',
  }
}

function resultRosterMembers(match, rosterMembers) {
  const available = rosterMembers.filter((member) => member.available)
  if (!match) return available
  const membersById = new Map(available.map((member) => [Number(member.id), member]))
  return (Array.isArray(match.roster) ? match.roster : []).flatMap((entry) => {
    const member = membersById.get(Number(entry.club_roster_member_id))
    return member ? [{ ...member, jersey_number: entry.jersey_number }] : []
  })
}

function resultEntryValues(member, returnedMatch, included) {
  return {
    club_roster_member_id: member.id,
    included,
    minutes: String(returnedMatch?.minutes ?? 0),
    goals: String(returnedMatch?.goals ?? 0),
    assists: String(returnedMatch?.assists ?? 0),
    yellows: String(returnedMatch?.yellows ?? 0),
    reds: String(returnedMatch?.reds ?? 0),
    saves: returnedMatch?.saves === null || typeof returnedMatch?.saves === 'undefined' ? '' : String(returnedMatch.saves),
    goals_conceded: returnedMatch?.goals_conceded === null || typeof returnedMatch?.goals_conceded === 'undefined' ? '' : String(returnedMatch.goals_conceded),
    note: returnedMatch?.note || '',
  }
}

function resultEntriesValues(members, savedResult, defaultIncluded) {
  const returnedMatches = Array.isArray(savedResult?.matches) ? savedResult.matches : []
  const returnedByMemberId = new Map(returnedMatches.flatMap((match) => (
    match.club_roster_member_id == null ? [] : [[String(match.club_roster_member_id), match]]
  )))
  const returnedByPlayerId = new Map(returnedMatches.map((match) => [
    String(match.player_api_id),
    match,
  ]))
  return members.map((member) => resultEntryValues(
    member,
    returnedByMemberId.get(String(member.id))
      || returnedByPlayerId.get(signedPlayerIdForMember(member)),
    defaultIncluded,
  ))
}

function boundedInteger(value, label, max) {
  if (value === '' || value === null || typeof value === 'undefined') {
    throw new Error(`${label} is required.`)
  }
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > max) {
    throw new Error(`${label} must be a whole number from 0 to ${max}.`)
  }
  return parsed
}

function nullableBoundedInteger(value, label, max) {
  if (value === '' || value === null || typeof value === 'undefined') return null
  return boundedInteger(value, label, max)
}

function signedPlayerIdForMember(member) {
  if (member?.player_api_id !== null && typeof member?.player_api_id !== 'undefined') {
    return String(member.player_api_id)
  }
  const localPlayerId = Number(member?.local_player_id)
  return Number.isInteger(localPlayerId) && localPlayerId > 0 ? String(-localPlayerId) : null
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

function PreflightSelect({ id, field, label, value, onChange, disabled = false }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} aria-label={label}>
          <SelectValue placeholder="Select" />
        </SelectTrigger>
        <SelectContent>
          {PREFLIGHT_OPTIONS[field].map(([optionValue, optionLabel]) => (
            <SelectItem key={optionValue} value={optionValue}>{optionLabel}</SelectItem>
          ))}
        </SelectContent>
      </Select>
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

function BriefEditor({ id, title, description, brief, onSave, onAccessDenied }) {
  const [body, setBody] = useState(brief?.body || '')
  const [busy, setBusy] = useState(false)
  const [fieldError, setFieldError] = useState(null)
  const updated = formatUpdatedTime(brief?.updated_at)

  const submit = async (nextBody) => {
    if (busy) return
    setBusy(true)
    setFieldError(null)
    try {
      const saved = await onSave(nextBody)
      setBody(saved?.body || '')
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      setFieldError(errorText(requestError, 'Could not save this brief.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Label htmlFor={id} className="font-semibold">{title}</Label>
        {updated ? <span className="text-xs text-muted-foreground">updated {updated}</span> : null}
      </div>
      <Textarea
        id={id}
        value={body}
        onChange={(event) => { setBody(event.target.value); setFieldError(null) }}
        maxLength={MAX_BRIEF_CHARS}
        rows={4}
        aria-invalid={Boolean(fieldError)}
      />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        <span className="text-xs tabular-nums text-muted-foreground">{body.length}/{MAX_BRIEF_CHARS}</span>
      </div>
      <InlineError>{fieldError}</InlineError>
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => submit(body)} disabled={busy}>
          {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Check className="mr-1.5 h-4 w-4" />}
          {busy ? 'Saving…' : 'Save'}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => submit('')} disabled={busy || !body}>
          Clear
        </Button>
      </div>
    </div>
  )
}

export function ClubInvitationPanel({ programId, token, onChanged = () => {} }) {
  const [rows, setRows] = useState([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [disabled, setDisabled] = useState(false)
  const [notice, setNotice] = useState('')
  const [nextBefore, setNextBefore] = useState(null)
  const alive = useRef(false)
  const requestIdentity = useRef(null)
  const scope = `${programId}:${token}`
  const activeScope = useRef(scope)
  useEffect(() => { activeScope.current = scope }, [scope])
  const endpoint = `/club/${programId}/invitations`

  useEffect(() => {
    alive.current = true
    let cancelled = false
    setRows([])
    setLoading(true)
    setError(null)
    setDisabled(false)
    APIService.request(endpoint).then((data) => {
      if (!cancelled) { setRows(data.invitations || []); setNextBefore(data.next_before) }
    }).catch((err) => {
      if (!cancelled) {
        if (err.status === 404) setDisabled(true)
        else setError(err.status === 403 ? 'Club manager access denied.' : 'Could not load invitations.')
      }
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; alive.current = false }
  }, [endpoint, token])

  useEffect(() => {
    const controller = new AbortController()
    setResults([])
    const trimmed = query.trim()
    const signedId = /^-?\d+$/.test(trimmed) ? Number(trimmed) : null
    if ((signedId === null && trimmed.length < 2) || (signedId !== null && (!Number.isInteger(signedId) || signedId === 0 || Math.abs(signedId) > 2147483647))) return () => controller.abort()
    const timer = setTimeout(() => {
      const path = signedId === null
        ? `/scout/players?search=${encodeURIComponent(trimmed)}&per_page=8&sort=name&order=asc`
        : `/players/${signedId}/profile`
      APIService.request(path, { signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) setResults(signedId === null ? data.players || [] : [data]) })
        .catch(() => { if (!controller.signal.aborted) setError('Player search is unavailable.') })
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [query, scope])

  async function mutate(invitation = null) {
    if (busy || (!invitation && !selected)) return
    const capturedScope = scope
    const current = () => alive.current && activeScope.current === capturedScope
    setBusy(true); setError(null); setNotice('')
    const action = invitation ? 'relationship_revoked' : 'invite_created'
    try {
      const data = await APIService.request(invitation ? `${endpoint}/${invitation.id}/revoke` : endpoint, {
        method: 'POST', body: JSON.stringify(invitation ? {} : {
          player_api_id: Number(selected.player_api_id ?? selected.player_id),
          client_request_id: requestIdentity.current,
        }),
      })
      if (!current()) return
      setRows((old) => [data.invitation, ...old.filter((row) => row.id !== data.invitation.id)])
      setNotice(invitation ? 'Relationship revoked.' : 'Invitation ready to share.')
      track('pilot_ui', { package: 'P2', action, outcome: 'success' })
      onChanged()
    } catch (err) {
      if (!current()) return
      const message = {
        invitation_exists: 'An invitation or accepted relationship already exists.',
        client_request_id_reused: 'This request was already used for a different player. Select the player again.',
        invitation_expired: 'This invitation has expired.',
        invitation_unavailable: 'This relationship is unavailable.',
        retry_conflict: 'Another update occurred. Please retry.',
      }[err.body?.error]
      setError(message || (err.status === 403 ? 'Club manager access denied.' : 'Could not update the invitation.'))
      track('pilot_ui', { package: 'P2', action, outcome: 'error' })
    } finally { if (current()) setBusy(false) }
  }

  async function copyLink(row) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/players/${row.player_api_id}#club-invitation=${row.id}`)
      if (alive.current) setNotice('Invitation link copied.')
    } catch { if (alive.current) setError('Could not copy the invitation link. Please try again.') }
  }

  async function loadMore() {
    const capturedScope = scope
    setBusy(true)
    try {
      const data = await APIService.request(`${endpoint}?before=${encodeURIComponent(nextBefore)}`)
      if (alive.current && activeScope.current === capturedScope) {
        setRows((old) => [...old, ...data.invitations]); setNextBefore(data.next_before)
      }
    } catch { if (alive.current && activeScope.current === capturedScope) setError('Could not load more invitations.') }
    finally { if (alive.current && activeScope.current === capturedScope) setBusy(false) }
  }

  if (disabled) return null
  return <Card aria-label="Club relationships">
    <CardHeader>
      <CardTitle>Invite player</CardTitle>
      <CardDescription>The player must accept before this relationship is active.</CardDescription>
    </CardHeader>
    <CardContent className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="invitation-player-search">Find a public player</Label>
        <Input id="invitation-player-search" value={query} maxLength={100} disabled={busy} placeholder="Search player name or signed ID" onChange={(event) => { setQuery(event.target.value); setSelected(null); requestIdentity.current = null }} />
        {results.length > 0 && !selected && <ul className="divide-y rounded-md border">{results.map((player) => <li key={player.player_api_id ?? player.player_id}>
          <button type="button" className="w-full p-3 text-left hover:bg-muted" onClick={() => { setSelected(player); requestIdentity.current = crypto.randomUUID() }}>{player.player_name || player.name}{Number(player.player_api_id ?? player.player_id) < 0 ? ' · Local player' : ''}</button>
        </li>)}</ul>}
        {selected && <p className="text-sm">Selected: {selected.player_name || selected.name}</p>}
        <Button disabled={!selected || busy || loading} onClick={() => mutate()}>{busy ? 'Saving…' : 'Create invitation'}</Button>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {notice && <p role="status" className="text-sm">{notice}</p>}
      {loading ? <p role="status">Loading invitations…</p> : rows.length === 0 ? <p className="text-sm text-muted-foreground">No club invitations yet.</p> : <ul className="divide-y">{rows.map((row) => {
        const expired = row.status === 'expired' || (row.status === 'pending' && Date.now() >= Date.parse(row.expires_at))
        return <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div><a href={`/players/${row.player_api_id}`} className="text-sm underline">Player {row.player_api_id}</a><p className="text-sm text-muted-foreground">{expired ? 'Expired' : ({ pending: 'Awaiting player', accepted: 'Accepted', declined: 'Declined', revoked: 'Revoked' }[row.status])}</p></div>
          <div className="flex flex-wrap gap-2">{row.status === 'pending' && !expired && <Button variant="outline" size="sm" onClick={() => copyLink(row)}>Copy invitation link</Button>}{['pending', 'accepted'].includes(row.status) && !expired && <Button variant="outline" size="sm" disabled={busy} onClick={() => mutate(row)}>Revoke relationship</Button>}</div>
        </li>
      })}</ul>}
      {nextBefore && <Button variant="outline" disabled={busy} onClick={loadMore}>More invitations</Button>}
    </CardContent>
  </Card>
}

export function PlayerFeedbackPanel({ programId, invitationId, playerName, token, onAccessDenied = () => {} }) {
  if (!token || !invitationId) return null
  return <FeedbackPublisher key={`${programId}:${invitationId}:${token}`} programId={programId} invitationId={invitationId} playerName={playerName} onAccessDenied={onAccessDenied} />
}

function FeedbackPublisher({ programId, invitationId, playerName, onAccessDenied }) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState([])
  const [nextBefore, setNextBefore] = useState(null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [videoId, setVideoId] = useState('')
  const [refs, setRefs] = useState([])
  const [correction, setCorrection] = useState(null)
  const [preview, setPreview] = useState(false)
  const [withdraw, setWithdraw] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [denied, setDenied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const lifetime = useRef(null)
  const requestIdentity = useRef(null)
  const endpoint = `/club/${programId}/player-feedback`

  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    return () => controller.abort()
  }, [])

  function resetDraft() {
    setTitle(''); setBody(''); setVideoId(''); setRefs([]); setPreview(false); setCorrection(null)
    requestIdentity.current = null
  }
  function failure(err) {
    if (lifetime.current.signal.aborted) return
    if ([401, 403, 404].includes(err.status) || ['feedback_withdrawn', 'club_relationship_required'].includes(err.body?.error)) {
      resetDraft(); setRows([]); setWithdraw(null); setDenied(true)
      setError('This feedback is no longer available.')
      if (err.status === 403) onAccessDenied()
    } else if (err.body?.error === 'feedback_revision_conflict') {
      setPreview(false)
      setError('A newer revision was published. Refresh history and start a new correction.')
    } else if (err.body?.error === 'feedback_reference_unavailable') setError('That finalized match is unavailable for this player. Check the reference.')
    else if (err.status === 429) setError('Too many requests. Please wait before trying again.')
    else setError('Could not save feedback. Your draft is still here; please try again.')
  }
  async function history(before = null) {
    setBusy(true); setError('')
    try {
      const data = await APIService.request(`${endpoint}?invitation_id=${invitationId}${before ? `&before=${before}` : ''}`, { signal: lifetime.current.signal })
      if (lifetime.current.signal.aborted) return
      setRows((old) => before ? [...old, ...data.feedback] : data.feedback)
      setNextBefore(data.next_before)
      setLoaded(true)
    } catch (err) { failure(err) }
    finally { if (!lifetime.current.signal.aborted) setBusy(false) }
  }
  async function publishDraft() {
    if (busy || !preview) return
    setBusy(true); setError(''); setNotice('')
    const authored = { title: title.trim(), body: body.trim(), video_match_id: videoId ? Number(videoId) : null, observation_refs: refs.map((ref) => ({ label: ref.label.trim(), timestamp_s: ref.timestamp_s === '' ? null : Number(ref.timestamp_s) })) }
    const target = correction ? `${endpoint}/${correction.thread_id}/revisions` : endpoint
    const data = { ...authored, ...(correction ? { expected_revision: correction.revision } : { invitation_id: invitationId }) }
    const identity = JSON.stringify({ target, data })
    if (requestIdentity.current?.identity !== identity) requestIdentity.current = { identity, id: crypto.randomUUID() }
    try {
      await APIService.request(target, { method: 'POST', body: JSON.stringify({ ...data, client_request_id: requestIdentity.current.id }), signal: lifetime.current.signal })
      if (lifetime.current.signal.aborted) return
      resetDraft(); setNotice('Feedback published.')
      track('pilot_ui', { package: 'P3', action: 'feedback_published', outcome: 'success' })
      await history()
    } catch (err) { failure(err) }
    finally { if (!lifetime.current.signal.aborted) setBusy(false) }
  }
  async function withdrawThread() {
    if (busy || !withdraw) return
    setBusy(true); setError('')
    try {
      await APIService.request(`${endpoint}/${withdraw.thread_id}/withdraw`, { method: 'POST', body: JSON.stringify({ expected_revision: withdraw.revision }), signal: lifetime.current.signal })
      if (lifetime.current.signal.aborted) return
      setWithdraw(null); resetDraft(); setNotice('Feedback withdrawn.')
      track('pilot_ui', { package: 'P3', action: 'feedback_withdrawn', outcome: 'success' })
      await history()
    } catch (err) { failure(err) }
    finally { if (!lifetime.current.signal.aborted) setBusy(false) }
  }
  const valid = title.trim() && body.trim() && refs.every((ref) => ref.label.trim() && (ref.timestamp_s === '' || Number.isFinite(Number(ref.timestamp_s)) && Number(ref.timestamp_s) >= 0)) && (!videoId || Number.isSafeInteger(Number(videoId)) && Number(videoId) > 0)

  if (!open) return <Button variant="outline" size="sm" onClick={() => { setOpen(true); history() }}><Send className="mr-2 h-4 w-4" />Publish feedback</Button>
  return <section aria-label={`Publish feedback for ${playerName}`} className="space-y-5 rounded-xl border border-primary/20 bg-muted/20 p-4 sm:p-5">
    <div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">Private feedback for {playerName}</h3><p className="mt-1 text-xs leading-relaxed text-muted-foreground">Write feedback specifically for the player. Publication sends this text to their private profile inbox.</p></div><Button variant="ghost" size="sm" disabled={busy} onClick={() => { resetDraft(); setOpen(false) }}>Close</Button></div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-sm font-medium">{notice}</p>}
    {!denied && <>
      <div className="space-y-3 border-b border-border pb-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold">Publication history</h4><Button variant="ghost" size="sm" disabled={busy} onClick={() => history()}>Refresh history</Button></div>
        {loaded && rows.length === 0 && <p className="text-xs text-muted-foreground">No feedback published yet.</p>}
        {rows.map((row) => <div key={row.id} className="space-y-2 rounded-lg border border-border bg-card p-3">
          {row.unavailable ? <p className="text-sm">This feedback is no longer available.</p> : <>
            <p className="break-words text-sm font-medium">{row.title}</p>
            <p className="text-xs text-muted-foreground">Revision {row.revision} · {row.acknowledged_at ? 'Acknowledged' : 'Awaiting acknowledgment'}</p>
            <ul className="space-y-1 text-xs text-muted-foreground">{row.revision_history?.map((revision) => <li key={revision.id}>Revision {revision.revision} — {revision.acknowledged_at ? 'Acknowledged' : 'Not acknowledged'}</li>)}</ul>
            <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={busy} onClick={() => { resetDraft(); setCorrection(row); setNotice(''); setError('') }}>Publish correction</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setWithdraw(row)}>Withdraw feedback</Button></div>
          </>}
        </div>)}
        {nextBefore && <Button variant="outline" size="sm" disabled={busy} onClick={() => history(nextBefore)}>Load more history</Button>}
      </div>
      {withdraw && <div className="space-y-3 rounded-lg border border-destructive/30 p-4"><p className="text-sm">Withdraw this entire feedback thread? The player will lose access to every revision. This cannot be reopened.</p><div className="flex flex-wrap gap-2"><Button variant="destructive" disabled={busy} onClick={withdrawThread}>Confirm withdrawal</Button><Button variant="ghost" disabled={busy} onClick={() => setWithdraw(null)}>Cancel withdrawal</Button></div></div>}
      {preview ? <div className="space-y-4" aria-label="Publication preview">
        <h4 className="font-semibold">Confirm publication · {correction ? `Revision ${correction.revision + 1}` : 'New feedback'}</h4>
        <p className="break-words font-medium">{title}</p><p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{body}</p>
        {videoId && <p className="text-xs text-muted-foreground">Textual match reference: {videoId}</p>}
        {refs.map((ref, index) => <p key={index} className="break-words text-xs text-muted-foreground">{ref.timestamp_s === '' ? '' : `${ref.timestamp_s}s — `}{ref.label}</p>)}
        <p className="text-xs text-muted-foreground">This revision cannot be edited after publication. A correction creates a new revision requiring a new acknowledgment.</p>
        <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={publishDraft}>Confirm and publish</Button><Button variant="ghost" disabled={busy} onClick={() => setPreview(false)}>Back to draft</Button></div>
      </div> : <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); if (valid) setPreview(true) }}>
        <h4 className="text-sm font-semibold">{correction ? `Write correction · Revision ${correction.revision + 1}` : 'Write new feedback'}</h4>
        <label className="block space-y-1 text-sm">Feedback title<Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={140} required disabled={busy} /></label>
        <div className="space-y-1"><label htmlFor={`feedback-body-${invitationId}`} className="text-sm">Feedback text</label><Textarea id={`feedback-body-${invitationId}`} value={body} onChange={(event) => setBody(event.target.value)} maxLength={4000} rows={6} required disabled={busy} /></div>
        <p className="text-right text-xs text-muted-foreground">{body.length} / 4,000</p>
        <label className="block space-y-1 text-sm">Finalized match ID (optional)<Input type="number" min="1" step="1" value={videoId} onChange={(event) => setVideoId(event.target.value)} disabled={busy} /></label>
        {refs.map((ref, index) => <div key={index} className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-2"><label className="space-y-1 text-sm">Observation {index + 1}<Input value={ref.label} maxLength={160} required disabled={busy} onChange={(event) => setRefs((old) => old.map((item, i) => i === index ? { ...item, label: event.target.value } : item))} /></label><label className="space-y-1 text-sm">Timestamp in seconds (optional)<Input type="number" min="0" step="any" value={ref.timestamp_s} disabled={busy} onChange={(event) => setRefs((old) => old.map((item, i) => i === index ? { ...item, timestamp_s: event.target.value } : item))} /></label><Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setRefs((old) => old.filter((_, i) => i !== index))}>Remove observation {index + 1}</Button></div>)}
        <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" size="sm" disabled={busy || refs.length >= 10} onClick={() => setRefs((old) => [...old, { label: '', timestamp_s: '' }])}>Add observation reference</Button><Button type="submit" disabled={busy || !valid}>Preview publication</Button>{correction && <Button type="button" variant="ghost" onClick={resetDraft} disabled={busy}>Cancel correction</Button>}</div>
      </form>}
    </>}
  </section>
}

export function RosterPanel({ programId, members, systemBrief, loading, error, onMembersChange, onSystemBriefChange, onReload, onAccessDenied }) {
  const { token } = useAuth()
  const [acceptedInvitations, setAcceptedInvitations] = useState({})
  const [invitationError, setInvitationError] = useState(null)
  const [invitationReload, setInvitationReload] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setAcceptedInvitations({})
    setInvitationError(null)
    if (!token || !members.length) return () => controller.abort()
    async function loadAccepted() {
      const accepted = {}
      let cursor = null
      do {
        const data = await APIService.request(`/club/${programId}/invitations?limit=50${cursor ? `&before=${cursor}` : ''}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        for (const row of data.invitations || []) {
          if (row.status === 'accepted' && row.roster_member_id) accepted[row.roster_member_id] = row.id
        }
        cursor = data.next_before
      } while (cursor)
      if (!controller.signal.aborted) setAcceptedInvitations(accepted)
    }
    loadAccepted().catch(() => {
      if (!controller.signal.aborted) setInvitationError('Could not load accepted club invitations. Feedback publishing is unavailable until you retry.')
    })
    return () => controller.abort()
  }, [programId, token, members, invitationReload])
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
      {invitationError && <div className="space-y-2">
        <InlineError>{invitationError}</InlineError>
        <Button variant="outline" size="sm" onClick={() => setInvitationReload((value) => value + 1)}>Retry accepted invitations</Button>
      </div>}
      <ClubInvitationPanel key={`${programId}:${token}`} programId={programId} token={token} onChanged={onReload} />
      <Card className="border-border/80">
        <CardHeader>
          <CardTitle className="text-lg">How we play</CardTitle>
          <CardDescription>Give the analysis the team context behind each player expectation.</CardDescription>
        </CardHeader>
        <CardContent>
          <BriefEditor
            key={`system-${systemBrief?.updated_at || 'empty'}`}
            id="club-system-brief"
            title="System brief"
            description="one expectation per line, up to 8 lines — describe behaviours, not people"
            brief={systemBrief}
            onSave={async (body) => {
              const response = await APIService.setClubSystemBrief(programId, body)
              const saved = response?.system_brief || { body: null, updated_at: null, hash: null }
              onSystemBriefChange(saved)
              return saved
            }}
            onAccessDenied={onAccessDenied}
          />
        </CardContent>
      </Card>

      <Card className="overflow-hidden border-border/80">
        <CardHeader className="flex flex-row items-start justify-between gap-4 border-b border-border/60 bg-card">
          <div>
            <CardTitle className="flex items-center gap-2"><Users className="h-5 w-5 text-primary" /> Private roster</CardTitle>
            <CardDescription className="mt-1">Private attachments for this club&apos;s match sheets and reports are separate from player-accepted relationships.</CardDescription>
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
                <div key={member.id} className="space-y-4 px-5 py-5 transition-colors hover:bg-muted/35">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
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
                  {member.available && !member.is_minor && acceptedInvitations[member.id] && <PlayerFeedbackPanel
                    programId={programId} invitationId={acceptedInvitations[member.id]} playerName={member.display_name} token={token} onAccessDenied={onAccessDenied}
                  />}
                  <BriefEditor
                    key={`${member.id}-${member.brief?.updated_at || 'empty'}`}
                    id={`coach-brief-${member.id}`}
                    title="Coach's brief"
                    description="one expectation per line, up to 8 lines — describe behaviours, not people"
                    brief={member.brief}
                    onSave={async (body) => {
                      const response = await APIService.setRosterMemberBrief(programId, member.id, body)
                      const savedMember = response?.member
                      if (savedMember) onMembersChange((current) => current.map((row) => row.id === savedMember.id ? savedMember : row))
                      return savedMember?.brief
                    }}
                    onAccessDenied={onAccessDenied}
                  />
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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
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
          <PreflightSelect id="new-match-camera-view" field="camera_view" label="Camera view" value={form.camera_view} onChange={(value) => update('camera_view', value)} />
          <PreflightSelect id="new-match-camera-motion" field="camera_motion" label="Camera motion" value={form.camera_motion} onChange={(value) => update('camera_motion', value)} />
          <PreflightSelect id="new-match-pitch-lines" field="pitch_lines_visible" label="Pitch lines visible" value={form.pitch_lines_visible} onChange={(value) => update('pitch_lines_visible', value)} />
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

function RecordResultDialog({ programId, videoMatch, members, savedResult, onSaved, onClose, onAccessDenied }) {
  const { logout, openLoginModal } = useAuthUI()
  const [form, setForm] = useState(() => resultFormValues(videoMatch, savedResult))
  const [entries, setEntries] = useState(() => resultEntriesValues(members, savedResult, Boolean(videoMatch)))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const errorRef = useRef(null)
  const memberById = useMemo(() => new Map(members.map((member) => [Number(member.id), member])), [members])
  const memberByPlayerId = useMemo(() => new Map(members.flatMap((member) => {
    const signedPlayerId = signedPlayerIdForMember(member)
    return signedPlayerId ? [[signedPlayerId, member]] : []
  })), [members])
  const seasonStats = result?.season_stats_by_player && typeof result.season_stats_by_player === 'object'
    ? Object.entries(result.season_stats_by_player)
    : []
  const noVideo = !videoMatch
  const selectedEntryCount = entries.filter((entry) => entry.included).length

  useEffect(() => {
    if (error) errorRef.current?.focus()
  }, [error])

  const updateForm = (field, value) => {
    setError(null)
    setForm((current) => ({ ...current, [field]: value }))
  }
  const updateEntry = (memberId, field, value) => {
    setError(null)
    setEntries((current) => current.map((entry) => Number(entry.club_roster_member_id) === Number(memberId)
      ? { ...entry, [field]: value }
      : entry))
  }

  const buildPayload = () => {
    const matchDate = form.match_date.trim()
    if (!matchDate) throw new Error('Match date is required.')
    const today = new Date()
    const todayString = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-')
    if (matchDate > todayString) throw new Error('Match date cannot be in the future.')

    const opponent = form.opponent.trim()
    const competition = form.competition.trim()
    if (!opponent) throw new Error('Opponent is required.')
    if (opponent.length > MAX_RESULT_TEXT_LENGTH) throw new Error(`Opponent must be at most ${MAX_RESULT_TEXT_LENGTH} characters.`)
    if (competition.length > MAX_RESULT_TEXT_LENGTH) throw new Error(`Competition must be at most ${MAX_RESULT_TEXT_LENGTH} characters.`)
    if (!['home', 'away', 'neutral'].includes(form.home_away)) throw new Error('Choose whether the fixture was home, away or neutral.')

    const selectedEntries = entries.filter((entry) => entry.included)
    if (selectedEntries.length === 0) throw new Error('Select at least one roster member.')

    return {
      video_match_id: videoMatch ? Number(videoMatch.id) : null,
      match_date: matchDate,
      opponent,
      competition: competition || null,
      home_away: form.home_away,
      result_for: boundedInteger(form.result_for, 'Our score', MAX_MATCH_COUNT),
      result_against: boundedInteger(form.result_against, 'Their score', MAX_MATCH_COUNT),
      entries: selectedEntries.map((entry) => {
        const member = memberById.get(Number(entry.club_roster_member_id))
        const memberId = Number(entry.club_roster_member_id)
        if (!member || !Number.isInteger(memberId) || memberId <= 0) {
          throw new Error('A selected roster member is no longer available.')
        }
        const note = entry.note.trim()
        if (note.length > MAX_RESULT_NOTE_LENGTH) {
          throw new Error(`${member.display_name || 'Player'}’s note must be at most ${MAX_RESULT_NOTE_LENGTH} characters.`)
        }
        const goalkeeper = isGoalkeeper(member)
        return {
          club_roster_member_id: memberId,
          minutes: boundedInteger(entry.minutes, `${member.display_name || 'Player'} minutes`, MAX_MATCH_MINUTES),
          goals: boundedInteger(entry.goals, `${member.display_name || 'Player'} goals`, MAX_MATCH_COUNT),
          assists: boundedInteger(entry.assists, `${member.display_name || 'Player'} assists`, MAX_MATCH_COUNT),
          yellows: boundedInteger(entry.yellows, `${member.display_name || 'Player'} yellows`, MAX_MATCH_COUNT),
          reds: boundedInteger(entry.reds, `${member.display_name || 'Player'} reds`, MAX_MATCH_COUNT),
          saves: goalkeeper ? nullableBoundedInteger(entry.saves, `${member.display_name || 'Goalkeeper'} saves`, MAX_MATCH_COUNT) : null,
          goals_conceded: goalkeeper ? nullableBoundedInteger(entry.goals_conceded, `${member.display_name || 'Goalkeeper'} goals conceded`, MAX_MATCH_COUNT) : null,
          note: note || null,
        }
      }),
    }
  }

  const submit = async () => {
    if (busy) return
    let payload
    try {
      payload = buildPayload()
    } catch (validationError) {
      setError(validationError.message)
      return
    }

    setBusy(true)
    setError(null)
    try {
      const response = await APIService.recordClubResult(programId, payload)
      setResult(response || { season_stats_by_player: {} })
      if (videoMatch && response) onSaved(response)
    } catch (requestError) {
      if (requestError?.status === 401) {
        logout({ clearAdminKey: true })
        onClose()
        openLoginModal()
        return
      }
      if (requestError?.status === 403) {
        onClose()
        onAccessDenied()
        return
      }
      if (requestError?.status === 404) {
        setError(requestError.body?.error || 'This match or roster is no longer available. Refresh and try again.')
      } else if (requestError?.status === 409) {
        setError(requestError.body?.error || 'This result conflicts with the current match or roster. Refresh and try again.')
      } else {
        setError(errorText(requestError, 'Could not record this result.'))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(nextOpen) => { if (!nextOpen && !busy) onClose() }}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{videoMatch ? `Record result vs ${videoMatch.opponent_name || 'opponent'}` : 'Record a result without video'}</DialogTitle>
          <DialogDescription>
            {videoMatch
              ? 'Add the final score and club-confirmed stats for the saved match roster.'
              : 'Log a fixture and club-confirmed player stats without creating or uploading a video.'}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-4 py-2">
            <Alert className="border-emerald-200 bg-emerald-50">
              <Check className="h-4 w-4 text-emerald-700" />
              <AlertDescription className="text-emerald-950">
                Result saved for {Array.isArray(result.matches) ? result.matches.length : selectedEntryCount} players. Their club-confirmed season totals are now updated.
              </AlertDescription>
            </Alert>
            <section aria-labelledby="club-result-season-totals" className="space-y-3">
              <div>
                <h3 id="club-result-season-totals" className="font-bold text-foreground">Season totals updated</h3>
                <p className="text-sm text-muted-foreground">Totals remain separated by source and are shown here exactly as returned after the write.</p>
              </div>
              {seasonStats.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">No season totals were returned.</p>
              ) : (
                <div className="grid gap-3 lg:grid-cols-2">
                  {seasonStats.map(([playerId, stats]) => {
                    const rosterMemberId = Number(stats?.club_roster_member_id)
                    const hasRosterMemberId = Number.isInteger(rosterMemberId) && rosterMemberId > 0
                    const member = (hasRosterMemberId ? memberById.get(rosterMemberId) : null)
                      || memberByPlayerId.get(String(playerId))
                    const withheldMinor = stats?.withheld === 'minor'
                    const playerName = stats?.player_name
                      || member?.display_name
                      || (withheldMinor ? 'Roster player' : `Player ${playerId}`)
                    const metrics = [
                      ['Apps', stats?.appearances ?? 0],
                      ['Minutes', stats?.minutes ?? 0],
                      ['Goals', stats?.goals ?? 0],
                      ['Assists', stats?.assists ?? 0],
                      ['Yellows', stats?.yellows ?? 0],
                      ['Reds', stats?.reds ?? 0],
                    ]
                    if (stats?.saves !== null && typeof stats?.saves !== 'undefined') metrics.push(['Saves', stats.saves])
                    if (stats?.goals_conceded !== null && typeof stats?.goals_conceded !== 'undefined') metrics.push(['Conceded', stats.goals_conceded])
                    return (
                      <article
                        key={hasRosterMemberId ? `roster-${rosterMemberId}` : `player-${playerId}`}
                        className="rounded-xl border border-border bg-secondary/25 p-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h4 className="font-semibold text-foreground">{playerName}</h4>
                          {!withheldMinor && stats?.season ? <Badge variant="outline">{stats.season} season</Badge> : null}
                        </div>
                        {withheldMinor ? (
                          <p className="mt-3 rounded-lg border border-dashed border-border bg-background px-3 py-3 text-sm text-muted-foreground">
                            Totals withheld for this player
                          </p>
                        ) : (
                          <dl className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
                            {metrics.map(([label, value]) => (
                              <div key={label} className="rounded-lg bg-background px-2.5 py-2 ring-1 ring-border/70">
                                <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
                                <dd className="mt-0.5 font-bold tabular-nums text-foreground">{value}</dd>
                              </div>
                            ))}
                          </dl>
                        )}
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          </div>
        ) : (
          <form
            className="space-y-5 py-2"
            aria-describedby={error ? 'club-result-error' : undefined}
            onSubmit={(event) => { event.preventDefault(); submit() }}
          >
            <section className="grid gap-4 rounded-xl border border-border bg-secondary/20 p-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Match result details">
              <div className="space-y-2">
                <Label htmlFor="club-result-date">Match date</Label>
                <Input id="club-result-date" type="date" value={form.match_date} onChange={(event) => updateForm('match_date', event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="club-result-opponent">Opponent</Label>
                <Input id="club-result-opponent" value={form.opponent} onChange={(event) => updateForm('opponent', event.target.value)} maxLength={MAX_RESULT_TEXT_LENGTH} placeholder="Opponent name" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="club-result-competition">Competition</Label>
                <Input id="club-result-competition" value={form.competition} onChange={(event) => updateForm('competition', event.target.value)} maxLength={MAX_RESULT_TEXT_LENGTH} placeholder="League or tournament" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="club-result-home-away">Home / away</Label>
                <Select value={form.home_away} onValueChange={(value) => updateForm('home_away', value)}>
                  <SelectTrigger id="club-result-home-away"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="home">Home</SelectItem>
                    <SelectItem value="away">Away</SelectItem>
                    <SelectItem value="neutral">Neutral</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="club-result-for">Our score</Label>
                <Input id="club-result-for" type="number" inputMode="numeric" min="0" max={MAX_MATCH_COUNT} step="1" value={form.result_for} onChange={(event) => updateForm('result_for', event.target.value)} placeholder="0" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="club-result-against">Their score</Label>
                <Input id="club-result-against" type="number" inputMode="numeric" min="0" max={MAX_MATCH_COUNT} step="1" value={form.result_against} onChange={(event) => updateForm('result_against', event.target.value)} placeholder="0" />
              </div>
            </section>

            <section className="space-y-3" aria-labelledby="club-result-player-stats">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h3 id="club-result-player-stats" className="font-bold text-foreground">Player stats</h3>
                  <p className="text-sm text-muted-foreground">Minutes allow 0–{MAX_MATCH_MINUTES}; every count allows 0–{MAX_MATCH_COUNT}. Leave goalkeeper fields blank when unknown.</p>
                </div>
                <Badge variant="outline">{selectedEntryCount} selected</Badge>
              </div>
              {entries.length === 0 ? (
                <EmptyState icon={Users} title="No available roster members">Add players to the club roster{videoMatch ? ' and save the match roster' : ''} before recording a result.</EmptyState>
              ) : (
                <div className="space-y-3">
                  {entries.map((entry) => {
                    const member = memberById.get(Number(entry.club_roster_member_id))
                    if (!member) return null
                    const goalkeeper = isGoalkeeper(member)
                    const playerLabel = member.display_name || `Roster member #${member.id}`
                    const prefix = `club-result-player-${member.id}`
                    return (
                      <article key={member.id} aria-labelledby={`${prefix}-name`} className={`rounded-xl border p-4 transition-colors ${entry.included ? 'border-border bg-card' : 'border-border/60 bg-muted/25 opacity-70'}`}>
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                          <div className="flex min-w-0 items-center gap-3">
                            {noVideo ? (
                              <input
                                type="checkbox"
                                checked={entry.included}
                                onChange={(event) => updateEntry(member.id, 'included', event.target.checked)}
                                aria-label={`Include ${playerLabel} in result`}
                                className="h-4 w-4 shrink-0 accent-primary"
                              />
                            ) : null}
                            <div className="min-w-0">
                              <h4 id={`${prefix}-name`} className="truncate font-semibold text-foreground">{playerLabel}</h4>
                              <p className="truncate text-xs text-muted-foreground">{[member.jersey_number ? `#${member.jersey_number}` : null, member.position || member.role, member.is_minor ? 'Minor — private' : null].filter(Boolean).join(' · ') || 'Club roster member'}</p>
                            </div>
                          </div>
                          {goalkeeper ? <Badge className="border-sky-200 bg-sky-50 text-sky-800">Goalkeeper</Badge> : null}
                        </div>
                        <fieldset disabled={!entry.included} className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                          {[
                            ['minutes', 'Minutes', MAX_MATCH_MINUTES],
                            ['goals', 'Goals', MAX_MATCH_COUNT],
                            ['assists', 'Assists', MAX_MATCH_COUNT],
                            ['yellows', 'Yellows', MAX_MATCH_COUNT],
                            ['reds', 'Reds', MAX_MATCH_COUNT],
                          ].map(([field, label, max]) => (
                            <div key={field} className="space-y-1.5">
                              <Label htmlFor={`${prefix}-${field}`}>{label}</Label>
                              <Input id={`${prefix}-${field}`} type="number" inputMode="numeric" min="0" max={max} step="1" value={entry[field]} onChange={(event) => updateEntry(member.id, field, event.target.value)} />
                            </div>
                          ))}
                          {goalkeeper ? (
                            <>
                              <div className="space-y-1.5">
                                <Label htmlFor={`${prefix}-saves`}>Saves</Label>
                                <Input id={`${prefix}-saves`} type="number" inputMode="numeric" min="0" max={MAX_MATCH_COUNT} step="1" value={entry.saves} onChange={(event) => updateEntry(member.id, 'saves', event.target.value)} placeholder="Unknown" />
                              </div>
                              <div className="space-y-1.5">
                                <Label htmlFor={`${prefix}-goals-conceded`}>Goals conceded</Label>
                                <Input id={`${prefix}-goals-conceded`} type="number" inputMode="numeric" min="0" max={MAX_MATCH_COUNT} step="1" value={entry.goals_conceded} onChange={(event) => updateEntry(member.id, 'goals_conceded', event.target.value)} placeholder="Unknown" />
                              </div>
                            </>
                          ) : null}
                          <div className="space-y-1.5 sm:col-span-3 lg:col-span-6">
                            <Label htmlFor={`${prefix}-note`}>Note</Label>
                            <Textarea id={`${prefix}-note`} value={entry.note} onChange={(event) => updateEntry(member.id, 'note', event.target.value)} maxLength={MAX_RESULT_NOTE_LENGTH} rows={2} placeholder="Optional manager note" />
                          </div>
                        </fieldset>
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
            {error ? (
              <p id="club-result-error" ref={errorRef} className="text-sm text-destructive" role="alert" tabIndex={-1}>
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
              <Button type="submit" disabled={busy || selectedEntryCount === 0}>
                {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Trophy className="mr-1.5 h-4 w-4" />}
                {busy ? 'Saving result…' : 'Save result'}
              </Button>
            </DialogFooter>
          </form>
        )}
        {result ? <DialogFooter><Button type="button" onClick={onClose}>Close</Button></DialogFooter> : null}
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

function ClubPlayerReels({ programId, match, rosterMembers, onAccessDenied }) {
  const [opened, setOpened] = useState(false)
  const [loading, setLoading] = useState(false)
  const [reel, setReel] = useState(null)
  const [mediaToken, setMediaToken] = useState(null)
  const [openPlayerId, setOpenPlayerId] = useState(null)
  const [error, setError] = useState(null)

  const loadFresh = useCallback(async () => {
    if (loading) return
    setLoading(true)
    setError(null)
    setOpened(false)
    setReel(null)
    setMediaToken(null)
    setOpenPlayerId(null)
    try {
      const [reelResponse, tokenResponse] = await Promise.all([
        APIService.getClubMatchReel(programId, match.id),
        APIService.clubVideoMediaToken(programId, match.id),
      ])
      setReel(reelResponse)
      setMediaToken(tokenResponse?.token || null)
      setOpened(true)
    } catch (requestError) {
      if (requestError?.status === 403) {
        onAccessDenied()
        return
      }
      setError(requestError?.status === 404
        ? 'Player reels are not available for this match.'
        : errorText(requestError, 'Player reels could not be loaded. Try again.'))
    } finally {
      setLoading(false)
    }
  }, [loading, match.id, onAccessDenied, programId])

  if (!REEL_MATCH_STATUSES.has(match.status)) return null

  return (
    <section className="space-y-3 border-t border-border pt-5" aria-labelledby={`match-${match.id}-reels`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 id={`match-${match.id}-reels`} className="font-bold text-foreground">Player reels</h3>
          <p className="text-sm text-muted-foreground">Watch read-only on-camera windows from this club&apos;s private match.</p>
        </div>
        <Button
          variant={opened ? 'secondary' : 'outline'}
          onClick={() => {
            if (opened) setOpened(false)
            else loadFresh()
          }}
          disabled={loading}
        >
          {loading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Film className="mr-1.5 h-4 w-4" />}
          {loading ? 'Loading reels…' : opened ? 'Hide player reels' : 'View player reels'}
        </Button>
      </div>
      {error ? <Alert className="border-amber-200 bg-amber-50"><AlertCircle className="h-4 w-4 text-amber-800" /><AlertDescription className="text-amber-950">{error}</AlertDescription></Alert> : null}
      {opened && reel ? (
        <PlayerReels
          match={match}
          reel={reel}
          mediaToken={mediaToken}
          openPlayerId={openPlayerId}
          onTogglePlayer={(rosterEntryId) => setOpenPlayerId((current) => current === rosterEntryId ? null : rosterEntryId)}
          onMediaError={loadFresh}
          readOnly
          mediaSource={CLUB_REEL_MEDIA_SOURCE}
          clubRoster={rosterMembers}
        />
      ) : null}
    </section>
  )
}

function MatchDetail({ programId, match, uploadGrant, rosterMembers, onMatchChange, onUploadGrantChange, onAccessDenied, onRefresh, onRecordResult }) {
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
        ...Object.fromEntries(PREFLIGHT_FIELDS.filter((field) => form[field]).map((field) => [field, form[field]])),
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
            <CardDescription className="mt-1 text-slate-300">{[match.competition, formatDateOnly(match.match_date)].filter(Boolean).join(' · ') || 'Add match details below'}</CardDescription>
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
            <PreflightSelect id={`camera-view-${match.id}`} field="camera_view" label="Camera view" value={form.camera_view} onChange={(value) => updateForm('camera_view', value)} disabled={!editable} />
            <PreflightSelect id={`camera-motion-${match.id}`} field="camera_motion" label="Camera motion" value={form.camera_motion} onChange={(value) => updateForm('camera_motion', value)} disabled={!editable} />
            <PreflightSelect id={`pitch-lines-${match.id}`} field="pitch_lines_visible" label="Pitch lines visible" value={form.pitch_lines_visible} onChange={(value) => updateForm('pitch_lines_visible', value)} disabled={!editable} />
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

        {editable ? (
          <section className="space-y-3 border-t border-border pt-5" aria-labelledby={`match-${match.id}-result`}>
            <div>
              <h3 id={`match-${match.id}-result`} className="font-bold text-foreground">Record result</h3>
              <p className="text-sm text-muted-foreground">Save the score and club-confirmed stats for the players on this match roster.</p>
            </div>
            {match.roster.length === 0 ? <p className="text-sm text-amber-800">Select players and save the match roster first.</p> : null}
            <Button
              variant="outline"
              onClick={() => onRecordResult(match)}
              disabled={match.roster.length === 0}
              aria-label={`Record result for ${match.opponent_name || `match ${match.id}`}`}
            >
              <Trophy className="mr-1.5 h-4 w-4" /> Record result
            </Button>
          </section>
        ) : null}

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

        <ClubPlayerReels programId={programId} match={match} rosterMembers={rosterMembers} onAccessDenied={onAccessDenied} />
      </CardContent>
    </Card>
  )
}

function MatchesPanel({ programId, rosterMembers, matches, loading, error, loadFailureCount, uploadGrants, onMatchesChange, onUploadGrantChange, onReload, onAccessDenied }) {
  const [createOpen, setCreateOpen] = useState(false)
  const [resultTarget, setResultTarget] = useState(null)
  const [savedVideoResults, setSavedVideoResults] = useState({})
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

  // List rows are summaries without `roster`. MatchDetail must never start from a missing roster — a save would
  // then wipe the saved entries — so the selected match is fetched in full once, and the editor renders only after.
  const selectedMatchId = selectedMatch?.id || null
  const hydrated = Array.isArray(selectedMatch?.roster)
  const [hydrateError, setHydrateError] = useState(null) // { id, message } for the match whose fetch failed
  const [hydrateAttempt, setHydrateAttempt] = useState(0)
  useEffect(() => {
    if (!selectedMatchId || hydrated) return undefined
    let cancelled = false
    APIService.getClubMatch(programId, selectedMatchId)
      .then((full) => {
        if (cancelled) return
        setHydrateError(null)
        upsertMatch({ ...full, roster: Array.isArray(full?.roster) ? full.roster : [] })
      })
      .catch((requestError) => {
        if (cancelled) return
        if (requestError?.status === 403) {
          onAccessDenied()
          return
        }
        setHydrateError({ id: selectedMatchId, message: errorText(requestError, 'Match details could not be loaded. Try again.') })
      })
    return () => { cancelled = true }
  }, [selectedMatchId, hydrated, hydrateAttempt, programId, upsertMatch, onAccessDenied])
  const hydrateMessage = hydrateError?.id === selectedMatchId ? hydrateError.message : null

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 className="text-xl font-bold tracking-tight text-foreground">Matches &amp; reports</h2><p className="mt-1 text-sm text-muted-foreground">Create, upload and queue private match analysis.</p></div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => setResultTarget({ videoMatch: null, members: resultRosterMembers(null, rosterMembers), savedResult: null })}
            disabled={!rosterMembers.some((member) => member.available)}
            aria-label="Record result without video"
          >
            <Trophy className="mr-1.5 h-4 w-4" /> Record result
          </Button>
          <Button onClick={() => setCreateOpen(true)}><Plus className="mr-1.5 h-4 w-4" /> Create match</Button>
        </div>
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
      ) : error && loadFailureCount === 0 ? (
        <Card><CardContent className="space-y-3 py-10 text-center"><InlineError>{error}</InlineError><Button variant="outline" onClick={onReload}><RefreshCw className="mr-1.5 h-4 w-4" /> Try again</Button></CardContent></Card>
      ) : matches.length === 0 && loadFailureCount === 0 ? (
        <EmptyState icon={Film} title="No matches yet">Create the first match workspace. Your club's matches are saved to your account and follow you to any device.</EmptyState>
      ) : matches.length > 0 ? (
        <div className="grid items-start gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="space-y-2 lg:sticky lg:top-20">
            {matches.map((match) => {
              const selected = selectedMatch?.id === match.id
              return (
                <button key={match.id} type="button" onClick={() => setSelectedId(match.id)} className={`w-full rounded-xl border p-4 text-left transition-all ${selected ? 'border-primary/40 bg-primary/5 shadow-sm' : 'border-border bg-card hover:border-primary/25 hover:bg-muted/30'}`}>
                  <div className="flex items-start justify-between gap-3"><p className="truncate font-bold text-foreground">vs {match.opponent_name || 'Opponent TBD'}</p><ChevronRight className={`h-4 w-4 shrink-0 ${selected ? 'text-primary' : 'text-muted-foreground'}`} /></div>
                  <p className="mt-1 truncate text-xs text-muted-foreground">{[match.competition, formatDateOnly(match.match_date)].filter(Boolean).join(' · ') || `Match #${match.id}`}</p>
                  <div className="mt-3"><MatchStatusBadge status={match.status} /></div>
                </button>
              )
            })}
          </div>
          {selectedMatch && !hydrated ? (
            <Card><CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-muted-foreground">{hydrateMessage ? (<><InlineError>{hydrateMessage}</InlineError><Button variant="outline" onClick={() => { setHydrateError(null); setHydrateAttempt((n) => n + 1) }}><RefreshCw className="mr-1.5 h-4 w-4" /> Retry</Button></>) : (<span className="inline-flex items-center"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading match details…</span>)}</CardContent></Card>
          ) : selectedMatch ? (
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
              onRecordResult={(videoMatch) => setResultTarget({
                videoMatch,
                members: resultRosterMembers(videoMatch, rosterMembers),
                savedResult: savedVideoResults[String(videoMatch.id)] || null,
              })}
            />
          ) : null}
        </div>
      ) : null}
      <CreateMatchDialog open={createOpen} onOpenChange={setCreateOpen} programId={programId} onCreated={created} onAccessDenied={onAccessDenied} />
      {resultTarget ? (
        <RecordResultDialog
          programId={programId}
          videoMatch={resultTarget.videoMatch}
          members={resultTarget.members}
          savedResult={resultTarget.savedResult}
          onSaved={(response) => {
            const matchId = resultTarget.videoMatch?.id
            if (matchId) setSavedVideoResults((current) => ({ ...current, [String(matchId)]: response }))
          }}
          onClose={() => setResultTarget(null)}
          onAccessDenied={onAccessDenied}
        />
      ) : null}
    </div>
  )
}

const EMPTY_PROFILE_FORM = {
  summary: '', age_groups: '', activities: '', funding_purpose: '', official_url: '', safeguarding_url: '', media_urls: '', external_support_provider: 'none', external_support_url: '',
}

function profileForm(revision) {
  if (!revision) return EMPTY_PROFILE_FORM
  return {
    summary: revision.summary || '',
    age_groups: (revision.age_groups || []).join(', '),
    activities: (revision.activities || []).join(', '),
    funding_purpose: revision.funding_purpose || '',
    official_url: revision.official_url || '',
    safeguarding_url: revision.safeguarding_url || '',
    media_urls: (revision.media_urls || []).join('\n'),
    external_support_provider: revision.external_support?.provider || 'none',
    external_support_url: revision.external_support?.url || '',
  }
}

function splitValues(value, separator) {
  return String(value || '').split(separator).map((item) => item.trim()).filter(Boolean)
}

function ReadOnlyClubProfile({ program, claim }) {
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
          ['Verified', formatTimestampDate(program.verified_at)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-secondary/25 p-4"><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p><p className="mt-1.5 font-semibold capitalize text-foreground">{value || '—'}</p></div>
        ))}
      </CardContent>
    </Card>
  )
}

function ClubProfile({ program, claim, onAccessDenied }) {
  const deniedRef = useRef(onAccessDenied)
  const [profile, setProfile] = useState(null)
  const [updates, setUpdates] = useState([])
  const [loadState, setLoadState] = useState('loading')
  const [form, setForm] = useState(EMPTY_PROFILE_FORM)
  const [updateForm, setUpdateForm] = useState({ title: '', body: '', impact: '' })
  const [saving, setSaving] = useState(false)
  const [posting, setPosting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState({})
  const [updateErrors, setUpdateErrors] = useState({})
  const [message, setMessage] = useState(null)

  useEffect(() => {
    deniedRef.current = onAccessDenied
  }, [onAccessDenied])

  const load = useCallback(async () => {
    setLoadState('loading')
    setMessage(null)
    try {
      const [profileResult, updateResult] = await Promise.allSettled([
        APIService.getClubProfile(program.id),
        APIService.listClubUpdates(program.id),
      ])
      const profileData = profileResult.status === 'fulfilled' ? profileResult.value : undefined
      const updateData = updateResult.status === 'fulfilled' ? updateResult.value : undefined
      if (profileData === null || updateData === null) {
        setLoadState('unavailable')
        return
      }
      if (profileResult.status === 'rejected') throw profileResult.reason
      if (updateResult.status === 'rejected') throw updateResult.reason
      setProfile(profileData)
      setUpdates(updateData?.updates || [])
      setForm(profileForm(profileData?.pending || profileData?.approved))
      setLoadState('ready')
    } catch (error) {
      setLoadState('failed')
      if (error?.status === 403) deniedRef.current()
    }
  }, [program.id])

  useEffect(() => {
    const timer = setTimeout(load, 0)
    return () => clearTimeout(timer)
  }, [load])

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFieldErrors({})
    setMessage(null)
    const externalSupport = form.external_support_provider === 'none'
      ? null
      : { provider: form.external_support_provider, url: form.external_support_url.trim() }
    const payload = {
      summary: form.summary,
      age_groups: splitValues(form.age_groups, ','),
      activities: splitValues(form.activities, ','),
      funding_purpose: form.funding_purpose,
      official_url: form.official_url,
      safeguarding_url: form.safeguarding_url,
      media_urls: splitValues(form.media_urls, /\n/),
      external_support: externalSupport,
    }
    try {
      const result = await APIService.putClubProfile(program.id, payload)
      setProfile((current) => ({ ...current, pending: result.pending }))
      setForm(profileForm(result.pending))
      setMessage({ type: 'success', text: 'Profile submitted for review.' })
    } catch (error) {
      if (error?.status === 403) deniedRef.current()
      else if (error?.status === 400 && error?.body?.error === 'validation_failed') setFieldErrors(error.body.fields || {})
      else setMessage({ type: 'error', text: errorText(error, 'Profile could not be saved.') })
    } finally {
      setSaving(false)
    }
  }

  const postUpdate = async (event) => {
    event.preventDefault()
    setPosting(true)
    setMessage(null)
    setUpdateErrors({})
    try {
      const result = await APIService.createClubUpdate(program.id, updateForm)
      setUpdates((current) => [result.update, ...current])
      setUpdateForm({ title: '', body: '', impact: '' })
      setMessage({ type: 'success', text: 'Update submitted for review.' })
    } catch (error) {
      if (error?.status === 403) deniedRef.current()
      else if (error?.status === 409 && error?.body?.error === 'pending_limit_reached') setMessage({ type: 'error', text: 'You already have 5 updates pending review.' })
      else if (error?.status === 400 && error?.body?.error === 'validation_failed') setUpdateErrors(error.body.fields || {})
      else setMessage({ type: 'error', text: errorText(error, 'Update could not be submitted.') })
    } finally {
      setPosting(false)
    }
  }

  const removeUpdate = async (update) => {
    try {
      const result = await APIService.deleteClubUpdate(program.id, update.id)
      setUpdates((current) => result.deleted
        ? current.filter((item) => item.id !== update.id)
        : current.map((item) => item.id === update.id ? { ...item, status: result.status } : item))
    } catch (error) {
      if (error?.status === 403) deniedRef.current()
      else setMessage({ type: 'error', text: errorText(error, 'Update could not be removed.') })
    }
  }

  if (loadState === 'loading') return <Card><CardContent className="flex items-center justify-center py-16 text-sm text-muted-foreground"><Loader2 className="mr-2 h-5 w-5 animate-spin" />Loading club profile…</CardContent></Card>
  if (loadState === 'unavailable') return <ReadOnlyClubProfile program={program} claim={claim} />
  if (loadState === 'failed') return <Card><CardHeader><CardTitle>Club profile couldn&apos;t be loaded.</CardTitle><CardDescription>Your existing profile and updates have not been changed.</CardDescription></CardHeader><CardContent><Button variant="outline" onClick={load}>Retry</Button></CardContent></Card>

  const edit = (field, value) => setForm((current) => ({ ...current, [field]: value }))
  const selectSupportProvider = (value) => setForm((current) => ({
    ...current,
    external_support_provider: value,
    external_support_url: value === 'none' ? '' : current.external_support_url,
  }))
  const profileField = (id, label, control) => <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{control}{fieldErrors[id] ? <p className="text-xs text-destructive">{fieldErrors[id]}</p> : null}</div>

  return (
    <div className="space-y-6">
      {message ? <Alert className={message.type === 'error' ? 'border-rose-300 bg-rose-50' : 'border-emerald-300 bg-emerald-50'}><AlertCircle className="h-4 w-4" /><AlertDescription>{message.text}</AlertDescription></Alert> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <Card><CardHeader><CardTitle>Approved</CardTitle><CardDescription>The profile currently visible to the public.</CardDescription></CardHeader><CardContent>{profile?.approved ? <><Badge>{profile.approved.status}</Badge><p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">{profile.approved.summary || 'No summary supplied.'}</p></> : <p className="text-sm text-muted-foreground">No approved profile revision yet.</p>}</CardContent></Card>
        <Card className="border-amber-200"><CardHeader><CardTitle>Pending review</CardTitle><CardDescription>Saving replaces this draft; it never changes the approved profile directly.</CardDescription></CardHeader><CardContent>{profile?.pending ? <><Badge className="border-amber-200 bg-amber-50 text-amber-800">{profile.pending.status}</Badge><p className="mt-3 text-sm text-muted-foreground">Submitted {formatTimestampDate(profile.pending.created_at) || 'for review'}.</p></> : <p className="text-sm text-muted-foreground">No revision is waiting for review.</p>}</CardContent></Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Edit program profile</CardTitle><CardDescription>Public content is moderated before publication.</CardDescription></CardHeader>
        <CardContent><form className="space-y-5" onSubmit={save}>
          {profileField('summary', 'Summary', <Textarea id="summary" value={form.summary} onChange={(event) => edit('summary', event.target.value)} maxLength={profile?.limits?.summary_max || 2000} rows={5} />)}
          <div className="grid gap-4 sm:grid-cols-2">{profileField('age_groups', 'Age groups (comma separated)', <Input id="age_groups" value={form.age_groups} onChange={(event) => edit('age_groups', event.target.value)} placeholder="U12, U14, U16" />)}{profileField('activities', 'Activities (comma separated)', <Input id="activities" value={form.activities} onChange={(event) => edit('activities', event.target.value)} placeholder="Training, league matches" />)}</div>
          {profileField('funding_purpose', 'Funding purpose', <Textarea id="funding_purpose" value={form.funding_purpose} onChange={(event) => edit('funding_purpose', event.target.value)} maxLength={profile?.limits?.funding_purpose_max || 1000} rows={3} />)}
          <div className="grid gap-4 sm:grid-cols-2">{profileField('official_url', 'Official URL', <Input id="official_url" type="url" value={form.official_url} onChange={(event) => edit('official_url', event.target.value)} placeholder="https://…" />)}{profileField('safeguarding_url', 'Safeguarding URL', <Input id="safeguarding_url" type="url" value={form.safeguarding_url} onChange={(event) => edit('safeguarding_url', event.target.value)} placeholder="https://…" />)}</div>
          {profileField('media_urls', 'Media URLs (one per line)', <Textarea id="media_urls" value={form.media_urls} onChange={(event) => edit('media_urls', event.target.value)} rows={3} placeholder="https://…" />)}
          <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-1.5"><Label htmlFor="external_support_provider">External support provider</Label><Select value={form.external_support_provider} onValueChange={selectSupportProvider}><SelectTrigger id="external_support_provider"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem><SelectItem value="patreon">Patreon</SelectItem><SelectItem value="buy_me_a_coffee">Buy Me a Coffee</SelectItem></SelectContent></Select>{fieldErrors.external_support ? <p className="text-xs text-destructive">{fieldErrors.external_support}</p> : null}</div>{profileField('external_support_url', 'External support URL', <Input id="external_support_url" type="url" value={form.external_support_url} onChange={(event) => edit('external_support_url', event.target.value)} placeholder="https://patreon.com/your-program" />)}</div>
          <Button type="submit" disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}Save for review</Button>
        </form></CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Updates</CardTitle><CardDescription>Share program news after admin review. Up to {profile?.limits?.updates_pending_max || 5} may be pending.</CardDescription></CardHeader>
        <CardContent className="space-y-6">
          <form onSubmit={postUpdate} className="space-y-3 rounded-xl border bg-secondary/20 p-4"><div className="space-y-1.5"><Label htmlFor="update-title">Title</Label><Input id="update-title" value={updateForm.title} onChange={(event) => setUpdateForm((current) => ({ ...current, title: event.target.value }))} minLength={3} maxLength={140} required />{updateErrors.title ? <p className="text-xs text-destructive">{updateErrors.title}</p> : null}</div><div className="space-y-1.5"><Label htmlFor="update-body">Body</Label><Textarea id="update-body" value={updateForm.body} onChange={(event) => setUpdateForm((current) => ({ ...current, body: event.target.value }))} minLength={20} maxLength={4000} rows={4} required />{updateErrors.body ? <p className="text-xs text-destructive">{updateErrors.body}</p> : null}</div><div className="space-y-1.5"><Label htmlFor="update-impact">Impact (optional)</Label><Textarea id="update-impact" value={updateForm.impact} onChange={(event) => setUpdateForm((current) => ({ ...current, impact: event.target.value }))} maxLength={500} rows={2} />{updateErrors.impact ? <p className="text-xs text-destructive">{updateErrors.impact}</p> : null}</div><Button type="submit" disabled={posting}>{posting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}Submit update</Button></form>
          <div className="space-y-3">{updates.length ? updates.map((update) => <article key={update.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{update.title}</h3><Badge variant="outline" className="capitalize">{update.status}</Badge></div><p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{update.body}</p>{update.impact ? <p className="mt-2 text-sm"><strong>Impact:</strong> {update.impact}</p> : null}{update.review_reason ? <p className="mt-2 text-xs text-muted-foreground">Review note: {update.review_reason}</p> : null}{update.status !== 'withdrawn' ? <Button variant="ghost" size="sm" className="mt-3 text-destructive" onClick={() => removeUpdate(update)}><Trash2 className="mr-1.5 h-4 w-4" />{update.status === 'approved' ? 'Withdraw' : 'Delete'}</Button> : null}</article>) : <p className="text-sm text-muted-foreground">No updates submitted yet.</p>}</div>
        </CardContent>
      </Card>
    </div>
  )
}

export function MyClubConsole({
  programClaim,
  initialRoster,
  programOptions,
  moderationContent,
  moderationCount = 0,
  erroredProgramCount = 0,
  checkingPrograms = false,
  onProgramChange,
  onRetryPrograms,
  onAccessDenied,
}) {
  const program = programClaim.program
  const programId = program.id
  const contactRail = useContactRail()
  const [members, setMembers] = useState(() => (Array.isArray(initialRoster?.members) ? initialRoster.members : []))
  const [systemBrief, setSystemBrief] = useState(() => initialRoster?.system_brief || { body: null, updated_at: null, hash: null })
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
      if (mountedRef.current) {
        setMembers(Array.isArray(response?.members) ? response.members : [])
        setSystemBrief(response?.system_brief || { body: null, updated_at: null, hash: null })
      }
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
    try {
      const response = await APIService.listClubMatches(programId)
      if (!mountedRef.current) return
      setMatches(Array.isArray(response?.matches) ? response.matches : [])
    } catch (error) {
      if (!mountedRef.current) return
      if (error?.status === 403) {
        onAccessDenied()
        return
      }
      setMatches([])
      setMatchesLoadFailureCount(1)
      setMatchesError(errorText(error, 'Matches could not be loaded. Try again.'))
    } finally {
      if (mountedRef.current) setMatchesLoading(false)
    }
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

        {erroredProgramCount > 0 ? (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-800" />
            <AlertDescription className="flex flex-wrap items-center gap-1 text-amber-950">
              {erroredProgramCount} {erroredProgramCount === 1 ? 'club' : 'clubs'} couldn&apos;t be checked —
              <Button
                variant="link"
                className="h-auto p-0 text-amber-950 underline"
                onClick={onRetryPrograms}
                disabled={checkingPrograms}
              >
                {checkingPrograms ? 'Checking…' : 'Retry'}
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        <Tabs defaultValue="roster" className="gap-5">
          <TabsList className={`grid h-auto w-full grid-cols-2 bg-slate-200/70 p-1 ${moderationContent ? 'sm:grid-cols-5 lg:min-w-[55rem]' : 'sm:grid-cols-4 lg:min-w-[44rem]'} lg:w-fit`}>
            <TabsTrigger value="roster" className="py-2"><Users className="h-4 w-4" /> Roster</TabsTrigger>
            <TabsTrigger value="matches" className="py-2"><Film className="h-4 w-4" /> Matches &amp; reports</TabsTrigger>
            <TabsTrigger value="profile" className="py-2"><ShieldCheck className="h-4 w-4" /> Club profile</TabsTrigger>
            {contactRail === true ? <TabsTrigger value="introductions" className="py-2"><Send className="h-4 w-4" /> Introductions</TabsTrigger> : null}
            {moderationContent ? (
              <TabsTrigger value="affiliations" className="py-2">
                <Check className="h-4 w-4" /> Affiliations &amp; vouches
                {moderationCount > 0 ? <Badge className="ml-1 border-amber-300 bg-amber-100 text-amber-900">{moderationCount}</Badge> : null}
              </TabsTrigger>
            ) : null}
          </TabsList>
          <TabsContent value="roster">
            <RosterPanel programId={programId} members={members} systemBrief={systemBrief} loading={rosterLoading} error={rosterError} onMembersChange={setMembers} onSystemBriefChange={setSystemBrief} onReload={loadRoster} onAccessDenied={onAccessDenied} />
          </TabsContent>
          <TabsContent value="matches">
            <MatchesPanel programId={programId} rosterMembers={members} matches={matches} loading={matchesLoading} error={matchesError} loadFailureCount={matchesLoadFailureCount} uploadGrants={uploadGrants} onMatchesChange={setMatches} onUploadGrantChange={setGrant} onReload={loadMatches} onAccessDenied={onAccessDenied} />
          </TabsContent>
          <TabsContent value="profile"><ClubProfile program={program} claim={programClaim} onAccessDenied={onAccessDenied} /></TabsContent>
          {contactRail === true ? <TabsContent value="introductions"><ClubIntroductionsPanel programId={programId} onAccessDenied={onAccessDenied} /></TabsContent> : null}
          {moderationContent ? <TabsContent value="affiliations">{moderationContent}</TabsContent> : null}
        </Tabs>

        <p className="flex items-center justify-center gap-2 text-center text-xs text-muted-foreground"><LockKeyhole className="h-3.5 w-3.5" /> Club-console data is manager-only. Opposition players remain anonymous.</p>
      </div>
    </div>
  )
}

export default MyClubConsole
