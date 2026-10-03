import { CleatLoader } from '@/components/CleatLoader'
import { useSeasonDirectory } from '@/hooks/useSeasonDirectory'
import { positionAbbreviation } from '@/lib/positions'
// --- p2-c4 begin ---
import { useScoutAttend } from '@/components/attendance/useScoutAttend'
import { ScoutClubsTrials, ScoutTabs } from '@/components/attendance/ScoutClubsTrials'
// --- p2-c4 end ---
import { useDataMode } from '@/hooks/useDataMode'
import { useState, useEffect, useMemo, useCallback, useRef, Fragment } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { track } from '@/lib/track'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { SeasonSelect } from '@/components/ui/SeasonSelect'
import { IntroduceDialog } from '@/components/contact/IntroduceDialog'
import { ProvenanceChip } from '@/components/SelfReportedBadge'
import { useContactRail } from '@/hooks/useContactRail.js'
import { useGuarded, useViewerKey, useViewerLifetime, useViewerState } from '@/hooks/useViewerState'
import { ScoutSurface, ScoutHeader, deskPillClass } from '@/components/scout/ScoutDesk'
import { PlayerCard } from '@/components/player-card/PlayerCard'
import { cardLine, viewerKey } from '@/lib/player-card'
import { cn } from '@/lib/utils'
import { saveBlobAs } from '@/lib/download'
import { isStaleViewerError } from '@/lib/viewer-lifetime'
import { seasonStore } from '@/lib/seasonStore'
import { formatSeasonLabel, withSeasonParam } from '@/lib/seasons'
import {
  Loader2, Search, ArrowUpDown, ArrowLeft, ArrowRight,
  Trophy, Zap, Clock, Gauge, X, GitCompareArrows, Globe,
  Star, Download, Link2,
  Crosshair, Sparkles, Send, Swords, Shield, ShieldCheck, Hand, UserPlus,
} from 'lucide-react'
import { STATUS_BADGE_CLASSES } from '../lib/theme-constants'

const AGE_PRESETS = [
  { key: 'all', label: 'All ages', params: {} },
  { key: 'u21', label: 'U21', params: { max_age: 20 } },
  { key: 'u23', label: 'U23', params: { max_age: 22 } },
]

const SOURCE_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'api', label: 'API' },
  { value: 'club', label: 'Club-confirmed' },
  { value: 'self', label: 'Self-reported' },
]
const SOURCE_VALUES = new Set(SOURCE_FILTERS.slice(1).map(({ value }) => value))

function normalizeSignedPlayerId(value) {
  const normalized = String(value ?? '').trim()
  return /^-?[1-9]\d*$/.test(normalized) ? normalized : null
}

// Sorts that default ascending because lower is better (or alphabetical).
const RESULT_VIEWS = [
  { value: 'cards', label: 'Cards' },
  { value: 'table', label: 'Table' },
]
const RESULT_VIEW_KEY = 'aw.scout.view'

// Stable identity, so the guarded saver is made once per lifetime.
const saveScoutCsv = (blob) => saveBlobAs(blob, 'academy-watch-scout-export.csv')

