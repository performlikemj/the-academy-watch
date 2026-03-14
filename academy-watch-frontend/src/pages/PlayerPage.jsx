import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { Loader2, ArrowLeft, User, TrendingUp, Calendar, Target, PenTool, ChevronRight, Users, ExternalLink, MapPin } from 'lucide-react'
import { APIService } from '@/lib/api'
import { format } from 'date-fns'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { SponsorStrip } from '@/components/SponsorSidebar'
import { MatchDetailDrawer } from '@/components/MatchDetailDrawer'
import PlayerJourneyView from '@/components/PlayerJourneyView'
import { JourneyProvider, useJourney } from '@/contexts/JourneyContext'
import { MiniProgressBar } from '@/components/MiniProgressBar'
import { SeasonStatsPanel } from '@/components/SeasonStatsPanel'
import { CommentSection } from '@/components/CommentSection'
import { PlayerLinksSection } from '@/components/PlayerLinksSection'
import { CHART_GRID_COLOR, CHART_AXIS_COLOR, CHART_TOOLTIP_BG, CHART_TOOLTIP_BORDER } from '../lib/theme-constants'

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
            { key: 'goals', label: 'Goals', color: '#059669' },
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
            { key: 'goals', label: 'Goals', color: '#059669' },
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
            { key: 'duels_won', label: 'Duels Won', color: '#059669' },
            { key: 'interceptions', label: 'Interceptions', color: '#7c3aed' },
            { key: 'blocks', label: 'Blocks', color: '#db2777' },
            { key: 'clearances', label: 'Clearances', color: '#d97706' },
            { key: 'passes_total', label: 'Passes', color: '#0891b2' },
        ]
    },
    'Goalkeeper': {
        default: ['saves', 'passes_total'],
        options: [
            { key: 'saves', label: 'Saves', color: '#059669' },
            { key: 'passes_total', label: 'Passes', color: '#d97706' },
            { key: 'rating', label: 'Rating', color: '#ca8a04' },
        ]
    }
}

const DEFAULT_POSITION = 'Midfielder'

