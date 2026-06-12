import { useState, useEffect, useMemo, useCallback, useRef, Fragment } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Loader2, Search, ArrowUpDown, ArrowLeft, ArrowRight,
  Trophy, Zap, Clock, Gauge, X, GitCompareArrows, Globe,
} from 'lucide-react'
import { STATUS_BADGE_CLASSES } from '../lib/theme-constants'

const AGE_PRESETS = [
  { key: 'all', label: 'All ages', params: {} },
  { key: 'u18', label: 'U18', params: { max_age: 18 } },
  { key: 'u21', label: 'U21', params: { max_age: 21 } },
  { key: 'u23', label: 'U23', params: { max_age: 23 } },
]

const SORT_OPTIONS = [
  { value: 'contributions', label: 'Goal contributions' },
  { value: 'goals', label: 'Goals' },
  { value: 'assists', label: 'Assists' },
  { value: 'minutes', label: 'Minutes played' },
  { value: 'appearances', label: 'Appearances' },
  { value: 'rating', label: 'Avg rating' },
  { value: 'per90', label: 'G+A per 90' },
  { value: 'age', label: 'Age' },
  { value: 'name', label: 'Name' },
]

const BOARD_META = [
  { key: 'top_scorers', title: 'Top Scorers', icon: Trophy, metric: (p) => p.goals, suffix: 'goals' },
  { key: 'top_assists', title: 'Top Assists', icon: Zap, metric: (p) => p.assists, suffix: 'assists' },
  { key: 'most_minutes', title: 'Most Minutes', icon: Clock, metric: (p) => p.minutes_played?.toLocaleString(), suffix: 'mins' },
  { key: 'best_per90', title: 'Best G+A / 90', icon: Gauge, metric: (p) => p.contributions_per90, suffix: '/90' },
]

const RANK_CHIP_CLASSES = [
  'bg-primary text-primary-foreground',
  'bg-amber-100 text-amber-900 border border-amber-300',
  'bg-stone-100 text-stone-700 border border-stone-300',
]

const COMPARE_ROWS = [
  { section: 'Season', key: 'appearances', label: 'Appearances', source: 'totals' },
  { key: 'minutes_played', label: 'Minutes', source: 'totals' },
  { key: 'goals', label: 'Goals', source: 'totals' },
  { key: 'assists', label: 'Assists', source: 'totals' },
  { key: 'avg_rating', label: 'Avg rating', source: 'totals' },
  { key: 'shots_total', label: 'Shots', source: 'totals' },
  { key: 'key_passes', label: 'Key passes', source: 'totals' },
  { key: 'dribbles_success', label: 'Dribbles won', source: 'totals' },
  { key: 'tackles', label: 'Tackles', source: 'totals' },
  { key: 'interceptions', label: 'Interceptions', source: 'totals' },
  { key: 'duels_won', label: 'Duels won', source: 'totals' },
  { key: 'saves', label: 'Saves', source: 'totals', position: 'Goalkeeper' },
  { section: 'Per 90', key: 'goal_contributions', label: 'G+A / 90', source: 'per90' },
  { key: 'goals', label: 'Goals / 90', source: 'per90' },
  { key: 'assists', label: 'Assists / 90', source: 'per90' },
  { key: 'key_passes', label: 'Key passes / 90', source: 'per90' },
  { key: 'shots_total', label: 'Shots / 90', source: 'per90' },
  { key: 'dribbles_success', label: 'Dribbles / 90', source: 'per90' },
  { key: 'tackles', label: 'Tackles / 90', source: 'per90' },
  { key: 'duels_won', label: 'Duels won / 90', source: 'per90' },
  { section: 'Career', key: 'youth_apps', label: 'Academy apps', source: 'career' },
  { key: 'loan_apps', label: 'Loan apps', source: 'career' },
  { key: 'first_team_apps', label: 'First-team apps', source: 'career' },
  { key: 'goals', label: 'Career goals', source: 'career' },
  { key: 'assists', label: 'Career assists', source: 'career' },
]

function StatusBadge({ status }) {
  if (!status) return null
  const colorClass = STATUS_BADGE_CLASSES[status] || 'bg-secondary text-foreground/80 border-border'
  return <Badge className={`${colorClass} capitalize whitespace-nowrap`}>{status.replace('_', ' ')}</Badge>
}

function PlayerCell({ player }) {
  return (
    <Link to={`/players/${player.player_id}`} className="flex items-center gap-3 no-underline hover:no-underline group">
      {player.player_photo ? (
        <img src={player.player_photo} alt="" loading="lazy" className="h-9 w-9 rounded-full object-cover bg-secondary shrink-0" />
      ) : (
        <span className="h-9 w-9 rounded-full bg-secondary inline-flex items-center justify-center text-xs font-semibold text-muted-foreground shrink-0">
          {player.player_name?.slice(0, 2).toUpperCase()}
        </span>
      )}
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
          {player.player_name}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {[player.nationality, player.age ? `${player.age} yrs` : null].filter(Boolean).join(' · ')}
        </span>
      </span>
    </Link>
  )
}