// The stored choice wins; otherwise cards on phones (where the table scrolls
// sideways) and the dense table on wider screens.
function initialResultView() {
  if (typeof window === 'undefined') return 'table'
  try {
    const stored = window.localStorage.getItem(RESULT_VIEW_KEY)
    if (RESULT_VIEWS.some((option) => option.value === stored)) return stored
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
  return window.matchMedia?.('(max-width: 767px)').matches ? 'cards' : 'table'
}

const ASC_DEFAULT_SORTS = new Set(['name', 'age', 'goals_conceded', 'conceded_per90'])

const fmtStat = (value) => (value === null || value === undefined ? '—' : value)

// Stat column registry. Phase stats (tackles, saves, …) arrive as null for
// players without per-fixture coverage — render a dash, never a fake zero.
// Columns without a sortKey render a static (non-sortable) header.
const STAT_COLUMNS = {
  apps: { sortKey: 'appearances', label: 'Apps', render: (p) => p.appearances },
  mins: { sortKey: 'minutes', label: 'Mins', render: (p) => p.minutes_played?.toLocaleString() },
  goals: { sortKey: 'goals', label: 'G', title: 'Goals', cellClass: 'text-chalk', render: (p) => p.goals },
  assists: { sortKey: 'assists', label: 'A', title: 'Assists', cellClass: 'text-chalk', render: (p) => p.assists },
  rating: { sortKey: 'rating', label: 'Rating', render: (p) => fmtStat(p.avg_rating) },
  ga90: { sortKey: 'per90', label: 'G+A/90', cellClass: 'text-gold', render: (p) => fmtStat(p.contributions_per90) },
  shots: { sortKey: 'shots', label: 'Sh (OT)', title: 'Shots (on target)', render: (p) => (p.shots_total == null ? '—' : `${p.shots_total} (${p.shots_on ?? 0})`) },
  dribbles: { sortKey: 'dribbles', label: 'Drb', title: 'Successful dribbles', render: (p) => fmtStat(p.dribbles_success) },
  foulsWon: { sortKey: 'fouls_won', label: 'FW', title: 'Fouls won', render: (p) => fmtStat(p.fouls_drawn) },
  passes: { sortKey: 'passes', label: 'Passes', render: (p) => (p.passes_total == null ? '—' : p.passes_total.toLocaleString()) },
  keyPasses: { sortKey: 'key_passes', label: 'KP', title: 'Key passes', render: (p) => fmtStat(p.key_passes) },
  kp90: { sortKey: 'key_passes_per90', label: 'KP/90', title: 'Key passes per 90', cellClass: 'text-gold', render: (p) => fmtStat(p.key_passes_per90) },
  tackles: { sortKey: 'tackles', label: 'Tkl', title: 'Tackles', render: (p) => fmtStat(p.tackles) },
  tkl90: { sortKey: 'tackles_per90', label: 'Tkl/90', title: 'Tackles per 90', cellClass: 'text-gold', render: (p) => fmtStat(p.tackles_per90) },
  duelsWon: { sortKey: 'duels_won', label: 'Duels W', title: 'Duels won', render: (p) => fmtStat(p.duels_won) },
  duelPct: { label: 'Duel %', title: 'Duel win rate', render: (p) => (p.duel_win_pct == null ? '—' : `${p.duel_win_pct}%`) },
  cards: { label: 'Y/R', title: 'Yellow / red cards', render: (p) => (p.yellows == null ? '—' : `${p.yellows}/${p.reds ?? 0}`) },
  saves: { sortKey: 'saves', label: 'Saves', render: (p) => fmtStat(p.saves) },
  savePct: { sortKey: 'save_pct', label: 'Save %', title: 'Save percentage', render: (p) => (p.save_pct == null ? '—' : `${p.save_pct}%`) },
  conceded: { sortKey: 'goals_conceded', label: 'GA', title: 'Goals against', render: (p) => fmtStat(p.goals_conceded) },
  concededPer90: { sortKey: 'conceded_per90', label: 'GA/90', title: 'Goals against per 90', render: (p) => fmtStat(p.conceded_per90) },
  cleanSheets: { sortKey: 'clean_sheets', label: 'CS', title: 'Clean sheets', cellClass: 'text-gold', render: (p) => fmtStat(p.clean_sheets) },
  penSaved: { label: 'Pen SV', title: 'Penalties saved', render: (p) => fmtStat(p.penalty_saved) },
}

const BASE_SORT_OPTIONS = [
  { value: 'minutes', label: 'Minutes played' },
  { value: 'appearances', label: 'Appearances' },
  { value: 'rating', label: 'Avg rating' },
  { value: 'age', label: 'Age' },
  { value: 'name', label: 'Name' },
]

// Phase-of-play views: each phase filters to its position group and swaps the
// stat columns, sort options, default sort, and leaderboard cards. 'all' is
// the original Scout Desk view, unchanged.
const PHASES = {
  all: {
    label: 'All',
    position: null,
    defaultSort: 'contributions',
    columns: ['apps', 'goals', 'assists', 'mins', 'rating', 'ga90'],
    sortOptions: [
      { value: 'contributions', label: 'Goal contributions' },
      { value: 'goals', label: 'Goals' },
      { value: 'assists', label: 'Assists' },
      { value: 'per90', label: 'G+A per 90' },
      ...BASE_SORT_OPTIONS,
    ],
    boards: [
      { key: 'top_scorers', title: 'Top Scorers', icon: Trophy, metric: (p) => p.goals, suffix: 'goals' },
      { key: 'top_assists', title: 'Top Assists', icon: Zap, metric: (p) => p.assists, suffix: 'assists' },
      { key: 'most_minutes', title: 'Most Minutes', icon: Clock, metric: (p) => p.minutes_played?.toLocaleString(), suffix: 'mins' },
      { key: 'best_per90', title: 'Best G+A / 90', icon: Gauge, metric: (p) => p.contributions_per90, suffix: '/90' },
    ],
  },
  attack: {
    label: 'Attack',
    position: 'Attacker',
    description: 'Showing attackers ranked on attacking output — goals, shots, dribbles, fouls won.',
    defaultSort: 'goals',
    columns: ['apps', 'mins', 'goals', 'assists', 'shots', 'dribbles', 'foulsWon', 'rating', 'ga90'],
    sortOptions: [
      { value: 'goals', label: 'Goals' },
      { value: 'assists', label: 'Assists' },
      { value: 'contributions', label: 'Goal contributions' },
      { value: 'per90', label: 'G+A per 90' },
      { value: 'shots', label: 'Shots' },
      { value: 'dribbles', label: 'Dribbles won' },
      { value: 'fouls_won', label: 'Fouls won' },
      ...BASE_SORT_OPTIONS,
    ],
    boards: [
      { key: 'top_scorers', title: 'Top Scorers', icon: Trophy, metric: (p) => p.goals, suffix: 'goals' },
      { key: 'top_assists', title: 'Top Assists', icon: Zap, metric: (p) => p.assists, suffix: 'assists' },
      { key: 'best_per90', title: 'Best G+A / 90', icon: Gauge, metric: (p) => p.contributions_per90, suffix: '/90' },
      { key: 'most_shots', title: 'Most Shots', icon: Crosshair, metric: (p) => p.shots_total, suffix: 'shots' },
    ],
  },
  midfield: {
    label: 'Midfield',
    position: 'Midfielder',
    description: 'Showing midfielders ranked on creative output — key passes, passing volume, duels.',
    defaultSort: 'key_passes',
    columns: ['apps', 'mins', 'passes', 'keyPasses', 'kp90', 'assists', 'goals', 'duelPct', 'rating'],
    sortOptions: [
      { value: 'key_passes', label: 'Key passes' },
      { value: 'key_passes_per90', label: 'Key passes per 90' },
      { value: 'assists', label: 'Assists' },
      { value: 'passes', label: 'Passes' },
      { value: 'goals', label: 'Goals' },
      { value: 'duels_won', label: 'Duels won' },
      ...BASE_SORT_OPTIONS,
    ],
    boards: [
      { key: 'most_key_passes', title: 'Most Key Passes', icon: Sparkles, metric: (p) => p.key_passes, suffix: 'key passes' },
      { key: 'top_assists', title: 'Top Assists', icon: Zap, metric: (p) => p.assists, suffix: 'assists' },
      { key: 'most_passes', title: 'Most Passes', icon: Send, metric: (p) => p.passes_total?.toLocaleString(), suffix: 'passes' },
      { key: 'best_kp_per90', title: 'Best KP / 90', icon: Gauge, metric: (p) => p.key_passes_per90, suffix: '/90' },
    ],
  },
  defense: {
    label: 'Defense',
    position: 'Defender',
    description: 'Showing defenders ranked on defensive output — tackles, duels, discipline.',
    defaultSort: 'tackles',
    columns: ['apps', 'mins', 'tackles', 'tkl90', 'duelsWon', 'duelPct', 'cards', 'rating'],
    sortOptions: [
      { value: 'tackles', label: 'Tackles' },
      { value: 'tackles_per90', label: 'Tackles per 90' },
      { value: 'duels_won', label: 'Duels won' },
      ...BASE_SORT_OPTIONS,
    ],
    boards: [
      { key: 'most_tackles', title: 'Most Tackles', icon: Swords, metric: (p) => p.tackles, suffix: 'tackles' },
      { key: 'most_duels_won', title: 'Most Duels Won', icon: Shield, metric: (p) => p.duels_won, suffix: 'duels' },
      { key: 'best_tackles_per90', title: 'Best Tkl / 90', icon: Gauge, metric: (p) => p.tackles_per90, suffix: '/90' },
      { key: 'most_minutes', title: 'Most Minutes', icon: Clock, metric: (p) => p.minutes_played?.toLocaleString(), suffix: 'mins' },
    ],
  },
  gk: {
    label: 'Goalkeepers',
    position: 'Goalkeeper',
    description: 'Showing goalkeepers ranked on goalkeeping output — clean sheets, saves, goals against.',
    defaultSort: 'clean_sheets',
    columns: ['apps', 'mins', 'saves', 'savePct', 'conceded', 'concededPer90', 'cleanSheets', 'penSaved', 'rating'],
    sortOptions: [
      { value: 'clean_sheets', label: 'Clean sheets' },
      { value: 'saves', label: 'Saves' },
      { value: 'save_pct', label: 'Save %' },
      { value: 'conceded_per90', label: 'Goals against per 90' },
      { value: 'goals_conceded', label: 'Goals against' },
      ...BASE_SORT_OPTIONS,
    ],
    boards: [
      { key: 'most_clean_sheets', title: 'Most Clean Sheets', icon: ShieldCheck, metric: (p) => p.clean_sheets, suffix: 'CS' },
      { key: 'most_saves', title: 'Most Saves', icon: Hand, metric: (p) => p.saves, suffix: 'saves' },
      { key: 'best_conceded_per90', title: 'Best GA / 90', icon: Gauge, metric: (p) => p.conceded_per90, suffix: '/90' },
      { key: 'most_minutes', title: 'Most Minutes', icon: Clock, metric: (p) => p.minutes_played?.toLocaleString(), suffix: 'mins' },
    ],
  },
}

const PHASE_ORDER = ['all', 'attack', 'midfield', 'defense', 'gk']


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
  { key: 'goals_conceded', label: 'Goals conceded', source: 'totals', position: 'Goalkeeper', lowerBetter: true },
  { key: 'clean_sheets', label: 'Clean sheets', source: 'totals', position: 'Goalkeeper' },
  { key: 'penalty_saved', label: 'Penalties saved', source: 'totals', position: 'Goalkeeper' },
  { section: 'Per 90', key: 'goal_contributions', label: 'G+A / 90', source: 'per90' },
  { key: 'goals', label: 'Goals / 90', source: 'per90' },
  { key: 'assists', label: 'Assists / 90', source: 'per90' },
  { key: 'key_passes', label: 'Key passes / 90', source: 'per90' },
  { key: 'shots_total', label: 'Shots / 90', source: 'per90' },
  { key: 'dribbles_success', label: 'Dribbles / 90', source: 'per90' },
  { key: 'tackles', label: 'Tackles / 90', source: 'per90' },
  { key: 'duels_won', label: 'Duels won / 90', source: 'per90' },
  { section: 'Availability', key: 'total_absences', label: 'Fixtures missed', source: 'availability', noHighlight: true },
  { key: 'last_reason', label: 'Last absence', source: 'availability', noHighlight: true },
  { section: 'Career', key: 'youth_apps', label: 'Academy apps', source: 'career' },
  { key: 'loan_apps', label: 'Loan apps', source: 'career' },
  { key: 'first_team_apps', label: 'First-team apps', source: 'career' },
  { key: 'goals', label: 'Career goals', source: 'career' },
  { key: 'assists', label: 'Career assists', source: 'career' },
]