export function PlayerPage() {
    const { playerId } = useParams()
    const navigate = useNavigate()
    const [profile, setProfile] = useState(null)
    const [stats, setStats] = useState([])
    const [seasonStats, setSeasonStats] = useState(null)
    const [commentaries, setCommentaries] = useState({ commentaries: [], authors: [], total_count: 0 })
    const [loading, setLoading] = useState(true)
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
    const [journeyData, setJourneyData] = useState(null)
    

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
        if (playerId) {
            loadPlayerData()
        }
    }, [playerId])

    const loadPlayerData = async () => {
        setLoading(true)
        setError(null)
        try {
            const [profileData, statsData, seasonData, commentariesData, journeyMapData] = await Promise.all([
                APIService.getPublicPlayerProfile(playerId).catch(() => null),
                APIService.getPublicPlayerStats(playerId),
                APIService.getPublicPlayerSeasonStats(playerId).catch(() => null),
                APIService.getPlayerCommentaries(playerId).catch(() => ({ commentaries: [], authors: [], total_count: 0 })),
                APIService.getPlayerJourneyMap(playerId).catch(() => null),
            ])

            setProfile(profileData)
            setStats(statsData || [])
            setSeasonStats(seasonData)
            setCommentaries(commentariesData || { commentaries: [], authors: [], total_count: 0 })

            // Journey: use cached data, or trigger on-demand sync if missing
            if (journeyMapData) {
                setJourneyData(journeyMapData)
            } else {
                try {
                    const synced = await APIService.request(`/players/${playerId}/journey/map?sync=true`)
                    if (synced) setJourneyData(synced)
                } catch {
                    // Sync failed — MiniProgressBar will just not render
                }
            }

            // Infer position from stats
            if (statsData && statsData.length > 0) {
                const positions = statsData.map(s => s.position).filter(Boolean)
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
            console.error('Failed to fetch player data', err)
            setError('Failed to load player data.')
        } finally {
            setLoading(false)
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

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-secondary to-background">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
                    <p className="text-muted-foreground">Loading player data...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-secondary to-background">
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

    return (
        <JourneyProvider journeyData={journeyData}>
        <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
            {/* Header */}
            <div className="bg-card border-b sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                        <Button variant="ghost" size="sm" onClick={handleBack} className="self-start">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back
                        </Button>
                        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                            {profile?.photo ? (
                                <img
                                    src={profile.photo}
                                    alt={playerName}
                                    width={64}
                                    height={64}
                                    className="w-12 h-12 sm:w-16 sm:h-16 rounded-full object-cover border-2 border-border shadow-md flex-shrink-0"
                                />
                            ) : (
                                <div className="w-12 h-12 sm:w-16 sm:h-16 rounded-full bg-gradient-to-br from-primary to-primary/80 flex items-center justify-center shadow-md flex-shrink-0">
                                    <User className="h-6 w-6 sm:h-8 sm:w-8 text-primary-foreground" />
                                </div>
                            )}
                            <div className="min-w-0">
                                <h1 className="text-xl sm:text-2xl font-bold text-foreground text-balance">{playerName}</h1>
                                <div className="flex flex-wrap items-center gap-2 mt-1">
                                    <Badge variant="secondary">{position}</Badge>
                                    {profile?.age && (
                                        <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20">
                                            {profile.age} yrs
                                        </Badge>
                                    )}
                                    {profile?.nationality && (
                                        <Badge variant="outline" className="text-muted-foreground">{profile.nationality}</Badge>
                                    )}
                                </div>
                                {/* Mini Progress Bar — career stops at a glance */}
                                <MiniProgressBar />
                                {/* Academy link — opens drawer to browse other academy players */}
                                {profile?.parent_team_name && (
                                    <div className="mt-2">
                                        <button
                                            onClick={handleParentClubClick}
                                            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-md"
                                        >
                                            {profile.parent_team_logo && (
                                                <img src={profile.parent_team_logo} alt="" width={20} height={20} className="w-5 h-5 rounded-full object-cover" />
                                            )}
                                            <span className="font-medium group-hover:underline">{profile.parent_team_name} Academy</span>
                                            <Users className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 pb-24 sm:pb-6">
                    <div className="space-y-8">
                        {stats.length === 0 && seasonStats?.stats_coverage !== 'limited' ? (
                            <Card>
                                <CardContent className="py-12 text-center">
                                    <Target className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                                    <p className="text-muted-foreground">No match data available for this player yet.</p>
                                </CardContent>
                            </Card>
                        ) : stats.length === 0 && seasonStats?.stats_coverage === 'limited' ? (
                            /* LIMITED COVERAGE VIEW - Show basic stats from lineup/events data */
                            <div className="space-y-6">
                                {/* Limited Coverage Notice */}
                                <Card className="bg-amber-50 border-amber-200">
                                    <CardContent className="py-4">
                                        <div className="flex items-start gap-3">
                                            <Target className="h-5 w-5 text-amber-600 mt-0.5" />
                                            <div>
                                                <p className="font-medium text-amber-800">Limited Stats Available</p>
                                                <p className="text-sm text-amber-700 mt-1">
                                                    {seasonStats?.limited_stats_note || 'Full match stats are not available for this league. Showing appearances, goals, and assists from lineup and event data.'}
                                                </p>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                                
                                {/* Basic Stats Cards */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-foreground">{seasonStats?.appearances || 0}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Appearances</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-emerald-600">{seasonStats?.goals || 0}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Goals</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-amber-600">{seasonStats?.assists || 0}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Assists</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-amber-600">{seasonStats?.yellows || 0}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Yellow Cards</div>
                                        </CardContent>
                                    </Card>
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
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
                            <Card>
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-foreground tabular-nums">{seasonTotals.appearances}</div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Appearances</div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-foreground tabular-nums">{seasonTotals.minutes}</div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Minutes</div>
                                </CardContent>
                            </Card>
                            {position === 'Goalkeeper' ? (
                                <>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-emerald-600 tabular-nums">{seasonTotals.saves}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Saves</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-orange-600 tabular-nums">{seasonTotals.goalsConceded}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Conceded</div>
                                        </CardContent>
                                    </Card>
                                </>
                            ) : (
                                <>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-emerald-600 tabular-nums">{seasonTotals.goals}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Goals</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-amber-600 tabular-nums">{seasonTotals.assists}</div>
                                            <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Assists</div>
                                        </CardContent>
                                    </Card>
                                </>
                            )}
                            <Card>
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-violet-600 tabular-nums">{seasonTotals.avgRating}</div>
                                    <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">Avg Rating</div>
                                </CardContent>
                            </Card>
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
                                                                <div className="text-lg font-bold text-emerald-600">{club.saves ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Saves</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-orange-600">{club.goals_conceded ?? 0}</div>
                                                                <div className="text-xs text-muted-foreground">Conceded</div>
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <div>
                                                                <div className="text-lg font-bold text-emerald-600">{club.goals}</div>
                                                                <div className="text-xs text-muted-foreground">Goals</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-amber-600">{club.assists}</div>
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
                                                                <ReferenceLine y={7} stroke="#059669" strokeDasharray="3 3" label={{ value: 'Good (7.0)', position: 'insideTopRight', fontSize: 10, fill: '#059669' }} />
                                                                <Line type="monotone" dataKey="rating" stroke="#ca8a04" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Rating" />
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
                                                                <Bar dataKey="minutes" fill="#0f172a" radius={[4, 4, 0, 0]} name="Minutes" />
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
                                                                    <Badge variant="outline" className="text-xs mt-0.5 bg-orange-50 text-orange-600 border-orange-200">
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
                                                                <span className={`px-1.5 sm:px-2 py-1 rounded text-xs font-medium tabular-nums ${parseFloat(s.rating) >= 7.5 ? 'bg-emerald-100 text-emerald-700' :
                                                                    parseFloat(s.rating) >= 6.0 ? 'bg-secondary text-foreground/80' :
                                                                        'bg-rose-50 text-rose-700'
                                                                    }`}>
                                                                    {s.rating || '-'}
                                                                </span>
                                                            </td>
                                                            <td className="px-2 py-2.5 sm:p-3">
                                                                {position === 'Goalkeeper' ? (
                                                                    <div className="flex flex-col gap-0.5">
                                                                        {(s.saves > 0 || s.saves === 0) && (
                                                                            <span className="text-emerald-600 text-xs font-medium">{s.saves} {s.saves === 1 ? 'save' : 'saves'}</span>
                                                                        )}
                                                                        {s.goals_conceded === 0 && (
                                                                            <span className="text-emerald-600 text-xs font-medium">Clean sheet</span>
                                                                        )}
                                                                        {s.goals_conceded > 0 && (
                                                                            <span className="text-orange-600 text-xs">{s.goals_conceded} conceded</span>
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

                    {/* Writer Coverage Section */}
                        {commentaries.total_count > 0 && (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-center gap-2 text-pretty">
                                        <PenTool className="h-5 w-5" />
                                        Writer Coverage
                                    </CardTitle>
                                    <CardDescription>
                                        {commentaries.total_count} writeup{commentaries.total_count !== 1 ? 's' : ''} from {commentaries.authors.length} journalist{commentaries.authors.length !== 1 ? 's' : ''}
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    {/* Featured Authors */}
                                    <div className="mb-6">
                                        <h3 className="text-sm font-medium text-foreground/80 mb-3">Writers covering this player</h3>
                                        <div className="flex flex-wrap gap-3">
                                            {commentaries.authors.map((author) => (
                                                <Link
                                                    key={author.id}
                                                    to={`/journalists/${author.id}`}
                                                    className="flex items-center gap-2 px-3 py-2 bg-secondary hover:bg-muted rounded-lg transition-colors group"
                                                >
                                                    <Avatar className="h-8 w-8">
                                                        <AvatarImage src={author.profile_image_url} alt={author.display_name} />
                                                        <AvatarFallback className="text-xs bg-primary/10 text-primary">
                                                            {author.display_name?.charAt(0) || 'W'}
                                                        </AvatarFallback>
                                                    </Avatar>
                                                    <div className="text-left">
                                                        <div className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                                                            {author.display_name}
                                                        </div>
                                                        <div className="text-xs text-muted-foreground">
                                                            {author.commentary_count} writeup{author.commentary_count !== 1 ? 's' : ''}
                                                        </div>
                                                    </div>
                                                    <ChevronRight className="h-4 w-4 text-muted-foreground/70 group-hover:text-primary transition-colors" />
                                                </Link>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Recent Writeups */}
                                    <div>
                                        <h3 className="text-sm font-medium text-foreground/80 mb-3">Recent writeups</h3>
                                        <div className="space-y-3">
                                            {commentaries.commentaries.slice(0, 5).map((commentary) => (
                                                <Link
                                                    key={commentary.id}
                                                    to={`/writeups/${commentary.id}`}
                                                    className="block p-4 bg-secondary hover:bg-muted rounded-lg transition-colors group"
                                                >
                                                    <div className="flex items-start gap-3">
                                                        {commentary.author && (
                                                            <Avatar className="h-10 w-10 flex-shrink-0">
                                                                <AvatarImage src={commentary.author.profile_image_url} alt={commentary.author.display_name} />
                                                                <AvatarFallback className="text-sm bg-primary/10 text-primary">
                                                                    {commentary.author.display_name?.charAt(0) || 'W'}
                                                                </AvatarFallback>
                                                            </Avatar>
                                                        )}
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <span className="font-medium text-foreground group-hover:text-primary transition-colors">
                                                                    {commentary.author?.display_name || 'Anonymous'}
                                                                </span>
                                                                {commentary.is_premium && (
                                                                    <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-700 border-amber-200">
                                                                        Premium
                                                                    </Badge>
                                                                )}
                                                            </div>
                                                            {commentary.title && (
                                                                <div className="text-sm font-medium text-foreground mb-1">{commentary.title}</div>
                                                            )}
                                                            <div className="text-sm text-muted-foreground line-clamp-2">
                                                                {commentary.content?.substring(0, 150)}...
                                                            </div>
                                                            <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                                                                {commentary.newsletter && (
                                                                    <span>{commentary.newsletter.team_name}</span>
                                                                )}
                                                                {commentary.created_at && (
                                                                    <>
                                                                        <span>·</span>
                                                                        <span>{format(new Date(commentary.created_at), 'MMM d, yyyy')}</span>
                                                                    </>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <ChevronRight className="h-5 w-5 text-muted-foreground/70 group-hover:text-primary transition-colors flex-shrink-0" />
                                                    </div>
                                                </Link>
                                            ))}
                                        </div>
                                        {commentaries.total_count > 5 && (
                                            <div className="mt-4 text-center">
                                                <span className="text-sm text-muted-foreground">
                                                    Showing 5 of {commentaries.total_count} writeups
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Inline Sponsor Strip */}
                        <SponsorStrip />

                        {/* Community */}
                        <section aria-label="Community" className="space-y-6">
                            <h2 className="text-lg font-semibold text-foreground text-pretty">Community</h2>
                            <CommentSection playerId={parseInt(playerId)} title="Discussion" />
                            <PlayerLinksSection playerId={parseInt(playerId)} />
                        </section>
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
                                        to={`/players/${player.player_id}`}
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
        </JourneyProvider>
    )
}

export default PlayerPage

