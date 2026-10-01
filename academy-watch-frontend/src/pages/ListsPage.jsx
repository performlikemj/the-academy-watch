import { useDataMode } from '@/hooks/useDataMode'
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { track } from '@/lib/track'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import TeamSelect from '@/components/ui/TeamSelect'
import { StatusBadge, PlayerCell } from './ScoutPage'
import { ScoutSurface, ScoutHeader, DeskSectionTitle, deskPillClass } from '@/components/scout/ScoutDesk'
import {
  ListChecks, Plus, X, Loader2, Search, Trash2, Star, Users, MapPin, Filter, Check,
} from 'lucide-react'

const POSITION_OPTIONS = [
  { value: 'Goalkeeper', label: 'Goalkeeper' },
  { value: 'Defender', label: 'Defender' },
  { value: 'Midfielder', label: 'Midfielder' },
  { value: 'Attacker', label: 'Attacker' },
]

const STATUS_OPTIONS = [
  { value: 'academy', label: 'Academy' },
  { value: 'on_loan', label: 'On loan' },
  { value: 'first_team', label: 'First team' },
  { value: 'sold', label: 'Sold' },
  { value: 'released', label: 'Released' },
  { value: 'left', label: 'Left' },
]

const KIND_META = [
  { kind: 'player', title: 'Players', icon: Star },
  { kind: 'academy_club', title: 'Club academies', icon: Users },
  { kind: 'geo', title: 'Countries', icon: MapPin },
  { kind: 'query', title: 'Saved searches', icon: Filter },
]

const titleCase = (s) => (s || '')
  .trim()
  .replace(/\s+/g, ' ')
  .split(' ')
  .map((w) => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : ''))
  .join(' ')

// Human label for a follow — prefer the server-derived label, fall back to selector.
function followLabel(follow) {
  if (follow.label) return follow.label
  const sel = follow.selector || {}
  switch (follow.kind) {
    case 'player':
      return sel.player_api_id ? `Player #${sel.player_api_id}` : 'Player'
    case 'academy_club':
      return sel.team_id ? `Club academy #${sel.team_id}` : 'Club academy'
    case 'geo': {
      const countries = (sel.countries || []).join(', ')
      const verb = sel.match === 'nationality' ? 'Nationality' : 'Playing in'
      return `${verb}: ${countries || '—'}`
    }
    case 'query': {
      const args = sel.scout_args || {}
      const parts = []
      if (args.position) parts.push(args.position)
      if (args.status) parts.push(String(args.status).replace('_', ' '))
      if (args.min_age || args.max_age) parts.push(`${args.min_age || ''}-${args.max_age || ''} yrs`.trim())
      if (args.nationality) parts.push(args.nationality)
      if (args.min_minutes) parts.push(`${args.min_minutes}+ mins`)
      return `Filter: ${parts.join(', ') || 'any'}`
    }
    default:
      return follow.kind
  }
}