export function StatusBadge({ status }) {
  if (!status) return null
  const colorClass = STATUS_BADGE_CLASSES[status] || 'bg-secondary text-foreground/80 border-border'
  return <Badge className={`${colorClass} capitalize whitespace-nowrap`}>{status.replace('_', ' ')}</Badge>
}

export function FormIndicator({ form }) {
  if (!form?.length) return <span className="text-xs text-muted-foreground">—</span>
  // API returns newest first; show oldest → newest like a form guide
  const matches = [...form].reverse()
  return (
    <span className="inline-flex items-end gap-0.5" aria-label={`Last ${matches.length} matches`}>
      {matches.map((match, index) => {
        const contributed = (match.goals || 0) + (match.assists || 0) > 0
        const height = Math.max(6, Math.round(((match.minutes || 0) / 90) * 18))
        const title = `${match.date ? match.date.slice(0, 10) : 'Match'}: ${match.minutes}' ${match.goals}G ${match.assists}A${match.rating ? ` · ${match.rating}` : ''}`
        return (
          <span
            key={index}
            title={title}
            className={`w-1.5 rounded-sm ${contributed ? 'bg-gold' : 'bg-chalk/25'}`}
            style={{ height: `${height}px` }}
          />
        )
      })}
    </span>
  )
}

export function PlayerCell({ player, season }) {
  return (
    <Link to={withSeasonParam(`/players/${player.player_id}`, season)} className="flex items-center gap-3 no-underline hover:no-underline group">
      {player.player_photo ? (
        <img src={player.player_photo} alt="" loading="lazy" className="h-10 w-10 rounded-full object-cover bg-secondary opacity-90 shrink-0" />
      ) : (
        <span className="h-10 w-10 rounded-full bg-secondary inline-flex items-center justify-center font-mono text-[11px] text-muted-foreground shrink-0">
          {player.player_name?.slice(0, 2).toUpperCase()}
        </span>
      )}
      <span className="min-w-0">
        <span className="block truncate text-[14.5px] font-medium text-foreground group-hover:text-gold transition-colors">
          {player.player_name}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {[player.nationality, player.age ? `${player.age} yrs` : null].filter(Boolean).join(' · ')}
        </span>
      </span>
    </Link>
  )
}

