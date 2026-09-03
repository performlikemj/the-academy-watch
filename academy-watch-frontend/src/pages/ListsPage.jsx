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
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search players worldwide by name…"
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
                            {row.shadow ? 'Worldwide' : 'Worldwide — will start tracking'}
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
      <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
        <div className="mx-auto flex max-w-7xl items-center justify-center px-4 py-24 sm:px-6 lg:px-8">
          <Card className="w-full max-w-md overflow-hidden border-border/80">
            <CardContent className="flex flex-col items-center gap-4 px-8 py-12 text-center">
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <ListChecks className="h-6 w-6 text-primary" />
              </span>
              <h1 className="text-xl font-bold tracking-tight text-foreground">Sign in to organize your scouting</h1>
              <p className="text-sm text-muted-foreground">
                Group who you track into named lists — players, whole club academies, countries, or saved filters.
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
              <ListChecks className="h-3.5 w-3.5" />
              Scout Pro — free during beta
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">Your Lists</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
              Organize who you track into named lists. Follow players, whole club academies, countries,
              or a saved search — each list resolves to a live player set.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 lg:shrink-0 lg:pt-7">
            <Button variant="outline" size="sm" asChild>
              <Link to="/scout/watchlist" className="no-underline hover:no-underline">
                <Star className="mr-1.5 h-4 w-4" />
                Watchlist
              </Link>
            </Button>
            <Button size="sm" asChild>
              <Link to="/scout" className="no-underline hover:no-underline">
                <Search className="mr-1.5 h-4 w-4" />
                Find players
              </Link>
            </Button>
          </div>
        </header>

        {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Left: list cards */}
          <div className="space-y-3 lg:col-span-1">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Lists</h2>
              {!creating && (
                <Button variant="outline" size="sm" onClick={() => { setCreating(true); setCreateError(null) }}>
                  <Plus className="mr-1.5 h-4 w-4" />
                  New list
                </Button>
              )}
            </div>

            {creating && (
              <Card className="border-border/80">
                <CardContent className="space-y-2 p-3">
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
                  <Card key={list.id} className={`overflow-hidden border-border/80 transition-shadow ${selected ? 'ring-2 ring-primary' : ''}`}>
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedListId(list.id)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <span className="flex items-center gap-2">
                            <span className="truncate text-sm font-semibold text-foreground">{list.name}</span>
                            {list.is_default && <Badge variant="secondary" className="shrink-0 text-[10px]">Default</Badge>}
                            {list.is_active === false && <Badge variant="outline" className="shrink-0 text-[10px]">Paused</Badge>}
                          </span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">
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
                    </CardContent>
                  </Card>
                )
              })
            ) : !creating ? (
              <Card className="border-border/80">
                <CardContent className="flex flex-col items-center gap-3 px-6 py-10 text-center">
                  <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                    <ListChecks className="h-5 w-5 text-primary" />
                  </span>
                  <p className="text-sm text-muted-foreground">No lists yet. Create your first list to start following.</p>
                  <Button size="sm" onClick={() => { setCreating(true); setCreateError(null) }}>
                    <Plus className="mr-1.5 h-4 w-4" />
                    New list
                  </Button>
                </CardContent>
              </Card>
            ) : null}
          </div>

          {/* Right: selected list detail + resolved preview */}
          <div className="lg:col-span-2">
            {!selectedList ? (
              <Card className="border-border/80">
                <CardContent className="px-6 py-16 text-center text-sm text-muted-foreground">
                  {lists.length ? 'Select a list to manage its follows.' : 'Create a list to get started.'}
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-6">
                {/* Detail header */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-bold tracking-tight text-foreground">{selectedList.name}</h2>
                    <p className="text-xs text-muted-foreground">
                      {followCount(selectedList)} {followCount(selectedList) === 1 ? 'follow' : 'follows'}
                      {selectedList.is_default ? ' · default list' : ''}
                    </p>
                  </div>
                  <Button size="sm" onClick={() => { setAddError(null); setAddOpen(true) }}>
                    <Plus className="mr-1.5 h-4 w-4" />
                    Add follow
                  </Button>
                </div>

                {/* Follows grouped by kind */}
                <Card className="overflow-hidden border-border/80">
                  <CardContent className="p-0">
                    {!(selectedList.follows && selectedList.follows.length) ? (
                      <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                        No follows yet. Use “Add follow” to track players, clubs, countries or a saved search.
                      </p>
                    ) : (
                      KIND_META.map((meta) => {
                        const rows = (selectedList.follows || []).filter((f) => f.kind === meta.kind)
                        if (!rows.length) return null
                        const Icon = meta.icon
                        return (
                          <div key={meta.kind} className="border-b border-border/50 last:border-b-0">
                            <div className="flex items-center gap-2 bg-secondary/50 px-4 py-2">
                              <Icon className="h-3.5 w-3.5 text-primary" />
                              <span className="text-xs font-semibold uppercase tracking-wider text-foreground/70">{meta.title}</span>
                            </div>
                            <ul className="divide-y divide-border/40">
                              {rows.map((follow) => (
                                <li key={follow.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                                  <div className="min-w-0">
                                    <span className="block truncate text-sm text-foreground">{followLabel(follow)}</span>
                                    {follow.note && (
                                      <span className="block max-w-full truncate text-xs italic text-primary/80" title={follow.note}>
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
                  </CardContent>
                </Card>

                {/* Resolved preview */}
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      Resolved players
                    </h3>
                    {preview.total > 0 && (
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {preview.players.length} of {preview.total.toLocaleString()}
                      </span>
                    )}
                  </div>
                  <Card className="overflow-hidden border-border/80">
                    {previewError ? (
                      <p className="px-4 py-8 text-center text-sm text-destructive">{previewError}</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[480px] border-collapse">
                          <thead>
                            <tr className="border-b border-border/60 bg-secondary/60">
                              <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Player</th>
                              <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                              <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Club</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/40">
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
                                  <tr key={`${p.source}-${p.player_api_id}`} className="transition-colors hover:bg-secondary/40">
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
                      <div className="border-t border-border/60 px-4 py-3 text-center">
                        <Button variant="outline" size="sm" onClick={loadMorePreview} disabled={previewLoading}>
                          {previewLoading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                          Load more
                        </Button>
                      </div>
                    )}
                  </Card>
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
    </div>
  )
}