function PlayerSearchTab({ onAdd, adding, addError }) {
  const { api_football_frozen: frozen } = useDataMode()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [added, setAdded] = useState(() => new Set())
  const timer = useRef(null)

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setDebounced(query.trim()), 300)
    return () => clearTimeout(timer.current)
  }, [query])

  useEffect(() => {
    if (debounced.length < 3) {
      setResults([])
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    track('search_performed', { q_len: debounced.length, surface: 'lists' })
    APIService.scoutPlayerSearch(debounced)
      .then((data) => { if (!cancelled) setResults(data?.players || []) })
      .catch((err) => { if (!cancelled) { setError(err.message || 'Search failed'); setResults([]) } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [debounced])

  const handleAdd = async (row) => {
    const ok = await onAdd({ kind: 'player', selector: { player_api_id: row.player_api_id } })
    if (ok) setAdded((prev) => new Set(prev).add(row.player_api_id))
  }

  return (
    <div className="space-y-3">
      {frozen && <p className="text-sm text-muted-foreground">Search stored records. Can’t find them? <Link className="underline" to="/local-players/new">Create a local profile</Link>.</p>}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={frozen ? 'Search stored players by name…' : 'Search players worldwide by name…'}
          className="pl-9"
          aria-label="Search players"
          autoFocus
        />
      </div>
      {addError && <p className="text-xs text-destructive">{addError}</p>}
      {query.trim().length > 0 && query.trim().length < 3 && (
        <p className="text-xs text-muted-foreground">Type at least 3 characters to search.</p>
      )}
      <div className="max-h-72 overflow-y-auto">
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-11 w-full" />)}
          </div>
        ) : error ? (
          <p className="py-6 text-center text-sm text-destructive">{error}</p>
        ) : results.length ? (
          <ul className="divide-y divide-border/50">
            {results.map((row) => {
              const isAdded = added.has(row.player_api_id)
              return (
                <li key={row.player_api_id}>
                  <button
                    type="button"
                    onClick={() => handleAdd(row)}
                    disabled={isAdded || adding}
                    className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-secondary/60 disabled:opacity-70"
                  >
                    {row.photo ? (
                      <img src={row.photo} alt="" loading="lazy" className="h-9 w-9 shrink-0 rounded-full bg-secondary object-cover" />
                    ) : (
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-muted-foreground">
                        {row.name?.slice(0, 2).toUpperCase()}
                      </span>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-foreground">{row.name}</span>
                        {!row.tracked && (
                          <Badge variant="outline" className="shrink-0 text-[10px] font-normal">
                            {frozen ? 'Stored public record' : row.shadow ? 'Worldwide' : 'Worldwide — will start tracking'}
                          </Badge>
                        )}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {[row.nationality, row.age ? `${row.age} yrs` : null, row.club_name].filter(Boolean).join(' · ') || '—'}
                      </span>
                    </span>
                    {isAdded ? (
                      <Check className="h-4 w-4 shrink-0 text-emerald-500" />
                    ) : (
                      <Plus className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        ) : debounced.length >= 3 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No players found for “{debounced}”.</p>
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Search any player in the world. Following one outside the tracked universe starts tracking them.
          </p>
        )}
      </div>
    </div>
  )
}

function ClubTab({ onAdd, adding, addError }) {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [teamId, setTeamId] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    // All supported regions — the follow graph is a worldwide feature
    APIService.getTeams()
      .then((data) => { if (!cancelled) setTeams(Array.isArray(data) ? data : (data?.teams || [])) })
      .catch((err) => { console.error('Failed to load teams', err); if (!cancelled) setTeams([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const handleAdd = async () => {
    if (!teamId) return
    const ok = await onAdd({ kind: 'academy_club', selector: { team_id: teamId } })
    if (ok) setTeamId(null)
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Follow a club&apos;s whole academy — every tracked player from that club stays in this list.
      </p>
      {loading ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <TeamSelect teams={teams} value={teamId} onChange={setTeamId} placeholder="Select a club…" />
      )}
      {addError && <p className="text-xs text-destructive">{addError}</p>}
      <Button onClick={handleAdd} disabled={!teamId || adding} className="w-full sm:w-auto">
        {adding ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plus className="mr-1.5 h-4 w-4" />}
        Add club academy
      </Button>
    </div>
  )
}

function CountriesTab({ onAdd, adding, addError }) {
  const [input, setInput] = useState('')
  const [countries, setCountries] = useState([])
  const [match, setMatch] = useState('playing_in')

  const addCountry = () => {
    const value = titleCase(input)
    if (!value) return
    if (value.length > 50) return
    setCountries((prev) => (prev.includes(value) || prev.length >= 10 ? prev : [...prev, value]))
    setInput('')
  }

  const removeCountry = (value) => setCountries((prev) => prev.filter((c) => c !== value))

  const handleAdd = async () => {
    if (!countries.length) return
    const ok = await onAdd({ kind: 'geo', selector: { countries, match } })
    if (ok) { setCountries([]); setInput('') }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Follow players by country — either where they currently play or their nationality.
      </p>
      <ToggleGroup
        type="single"
        value={match}
        onValueChange={(v) => v && setMatch(v)}
        variant="outline"
        className="w-full"
      >
        <ToggleGroupItem value="playing_in" className="flex-1">Playing in</ToggleGroupItem>
        <ToggleGroupItem value="nationality" className="flex-1">Nationality</ToggleGroupItem>
      </ToggleGroup>
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCountry() } }}
          placeholder="Type a country and press Enter…"
          aria-label="Add country"
          disabled={countries.length >= 10}
        />
        <Button type="button" variant="outline" onClick={addCountry} disabled={!input.trim() || countries.length >= 10}>
          Add
        </Button>
      </div>
      {countries.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {countries.map((c) => (
            <span key={c} className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-foreground">
              {c}
              <button
                type="button"
                onClick={() => removeCountry(c)}
                className="text-muted-foreground hover:text-destructive"
                aria-label={`Remove ${c}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">{countries.length}/10 countries</p>
      {addError && <p className="text-xs text-destructive">{addError}</p>}
      <Button onClick={handleAdd} disabled={!countries.length || adding} className="w-full sm:w-auto">
        {adding ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plus className="mr-1.5 h-4 w-4" />}
        Add country follow
      </Button>
    </div>
  )
}

function FiltersTab({ onAdd, adding, addError }) {
  const [position, setPosition] = useState('all')
  const [status, setStatus] = useState('all')
  const [minAge, setMinAge] = useState('')
  const [maxAge, setMaxAge] = useState('')
  const [minMinutes, setMinMinutes] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const args = useMemo(() => {
    const built = {}
    if (position !== 'all') built.position = position
    if (status !== 'all') built.status = status
    const minA = parseInt(minAge, 10)
    const maxA = parseInt(maxAge, 10)
    const minM = parseInt(minMinutes, 10)
    if (Number.isInteger(minA)) built.min_age = minA
    if (Number.isInteger(maxA)) built.max_age = maxA
    if (Number.isInteger(minM)) built.min_minutes = minM
    return built
  }, [position, status, minAge, maxAge, minMinutes])
  const hasArgs = Object.keys(args).length > 0

  // Live preview: show who the standing search catches TODAY before following.
  useEffect(() => {
    if (!hasArgs) { setPreview(null); return undefined }
    let cancelled = false
    setPreviewLoading(true)
    const timer = setTimeout(() => {
      APIService.getScoutPlayers({ ...args, per_page: 3 })
        .then((data) => {
          if (cancelled) return
          setPreview({
            total: data?.total ?? 0,
            names: (data?.players || []).map((p) => p.player_name).filter(Boolean),
          })
        })
        .catch(() => { if (!cancelled) setPreview(null) })
        .finally(() => { if (!cancelled) setPreviewLoading(false) })
    }, 400)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [args, hasArgs])

  const handleAdd = async () => {
    if (!hasArgs) return
    const ok = await onAdd({ kind: 'query', selector: { scout_args: args } })
    if (ok) { setPosition('all'); setStatus('all'); setMinAge(''); setMaxAge(''); setMinMinutes('') }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        A standing scouting brief: whoever matches is in your list — including{' '}
        <span className="font-medium text-foreground">new players who qualify later, automatically</span>.
        Use it to catch risers you don&apos;t know about yet.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs font-medium text-muted-foreground">Position</span>
          <Select value={position} onValueChange={setPosition}>
            <SelectTrigger className="w-full" aria-label="Position"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any position</SelectItem>
              {POSITION_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-muted-foreground">Status</span>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-full" aria-label="Status"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any status</SelectItem>
              {STATUS_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-muted-foreground">Min age</span>
          <Input type="number" inputMode="numeric" min="14" max="45" value={minAge} onChange={(e) => setMinAge(e.target.value)} placeholder="16" />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-muted-foreground">Max age</span>
          <Input type="number" inputMode="numeric" min="14" max="45" value={maxAge} onChange={(e) => setMaxAge(e.target.value)} placeholder="21" />
        </label>
        <label className="space-y-1 sm:col-span-2">
          <span className="text-xs font-medium text-muted-foreground">Min minutes played</span>
          <Input type="number" inputMode="numeric" min="0" value={minMinutes} onChange={(e) => setMinMinutes(e.target.value)} placeholder="270" />
        </label>
      </div>
      {hasArgs && (
        <div className="rounded-md border border-border/60 bg-secondary/40 px-3 py-2 text-sm">
          {previewLoading ? (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking who matches…
            </span>
          ) : preview ? (
            preview.total > 0 ? (
              <span>
                Catches <span className="font-semibold text-foreground">{preview.total.toLocaleString()}</span>{' '}
                {preview.total === 1 ? 'player' : 'players'} today
                {preview.names.length > 0 && (
                  <span className="text-muted-foreground"> — e.g. {preview.names.join(', ')}</span>
                )}
              </span>
            ) : (
              <span className="text-muted-foreground">
                No players match today — the search stays live and future risers who qualify will appear automatically.
              </span>
            )
          ) : null}
        </div>
      )}
      {addError && <p className="text-xs text-destructive">{addError}</p>}
      <Button onClick={handleAdd} disabled={!hasArgs || adding} className="w-full sm:w-auto">
        {adding ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plus className="mr-1.5 h-4 w-4" />}
        Follow this search
      </Button>
    </div>
  )
}

function AddFollowDialog({ open, onOpenChange, onAdd, adding, addError }) {
  const [tab, setTab] = useState('player')

  useEffect(() => {
    if (open) setTab('player')
  }, [open])

  // Wrap onAdd so any tab closes only the ones that make sense; player tab stays open.
  const handleAdd = useCallback(async (payload) => {
    const ok = await onAdd(payload)
    if (ok && payload.kind !== 'player') onOpenChange(false)
    return ok
  }, [onAdd, onOpenChange])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a follow</DialogTitle>
          <DialogDescription>
            Follow a specific player, a club&apos;s academy, countries — or save a search that keeps catching new players.
          </DialogDescription>
        </DialogHeader>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="player">Player</TabsTrigger>
            <TabsTrigger value="academy_club">Club</TabsTrigger>
            <TabsTrigger value="geo">Countries</TabsTrigger>
            <TabsTrigger value="query">Saved search</TabsTrigger>
          </TabsList>
          <TabsContent value="player" className="pt-3">
            <PlayerSearchTab onAdd={handleAdd} adding={adding} addError={tab === 'player' ? addError : null} />
          </TabsContent>
          <TabsContent value="academy_club" className="pt-3">
            <ClubTab onAdd={handleAdd} adding={adding} addError={tab === 'academy_club' ? addError : null} />
          </TabsContent>
          <TabsContent value="geo" className="pt-3">
            <CountriesTab onAdd={handleAdd} adding={adding} addError={tab === 'geo' ? addError : null} />
          </TabsContent>
          <TabsContent value="query" className="pt-3">
            <FiltersTab onAdd={handleAdd} adding={adding} addError={tab === 'query' ? addError : null} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

export function ListsPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()

  const [lists, setLists] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedListId, setSelectedListId] = useState(null)

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [createSaving, setCreateSaving] = useState(false)
  const [createError, setCreateError] = useState(null)

  const [addOpen, setAddOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState(null)

  const [preview, setPreview] = useState({ players: [], total: 0, offset: 0 })
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(null)
  const [previewNonce, setPreviewNonce] = useState(0)

  const selectedList = lists.find((l) => l.id === selectedListId) || null

  // Load lists when signed in
  useEffect(() => {
    if (!auth?.token) {
      setLists([])
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    APIService.getFollowLists()
      .then((data) => {
        if (cancelled) return
        const arr = data?.lists || []
        setLists(arr)
        setSelectedListId((prev) => (prev && arr.some((l) => l.id === prev) ? prev : (arr[0]?.id ?? null)))
      })
      .catch((err) => { if (!cancelled) setError(err.message || 'Failed to load lists') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [auth?.token])

  // Load resolved preview for the selected list
  useEffect(() => {
    if (!selectedListId) {
      setPreview({ players: [], total: 0, offset: 0 })
      return
    }
    let cancelled = false
    setPreviewLoading(true)
    setPreviewError(null)
    APIService.resolveFollowList(selectedListId, { limit: 20, offset: 0 })
      .then((data) => {
        if (cancelled) return
        const players = data?.players || []
        setPreview({ players, total: data?.total ?? players.length, offset: players.length })
      })
      .catch((err) => {
        if (cancelled) return
        setPreviewError(err.message || 'Failed to resolve list')
        setPreview({ players: [], total: 0, offset: 0 })
      })
      .finally(() => { if (!cancelled) setPreviewLoading(false) })
    return () => { cancelled = true }
  }, [selectedListId, previewNonce])

  const reloadPreview = useCallback(() => setPreviewNonce((n) => n + 1), [])

  const loadMorePreview = useCallback(async () => {
    if (!selectedListId || previewLoading) return
    setPreviewLoading(true)
    try {
      const data = await APIService.resolveFollowList(selectedListId, { limit: 20, offset: preview.offset })
      const more = data?.players || []
      setPreview((prev) => ({
        players: [...prev.players, ...more],
        total: data?.total ?? prev.total,
        offset: prev.offset + more.length,
      }))
    } catch (err) {
      setPreviewError(err.message || 'Failed to load more')
    } finally {
      setPreviewLoading(false)
    }
  }, [selectedListId, previewLoading, preview.offset])

  const handleCreate = useCallback(async () => {
    const name = newName.trim()
    if (!name) return
    setCreateSaving(true)
    setCreateError(null)
    try {
      const res = await APIService.createFollowList(name)
      const created = res?.list
      if (created) {
        track('list_created', { list_id: created.id })
        setLists((prev) => [...prev, created])
        setSelectedListId(created.id)
      }
      setNewName('')
      setCreating(false)
    } catch (err) {
      setCreateError(err.body?.error || err.message || 'Failed to create list')
    } finally {
      setCreateSaving(false)
    }
  }, [newName])

  const handleToggleActive = useCallback((list, checked) => {
    setLists((prev) => prev.map((l) => (l.id === list.id ? { ...l, is_active: checked } : l)))
    APIService.updateFollowList(list.id, { is_active: checked }).catch((err) => {
      console.error('Failed to toggle list', err)
      setLists((prev) => prev.map((l) => (l.id === list.id ? { ...l, is_active: !checked } : l)))
    })
  }, [])

  const handleDelete = useCallback((list) => {
    let removedIndex = -1
    setLists((prev) => {
      removedIndex = prev.findIndex((l) => l.id === list.id)
      return prev.filter((l) => l.id !== list.id)
    })
    setSelectedListId((prev) => {
      if (prev !== list.id) return prev
      const remaining = lists.filter((l) => l.id !== list.id)
      return remaining[0]?.id ?? null
    })
    APIService.deleteFollowList(list.id).catch((err) => {
      console.error('Failed to delete list', err)
      // Revert
      setLists((prev) => {
        if (prev.some((l) => l.id === list.id)) return prev
        const next = [...prev]
        next.splice(Math.min(Math.max(removedIndex, 0), next.length), 0, list)
        return next
      })
    })
  }, [lists])

  const handleAddFollow = useCallback(async (payload) => {
    if (!selectedListId) return false
    setAdding(true)
    setAddError(null)
    try {
      const res = await APIService.addFollow(selectedListId, payload)
      const follow = res?.follow
      track('follow_added', { kind: payload.kind })
      if (res?.shadow_created === true) {
        track('shadow_minted', { player_api_id: payload.selector?.player_api_id })
      }
      if (follow) {
        setLists((prev) => prev.map((l) => (
          l.id === selectedListId
            ? { ...l, follows: [...(l.follows || []), follow], follow_count: (l.follow_count ?? (l.follows || []).length) + 1 }
            : l
        )))
      }
      reloadPreview()
      return true
    } catch (err) {
      setAddError(err.body?.error || err.message || 'Failed to add follow')
      return false
    } finally {
      setAdding(false)
    }
  }, [selectedListId, reloadPreview])

  const handleRemoveFollow = useCallback((follow) => {
    if (!selectedListId) return
    setLists((prev) => prev.map((l) => (
      l.id === selectedListId
        ? {
            ...l,
            follows: (l.follows || []).filter((f) => f.id !== follow.id),
            follow_count: Math.max(0, (l.follow_count ?? (l.follows || []).length) - 1),
          }
        : l
    )))
    APIService.removeFollow(selectedListId, follow.id)
      .then(() => reloadPreview())
      .catch((err) => {
        console.error('Failed to remove follow', err)
        setLists((prev) => prev.map((l) => (
          l.id === selectedListId && !(l.follows || []).some((f) => f.id === follow.id)
            ? { ...l, follows: [...(l.follows || []), follow], follow_count: (l.follow_count ?? (l.follows || []).length) + 1 }
            : l
        )))
      })
  }, [selectedListId, reloadPreview])

  const followCount = (list) => (list.follows ? list.follows.length : (list.follow_count ?? 0))

  // Signed out
  if (!auth?.token) {
    return (
      <ScoutSurface>
        <div className="floodlight-container flex justify-center py-24">
          <div className="flex w-full max-w-md flex-col items-center gap-5 text-center">
            <span className="inline-flex h-14 w-14 items-center justify-center rounded-full border border-gold/60">
              <ListChecks className="h-6 w-6 text-gold" />
            </span>
            <h1 className="display text-4xl text-chalk sm:text-5xl">Sign in to organize your scouting</h1>
            <p className="text-[15px] leading-relaxed text-muted-dark">
              Group who you track into named lists — players, whole club academies, countries, or saved filters.
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
          eyebrow={<span className="inline-flex items-center gap-2"><ListChecks className="h-3.5 w-3.5" aria-hidden="true" />Lists · Scout Pro — free during beta</span>}
          title="Your"
          accent="lists"
          lede="Organize who you track into named lists. Follow players, whole club academies, countries, or a saved search — each list resolves to a live player set."
          actions={(
            <>
              <Button variant="outline" size="sm" asChild className={deskPillClass}>
                <Link to="/scout/watchlist" className="no-underline hover:no-underline">
                  <Star className="mr-1.5 h-4 w-4" />
                  Watchlist
                </Link>
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

        {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

        <div className="grid grid-cols-1 gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
          {/* Left: list rows */}
          <div className="flex flex-col gap-3">
            <DeskSectionTitle
              title="Lists"
              count={!loading ? `${lists.length}` : null}
              action={!creating ? (
                <Button variant="outline" size="sm" className={deskPillClass} onClick={() => { setCreating(true); setCreateError(null) }}>
                  <Plus className="mr-1.5 h-4 w-4" />
                  New list
                </Button>
              ) : null}
            />

            {creating && (
              <Card className="gap-0 py-0">
                <CardContent className="space-y-2 p-4">
                  <Input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCreate() } }}
                    placeholder="List name…"
                    maxLength={120}
                    aria-label="New list name"
                    autoFocus
                  />
                  {createError && <p className="text-xs text-destructive">{createError}</p>}
                  <div className="flex items-center justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={() => { setCreating(false); setNewName(''); setCreateError(null) }}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={handleCreate} disabled={createSaving || !newName.trim()}>
                      {createSaving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                      Create
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {loading ? (
              <div className="space-y-2">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : lists.length ? (
              lists.map((list) => {
                const selected = list.id === selectedListId
                return (
                  <div key={list.id} className={`border-b border-hairline-dark transition-colors duration-150 ${selected ? 'bg-chalk/[0.05] shadow-[inset_2px_0_0_var(--color-gold)]' : 'hover:bg-chalk/[0.03]'}`}>
                    <div className="px-3 py-3.5">
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedListId(list.id)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <span className="flex items-center gap-2">
                            <span className="truncate font-serif text-[1.375rem] leading-tight text-chalk">{list.name}</span>
                            {list.is_default && <Badge variant="secondary" className="shrink-0 text-[10px]">Default</Badge>}
                            {list.is_active === false && <Badge variant="outline" className="shrink-0 text-[10px]">Paused</Badge>}
                          </span>
                          <span className="mt-1 block font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#8C9791]">
                            {followCount(list)} {followCount(list) === 1 ? 'follow' : 'follows'}
                          </span>
                        </button>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <Switch
                            checked={list.is_active !== false}
                            onCheckedChange={(c) => handleToggleActive(list, c)}
                            aria-label={`${list.is_active !== false ? 'Pause' : 'Activate'} ${list.name}`}
                          />
                          {!list.is_default && (
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <button
                                  type="button"
                                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground/60 transition-colors hover:bg-secondary hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                  aria-label={`Delete ${list.name}`}
                                  title="Delete list"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>Delete “{list.name}”?</AlertDialogTitle>
                                  <AlertDialogDescription>
                                    This removes the list and all of its follows. This cannot be undone.
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                                  <AlertDialogAction onClick={() => handleDelete(list)}>Delete</AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })
            ) : !creating ? (
              <div className="flex flex-col items-start gap-4 py-8">
                <p className="text-[15px] text-muted-dark">No lists yet. Create your first list to start following.</p>
                <Button size="sm" variant="on-dark" onClick={() => { setCreating(true); setCreateError(null) }}>
                  <Plus className="mr-1.5 h-4 w-4" />
                  New list
                </Button>
              </div>
            ) : null}
          </div>

          {/* Right: selected list detail + resolved preview */}
          <div className="min-w-0">
            {!selectedList ? (
              <div className="border-t border-hairline-dark px-2 py-16 text-[15px] text-muted-dark">
                {lists.length ? 'Select a list to manage its follows.' : 'Create a list to get started.'}
              </div>
            ) : (
              <div className="space-y-10">
                {/* Detail header */}
                <div className="flex flex-wrap items-end justify-between gap-3 border-b border-chalk pb-3">
                  <div>
                    <h2 className="display text-[2.25rem] leading-none text-chalk sm:text-[2.75rem]">{selectedList.name}</h2>
                    <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#8C9791]">
                      {followCount(selectedList)} {followCount(selectedList) === 1 ? 'follow' : 'follows'}
                      {selectedList.is_default ? ' · default list' : ''}
                    </p>
                  </div>
                  <Button size="sm" variant="on-dark" onClick={() => { setAddError(null); setAddOpen(true) }}>
                    <Plus className="mr-1.5 h-4 w-4" />
                    Add follow
                  </Button>
                </div>

                {/* Follows grouped by kind */}
                <div>
                  <div>
                    {!(selectedList.follows && selectedList.follows.length) ? (
                      <p className="py-8 text-[15px] text-muted-dark">
                        No follows yet. Use “Add follow” to track players, clubs, countries or a saved search.
                      </p>
                    ) : (
                      KIND_META.map((meta) => {
                        const rows = (selectedList.follows || []).filter((f) => f.kind === meta.kind)
                        if (!rows.length) return null
                        const Icon = meta.icon
                        return (
                          <div key={meta.kind} className="pt-5 first:pt-2">
                            <div className="flex items-center gap-2 pb-2">
                              <Icon className="h-3.5 w-3.5 text-gold" aria-hidden="true" />
                              <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.16em] text-[#8C9791]">{meta.title}</span>
                            </div>
                            <ul className="divide-y divide-hairline-dark border-y border-hairline-dark">
                              {rows.map((follow) => (
                                <li key={follow.id} className="flex items-center justify-between gap-3 px-1 py-3">
                                  <div className="min-w-0">
                                    <span className="block truncate text-[15px] text-chalk">{followLabel(follow)}</span>
                                    {follow.note && (
                                      <span className="block max-w-full truncate font-serif text-[15px] italic text-gold/90" title={follow.note}>
                                        “{follow.note}”
                                      </span>
                                    )}
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => handleRemoveFollow(follow)}
                                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground/60 transition-colors hover:bg-secondary hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    aria-label={`Remove ${followLabel(follow)}`}
                                    title="Remove follow"
                                  >
                                    <X className="h-4 w-4" />
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )
                      })
                    )}
                  </div>
                </div>

                {/* Resolved preview */}
                <div>
                  <DeskSectionTitle
                    as="h3"
                    title="Resolved players"
                    count={preview.total > 0 ? `${preview.players.length} of ${preview.total.toLocaleString()}` : null}
                  />
                  <div>
                    {previewError ? (
                      <p className="px-4 py-8 text-center text-sm text-destructive">{previewError}</p>
                    ) : (
                      <div className="relative overflow-x-auto">
                        <table className="w-full min-w-[480px] border-collapse">
                          <thead>
                            <tr className="border-b border-hairline-dark">
                              <th className="px-3 py-3 text-left font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-[#8C9791]">Player</th>
                              <th className="px-3 py-3 text-left font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-[#8C9791]">Status</th>
                              <th className="px-3 py-3 text-left font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-[#8C9791]">Club</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-hairline-dark">
                            {previewLoading && !preview.players.length ? (
                              Array.from({ length: 5 }).map((_, i) => (
                                <tr key={i}><td colSpan={3} className="px-3 py-2.5"><Skeleton className="h-9 w-full" /></td></tr>
                              ))
                            ) : preview.players.length ? (
                              preview.players.map((p) => {
                                const cellPlayer = {
                                  player_id: p.player_api_id,
                                  player_name: p.player_name,
                                  player_photo: p.photo,
                                }
                                return (
                                  <tr key={`${p.source}-${p.player_api_id}`} className="transition-colors duration-150 hover:bg-chalk/[0.035]">
                                    <td className="px-3 py-2.5">
                                      <div className="flex items-center gap-2">
                                        <PlayerCell player={cellPlayer} />
                                        {p.source === 'shadow' && (
                                          <Badge variant="outline" className="shrink-0 text-[10px] font-normal">Worldwide</Badge>
                                        )}
                                      </div>
                                    </td>
                                    <td className="px-3 py-2.5"><StatusBadge status={p.status} /></td>
                                    <td className="px-3 py-2.5 max-w-44">
                                      <span className="block truncate text-sm text-foreground/90">{p.team_name || '—'}</span>
                                    </td>
                                  </tr>
                                )
                              })
                            ) : (
                              <tr>
                                <td colSpan={3} className="px-3 py-12 text-center text-sm text-muted-foreground">
                                  No players resolve from this list yet.
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {preview.players.length < preview.total && (
                      <div className="border-t border-hairline-dark px-4 py-4 text-center">
                        <Button variant="outline" size="sm" className={deskPillClass} onClick={loadMorePreview} disabled={previewLoading}>
                          {previewLoading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                          Load more
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <AddFollowDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          onAdd={handleAddFollow}
          adding={adding}
          addError={addError}
        />
      </div>
    </ScoutSurface>
  )
}
