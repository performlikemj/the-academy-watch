import { useSeasonDirectory } from '@/hooks/useSeasonDirectory'
import { PublicMatchPanels } from '@/components/PublicMatchPanels'
import { useDataMode } from '@/hooks/useDataMode'
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { StatFigure } from '@/components/public/Floodlight'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
    Drawer,
    DrawerContent,
    DrawerHeader,
    DrawerTitle,
    DrawerDescription,
} from '@/components/ui/drawer'
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
} from 'recharts'
import { Loader2, ArrowLeft, User, TrendingUp, Calendar, Target, ChevronRight, ChevronDown, Users, ExternalLink, MapPin, Flag, Star } from 'lucide-react'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import FlagDataDialog from '@/components/FlagDataDialog'
import ContentReportDialog from '@/components/ContentReportDialog'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { format } from 'date-fns'
import { SponsorStrip } from '@/components/SponsorSidebar'
import { MatchDetailDrawer } from '@/components/MatchDetailDrawer'
import PlayerJourneyView from '@/components/PlayerJourneyView'
import { JourneyProvider, useJourney } from '@/contexts/JourneyContext'
import { MiniProgressBar } from '@/components/MiniProgressBar'
import { SeasonStatsPanel } from '@/components/SeasonStatsPanel'
import { CommentSection } from '@/components/CommentSection'
import { PlayerLinksSection } from '@/components/PlayerLinksSection'
import { PlayerReachControls } from '@/components/PlayerReachControls'
import { ShowcaseSection } from '@/components/ShowcaseSection'
import { ProvenanceChip } from '@/components/SelfReportedBadge'
import { PlayerAvailability } from '@/components/PlayerAvailability'
import { SeasonSelect } from '@/components/ui/SeasonSelect'
import { seasonStore } from '@/lib/seasonStore'
import { formatSeasonLabel, withSeasonParam } from '@/lib/seasons'
import { track } from '@/lib/track'
import { Tooltip as UiTooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
// Floodlight chart palette (page-local; shared theme-constants stay untouched).
const CHART_GRID_COLOR = '#D8D2C4'    // hairline
const CHART_AXIS_COLOR = '#5A6560'    // muted
const CHART_TOOLTIP_BG = '#F3F0E8'    // chalk
const CHART_TOOLTIP_BORDER = '#D8D2C4'
// Series step through clearly different lightness levels and dash patterns,
// so lines stay distinguishable without relying on hue.
const CHART_SERIES = [
    { color: '#0E1311', dash: undefined },  // ink
    { color: '#CFAE62', dash: undefined },  // gold
    { color: '#0F3D2E', dash: '6 3' },      // club green
    { color: '#A3ADA7', dash: '2 3' },      // light grey
    { color: '#84661F', dash: '8 3 2 3' },  // gold text
    { color: '#5A6560', dash: '4 4' },      // muted
    { color: '#0E1311', dash: '1 3' },      // ink, dotted
]

/** Dims children when viewing a past career stop so SeasonStatsPanel takes focus. */
function JourneyDimmer({ children, className = '' }) {
    const { selectedNode, progressionNodes } = useJourney()
    const isLatest = selectedNode && selectedNode.id === progressionNodes[progressionNodes.length - 1]?.id
    const dimmed = selectedNode && !isLatest
    return (
        <div className={`transition-opacity duration-300 ${dimmed ? 'opacity-30 pointer-events-none' : ''} ${className}`}>
            {children}
        </div>
    )
}

const METRIC_CONFIG = {
    'Attacker': {
        default: ['goals', 'shots_total', 'shots_on'],
        options: [
            { key: 'goals', label: 'Goals', color: '#1D5A40' },
            { key: 'assists', label: 'Assists', color: '#d97706' },
            { key: 'shots_total', label: 'Shots', color: '#dc2626' },
            { key: 'shots_on', label: 'Shots on Target', color: '#db2777' },
            { key: 'dribbles_success', label: 'Dribbles', color: '#ea580c' },
            { key: 'passes_key', label: 'Key Passes', color: '#0d9488' },
        ]
    },
    'Midfielder': {
        default: ['passes_total', 'passes_key', 'tackles_total'],
        options: [
            { key: 'goals', label: 'Goals', color: '#1D5A40' },
            { key: 'assists', label: 'Assists', color: '#d97706' },
            { key: 'passes_total', label: 'Passes', color: '#7c3aed' },
            { key: 'passes_key', label: 'Key Passes', color: '#0d9488' },
            { key: 'tackles_total', label: 'Tackles', color: '#ea580c' },
            { key: 'duels_won', label: 'Duels Won', color: '#0891b2' },
            { key: 'interceptions', label: 'Interceptions', color: '#dc2626' },
        ]
    },
    'Defender': {
        default: ['tackles_total', 'duels_won', 'interceptions'],
        options: [
            { key: 'tackles_total', label: 'Tackles', color: '#ea580c' },
            { key: 'duels_won', label: 'Duels Won', color: '#1D5A40' },
            { key: 'interceptions', label: 'Interceptions', color: '#7c3aed' },
            { key: 'blocks', label: 'Blocks', color: '#db2777' },
            { key: 'clearances', label: 'Clearances', color: '#d97706' },
            { key: 'passes_total', label: 'Passes', color: '#0891b2' },
        ]
    },
    'Goalkeeper': {
        default: ['saves', 'passes_total'],
        options: [
            { key: 'saves', label: 'Saves', color: '#1D5A40' },
            { key: 'passes_total', label: 'Passes', color: '#d97706' },
            { key: 'rating', label: 'Rating', color: '#84661F' },
        ]
    }
}

for (const config of Object.values(METRIC_CONFIG)) {
    config.options.forEach((option, index) => {
        const series = CHART_SERIES[index % CHART_SERIES.length]
        option.color = series.color
        option.dash = series.dash
    })
}

// Writeups are stored as HTML. Parse into an inert document (DOMParser never
// runs scripts or loads resources) and show only its text — never the markup.
const DEFAULT_POSITION = 'Midfielder'

function AcademyStatsSection({ academyStats, defaultOpen = false }) {
    const [open, setOpen] = useState(defaultOpen)

    // Group season_stats by season (descending) for development arc
    const seasonGroups = React.useMemo(() => {
        if (!academyStats.season_stats?.length) return []
        const groups = {}
        for (const entry of academyStats.season_stats) {
            const key = entry.season
            if (!groups[key]) groups[key] = []
            groups[key].push(entry)
        }
        return Object.entries(groups)
            .sort(([a], [b]) => Number(b) - Number(a))
            .map(([season, entries]) => ({ season: Number(season), entries }))
    }, [academyStats.season_stats])

    const statOrDash = (val) => val != null ? val : '\u2014'

    return (
        <Collapsible open={open} onOpenChange={setOpen}>
            <Card className={defaultOpen ? 'bg-chalk-2 border-border' : ''}>
                <CollapsibleTrigger asChild>
                    <button className="w-full text-left">
                        <CardContent className="py-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Users className="h-5 w-5 text-muted-foreground" />
                                    <div>
                                        <span className="font-medium text-ink">Academy Development</span>
                                        <span className="ml-3 text-sm text-muted-foreground">
                                            {academyStats.appearances} apps, {academyStats.goals}G {academyStats.assists}A
                                            {academyStats.season_stats?.length > 1 && ` across ${academyStats.season_stats.length} competitions`}
                                        </span>
                                    </div>
                                </div>
                                <ChevronDown className={`h-5 w-5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
                            </div>
                        </CardContent>
                    </button>
                </CollapsibleTrigger>

                <CollapsibleContent>
                    <div className="px-6 pb-6 space-y-6">
                        {academyStats.rating && (
                            <div className="flex items-center gap-2">
                                <Badge variant="secondary" className="text-sm">Avg Rating: {academyStats.rating}</Badge>
                            </div>
                        )}

                        <div className="grid grid-cols-3 md:grid-cols-6 gap-x-6">
                            <StatFigure label="Apps">{academyStats.appearances}</StatFigure>
                            <StatFigure label="Starts">{academyStats.starts || 0}</StatFigure>
                            <StatFigure label="Minutes">{(academyStats.minutes || 0).toLocaleString()}</StatFigure>
                            <StatFigure label="Goals">{academyStats.goals}</StatFigure>
                            <StatFigure label="Assists">{academyStats.assists}</StatFigure>
                            <StatFigure label="Cards">{(academyStats.yellow_cards || 0) + (academyStats.red_cards || 0)}</StatFigure>
                        </div>

                        {/* Per-season breakdown */}
                        {seasonGroups.length > 0 && (
                            <div className="space-y-5">
                                {seasonGroups.map(({ season, entries }) => (
                                    <div key={season} className="space-y-3">
                                        <h4 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                            <Calendar className="h-4 w-4" />
                                            {season}/{season + 1}
                                        </h4>
                                        {entries.map((league, i) => (
                                            <div key={i} className="rounded-lg border p-4 space-y-3">
                                                <div className="flex items-center justify-between">
                                                    <div>
                                                        <div className="font-medium">{league.league}</div>
                                                        {league.team && <div className="text-xs text-muted-foreground">{league.team}</div>}
                                                    </div>
                                                    {league.rating && (
                                                        <Badge variant="secondary" className="text-xs">{league.rating}</Badge>
                                                    )}
                                                </div>
                                                <div className="grid grid-cols-6 gap-2 text-center text-sm">
                                                    <div>
                                                        <div className="font-semibold">{league.appearances}</div>
                                                        <div className="text-xs text-muted-foreground">Apps</div>
                                                    </div>
                                                    <div>
                                                        <div className="font-semibold">{league.minutes || 0}</div>
                                                        <div className="text-xs text-muted-foreground">Mins</div>
                                                    </div>
                                                    <div>
                                                        <div className="font-semibold text-good">{league.goals}</div>
                                                        <div className="text-xs text-muted-foreground">Goals</div>
                                                    </div>
                                                    <div>
                                                        <div className="font-semibold text-gold-text">{league.assists}</div>
                                                        <div className="text-xs text-muted-foreground">Assists</div>
                                                    </div>
                                                    <div className="hidden sm:block">
                                                        <div className="font-semibold">{statOrDash(league.passes_accuracy != null ? `${league.passes_accuracy}%` : null)}</div>
                                                        <div className="text-xs text-muted-foreground">Pass%</div>
                                                    </div>
                                                    <div className="hidden sm:block">
                                                        <div className="font-semibold">{league.dribbles_success != null ? `${league.dribbles_success}/${league.dribbles_attempts || 0}` : '\u2014'}</div>
                                                        <div className="text-xs text-muted-foreground">Dribbles</div>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </CollapsibleContent>
            </Card>
        </Collapsible>
    )
}

export function PlayerPage() {
    const { api_football_frozen: apiFootballFrozen } = useDataMode()
    const { playerId } = useParams()
    const navigate = useNavigate()
    const [searchParams, setSearchParams] = useSearchParams()
    const seasonParam = searchParams.get('season')
    const urlSeason = /^\d{4}$/.test(seasonParam || '') ? Number(seasonParam) : undefined
    const [storedSeason, setStoredSeason] = useState(() => seasonStore.get())
    const { displaySeason: defaultSeason, ready: seasonReady } = useSeasonDirectory()
    // An explicit pick scopes reads; the default label must not disable server fallbacks.
    const selectedSeason = seasonParam === null ? storedSeason : urlSeason
    const seasonOverride = selectedSeason
    const [profile, setProfile] = useState(null)
    const [stats, setStats] = useState([])
    const [statsMeta, setStatsMeta] = useState(null)
    const [seasonStats, setSeasonStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [notFound, setNotFound] = useState(false)
    const [error, setError] = useState(null)
    const [position, setPosition] = useState(DEFAULT_POSITION)
    const [selectedMetrics, setSelectedMetrics] = useState([])
    
    // Parent club drawer state (players loaned OUT from parent club)
    const [drawerOpen, setDrawerOpen] = useState(false)
    const [teamPlayers, setTeamPlayers] = useState([])
    const [loadingTeamPlayers, setLoadingTeamPlayers] = useState(false)
    
    // Match detail drawer state
    const [matchDetailOpen, setMatchDetailOpen] = useState(false)
    const [selectedMatch, setSelectedMatch] = useState(null)

    // Journey data (lifted here so MiniProgressBar can access it from header)
    const [journeyState, setJourneyState] = useState({ playerId: null, data: null })
    const journeyData = journeyState.playerId === playerId ? journeyState.data : null
    const journeyHydrationRef = useRef({ playerId: null, promise: null })

    // Academy stats (youth league data)
    const [academyStats, setAcademyStats] = useState(null)

    // Flag dialog state
    const [flagOpen, setFlagOpen] = useState(false)

    // Watchlist state
    const auth = useAuth()
    const { openLoginModal } = useAuthUI()
    const [watchedIds, setWatchedIds] = useState(null)
    const playerApiId = parseInt(playerId, 10)
    const isLocalPlayer = playerApiId < 0
    const isWatched = !!watchedIds?.has(playerApiId)
    const emittedProfileViewIdsRef = useRef(new Set())

    const handlePublicConfirmed = useCallback((signedId) => {
        const numericId = Number(signedId)
        if (!Number.isInteger(numericId) || numericId === 0 || emittedProfileViewIdsRef.current.has(numericId)) return
        emittedProfileViewIdsRef.current.add(numericId)
        track('profile_view', { player_api_id: numericId })
    }, [])

    useEffect(() => {
        if (!auth?.token) {
            setWatchedIds(null)
            return
        }
        let cancelled = false
        APIService.getScoutWatchlistIds()
            .then((data) => { if (!cancelled) setWatchedIds(new Set(data?.player_ids || [])) })
            .catch((err) => { console.error('Failed to load watchlist ids', err) })
        return () => { cancelled = true }
    }, [auth?.token])

    const handleToggleWatch = () => {
        if (!auth?.token) {
            openLoginModal()
            return
        }
        if (!Number.isInteger(playerApiId)) return
        const wasWatched = isWatched
        setWatchedIds((current) => {
            const next = new Set(current || [])
            if (wasWatched) next.delete(playerApiId)
            else next.add(playerApiId)
            return next
        })
        const action = wasWatched
            ? APIService.removeFromScoutWatchlist(playerApiId)
            : APIService.addToScoutWatchlist(playerApiId)
        action.catch((err) => {
            console.error('Watchlist update failed', err)
            setWatchedIds((current) => {
                const next = new Set(current || [])
                if (wasWatched) next.add(playerApiId)
                else next.delete(playerApiId)
                return next
            })
        })
    }

    // Smart back navigation - goes to previous page, or home if no history
    const handleBack = () => {
        // Check if we have navigation history within the app
        if (window.history.length > 1) {
            navigate(-1)
        } else {
            // Fallback to home page if no history (direct link/bookmark)
            navigate('/')
        }
    }

    useEffect(() => {
        if (!playerId) return

        let cancelled = false

        let hydration = journeyHydrationRef.current
        if (hydration.playerId !== playerId) {
            const promise = APIService.getPlayerJourneyMap(playerId)
                .catch(() => null)
                .then((journeyMapData) => {
                    if (journeyMapData || isLocalPlayer) return journeyMapData
                    return APIService.request(`/players/${playerId}/journey/map?sync=true`).catch(() => null)
                })
            hydration = { playerId, promise }
            journeyHydrationRef.current = hydration
        }

        hydration.promise.then((data) => {
            if (!cancelled && data) setJourneyState({ playerId, data })
        })

        return () => { cancelled = true }
    }, [playerId, isLocalPlayer])

    useEffect(() => {
        let cancelled = false
        if (playerId && seasonReady) {
            loadPlayerData(() => cancelled)
        }
        return () => { cancelled = true }
    }, [playerId, selectedSeason, seasonReady])

    const loadPlayerData = async (isCancelled) => {
        setLoading(true)
        setNotFound(false)
        setError(null)
        try {
            let publicStatsNotFound = false
            const [profileData, statsData, seasonData, academyData] = await Promise.all([
                APIService.getPublicPlayerProfile(playerId).catch(() => null),
                APIService.getPublicPlayerStats(playerId, selectedSeason).catch((requestError) => {
                    if (requestError?.status === 404) {
                        publicStatsNotFound = true
                        return null
                    }
                    throw requestError
                }),
                APIService.getPublicPlayerSeasonStats(playerId, selectedSeason).catch(() => null),
                isLocalPlayer ? Promise.resolve(null) : APIService.getPlayerAcademyStats(playerId).catch(() => null),
            ])

            if (isCancelled()) return

            if (publicStatsNotFound || (profileData == null && statsData == null && seasonData == null)) {
                setNotFound(true)
                return
            }

            const statRows = Array.isArray(statsData) ? statsData : statsData?.matches ?? []
            setProfile(profileData)
            setStats(statRows)
            setStatsMeta(Array.isArray(statsData) ? null : statsData)
            setSeasonStats(seasonData)
            setAcademyStats(academyData)

            // Use profile position as initial value (backend enriches from multiple sources)
            if (profileData?.position) {
                const p = profileData.position
                let mapped = DEFAULT_POSITION
                if (p === 'G' || p === 'Goalkeeper') mapped = 'Goalkeeper'
                else if (p === 'D' || p === 'Defender') mapped = 'Defender'
                else if (p === 'M' || p === 'Midfielder') mapped = 'Midfielder'
                else if (p === 'F' || p === 'Attacker') mapped = 'Attacker'
                setPosition(mapped)
            }

            // Infer position from stats
            if (statRows.length > 0) {
                const positions = statRows.map(s => s.position).filter(Boolean)
                if (positions.length > 0) {
                    const counts = positions.reduce((acc, p) => {
                        acc[p] = (acc[p] || 0) + 1
                        return acc
                    }, {})
                    const likelyPos = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b)

                    let mappedPos = DEFAULT_POSITION
                    if (likelyPos === 'G') mappedPos = 'Goalkeeper'
                    else if (likelyPos === 'D') mappedPos = 'Defender'
                    else if (likelyPos === 'M') mappedPos = 'Midfielder'
                    else if (likelyPos === 'F') mappedPos = 'Attacker'

                    setPosition(mappedPos)
                    const config = METRIC_CONFIG[mappedPos] || METRIC_CONFIG[DEFAULT_POSITION]
                    setSelectedMetrics(config.default)
                }
            }
        } catch (err) {
            if (isCancelled()) return
            console.error('Failed to fetch player data', err)
            setError('Failed to load player data.')
        } finally {
            if (!isCancelled()) setLoading(false)
        }
    }
    

    const toggleMetric = (metricKey) => {
        setSelectedMetrics(prev => {
            if (prev.includes(metricKey)) {
                return prev.filter(k => k !== metricKey)
            }
            return [...prev, metricKey]
        })
    }

    // Handle parent club click to show tracked academy players
    const handleParentClubClick = async () => {
        if (!profile?.primary_team_db_id) return

        setDrawerOpen(true)
        setLoadingTeamPlayers(true)

        try {
            const loans = await APIService.getTeamLoans(profile.primary_team_db_id, {
                active_only: 'false',
                dedupe: 'true',
                direction: 'loaned_from',
                academy_only: 'true',
                aggregate_stats: 'true',
            })
            // Filter out current player
            const otherPlayers = loans.filter(loan => loan.player_id !== parseInt(playerId))
            setTeamPlayers(otherPlayers)
        } catch (err) {
            console.error('Failed to load team players:', err)
            setTeamPlayers([])
        } finally {
            setLoadingTeamPlayers(false)
        }
    }

    // Format data for charts
    const chartData = stats.map((s) => {
        const point = {
            date: s.fixture_date ? format(new Date(s.fixture_date), 'MMM d') : 'N/A',
            rating: s.rating ? parseFloat(s.rating) : null,
            minutes: s.minutes || 0,
            opponent: s.opponent,
            is_home: s.is_home,
            competition: s.competition,
            fullDate: s.fixture_date,
            loan_team_name: s.loan_team_name,
            loan_window: s.loan_window,
        }

        const getVal = (obj, path) => {
            return path.split('.').reduce((acc, part) => acc && acc[part], obj)
        }

        point['goals'] = s.goals || 0
        point['assists'] = s.assists || 0
        point['saves'] = s.saves || 0
        point['shots_total'] = getVal(s, 'shots.total') || 0
        point['shots_on'] = getVal(s, 'shots.on') || 0
        point['passes_total'] = getVal(s, 'passes.total') || 0
        point['passes_key'] = getVal(s, 'passes.key') || 0
        point['tackles_total'] = getVal(s, 'tackles.total') || 0
        point['blocks'] = getVal(s, 'tackles.blocks') || 0
        point['interceptions'] = getVal(s, 'tackles.interceptions') || 0
        point['duels_won'] = getVal(s, 'duels.won') || 0
        point['dribbles_success'] = getVal(s, 'dribbles.success') || 0

        const config = METRIC_CONFIG[position] || METRIC_CONFIG[DEFAULT_POSITION]
        config.options.forEach(opt => {
            if (point[opt.key] === undefined) {
                point[opt.key] = 0
            }
        })

        return point
    })

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload
            return (
                <div style={{ backgroundColor: CHART_TOOLTIP_BG, border: `1px solid ${CHART_TOOLTIP_BORDER}` }} className="p-3 rounded-lg shadow-lg text-xs z-50">
                    <p className="font-bold">{data.opponent} ({data.is_home ? 'H' : 'A'})</p>
                    <p className="text-muted-foreground">{label}</p>
                    {data.loan_team_name && (
                        <p className="text-primary text-xs mb-1">
                            for {data.loan_team_name}
                            {data.loan_window && data.loan_window !== 'Summer' && ` (${data.loan_window})`}
                        </p>
                    )}
                    {payload.map((p, i) => (
                        <p key={i} style={{ color: p.color }} className="font-semibold">
                            {p.name}: {p.value}
                        </p>
                    ))}
                    <p className="text-muted-foreground/70 italic mt-1">{data.competition}</p>
                </div>
            )
        }
        return null
    }

    const currentConfig = METRIC_CONFIG[position] || METRIC_CONFIG[DEFAULT_POSITION]
    const playerName = profile?.name || `Player #${playerId}`
    const resolvedSeason = selectedSeason ?? seasonStats?.season ?? statsMeta?.summary?.season
    const seasonLabel = formatSeasonLabel(selectedSeason ?? defaultSeason ?? resolvedSeason)
    const provenance = seasonStats?.provenance ?? statsMeta?.provenance
    const provenanceSource = provenance?.primary_source ?? provenance?.source
    const provenanceText = provenanceSource === 'journey' && ['cup-gap', 'fixtures-invisible'].includes(provenance?.reconcile_flag)
        ? 'incl. cups — journey'
        : provenanceSource

    const handleSeasonChange = (season, isCurrent) => {
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
    }

    // Calculate season totals - prefer API season stats, fallback to calculated from match data
    const seasonTotals = {
        minutes: seasonStats?.minutes ?? stats.reduce((acc, s) => acc + (s.minutes || 0), 0),
        goals: seasonStats?.goals ?? stats.reduce((acc, s) => acc + (s.goals || 0), 0),
        assists: seasonStats?.assists ?? stats.reduce((acc, s) => acc + (s.assists || 0), 0),
        avgRating: seasonStats?.avg_rating ?? (stats.filter(s => s.rating).length > 0
            ? (stats.reduce((acc, s) => acc + (parseFloat(s.rating) || 0), 0) / stats.filter(s => s.rating).length).toFixed(2)
            : '-'),
        appearances: seasonStats?.appearances ?? stats.length,
        // Goalkeeper stats
        saves: seasonStats?.saves ?? stats.reduce((acc, s) => acc + (s.saves || 0), 0),
        goalsConceded: seasonStats?.goals_conceded ?? stats.reduce((acc, s) => acc + (s.goals_conceded || 0), 0),
        cleanSheets: seasonStats?.clean_sheets ?? 0,
    }
    const hasSeasonTotals = (seasonStats?.appearances ?? 0) > 0 || (seasonStats?.minutes ?? 0) > 0

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-chalk">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
                    <p className="text-muted-foreground">Loading player data...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-chalk">
                <Card className="max-w-md">
                    <CardContent className="pt-6 text-center">
                        <p className="text-destructive mb-4">{error}</p>
                        <Button variant="outline" onClick={handleBack}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Go Back
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    if (notFound) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-chalk">
                <Card className="max-w-md">
                    <CardContent className="pt-6 text-center">
                        <h1 className="text-lg font-semibold text-foreground mb-4">
                            This profile doesn&apos;t exist or isn&apos;t public yet
                        </h1>
                        <p className="text-sm leading-relaxed text-muted-foreground mb-4">
                            It may still be waiting for review, or the profile link may be incorrect.
                        </p>
                        <Button variant="outline" onClick={handleBack}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Go Back
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <JourneyProvider journeyData={journeyData}>
        <div className="min-h-screen bg-chalk">
            {/* Header */}
            <header className="dark bg-night text-chalk">
                <div className="floodlight-container max-w-[1200px] pb-12 pt-5 sm:pb-16">
                    <div className="flex flex-wrap items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={handleBack} className="-ml-3 text-chalk/80 hover:text-chalk">
                            <ArrowLeft className="h-4 w-4" />
                            Back
                        </Button>
                        <div className="ml-auto flex items-center gap-1">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setFlagOpen(true)}
                                className="text-muted-dark hover:text-gold"
                                title="Report incorrect data"
                                aria-label="Report incorrect data"
                            >
                                <Flag className="h-4 w-4" />
                            </Button>
                            <ContentReportDialog subjectId={playerApiId} />
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={handleToggleWatch}
                                className={isWatched ? 'text-gold hover:text-gold' : 'text-muted-dark hover:text-gold'}
                                title={isWatched ? 'Remove from watchlist' : 'Watch this player'}
                                aria-label={isWatched ? 'Remove from watchlist' : 'Watch this player'}
                            >
                                <Star className={`h-4 w-4 ${isWatched ? 'fill-gold text-gold' : ''}`} />
                            </Button>
                        </div>
                    </div>
                    <div className="mt-8 flex flex-col gap-8 md:flex-row md:items-center md:gap-14">
                        <div className="relative flex h-32 w-32 shrink-0 items-center justify-center sm:h-44 sm:w-44">
                            <span aria-hidden="true" className="absolute inset-0 rounded-full border border-dashed border-gold/60" />
                            {profile?.photo ? (
                                <img
                                    src={profile.photo}
                                    alt={playerName}
                                    width={152}
                                    height={152}
                                    className="h-[86%] w-[86%] rounded-full object-cover"
                                />
                            ) : (
                                <div className="flex h-[86%] w-[86%] items-center justify-center rounded-full bg-club">
                                    <User className="h-12 w-12 text-gold sm:h-16 sm:w-16" />
                                </div>
                            )}
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="eyebrow flex flex-wrap items-center gap-x-5 gap-y-1">
                                {profile?.status && (
                                    <span className="text-gold">
                                        {profile.status.replace('_', ' ')}{profile.status === 'on_loan' && profile.owner_team_name ? ` · from ${profile.owner_team_name}` : ''}{profile.sale_fee ? ` · ${profile.sale_fee}` : ''}
                                    </span>
                                )}
                                {academyStats?.appearances > 0 && stats.length > 0 && (
                                    <span className="text-muted-dark">Academy: {academyStats.appearances} apps</span>
                                )}
                            </div>
                            <h1 className="display mt-3 text-balance break-words text-[48px] leading-[.92] [overflow-wrap:anywhere] sm:text-[80px] lg:text-[104px]">{playerName}</h1>
                            <p className="mt-4 flex flex-wrap gap-x-2 text-base text-chalk/80 sm:text-[17px]">
                                {[isLocalPlayer ? profile?.position : position, profile?.age ? `${profile.age} yrs` : null, profile?.nationality].filter(Boolean).map((item, index) => (
                                    <span key={item}>{index > 0 ? <span aria-hidden="true" className="mr-2 text-muted-dark">·</span> : null}{item}</span>
                                ))}
                            </p>
                            {/* Mini Progress Bar — career stops at a glance */}
                            <MiniProgressBar />
                            {/* Academy link — opens drawer to browse other academy players */}
                            {profile?.parent_team_name && (
                                <button
                                    onClick={handleParentClubClick}
                                    className="mt-4 inline-flex items-center gap-3 rounded-full border border-chalk/20 py-2 pl-2 pr-4 text-sm text-chalk transition-colors hover:border-chalk/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                >
                                    {profile.parent_team_logo ? (
                                        <img src={profile.parent_team_logo} alt="" width={28} height={28} className="h-7 w-7 rounded-full bg-chalk object-contain p-0.5" />
                                    ) : (
                                        <Users className="ml-1 h-4 w-4 text-gold" />
                                    )}
                                    <span className="font-medium">{profile.parent_team_name} Academy</span>
                                    <span className="eyebrow hidden sm:inline">Academy players</span>
                                </button>
                            )}
                            <PlayerReachControls
                                key={playerApiId}
                                signedId={playerApiId}
                                onPublicConfirmed={handlePublicConfirmed}
                            />
                        </div>
                    </div>
                </div>
            </header>

            <div className="floodlight-container max-w-[1200px] py-12 pb-24 sm:py-16">
                    <div className="space-y-8">
                        <ShowcaseSection
                            playerApiId={String(playerId)}
                            playerName={playerName}
                            playerPosition={profile?.position || position}
                            season={selectedSeason}
                            onSeasonStatsChange={(nextStats) => {
                                const nextSeason = Number.parseInt(String(nextStats?.season ?? ''), 10)
                                if (selectedSeason == null || nextSeason === Number(selectedSeason)) {
                                    setSeasonStats(nextStats)
                                }
                            }}
                        />
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="flex flex-wrap items-center gap-2">
                                <h2 className="display text-[34px] sm:text-[44px]">
                                    {seasonLabel} Totals
                                </h2>
                                <ProvenanceChip provenance={provenance} />
                                {provenanceText && provenanceText !== 'none' && provenanceText !== 'live-fallback' ? (
                                    <UiTooltip>
                                        <TooltipTrigger asChild>
                                            <Badge variant="outline" className="cursor-help text-[11px] font-medium text-muted-foreground">
                                                {provenanceText}
                                            </Badge>
                                        </TooltipTrigger>
                                        <TooltipContent side="top" className="max-w-72">
                                            Reconciliation: {provenance.reconcile_flag || 'sources agree'}
                                            {provenance.fixtures_minutes != null ? ` · fixtures ${provenance.fixtures_minutes.toLocaleString()} min` : ''}
                                            {provenance.journey_minutes != null ? ` · journey ${provenance.journey_minutes.toLocaleString()} min` : ''}
                                        </TooltipContent>
                                    </UiTooltip>
                                ) : null}
                            </div>
                            <SeasonSelect
                                value={selectedSeason}
                                onValueChange={handleSeasonChange}
                            />
                        </div>
                        {apiFootballFrozen && <PublicMatchPanels stats={seasonStats} hideProviderFreshness={isLocalPlayer} />}
                        {stats.length === 0 && academyStats?.appearances > 0 ? (
                            /* Academy player with no loan stats — academy section below is the primary view */
                            null
                        ) : stats.length === 0 && hasSeasonTotals && seasonStats?.stats_coverage !== 'limited' ? (
                            <div className="space-y-6">
                                <p className="text-sm text-muted-foreground">
                                    Season totals — per-match breakdown not available for this season.
                                </p>

                                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-x-6">
                                    <StatFigure label="Appearances">{seasonStats.appearances ?? 0}</StatFigure>
                                    <StatFigure label="Goals">{seasonStats.goals ?? 0}</StatFigure>
                                    <StatFigure label="Assists">{seasonStats.assists ?? 0}</StatFigure>
                                    <StatFigure label="Minutes">{(seasonStats.minutes ?? 0).toLocaleString()}</StatFigure>
                                    {seasonStats.avg_rating != null && (
                                        <StatFigure label="Avg Rating">{seasonStats.avg_rating}</StatFigure>
                                    )}
                                </div>

                                {seasonStats.clubs?.length > 0 && (
                                    <Card>
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-base flex items-center gap-2">
                                                <Calendar className="h-4 w-4" />
                                                Stats by Club
                                            </CardTitle>
                                            <CardDescription>Season breakdown by club</CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                {seasonStats.clubs.map((club, idx) => (
                                                    <div
                                                        key={idx}
                                                        className={`p-4 rounded-lg border ${club.is_current ? 'bg-primary/5 border-primary/20' : 'bg-secondary border-border'}`}
                                                    >
                                                        <div className="flex items-center gap-2 mb-3">
                                                            {club.team_logo && (
                                                                <img src={club.team_logo} alt="" width={24} height={24} className="w-6 h-6 rounded-full" />
                                                            )}
                                                            <span className="font-semibold">{club.team_name}</span>
                                                            {club.window_type && (
                                                                <Badge
                                                                    variant="outline"
                                                                    className={`text-xs ${club.is_current
                                                                        ? 'bg-primary/10 text-primary border-primary/20'
                                                                        : 'bg-secondary text-muted-foreground border-border'}`}
                                                                >
                                                                    {club.window_type}
                                                                </Badge>
                                                            )}
                                                        </div>
                                                        <div className="grid grid-cols-4 gap-3 text-center">
                                                            <div>
                                                                <div className="text-lg font-bold text-foreground">{club.appearances ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Apps</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-foreground">{(club.minutes ?? 0).toLocaleString()}</div>
                                                                <div className="text-xs text-muted-foreground">Mins</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-good">{club.goals ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Goals</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-gold-text">{club.assists ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Assists</div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}
                            </div>
                        ) : stats.length === 0 && seasonStats?.stats_coverage !== 'limited' ? (
                            <Card>
                                <CardContent className="py-12 text-center">
                                    <Target className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                                    <p className="text-muted-foreground">No match data available for this player yet.</p>
                                </CardContent>
                            </Card>
                        ) : stats.length === 0 && seasonStats?.stats_coverage === 'limited' && !academyStats?.appearances ? (
                            /* LIMITED COVERAGE VIEW - Show basic stats from lineup/events data */
                            <div className="space-y-6">
                                {/* Limited Coverage Notice */}
                                <Card className="bg-chalk-2 border-border">
                                    <CardContent className="py-4">
                                        <div className="flex items-start gap-3">
                                            <Target className="h-5 w-5 text-gold-text mt-0.5" />
                                            <div>
                                                <p className="font-medium text-ink">Limited Stats Available</p>
                                                <p className="text-sm text-muted-foreground mt-1">
                                                    {seasonStats?.limited_stats_note || 'Full match stats are not available for this league. Showing appearances, goals, and assists from lineup and event data.'}
                                                </p>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                                
                                {/* Basic Stats Cards */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6">
                                    <StatFigure label="Appearances">{seasonStats?.appearances || 0}</StatFigure>
                                    <StatFigure label="Goals">{seasonStats?.goals || 0}</StatFigure>
                                    <StatFigure label="Assists">{seasonStats?.assists || 0}</StatFigure>
                                    <StatFigure label="Yellow Cards">{seasonStats?.yellows || 0}</StatFigure>
                                </div>
                                
                                {/* Loan Club Info */}
                                {seasonStats?.clubs && seasonStats.clubs.length > 0 && (
                                    <Card>
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-base">Current Club</CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="flex items-center gap-3">
                                                {seasonStats.clubs[0].team_logo && (
                                                    <img
                                                        src={seasonStats.clubs[0].team_logo}
                                                        alt={seasonStats.clubs[0].team_name}
                                                        width={40}
                                                        height={40}
                                                        className="h-10 w-10 object-contain"
                                                    />
                                                )}
                                                <div>
                                                    <div className="font-semibold">{seasonStats.clubs[0].team_name}</div>
                                                    <div className="text-sm text-muted-foreground">
                                                        {seasonStats.clubs[0].appearances} appearances
                                                        {seasonStats.clubs[0].goals > 0 && ` · ${seasonStats.clubs[0].goals} goals`}
                                                        {seasonStats.clubs[0].assists > 0 && ` · ${seasonStats.clubs[0].assists} assists`}
                                                    </div>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}
                            </div>
                        ) : (
                            <div className="space-y-6">
                        {/* Season Summary Cards - Position-aware (dimmed when viewing past stop) */}
                        <JourneyDimmer>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-x-6">
                            <StatFigure label="Appearances">{seasonTotals.appearances}</StatFigure>
                            <StatFigure label="Minutes">{seasonTotals.minutes}</StatFigure>
                            {position === 'Goalkeeper' ? (
                                <>
                                    <StatFigure label="Saves">{seasonTotals.saves}</StatFigure>
                                    <StatFigure label="Conceded">{seasonTotals.goalsConceded}</StatFigure>
                                </>
                            ) : (
                                <>
                                    <StatFigure label="Goals">{seasonTotals.goals}</StatFigure>
                                    <StatFigure label="Assists">{seasonTotals.assists}</StatFigure>
                                </>
                            )}
                            <StatFigure label="Avg Rating">{seasonTotals.avgRating}</StatFigure>
                        </div>
                        </JourneyDimmer>

                        {/* Season Stats Panel — slides in when a past career stop is selected */}
                        <SeasonStatsPanel />

                        {/* Per-Club Breakdown (if multiple clubs) */}
                        {seasonStats?.clubs && seasonStats.clubs.length > 1 && (
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Calendar className="h-4 w-4" />
                                        Stats by Club
                                    </CardTitle>
                                    <CardDescription>Season breakdown by club</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {seasonStats.clubs.map((club, idx) => (
                                            <div 
                                                key={idx} 
                                                className={`p-4 rounded-lg border ${club.is_current ? 'bg-primary/5 border-primary/20' : 'bg-secondary border-border'}`}
                                            >
                                                <div className="flex items-center gap-2 mb-3">
                                                    {club.team_logo && (
                                                        <img src={club.team_logo} alt="" width={24} height={24} className="w-6 h-6 rounded-full" />
                                                    )}
                                                    <span className="font-semibold">{club.team_name}</span>
                                                    <Badge 
                                                        variant="outline" 
                                                        className={`text-xs ${club.is_current
                                                            ? 'bg-primary/10 text-primary border-primary/20'
                                                            : 'bg-secondary text-muted-foreground border-border'}`}
                                                    >
                                                        {club.window_type}
                                                    </Badge>
                                                </div>
                                                <div className="grid grid-cols-4 gap-3 text-center">
                                                    <div>
                                                        <div className="text-lg font-bold text-foreground">{club.appearances}</div>
                                                        <div className="text-xs text-muted-foreground">Apps</div>
                                                    </div>
                                                    <div>
                                                        <div className="text-lg font-bold text-foreground">{club.minutes}</div>
                                                        <div className="text-xs text-muted-foreground">Mins</div>
                                                    </div>
                                                    {position === 'Goalkeeper' ? (
                                                        <>
                                                            <div>
                                                                <div className="text-lg font-bold text-good">{club.saves ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Saves</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-warn">{club.goals_conceded ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Conceded</div>
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <div>
                                                                <div className="text-lg font-bold text-good">{club.goals}</div>
                                                                <div className="text-xs text-muted-foreground">Goals</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-gold-text">{club.assists}</div>
                                                                <div className="text-xs text-muted-foreground">Assists</div>
                                                            </div>
                                                        </>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Tabs for Charts and Match Log */}
                        <Card>
                            <Tabs defaultValue="charts">
                                <CardHeader className="pb-0">
                                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                                        <CardTitle className="flex items-center gap-2 text-pretty">
                                            <TrendingUp className="h-5 w-5" />
                                            Performance Analysis
                                        </CardTitle>
                                        <TabsList>
                                            <TabsTrigger value="charts">Charts</TabsTrigger>
                                            <TabsTrigger value="matches">Match Log</TabsTrigger>
                                            <TabsTrigger value="journey">
                                                <MapPin className="h-4 w-4 mr-1" />
                                                Journey
                                            </TabsTrigger>
                                        </TabsList>
                                    </div>
                                </CardHeader>
                                <CardContent className="pt-6">
                                    <TabsContent value="charts" className="mt-0">
                                        <div className="space-y-6">
                                            {/* Metrics Selector */}
                                            <div className="p-4 bg-secondary rounded-lg">
                                                <h3 className="text-sm font-medium mb-3 text-foreground/80">Select Metrics to Compare</h3>
                                                <div className="flex flex-wrap gap-2">
                                                    {currentConfig.options.map(opt => (
                                                        <button
                                                            key={opt.key}
                                                            onClick={() => toggleMetric(opt.key)}
                                                            aria-label={`${selectedMetrics.includes(opt.key) ? 'Remove' : 'Add'} ${opt.label} metric`}
                                                            aria-pressed={selectedMetrics.includes(opt.key)}
                                                            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${selectedMetrics.includes(opt.key)
                                                                ? 'bg-primary/5 border-primary/20 text-primary ring-1 ring-primary/20'
                                                                : 'bg-card border-border text-muted-foreground hover:bg-secondary'
                                                                }`}
                                                        >
                                                            <span 
                                                                className={`inline-block w-2 h-2 rounded-full mr-2 ${selectedMetrics.includes(opt.key) ? '' : 'bg-muted-foreground/50'}`} 
                                                                style={{ backgroundColor: selectedMetrics.includes(opt.key) ? opt.color : undefined }}
                                                            />
                                                            {opt.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Main Performance Chart */}
                                            <div>
                                                <h3 className="text-sm font-medium mb-4 text-foreground/80">Performance Trends</h3>
                                                <div className="h-[300px] w-full">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <LineChart data={chartData}>
                                                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART_GRID_COLOR} />
                                                            <XAxis
                                                                dataKey="date"
                                                                tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }}
                                                                interval="preserveStartEnd"
                                                                tickLine={false}
                                                                axisLine={false}
                                                            />
                                                            <YAxis
                                                                tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }}
                                                                tickLine={false}
                                                                axisLine={false}
                                                            />
                                                            <Tooltip content={<CustomTooltip />} />
                                                            {currentConfig.options.filter(opt => selectedMetrics.includes(opt.key)).map(opt => (
                                                                <Line
                                                                    key={opt.key}
                                                                    type="monotone"
                                                                    dataKey={opt.key}
                                                                    stroke={opt.color}
                                                                    strokeDasharray={opt.dash}
                                                                    strokeWidth={2}
                                                                    dot={{ r: 3, fill: opt.color, strokeWidth: 0 }}
                                                                    activeDot={{ r: 6, strokeWidth: 0 }}
                                                                    name={opt.label}
                                                                />
                                                            ))}
                                                        </LineChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            </div>

                                            {/* Rating & Minutes Charts Side by Side */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                                <div>
                                                    <h3 className="text-sm font-medium mb-4 text-foreground/80">Match Ratings</h3>
                                                    <div className="h-[250px] sm:h-[200px] w-full">
                                                        <ResponsiveContainer width="100%" height="100%">
                                                            <LineChart data={chartData}>
                                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART_GRID_COLOR} />
                                                                <XAxis dataKey="date" tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                                                                <YAxis domain={[0, 10]} tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} tickLine={false} axisLine={false} />
                                                                <Tooltip content={<CustomTooltip />} />
                                                                <ReferenceLine y={7} stroke="#1D5A40" strokeDasharray="3 3" label={{ value: 'Good (7.0)', position: 'insideTopRight', fontSize: 10, fill: '#1D5A40' }} />
                                                                <Line type="monotone" dataKey="rating" stroke="#84661F" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Rating" />
                                                            </LineChart>
                                                        </ResponsiveContainer>
                                                    </div>
                                                </div>

                                                <div>
                                                    <h3 className="text-sm font-medium mb-4 text-foreground/80">Minutes Played</h3>
                                                    <div className="h-[250px] sm:h-[200px] w-full">
                                                        <ResponsiveContainer width="100%" height="100%">
                                                            <BarChart data={chartData}>
                                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART_GRID_COLOR} />
                                                                <XAxis dataKey="date" tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                                                                <YAxis domain={[0, 90]} tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} tickLine={false} axisLine={false} />
                                                                <Tooltip content={<CustomTooltip />} />
                                                                <Bar dataKey="minutes" fill="#0E1311" radius={[4, 4, 0, 0]} name="Minutes" />
                                                            </BarChart>
                                                        </ResponsiveContainer>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </TabsContent>

                                    <TabsContent value="matches" className="mt-0">
                                        <ScrollArea className="h-[500px]">
                                            <table className="w-full text-sm text-left">
                                                <thead className="bg-secondary sticky top-0 z-10">
                                                    <tr>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground">Date</th>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground hidden sm:table-cell">Club</th>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground">Match</th>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground">Min</th>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground">Rating</th>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground">{position === 'Goalkeeper' ? 'Performance' : 'G/A'}</th>
                                                        <th className="px-2 py-2.5 sm:p-3 font-medium text-muted-foreground hidden sm:table-cell">Key Stats</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-border">
                                                    {stats.slice().reverse().map((s, i) => (
                                                        <tr
                                                            key={i}
                                                            className="hover:bg-primary/5 cursor-pointer transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                                                            tabIndex={0}
                                                            role="button"
                                                            aria-label={`View match details: ${s.opponent} on ${s.fixture_date ? format(new Date(s.fixture_date), 'MMM d') : 'unknown date'}`}
                                                            onClick={() => {
                                                                setSelectedMatch(s)
                                                                setMatchDetailOpen(true)
                                                            }}
                                                            onKeyDown={(e) => {
                                                                if (e.key === 'Enter' || e.key === ' ') {
                                                                    e.preventDefault()
                                                                    setSelectedMatch(s)
                                                                    setMatchDetailOpen(true)
                                                                }
                                                            }}
                                                        >
                                                            <td className="px-2 py-2.5 sm:p-3 text-xs sm:text-sm">
                                                                {s.fixture_date ? format(new Date(s.fixture_date), 'MMM d') : '-'}
                                                            </td>
                                                            <td className="px-2 py-2.5 sm:p-3 hidden sm:table-cell">
                                                                <div className="flex items-center gap-1.5">
                                                                    {s.loan_team_logo && (
                                                                        <img src={s.loan_team_logo} alt="" width={16} height={16} className="w-4 h-4 rounded-full" />
                                                                    )}
                                                                    <span className="text-xs text-muted-foreground font-medium truncate max-w-[80px]">
                                                                        {s.loan_team_name || 'Unknown'}
                                                                    </span>
                                                                </div>
                                                                {s.loan_window && s.loan_window !== 'Summer' && (
                                                                    <Badge variant="outline" className="text-xs mt-0.5 bg-warn/10 text-warn border-warn/30">
                                                                        {s.loan_window}
                                                                    </Badge>
                                                                )}
                                                            </td>
                                                            <td className="px-2 py-2.5 sm:p-3">
                                                                <div className="flex items-center gap-2 min-w-0">
                                                                    <div className="min-w-0">
                                                                        <div className="font-medium group-hover:text-primary transition-colors truncate">{s.opponent}</div>
                                                                        <div className="text-xs text-muted-foreground truncate">{s.competition}</div>
                                                                    </div>
                                                                    <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/50 group-hover:text-primary transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0" />
                                                                </div>
                                                            </td>
                                                            <td className="px-2 py-2.5 sm:p-3 tabular-nums">{s.minutes}'</td>
                                                            <td className="px-2 py-2.5 sm:p-3">
                                                                <span className={`px-1.5 sm:px-2 py-1 rounded text-xs font-medium tabular-nums ${parseFloat(s.rating) >= 7.5 ? 'bg-good/10 text-good' :
                                                                    parseFloat(s.rating) >= 6.0 ? 'bg-secondary text-foreground/80' :
                                                                        'bg-danger/10 text-danger'
                                                                    }`}>
                                                                    {s.rating || '-'}
                                                                </span>
                                                            </td>
                                                            <td className="px-2 py-2.5 sm:p-3">
                                                                {position === 'Goalkeeper' ? (
                                                                    <div className="flex flex-col gap-0.5">
                                                                        {(s.saves > 0 || s.saves === 0) && (
                                                                            <span className="text-good text-xs font-medium">{s.saves} {s.saves === 1 ? 'save' : 'saves'}</span>
                                                                        )}
                                                                        {s.goals_conceded === 0 && (
                                                                            <span className="text-good text-xs font-medium">Clean sheet</span>
                                                                        )}
                                                                        {s.goals_conceded > 0 && (
                                                                            <span className="text-warn text-xs">{s.goals_conceded} conceded</span>
                                                                        )}
                                                                        {s.saves === undefined && s.goals_conceded === undefined && <span className="text-muted-foreground/50">-</span>}
                                                                    </div>
                                                                ) : (
                                                                    <>
                                                                        {s.goals > 0 && <span className="mr-2">⚽ {s.goals}</span>}
                                                                        {s.assists > 0 && <span>🅰️ {s.assists}</span>}
                                                                        {s.goals === 0 && s.assists === 0 && <span className="text-muted-foreground/50">-</span>}
                                                                    </>
                                                                )}
                                                            </td>
                                                            <td className="px-2 py-2.5 sm:p-3 text-xs text-muted-foreground hidden sm:table-cell">
                                                                {position === 'Goalkeeper' ? (
                                                                    <>
                                                                        {s.passes?.total > 0 && <div>{s.passes.total} Passes</div>}
                                                                        {s.passes?.accuracy && <div>{s.passes.accuracy}% Pass Acc</div>}
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        {s.passes?.key > 0 && <div>{s.passes.key} Key Passes</div>}
                                                                        {s.tackles?.total > 0 && <div>{s.tackles.total} Tackles</div>}
                                                                        {s.dribbles?.success > 0 && <div>{s.dribbles.success} Dribbles</div>}
                                                                    </>
                                                                )}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </ScrollArea>
                                    </TabsContent>
                                    
                                    <TabsContent value="journey" className="mt-0">
                                        <PlayerJourneyView />
                                    </TabsContent>
                                </CardContent>
                            </Tabs>
                        </Card>
                        </div>
                    )}

                    {/* Academy Development Section — always shown when data exists */}
                    {academyStats?.appearances > 0 && (
                        <AcademyStatsSection
                            academyStats={academyStats}
                            defaultOpen={stats.length === 0 && seasonStats?.stats_coverage !== 'limited'}
                        />
                    )}

                        {/* Season availability (injuries / suspensions) */}
                        {!isLocalPlayer && <PlayerAvailability playerId={parseInt(playerId)} />}

                        {/* Inline Sponsor Strip */}
                        <SponsorStrip />

                        {/* Community */}
                        {!isLocalPlayer && <section aria-label="Community" className="space-y-6">
                            <h2 className="display text-[34px] sm:text-[44px]">Community</h2>
                            <CommentSection playerId={parseInt(playerId)} title="Discussion" />
                            <PlayerLinksSection playerId={parseInt(playerId)} />
                        </section>}
                    </div>
            </div>

            {/* Academy Drawer — browse other academy players from the same parent club */}
            <Drawer open={drawerOpen} onOpenChange={setDrawerOpen}>
                <DrawerContent>
                    <DrawerHeader className="border-b">
                        <div className="flex items-center gap-3">
                            {profile?.parent_team_logo && (
                                <img
                                    src={profile.parent_team_logo}
                                    alt=""
                                    className="w-10 h-10 rounded-full object-cover border-2 border-border"
                                />
                            )}
                            <div>
                                <DrawerTitle>{profile?.parent_team_name} Academy</DrawerTitle>
                                <DrawerDescription>
                                    {loadingTeamPlayers
                                        ? "Loading players..."
                                        : `${teamPlayers.length} tracked academy player${teamPlayers.length !== 1 ? 's' : ''}`
                                    }
                                </DrawerDescription>
                            </div>
                        </div>
                    </DrawerHeader>

                    <div className="p-4 max-h-[60vh] overflow-y-auto">
                        {loadingTeamPlayers ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                            </div>
                        ) : teamPlayers.length === 0 ? (
                            <p className="text-center text-muted-foreground py-8">No other tracked academy players</p>
                        ) : (
                            <div className="space-y-2">
                                {teamPlayers.map((player) => (
                                    <Link
                                        key={player.player_id}
                                        to={withSeasonParam(`/players/${player.player_id}`, seasonOverride)}
                                        onClick={() => setDrawerOpen(false)}
                                        className="flex items-center gap-3 p-3 rounded-lg hover:bg-secondary active:bg-muted transition-colors group"
                                    >
                                        {player.player_photo ? (
                                            <img 
                                                src={player.player_photo} 
                                                alt={player.player_name}
                                                className="w-12 h-12 rounded-full object-cover border-2 border-border"
                                            />
                                        ) : (
                                            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary to-primary/80 flex items-center justify-center flex-shrink-0">
                                                <User className="h-6 w-6 text-primary-foreground" />
                                            </div>
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <div className="font-medium text-foreground group-hover:text-primary transition-colors">
                                                {player.player_name}
                                            </div>
                                            {player.loan_team_name && (
                                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                                    {player.is_active && <span className="text-muted-foreground/70">at</span>}
                                                    {player.loan_team_logo && (
                                                        <img src={player.loan_team_logo} alt="" className="w-4 h-4 rounded-full" />
                                                    )}
                                                    <span className="truncate">{player.loan_team_name}</span>
                                                    {!player.is_active && <span className="text-muted-foreground/70 text-xs">(ended)</span>}
                                                </div>
                                            )}
                                            {(player.appearances > 0 || player.goals > 0 || player.assists > 0 || player.saves > 0) && (
                                                <div className="text-xs text-muted-foreground/70 mt-0.5">
                                                    {player.appearances || 0} apps · {player.position === 'G' || player.position === 'Goalkeeper' 
                                                        ? `${player.saves || 0} saves · ${player.goals_conceded || 0} conceded`
                                                        : `${player.goals || 0}G · ${player.assists || 0}A`}
                                                </div>
                                            )}
                                        </div>
                                        <ChevronRight className="h-5 w-5 text-muted-foreground/50 group-hover:text-primary transition-colors flex-shrink-0" />
                                    </Link>
                                ))}
                            </div>
                        )}
                    </div>
                </DrawerContent>
            </Drawer>

            {/* Match Detail Drawer - shows detailed stats for a single match */}
            <MatchDetailDrawer
                open={matchDetailOpen}
                onOpenChange={setMatchDetailOpen}
                match={selectedMatch}
                playerName={playerName}
                position={position}
            />

        </div>

        <FlagDataDialog
            open={flagOpen}
            onOpenChange={setFlagOpen}
            context={{
                playerApiId: parseInt(playerId, 10),
                playerName,
                teamName: profile?.parent_team_name || profile?.current_club_name || '',
                teamApiId: profile?.parent_team_api_id || profile?.current_club_api_id,
            }}
        />
        </JourneyProvider>
    )
}

export default PlayerPage