function LeaderboardCard({ board, entries, loading, season, seasonOverride }) {
  const Icon = board.icon
  return (
    <section className="flex min-w-0 flex-col" aria-label={board.title}>
      <div className="flex items-center gap-2 border-b border-chalk/70 pb-2.5">
        <Icon className="h-3.5 w-3.5 text-gold" aria-hidden="true" />
        <h3 className="font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-chalk">{board.title}</h3>
        <span className="ml-auto font-mono text-[10.5px] tabular-nums text-[#8C9791]">{formatSeasonLabel(season)}</span>
      </div>
      {loading ? (
        <div className="space-y-3 py-4">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
        </div>
      ) : entries?.length ? (
        <ol className="flex flex-col">
          {entries.map((player, index) => (
            <li key={player.player_id}>
              <Link
                to={withSeasonParam(`/players/${player.player_id}`, seasonOverride)}
                className="grid grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-3 border-b border-hairline-dark py-3 no-underline transition-colors duration-150 hover:bg-chalk/[0.035] hover:no-underline"
              >
                <span className={cn('font-mono text-[11px] tabular-nums', index === 0 ? 'text-gold' : 'text-[#8C9791]')}>
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-serif text-[1.3rem] leading-tight text-chalk">{player.player_name}</span>
                  <span className="block truncate text-[12.5px] text-muted-dark">{player.loan_team_name || player.primary_team_name}</span>
                  <ProvenanceChip provenance={player.provenance} className="mt-1.5" />
                </span>
                <span className="shrink-0 text-right">
                  <span className="block font-serif text-[1.75rem] leading-none tabular-nums text-chalk">{board.metric(player) ?? '—'}</span>
                  <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.12em] text-[#8C9791]">{board.suffix}</span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <p className="py-6 text-sm text-muted-dark">No data yet</p>
      )}
    </section>
  )
}

function CompareDialog({ open, onOpenChange, playerIds, season, seasonOverride, source = 'all' }) {
  // Requests and side effects go through this viewer's lifetime (see lib/viewer-lifetime.js).
  const life = useViewerLifetime()
  const api = life.api
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [copyState, setCopyState] = useState('idle') // idle | copied | failed
  const copyTimer = useRef(null)

  useEffect(() => {
    if (!open || !playerIds.length) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api.compareScoutPlayers(playerIds, {
      includeAvailability: true,
      season,
      ...(source !== 'all' ? { source } : {}),
    })
      .then((res) => { if (!cancelled) setData(res) })
      .catch((err) => { if (!cancelled) setError(err.message || 'Comparison failed') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [api, open, playerIds, season, source])

  useEffect(() => () => clearTimeout(copyTimer.current), [])

  const handleCopyLink = useCallback(() => {
    const params = new URLSearchParams({ compare: playerIds.join(',') })
    if (season != null) params.set('season', String(season))
    if (source !== 'all') params.set('source', source)
    const url = `${window.location.origin}/scout?${params}`
    const flash = (state) => {
      setCopyState(state)
      clearTimeout(copyTimer.current)
      copyTimer.current = setTimeout(() => setCopyState('idle'), 2000)
    }
    if (!navigator.clipboard) {
      flash('failed')
      return
    }
    navigator.clipboard.writeText(url).then(() => flash('copied')).catch(() => flash('failed'))
  }, [playerIds, season, source])

  const players = data?.players || []
  const anyGoalkeeper = players.some((p) => p.profile?.position === 'Goalkeeper')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl sm:max-w-4xl max-h-[85vh] overflow-y-auto border-hairline-dark bg-night">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitCompareArrows className="h-5 w-5 text-gold" aria-hidden="true" />
            Player Comparison · {formatSeasonLabel(data?.season ?? season)}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopyLink}
              className="ml-auto mr-6 text-muted-foreground hover:text-foreground"
            >
              <Link2 className="mr-1.5 h-4 w-4" />
              <span role="status" aria-live="polite">
                {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Copy link'}
              </span>
            </Button>
          </DialogTitle>
          <DialogDescription>
            Current-club season output, per-90 rates, and career volume side by side.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <CleatLoader surface="night" />
          </div>
        ) : error ? (
          <p className="py-8 text-center text-sm text-destructive">{error}</p>
        ) : players.length ? (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr>
                  <th className="w-36 p-2" />
                  {players.map((p) => (
                    <th key={p.profile.player_id} className="p-2 text-center align-bottom">
                      <Link to={withSeasonParam(`/players/${p.profile.player_id}`, seasonOverride)} className="inline-flex flex-col items-center gap-1.5 no-underline hover:no-underline group">
                        {p.profile.player_photo ? (
                          <img src={p.profile.player_photo} alt="" className="h-14 w-14 rounded-full object-cover bg-secondary" />
                        ) : (
                          <span className="h-14 w-14 rounded-full bg-secondary inline-flex items-center justify-center text-sm font-semibold text-muted-foreground">
                            {p.profile.player_name?.slice(0, 2).toUpperCase()}
                          </span>
                        )}
                        <span className="font-serif text-xl leading-tight text-foreground group-hover:text-gold transition-colors">
                          {p.profile.player_name}
                        </span>
                        <span className="text-xs text-muted-foreground font-normal">
                          {[p.profile.position, p.profile.age ? `${p.profile.age} yrs` : null].filter(Boolean).join(' · ')}
                        </span>
                        <StatusBadge status={p.profile.status} />
                        <span className="text-xs text-muted-foreground font-normal">
                          {p.profile.loan_team_name || p.profile.primary_team_name}
                        </span>
                        {p.totals?.rollup_missing ? (
                          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                            No data for this season
                          </span>
                        ) : p.provenance ? (
                          <ProvenanceChip provenance={p.provenance} />
                        ) : null}
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
                  // Lower-is-better rows (e.g. goals conceded) highlight the
                  // minimum — and a best of 0 is a real best there, so only the
                  // maximum-style rows keep the historical `best > 0` guard.
                  const numeric = values.map((v) => (typeof v === 'number' ? v : (row.lowerBetter ? Infinity : -Infinity)))
                  const best = row.lowerBetter ? Math.min(...numeric) : Math.max(...numeric)
                  const bestIsHighlightable = row.lowerBetter ? Number.isFinite(best) : best > 0
                  return (
                    <Fragment key={`${row.source}-${row.key}-${index}`}>
                      {row.section && (
                        <tr>
                          <td colSpan={players.length + 1} className="pt-4 pb-1 px-2">
                            <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.18em] text-gold">{row.section}</span>
                          </td>
                        </tr>
                      )}
                      <tr className="border-t border-hairline-dark">
                        <td className="p-2 text-xs text-muted-foreground">{row.label}</td>
                        {values.map((value, i) => (
                          <td
                            key={i}
                            className={`p-2 text-center tabular-nums ${!row.noHighlight && value !== null && numeric[i] === best && players.length > 1 && bestIsHighlightable ? 'font-semibold text-gold' : 'text-foreground'}`}
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

// Viewer change = fresh screen. The desk holds state that belongs to the person
// looking (watchlist marks, the open introduction form and its draft, the
// compare selection, the search text). It is keyed on the viewer, so on logout,
// login or an account switch React remounts it and all of that is discarded;
// late answers to the old instance land nowhere. Keep viewer-bound state inside
// ScoutDeskBody — never in this wrapper.
export function ScoutPage() {
  const viewer = useViewerKey()
  return <ScoutDeskBody key={viewer} />
}

// --- p2-c4 begin ---
function ScoutDeskBody() {
  const life = useViewerLifetime()
  const api = life.api
  const enabled = useScoutAttend(api)
  const [params] = useSearchParams()
  return enabled && params.get('desk') === 'clubs' ? <ScoutClubsTrials /> : <PlayerScoutPage clubsEnabled={enabled} />
}
// --- p2-c4 end ---

function PlayerScoutPage({ clubsEnabled }) {
  // Requests and side effects go through this viewer's lifetime (see lib/viewer-lifetime.js).
  const life = useViewerLifetime()
  const api = life.api
  const { api_football_frozen: frozen } = useDataMode()
  const [players, setPlayers] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [boards, setBoards] = useState(null)
  const [boardsLoading, setBoardsLoading] = useState(true)
  const [resolvedSeason, setResolvedSeason] = useState(null)
  const { currentSeason, displaySeason: defaultSeason } = useSeasonDirectory()
  const [storedSeason, setStoredSeason] = useState(() => seasonStore.get())

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  // Phase-of-play view — deep-linkable via /scout?phase=defense
  const [phase, setPhase] = useState(() => {
    const requested = new URLSearchParams(window.location.search).get('phase')
    return PHASES[requested] ? requested : 'all'
  })
  const [position, setPosition] = useState('all')
  const [status, setStatus] = useState('all')
  const [agePreset, setAgePreset] = useState('all')
  const [sort, setSort] = useState(() => {
    const requested = new URLSearchParams(window.location.search).get('phase')
    return (PHASES[requested] || PHASES.all).defaultSort
  })
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(1)
  const [resultView, setResultView] = useState(initialResultView)
  const changeResultView = useCallback((next) => {
    setResultView(next)
    try {
      window.localStorage.setItem(RESULT_VIEW_KEY, next)
    } catch {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }, [])

  const [compareIds, setCompareIds] = useState([])
  const [compareOpen, setCompareOpen] = useState(false)
  const searchTimer = useRef(null)

  const auth = useAuth()
  const contactRail = useContactRail()
  const openLoginModal = useGuarded(life, useAuthUI().openLoginModal)
  const saveCsv = useGuarded(life, saveScoutCsv)
  const [verificationState, setVerificationState] = useState(null)
  const scoutVerification = !auth?.token ? 'signed-out'
    : verificationState?.token === auth.token ? verificationState.status : 'loading'
  const verifiedScout = scoutVerification === 'approved'
  const canIntroduce = scoutVerification !== 'unverified'
  // Watchlist membership and an open introduction belong to the viewer who
  // loaded or opened them. useViewerState refuses writes made for another
  // viewer (a late answer to a request the previous viewer started).
  const viewer = viewerKey(auth?.token)
  const [watchedIds, setWatchedIds] = useViewerState(viewer, null)
  const [introducePlayer, setIntroducePlayer] = useViewerState(viewer, null)
  const [exporting, setExporting] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedSource = searchParams.get('source')
  const source = SOURCE_VALUES.has(requestedSource) ? requestedSource : 'all'
  const seasonParam = searchParams.get('season')
  const urlSeason = /^\d{4}$/.test(seasonParam || '') ? Number(seasonParam) : undefined
  // Leave implicit reads to the server; display_season labels the default only.
  const selectedSeason = seasonParam === null ? storedSeason : urlSeason
  const seasonOverride = selectedSeason

  const phaseConfig = PHASES[phase]
  // The phase IS a position filter when active; the standalone position
  // Select only applies on the 'all' view (it's hidden otherwise).
  const effectivePosition = phase === 'all' ? (position !== 'all' ? position : null) : phaseConfig.position

  // Keep phase in sync with the URL after mount: same-route navigation (the
  // header's Scout link renders bare /scout without remounting) and browser
  // back/forward change searchParams without going through changePhase.
  useEffect(() => {
    const requested = searchParams.get('phase')
    const next = PHASES[requested] ? requested : 'all'
    setPhase((current) => {
      if (next === current) return current
      setSort(PHASES[next].defaultSort)
      setOrder(ASC_DEFAULT_SORTS.has(PHASES[next].defaultSort) ? 'asc' : 'desc')
      return next
    })
  }, [searchParams])

  const changePhase = useCallback((next) => {
    if (!next || !PHASES[next]) return // Radix emits '' when re-clicking the active item
    setPhase(next)
    setSort(PHASES[next].defaultSort)
    setOrder(ASC_DEFAULT_SORTS.has(PHASES[next].defaultSort) ? 'asc' : 'desc')
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev)
      if (next === 'all') params.delete('phase')
      else params.set('phase', next)
      return params
    }, { replace: true })
    track('scout_phase_changed', { phase: next })
  }, [setSearchParams])

  const changeSeason = useCallback((season, isCurrent) => {
    if (isCurrent) {
      seasonStore.clear()
      setStoredSeason(undefined)
    } else {
      seasonStore.set(season)
      setStoredSeason(season)
    }
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      next.set('season', String(season))
      return next
    }, { replace: true })
  }, [setSearchParams])

  const changeSource = useCallback((nextSource) => {
    if (nextSource !== 'all' && !SOURCE_VALUES.has(nextSource)) return
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (nextSource === 'all') next.delete('source')
      else next.set('source', nextSource)
      return next
    }, { replace: true })
  }, [setSearchParams])

  // Compare deep links keep signed IDs as strings so local-player negatives
  // survive navigation and never cross an API boundary as coerced numbers.
  useEffect(() => {
    const raw = searchParams.get('compare')
    if (!raw) return
    const ids = [...new Set(raw.split(',').map(normalizeSignedPlayerId).filter(Boolean))]
    if (ids.length >= 1 && ids.length <= 4) {
      // One id (the Compare button on a player's page) only fills the tray;
      // the comparison itself opens once there are two.
      setCompareIds(ids)
      if (ids.length >= 2) setCompareOpen(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!auth?.token || contactRail !== true) return
    let live = true
    api.getScoutVerification()
      .then((data) => {
        if (live) setVerificationState({ token: auth.token, status: data?.verification?.status === 'approved' ? 'approved' : 'unverified' })
      })
      .catch(() => { if (live) setVerificationState({ token: auth.token, status: 'unavailable' }) })
    return () => { live = false }
  }, [api, auth.token, contactRail])

  // Load watchlist ids once when signed in
  useEffect(() => {
    if (!auth?.token) return undefined
    let cancelled = false
    api.getScoutWatchlistIds()
      .then((data) => { if (!cancelled) setWatchedIds(new Set(data?.player_ids || [])) })
      .catch((err) => { console.error('Failed to load watchlist ids', err) })
    return () => { cancelled = true }
  }, [api, auth?.token, setWatchedIds])

  const toggleWatch = useCallback((player) => {
    if (!auth?.token) {
      openLoginModal()
      return
    }
    const playerId = player.player_id
    const wasWatched = !!watchedIds?.has(playerId)
    setWatchedIds((current) => {
      const next = new Set(current || [])
      if (wasWatched) next.delete(playerId)
      else next.add(playerId)
      return next
    })
    const action = wasWatched
      ? api.removeFromScoutWatchlist(playerId)
      : api.addToScoutWatchlist(playerId)
    action.catch((err) => {
      console.error('Watchlist update failed', err)
      // Revert optimistic update
      setWatchedIds((current) => {
        const next = new Set(current || [])
        if (wasWatched) next.add(playerId)
        else next.delete(playerId)
        return next
      })
    })
  }, [api, auth?.token, openLoginModal, setWatchedIds, watchedIds])

  const handleExportCsv = useCallback(async () => {
    if (!auth?.token) {
      openLoginModal()
      return
    }
    setExporting(true)
    try {
      const params = {}
      if (debouncedSearch) params.search = debouncedSearch
      if (effectivePosition) params.position = effectivePosition
      if (status !== 'all') params.status = status
      if (source !== 'all') params.source = source
      const preset = AGE_PRESETS.find((p) => p.key === agePreset)
      Object.assign(params, preset?.params || {})
      if (selectedSeason != null) params.season = selectedSeason
      // The whole body is read and the viewer re-checked (life.api) before the
      // guarded save: nothing is downloaded after a viewer change or after
      // leaving the desk.
      const blob = await api.fetchScoutCsv({ ...params, sort, order })
      saveCsv(blob)
    } catch (err) {
      if (!isStaleViewerError(err)) console.error('CSV export failed', err)
    } finally {
      setExporting(false)
    }
  }, [auth?.token, openLoginModal, debouncedSearch, effectivePosition, status, source, selectedSeason, api, saveCsv, sort, order, agePreset])

  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(searchTimer.current)
  }, [search])

  useEffect(() => {
    if (debouncedSearch) track('search_performed', { q_len: debouncedSearch.length, surface: 'scout' })
  }, [debouncedSearch])

  const filterParams = useMemo(() => {
    const params = {}
    if (debouncedSearch) params.search = debouncedSearch
    if (effectivePosition) params.position = effectivePosition
    if (status !== 'all') params.status = status
    if (source !== 'all') params.source = source
    const preset = AGE_PRESETS.find((p) => p.key === agePreset)
    Object.assign(params, preset?.params || {})
    if (selectedSeason != null) params.season = selectedSeason
    return params
  }, [debouncedSearch, effectivePosition, status, source, agePreset, selectedSeason])

  // Reset to first page when filters change
  useEffect(() => { setPage(1) }, [filterParams, sort, order])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.getScoutPlayers({ ...filterParams, sort, order, page, per_page: 25 })
      .then((data) => {
        if (cancelled) return
        setPlayers(data?.players || [])
        setTotal(data?.total || 0)
        setTotalPages(data?.total_pages || 0)
        if (data?.season != null) setResolvedSeason(data.season)
      })
      .catch((err) => {
        console.error('Failed to load scout players', err)
        if (!cancelled) { setPlayers([]); setTotal(0); setTotalPages(0) }
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [filterParams, sort, order, page, api])

  useEffect(() => {
    let cancelled = false
    setBoardsLoading(true)
    const boardFilters = { limit: 5, phase }
    if (selectedSeason != null) boardFilters.season = selectedSeason
    const preset = AGE_PRESETS.find((p) => p.key === agePreset)
    Object.assign(boardFilters, preset?.params || {})
    if (effectivePosition) boardFilters.position = effectivePosition
    if (status !== 'all') boardFilters.status = status
    if (source !== 'all') boardFilters.source = source
    api.getScoutLeaderboards(boardFilters)
      .then((data) => {
        if (cancelled) return
        setBoards(data?.leaderboards || null)
        if (data?.season != null) setResolvedSeason(data.season)
      })
      .catch((err) => {
        console.error('Failed to load leaderboards', err)
        if (!cancelled) setBoards(null)
      })
      .finally(() => { if (!cancelled) setBoardsLoading(false) })
    return () => { cancelled = true }
  }, [phase, effectivePosition, status, source, agePreset, selectedSeason, api])

  const toggleCompare = useCallback((playerId) => {
    const normalizedPlayerId = normalizeSignedPlayerId(playerId)
    if (!normalizedPlayerId) return
    setCompareIds((current) => {
      if (current.includes(normalizedPlayerId)) return current.filter((id) => id !== normalizedPlayerId)
      if (current.length >= 4) return current
      return [...current, normalizedPlayerId]
    })
  }, [])

  const toggleSort = useCallback((key) => {
    setSort((currentSort) => {
      if (currentSort === key) {
        setOrder((o) => (o === 'desc' ? 'asc' : 'desc'))
        return currentSort
      }
      setOrder(ASC_DEFAULT_SORTS.has(key) ? 'asc' : 'desc')
      return key
    })
  }, [])

  const headerCell = (key, label, alignRight = true, title = undefined) => (
    <th
      title={title}
      className={`px-3 py-3 font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] cursor-pointer select-none hover:text-chalk transition-colors whitespace-nowrap ${sort === key ? 'text-chalk' : 'text-[#8C9791]'} ${alignRight ? 'text-right' : 'text-left'}`}
      onClick={() => toggleSort(key)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className={`h-3 w-3 ${sort === key ? 'text-gold' : 'opacity-40'}`} />
      </span>
    </th>
  )

  const statColumns = phaseConfig.columns.map((key) => STAT_COLUMNS[key])
  const tableColumnCount = 8 + statColumns.length
  const displaySeason = selectedSeason ?? defaultSeason ?? resolvedSeason ?? currentSeason

  const thClass = 'px-3 py-3 font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-[#8C9791]'
  const selectTriggerClass = 'h-11 w-full rounded-full px-4 text-[13.5px]'

  return (
    <ScoutSurface>
      <div className="floodlight-container pb-28">
        <ScoutHeader
          eyebrow={<span className="inline-flex items-center gap-2"><Globe className="h-3.5 w-3.5" aria-hidden="true" />Scout desk · Global talent discovery</span>}
          title="Who are you"
          accent="looking for?"
          lede={`Every tracked academy and loan player, ranked across clubs and leagues — viewing ${formatSeasonLabel(displaySeason)}.`}
          actions={(
            <>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-[#8C9791]">Season</span>
                <SeasonSelect
                  value={selectedSeason}
                  onValueChange={changeSeason}
                />
              </div>
              <Button variant="outline" size="sm" asChild className={deskPillClass}>
                <Link to="/scout/watchlist" className="no-underline hover:no-underline">
                  <Star className="mr-1.5 h-4 w-4" />
                  Watchlist
                  {watchedIds && watchedIds.size > 0 && (
                    <span className="ml-1.5 font-mono text-[11px] tabular-nums text-gold">
                      {watchedIds.size}
                    </span>
                  )}
                </Link>
              </Button>
              {contactRail === true ? (
                <Button variant="outline" size="sm" asChild className={deskPillClass}>
                  <Link to="/introductions" className="no-underline hover:no-underline">
                    <Send className="mr-1.5 h-4 w-4" />
                    Introductions
                  </Link>
                </Button>
              ) : null}
              <Button variant="outline" size="sm" asChild className={deskPillClass}>
                <Link to="/scout/verification" className="no-underline hover:no-underline">
                  <ShieldCheck className="mr-1.5 h-4 w-4" />
                  {verifiedScout ? 'Verified scout' : scoutVerification === 'loading' && contactRail === true ? 'Checking verification…' : scoutVerification === 'unavailable' ? 'Scout verification' : scoutVerification === 'signed-out' ? 'Get verified' : contactRail === true ? 'Get verified to introduce yourself' : 'Get verified'}
                </Link>
              </Button>
              <Button variant="outline" size="sm" onClick={handleExportCsv} disabled={exporting} className={deskPillClass}>
                {exporting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
                Export CSV
              </Button>
            </>
          )}
        >
          {clubsEnabled && <ScoutTabs />}
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <label className="flex h-14 min-w-0 flex-1 items-center gap-3 rounded-full border border-chalk/25 px-5 transition-colors focus-within:border-gold">
              <Search className="h-[18px] w-[18px] shrink-0 text-muted-dark" aria-hidden="true" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search players by name…"
                className="min-w-0 flex-1 border-0 bg-transparent text-base text-chalk outline-none placeholder:text-[#8C9791]"
                aria-label="Search players"
              />
            </label>
            {/* Phase-of-play view switcher */}
            <section aria-label="Phase of play" className="min-w-0">
              <ToggleGroup
                type="single"
                value={phase}
                onValueChange={changePhase}
                className="w-full overflow-x-auto rounded-full border border-chalk/20 p-1 sm:w-fit"
              >
                {PHASE_ORDER.map((key) => (
                  <ToggleGroupItem
                    key={key}
                    value={key}
                    aria-label={`${PHASES[key].label} view`}
                    className="h-11 shrink-0 rounded-full px-4 text-[13.5px] font-normal text-[#C9CFCB] first:rounded-full last:rounded-full hover:bg-chalk/[0.05] hover:text-chalk data-[state=on]:bg-chalk data-[state=on]:text-night"
                  >
                    {PHASES[key].label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </section>
          </div>
          {phase !== 'all' ? (
            <p className="text-[13px] text-muted-dark">
              {phaseConfig.description} Dashes mean no per-match coverage for that player.
            </p>
          ) : null}
        </ScoutHeader>

        {/* Leaderboards */}
        <section aria-label="Leaderboards" className="mb-12 grid grid-cols-1 gap-x-8 gap-y-10 sm:grid-cols-2 xl:grid-cols-4">
          {phaseConfig.boards.map((board) => (
            <LeaderboardCard
              key={board.key}
              board={board}
              entries={boards?.[board.key]}
              loading={boardsLoading}
              season={selectedSeason ?? resolvedSeason}
              seasonOverride={seasonOverride}
            />
          ))}
        </section>

        {/* Filters */}
        <section aria-label="Filters" className="mb-4 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-chalk pb-3">
            <h2 className="display text-[1.875rem] leading-none sm:text-[2.125rem]">Players</h2>
            <div className="flex flex-wrap items-center gap-4">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] tabular-nums text-[#8C9791]">
                {loading ? 'Loading…' : `${total.toLocaleString()} players`}
              </span>
              <div role="group" aria-label="Show players as" className="flex rounded-full border border-chalk/20 p-1">
                {RESULT_VIEWS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => changeResultView(option.value)}
                    aria-pressed={resultView === option.value}
                    className={`h-11 rounded-full px-4 text-[13px] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      resultView === option.value ? 'bg-chalk text-night' : 'text-[#C9CFCB] hover:text-chalk'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 font-mono text-[10.5px] uppercase tracking-[0.16em] text-[#8C9791]">Age</span>
            {AGE_PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => setAgePreset(preset.key)}
                aria-pressed={agePreset === preset.key}
                className={`h-9 rounded-full border px-3.5 text-[13px] transition-colors duration-150 ${
                  agePreset === preset.key
                    ? 'border-chalk bg-chalk text-night'
                    : 'border-chalk/25 text-[#C9CFCB] hover:border-chalk/50 hover:text-chalk'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:flex lg:flex-row">
            {phase === 'all' && (
              <Select value={position} onValueChange={setPosition}>
                <SelectTrigger className={`${selectTriggerClass} lg:w-48`} aria-label="Filter by position">
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
            )}
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className={`${selectTriggerClass} lg:w-48`} aria-label="Filter by pathway status">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="academy">Academy</SelectItem>
                <SelectItem value="on_loan">On loan</SelectItem>
                <SelectItem value="first_team">First team</SelectItem>
                <SelectItem value="sold">Sold</SelectItem>
                <SelectItem value="released">Released</SelectItem>
                <SelectItem value="left">Left</SelectItem>
              </SelectContent>
            </Select>
            <Select value={source} onValueChange={changeSource}>
              <SelectTrigger className={`${selectTriggerClass} lg:w-52`} aria-label="Filter by stats source">
                <SelectValue placeholder="Source" />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_FILTERS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={(value) => { setSort(value); setOrder(ASC_DEFAULT_SORTS.has(value) ? 'asc' : 'desc') }}>
              <SelectTrigger className={`${selectTriggerClass} lg:ml-auto lg:w-56`} aria-label="Sort by">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                {phaseConfig.sortOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </section>

        {/* Results: the standard player card, or the dense table */}
        <section aria-label="Results" className="border-t border-hairline-dark">
          {resultView === 'cards' ? (
            loading ? (
              <div className="grid grid-cols-1 gap-6 py-8 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-[500px] w-full rounded-[28px]" />)}
              </div>
            ) : players.length ? (
              <ul className="pc-card-grid py-8" data-testid="scout-player-cards">
                {players.map((player) => {
                  const watched = !!watchedIds?.has(player.player_id)
                  const clubName = player.loan_team_name || player.primary_team_name || null
                  const selected = compareIds.includes(String(player.player_id))
                  return (
                    <li key={player.id}>
                      <PlayerCard
                        to={withSeasonParam(`/players/${player.player_id}`, seasonOverride)}
                        name={player.player_name}
                        photoUrl={player.approved_photo_url || null}
                        faceUrl={player.player_photo || null}
                        confirmed={player.club_confirmed === true}
                        clubName={clubName}
                        role={player.position ? positionAbbreviation(player.position) : null}
                        line={player.bio_line || cardLine({ position: player.position, clubName })}
                        appearances={player.appearances}
                        minutes={player.minutes_played}
                        action={{
                          label: watched ? 'Watching' : 'Watch',
                          pressed: watched,
                          ariaLabel: watched ? `Unwatch ${player.player_name}` : `Watch ${player.player_name}`,
                          onClick: () => toggleWatch(player),
                        }}
                        extras={(
                          <>
                            <button
                              type="button"
                              className="pc-icon"
                              aria-pressed={selected}
                              aria-label={`Compare ${player.player_name}`}
                              title={selected ? 'Remove from comparison' : 'Add to comparison'}
                              disabled={!selected && compareIds.length >= 4}
                              onClick={() => toggleCompare(player.player_id)}
                            >
                              <GitCompareArrows className="h-4 w-4" aria-hidden="true" />
                            </button>
                            {contactRail === true && player.contactable ? (auth?.token && !canIntroduce ? (
                              <Link to="/scout/verification" className="pc-icon" aria-label="Get verified to introduce yourself" title="Get verified to introduce yourself">
                                <Send className="h-4 w-4" aria-hidden="true" />
                              </Link>
                            ) : (
                              <button
                                type="button"
                                className="pc-icon"
                                aria-label={`Introduce yourself to ${player.player_name}`}
                                title="Introduce yourself"
                                onClick={() => (auth?.token ? setIntroducePlayer(player) : openLoginModal())}
                              >
                                <Send className="h-4 w-4" aria-hidden="true" />
                              </button>
                            )) : null}
                          </>
                        )}
                      />
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="display px-3 py-16 text-center text-3xl text-chalk">No players match these filters.</p>
            )
          ) : (
          <div className="relative overflow-x-auto">
            <table className={`w-full border-collapse ${statColumns.length > 6 ? 'min-w-[920px]' : 'min-w-[760px]'}`}>
              <thead>
                <tr className="border-b border-hairline-dark">
                  <th className={`w-10 px-2 text-left ${thClass}`}>
                    <span className="sr-only">Watch</span>
                  </th>
                  <th className={`w-10 text-left ${thClass}`}>
                    <span className="sr-only">Compare</span>
                  </th>
                  {headerCell('name', 'Player', false)}
                  <th className={`text-left ${thClass}`}>Pos</th>
                  <th className={`text-left ${thClass}`}>Status</th>
                  <th className={`text-left ${thClass}`}>Club</th>
                  <th className={`text-left ${thClass}`}>Form</th>
                  <th className={`text-left ${thClass}`}>Source</th>
                  {statColumns.map((col) =>
                    col.sortKey ? (
                      <Fragment key={col.label}>{headerCell(col.sortKey, col.label, true, col.title)}</Fragment>
                    ) : (
                      <th
                        key={col.label}
                        title={col.title}
                        className={`text-right whitespace-nowrap ${thClass}`}
                      >
                        {col.label}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline-dark">
                {loading ? (
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={tableColumnCount} className="px-3 py-3"><Skeleton className="h-10 w-full" /></td>
                    </tr>
                  ))
                ) : players.length ? (
                  players.map((player) => {
                    const selected = compareIds.includes(String(player.player_id))
                    const watched = !!watchedIds?.has(player.player_id)
                    return (
                      <tr key={player.id} className={`transition-colors duration-150 hover:bg-chalk/[0.035] ${selected ? 'bg-gold/[0.06]' : ''}`}>
                        <td className="px-2 py-3 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => toggleWatch(player)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-chalk/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            aria-label={watched ? `Unwatch ${player.player_name}` : `Watch ${player.player_name}`}
                            title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
                          >
                            <Star className={`h-4 w-4 transition-colors ${watched ? 'fill-gold text-gold' : 'text-muted-dark/60 hover:text-muted-dark'}`} />
                          </button>
                          {contactRail === true && player.contactable ? (auth?.token && !canIntroduce ? (
                            <Link to="/scout/verification" className="ml-0.5 inline-flex h-8 w-8 items-center justify-center rounded-full hover:bg-chalk/[0.06]" aria-label="Get verified to introduce yourself" title="Get verified to introduce yourself"><Send className="h-4 w-4 text-muted-dark/70" /></Link>
                          ) : (
                            <button
                              type="button"
                              onClick={() => (auth?.token ? setIntroducePlayer(player) : openLoginModal())}
                              className="ml-0.5 inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-chalk/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              aria-label={`Introduce yourself to ${player.player_name}`}
                              title="Introduce yourself"
                            >
                              <Send className="h-4 w-4 text-muted-dark/70 hover:text-gold" />
                            </button>
                          )) : null}
                        </td>
                        <td className="py-3">
                          <Checkbox
                            checked={selected}
                            onCheckedChange={() => toggleCompare(player.player_id)}
                            disabled={!selected && compareIds.length >= 4}
                            aria-label={`Compare ${player.player_name}`}
                          />
                        </td>
                        <td className="px-3 py-3"><PlayerCell player={player} season={seasonOverride} /></td>
                        <td className="px-3 py-3 font-mono text-[12px] text-muted-dark whitespace-nowrap">{positionAbbreviation(player.position)}</td>
                        <td className="px-3 py-3"><StatusBadge status={player.status} /></td>
                        <td className="px-3 py-3 max-w-44">
                          <span className="block truncate text-sm text-chalk/90">{player.loan_team_name || player.primary_team_name || '—'}</span>
                          {player.loan_team_name && (player.owner_team_name || player.primary_team_name) && (
                            <span className="block truncate text-xs text-muted-dark">from {player.owner_team_name || player.primary_team_name}</span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          {player.appearances === 0 && player.data_depth === 'profile_only' ? (
                            <Link
                              to="/pricing"
                              className="text-[11px] text-muted-dark underline decoration-dotted hover:text-gold"
                              title="No stats provider covers this league — Film Room will fix that"
                            >
                              No coverage
                            </Link>
                          ) : (
                            <FormIndicator form={player.recent_form} />
                          )}
                        </td>
                        <td className="px-3 py-3 whitespace-nowrap">
                          <ProvenanceChip provenance={player.provenance} />
                        </td>
                        {statColumns.map((col) => (
                          <td key={col.label} className={`px-3 py-3 text-right font-mono text-[13px] tabular-nums ${col.cellClass || 'text-chalk/85'}`}>
                            {col.render(player)}
                          </td>
                        ))}
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={tableColumnCount} className="px-3 py-16 text-center">
                      <p className="display text-3xl text-chalk">No players match these filters.</p>
                      <div className="mt-6 flex flex-wrap justify-center gap-2">
                        {!frozen && (<Button variant="outline" size="sm" asChild className={deskPillClass}>
                          <Link to="/scout/lists">
                            <Globe className="mr-1.5 h-4 w-4" />
                            Search worldwide
                          </Link>
                        </Button>)}
                        <Button variant="outline" size="sm" asChild className={deskPillClass}>
                          <Link to="/local-players/new">
                            <UserPlus className="mr-1.5 h-4 w-4" />
                            Add a local player
                          </Link>
                        </Button>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-hairline-dark py-4">
              <Button variant="outline" size="sm" className={deskPillClass} disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                <ArrowLeft className="mr-1 h-4 w-4" /> Previous
              </Button>
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] tabular-nums text-[#8C9791]">Page {page} of {totalPages}</span>
              <Button variant="outline" size="sm" className={deskPillClass} disabled={page >= totalPages || loading} onClick={() => setPage((p) => p + 1)}>
                Next <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          )}
        </section>

        {/* Compare tray */}
        {compareIds.length > 0 && (
          <div className="fixed inset-x-0 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-40 flex justify-center px-4 pointer-events-none sm:bottom-6 sm:pr-24">
            <div className="pointer-events-auto flex items-center gap-3 rounded-full border border-chalk/20 bg-ink/95 py-2 pl-5 pr-2 shadow-[0_12px_32px_rgb(0_0_0/0.4)] backdrop-blur">
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] tabular-nums text-[#C9CFCB]">
                {compareIds.length} of 4 selected
              </span>
              <Button
                size="sm"
                variant="on-dark"
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
                className="inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-dark hover:bg-chalk/[0.06] hover:text-chalk transition-colors"
                aria-label="Clear comparison selection"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        <CompareDialog
          open={compareOpen}
          onOpenChange={setCompareOpen}
          playerIds={compareIds}
          season={selectedSeason}
          seasonOverride={seasonOverride}
          source={source}
        />
        <IntroduceDialog
          open={canIntroduce && !!auth?.token && !!introducePlayer}
          onOpenChange={(next) => { if (!next) setIntroducePlayer(null) }}
          player={introducePlayer}
        />
      </div>
    </ScoutSurface>
  )
}