function LeaderboardCard({ board, entries, loading }) {
  const Icon = board.icon
  return (
    <Card className="overflow-hidden border-border/80">
      <div className="flex items-center gap-2 border-b border-border/60 bg-secondary/60 px-4 py-2.5">
        <Icon className="h-4 w-4 text-primary" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/70">{board.title}</h3>
      </div>
      <CardContent className="p-0">
        {loading ? (
          <div className="space-y-3 p-4">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
          </div>
        ) : entries?.length ? (
          <ol className="divide-y divide-border/50">
            {entries.map((player, index) => (
              <li key={player.player_id}>
                <Link
                  to={`/players/${player.player_id}`}
                  className="flex items-center gap-3 px-4 py-2.5 no-underline hover:no-underline hover:bg-secondary/50 transition-colors"
                >
                  <span className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${RANK_CHIP_CLASSES[index] || 'bg-secondary text-muted-foreground'}`}>
                    {index + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">{player.player_name}</span>
                    <span className="block truncate text-xs text-muted-foreground">{player.loan_team_name || player.primary_team_name}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-sm font-bold tabular-nums text-primary">{board.metric(player) ?? '—'}</span>
                    <span className="block text-[10px] uppercase tracking-wide text-muted-foreground">{board.suffix}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">No data yet</p>
        )}
      </CardContent>
    </Card>
  )
}

function CompareDialog({ open, onOpenChange, playerIds }) {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open || !playerIds.length) return
    let cancelled = false
    setLoading(true)
    setError(null)
    APIService.compareScoutPlayers(playerIds)
      .then((res) => { if (!cancelled) setData(res) })
      .catch((err) => { if (!cancelled) setError(err.message || 'Comparison failed') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, playerIds])

  const players = data?.players || []
  const anyGoalkeeper = players.some((p) => p.profile?.position === 'Goalkeeper')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl sm:max-w-4xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitCompareArrows className="h-5 w-5 text-primary" />
            Player Comparison
          </DialogTitle>
          <DialogDescription>
            Current-club season output, per-90 rates, and career volume side by side.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : error ? (
          <p className="py-8 text-center text-sm text-destructive">{error}</p>
        ) : players.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr>
                  <th className="w-36 p-2" />
                  {players.map((p) => (
                    <th key={p.profile.player_id} className="p-2 text-center align-bottom">
                      <Link to={`/players/${p.profile.player_id}`} className="inline-flex flex-col items-center gap-1.5 no-underline hover:no-underline group">
                        {p.profile.player_photo ? (
                          <img src={p.profile.player_photo} alt="" className="h-14 w-14 rounded-full object-cover bg-secondary" />
                        ) : (
                          <span className="h-14 w-14 rounded-full bg-secondary inline-flex items-center justify-center text-sm font-semibold text-muted-foreground">
                            {p.profile.player_name?.slice(0, 2).toUpperCase()}
                          </span>
                        )}
                        <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                          {p.profile.player_name}
                        </span>
                        <span className="text-xs text-muted-foreground font-normal">
                          {[p.profile.position, p.profile.age ? `${p.profile.age} yrs` : null].filter(Boolean).join(' · ')}
                        </span>
                        <StatusBadge status={p.profile.status} />
                        <span className="text-xs text-muted-foreground font-normal">
                          {p.profile.loan_team_name || p.profile.primary_team_name}
                        </span>
                      </Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE_ROWS.filter((row) => !row.position || (row.position === 'Goalkeeper' && anyGoalkeeper)).map((row, index) => {
                  const values = players.map((p) => {
                    const bucket = p[row.source]
                    const value = bucket?.[row.key]
                    return value === null || value === undefined ? null : value
                  })
                  if (values.every((v) => v === null)) return null
                  const numeric = values.map((v) => (typeof v === 'number' ? v : -Infinity))
                  const best = Math.max(...numeric)
                  return (
                    <Fragment key={`${row.source}-${row.key}-${index}`}>
                      {row.section && (
                        <tr>
                          <td colSpan={players.length + 1} className="pt-4 pb-1 px-2">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">{row.section}</span>
                          </td>
                        </tr>
                      )}
                      <tr className="border-t border-border/40">
                        <td className="p-2 text-xs font-medium text-muted-foreground">{row.label}</td>
                        {values.map((value, i) => (
                          <td
                            key={i}
                            className={`p-2 text-center tabular-nums ${value !== null && numeric[i] === best && players.length > 1 && best > 0 ? 'font-bold text-primary' : 'text-foreground'}`}
                          >
                            {value === null ? '—' : typeof value === 'number' ? value.toLocaleString() : value}
                          </td>
                        ))}
                      </tr>
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">No players found for comparison.</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function ScoutPage() {
  const [players, setPlayers] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [boards, setBoards] = useState(null)
  const [boardsLoading, setBoardsLoading] = useState(true)

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [position, setPosition] = useState('all')
  const [status, setStatus] = useState('all')
  const [agePreset, setAgePreset] = useState('all')
  const [sort, setSort] = useState('contributions')
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(1)

  const [compareIds, setCompareIds] = useState([])
  const [compareOpen, setCompareOpen] = useState(false)
  const searchTimer = useRef(null)

  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(searchTimer.current)
  }, [search])

  const filterParams = useMemo(() => {
    const params = {}
    if (debouncedSearch) params.search = debouncedSearch
    if (position !== 'all') params.position = position
    if (status !== 'all') params.status = status
    const preset = AGE_PRESETS.find((p) => p.key === agePreset)
    Object.assign(params, preset?.params || {})
    return params
  }, [debouncedSearch, position, status, agePreset])

  // Reset to first page when filters change
  useEffect(() => { setPage(1) }, [filterParams, sort, order])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    APIService.getScoutPlayers({ ...filterParams, sort, order, page, per_page: 25 })
      .then((data) => {
        if (cancelled) return
        setPlayers(data?.players || [])
        setTotal(data?.total || 0)
        setTotalPages(data?.total_pages || 0)
      })
      .catch((err) => {
        console.error('Failed to load scout players', err)
        if (!cancelled) { setPlayers([]); setTotal(0); setTotalPages(0) }
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [filterParams, sort, order, page])

  useEffect(() => {
    let cancelled = false
    setBoardsLoading(true)
    const boardFilters = { limit: 5 }
    const preset = AGE_PRESETS.find((p) => p.key === agePreset)
    Object.assign(boardFilters, preset?.params || {})
    if (position !== 'all') boardFilters.position = position
    if (status !== 'all') boardFilters.status = status
    APIService.getScoutLeaderboards(boardFilters)
      .then((data) => { if (!cancelled) setBoards(data?.leaderboards || null) })
      .catch((err) => {
        console.error('Failed to load leaderboards', err)
        if (!cancelled) setBoards(null)
      })
      .finally(() => { if (!cancelled) setBoardsLoading(false) })
    return () => { cancelled = true }
  }, [position, status, agePreset])

  const toggleCompare = useCallback((playerId) => {
    setCompareIds((current) => {
      if (current.includes(playerId)) return current.filter((id) => id !== playerId)
      if (current.length >= 4) return current
      return [...current, playerId]
    })
  }, [])

  const toggleSort = useCallback((key) => {
    setSort((currentSort) => {
      if (currentSort === key) {
        setOrder((o) => (o === 'desc' ? 'asc' : 'desc'))
        return currentSort
      }
      setOrder(key === 'name' || key === 'age' ? 'asc' : 'desc')
      return key
    })
  }, [])

  const headerCell = (key, label, alignRight = true) => (
    <th
      className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors whitespace-nowrap ${alignRight ? 'text-right' : 'text-left'}`}
      onClick={() => toggleSort(key)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className={`h-3 w-3 ${sort === key ? 'text-primary' : 'opacity-40'}`} />
      </span>
    </th>
  )

  return (
    <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Editorial header */}
        <header className="mb-8">
          <p className="mb-2 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            <Globe className="h-3.5 w-3.5" />
            Global talent discovery
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            The Scout Desk
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
            Every tracked academy and loan player, ranked across clubs and leagues.
            Filter by position and age band, sort by output, and compare prospects side by side.
          </p>
        </header>

        {/* Leaderboards */}
        <section aria-label="Leaderboards" className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {BOARD_META.map((board) => (
            <LeaderboardCard key={board.key} board={board} entries={boards?.[board.key]} loading={boardsLoading} />
          ))}
        </section>

        {/* Filters */}
        <section aria-label="Filters" className="mb-4 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {AGE_PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => setAgePreset(preset.key)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                  agePreset === preset.key
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'bg-card text-foreground/70 border border-border hover:bg-secondary'
                }`}
              >
                {preset.label}
              </button>
            ))}
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
              {loading ? 'Loading…' : `${total.toLocaleString()} players`}
            </span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search players by name…"
                className="pl-9"
                aria-label="Search players"
              />
            </div>
            <Select value={position} onValueChange={setPosition}>
              <SelectTrigger className="w-full sm:w-44" aria-label="Filter by position">
                <SelectValue placeholder="Position" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All positions</SelectItem>
                <SelectItem value="Goalkeeper">Goalkeeper</SelectItem>
                <SelectItem value="Defender">Defender</SelectItem>
                <SelectItem value="Midfielder">Midfielder</SelectItem>
                <SelectItem value="Attacker">Attacker</SelectItem>
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-full sm:w-44" aria-label="Filter by pathway status">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="academy">Academy</SelectItem>
                <SelectItem value="on_loan">On loan</SelectItem>
                <SelectItem value="first_team">First team</SelectItem>
                <SelectItem value="sold">Sold</SelectItem>
                <SelectItem value="released">Released</SelectItem>
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={(value) => { setSort(value); setOrder(value === 'name' || value === 'age' ? 'asc' : 'desc') }}>
              <SelectTrigger className="w-full sm:w-52" aria-label="Sort by">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </section>

        {/* Results table */}
        <Card className="overflow-hidden border-border/80">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse">
              <thead>
                <tr className="border-b border-border/60 bg-secondary/60">
                  <th className="w-10 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span className="sr-only">Compare</span>
                  </th>
                  {headerCell('name', 'Player', false)}
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pos</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Club</th>
                  {headerCell('appearances', 'Apps')}
                  {headerCell('goals', 'G')}
                  {headerCell('assists', 'A')}
                  {headerCell('minutes', 'Mins')}
                  {headerCell('rating', 'Rating')}
                  {headerCell('per90', 'G+A/90')}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {loading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={11} className="px-3 py-2.5"><Skeleton className="h-9 w-full" /></td>
                    </tr>
                  ))
                ) : players.length ? (
                  players.map((player) => {
                    const selected = compareIds.includes(player.player_id)
                    return (
                      <tr key={player.id} className={`transition-colors hover:bg-secondary/40 ${selected ? 'bg-primary/5' : ''}`}>
                        <td className="px-3 py-2.5">
                          <Checkbox
                            checked={selected}
                            onCheckedChange={() => toggleCompare(player.player_id)}
                            disabled={!selected && compareIds.length >= 4}
                            aria-label={`Compare ${player.player_name}`}
                          />
                        </td>
                        <td className="px-3 py-2.5"><PlayerCell player={player} /></td>
                        <td className="px-3 py-2.5 text-sm text-foreground/80 whitespace-nowrap">{player.position?.slice(0, 3) || '—'}</td>
                        <td className="px-3 py-2.5"><StatusBadge status={player.status} /></td>
                        <td className="px-3 py-2.5 max-w-44">
                          <span className="block truncate text-sm text-foreground/90">{player.loan_team_name || player.primary_team_name || '—'}</span>
                          {player.loan_team_name && player.primary_team_name && (
                            <span className="block truncate text-xs text-muted-foreground">from {player.primary_team_name}</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right text-sm tabular-nums">{player.appearances}</td>
                        <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums text-emerald-700">{player.goals}</td>
                        <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums text-amber-700">{player.assists}</td>
                        <td className="px-3 py-2.5 text-right text-sm tabular-nums">{player.minutes_played?.toLocaleString()}</td>
                        <td className="px-3 py-2.5 text-right text-sm tabular-nums">{player.avg_rating ?? '—'}</td>
                        <td className="px-3 py-2.5 text-right text-sm font-semibold tabular-nums text-primary">{player.contributions_per90 ?? '—'}</td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={11} className="px-3 py-12 text-center text-sm text-muted-foreground">
                      No players match these filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-border/60 px-4 py-3">
              <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                <ArrowLeft className="mr-1 h-4 w-4" /> Previous
              </Button>
              <span className="text-xs text-muted-foreground tabular-nums">Page {page} of {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages || loading} onClick={() => setPage((p) => p + 1)}>
                Next <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          )}
        </Card>

        {/* Compare tray */}
        {compareIds.length > 0 && (
          <div className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-4 pointer-events-none">
            <div className="pointer-events-auto flex items-center gap-3 rounded-full border border-border bg-card/95 px-4 py-2.5 shadow-lg backdrop-blur">
              <span className="text-sm text-foreground/80 tabular-nums">
                {compareIds.length} of 4 selected
              </span>
              <Button
                size="sm"
                disabled={compareIds.length < 2}
                onClick={() => setCompareOpen(true)}
                className="rounded-full"
              >
                <GitCompareArrows className="mr-1.5 h-4 w-4" />
                Compare
              </Button>
              <button
                type="button"
                onClick={() => setCompareIds([])}
                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                aria-label="Clear comparison selection"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        <CompareDialog open={compareOpen} onOpenChange={setCompareOpen} playerIds={compareIds} />
      </div>
    </div>
  )
}
