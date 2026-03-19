import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams, useLocation, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Loader2, ArrowLeft, ChevronRight, User, TrendingUp, Share2, Users, FileText, Search, X, Star, ArrowRightLeft, GraduationCap, UserMinus, BadgeDollarSign, Globe } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion' // eslint-disable-line no-unused-vars
import { APIService } from '@/lib/api'
import { AcademyConstellation } from '@/components/constellation/AcademyConstellation'
import { SquadOriginsView } from '@/components/origins/SquadOriginsView'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { getStatusLabel } from '@/components/constellation/constellation-utils'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { STATUS_BADGE_CLASSES } from '../lib/theme-constants'

const STATUS_ICONS = {
    first_team: Star,
    first_team_debut: TrendingUp,
    on_loan: ArrowRightLeft,
    academy: GraduationCap,
    released: UserMinus,
    sold: BadgeDollarSign,
}

function StatusIndicator({ status, teamName }) {
    const IconComponent = STATUS_ICONS[status]
    const colorClass = STATUS_BADGE_CLASSES[status] || 'bg-secondary text-muted-foreground border-border'
    const label = getStatusLabel(status, teamName)

    if (!IconComponent) return null

    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <span
                    className={`inline-flex items-center justify-center h-5 w-5 rounded-full border ${colorClass}`}
                    aria-label={label}
                >
                    <IconComponent className="h-3 w-3" />
                </span>
            </TooltipTrigger>
            <TooltipContent side="top">{label}</TooltipContent>
        </Tooltip>
    )
}

export function TeamDetailPage() {
    const { teamSlug: teamId } = useParams()
    const navigate = useNavigate()
    const location = useLocation()
    const [searchParams] = useSearchParams()

    const [team, setTeam] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    // Tab state — allow deep-linking via ?tab=
    const initialTab = searchParams.get('tab') || 'squad'
    const [activeTab, setActiveTab] = useState(initialTab)

    // Academy Network subtab: 'outbound' (constellation) or 'origins' (squad origins)
    const initialView = searchParams.get('view') || 'outbound'
    const [academyView, setAcademyView] = useState(initialView)
    const urlSeason = searchParams.get('season') ? parseInt(searchParams.get('season')) : undefined

    // Squad tab state
    const [players, setPlayers] = useState([])
    const [playersLoading, setPlayersLoading] = useState(false)
    const [playersLoaded, setPlayersLoaded] = useState(false)
    const [statusFilter, setStatusFilter] = useState('all')

    // Newsletters tab state
    const [newsletters, setNewsletters] = useState([])
    const [newslettersLoading, setNewslettersLoading] = useState(false)
    const [newslettersLoaded, setNewslettersLoaded] = useState(false)

    // Tracking request state
    const [trackingRequestState, setTrackingRequestState] = useState({ open: false, reason: '', email: '' })
    const [submittingTrackingRequest, setSubmittingTrackingRequest] = useState(false)
    const [message, setMessage] = useState(null)

    // Load team info on mount
    useEffect(() => {
        const loadTeam = async () => {
            setLoading(true)
            setError(null)
            try {
                const data = await APIService.getTeam(teamId)
                setTeam(data)
            } catch (err) {
                console.error('Failed to load team:', err)
                const navState = location.state
                if (navState?.teamName) {
                    setTeam({
                        name: navState.teamName,
                        logo: navState.teamLogo,
                        team_id: parseInt(teamId),
                        _isExternalTeam: true,
                    })
                    setActiveTab('alumni')
                    setAcademyView('origins')
                } else {
                    setError('Failed to load team data.')
                }
            } finally {
                setLoading(false)
            }
        }
        if (teamId) loadTeam()
    }, [teamId])

    // Load squad data
    const loadSquad = useCallback(async () => {
        if (playersLoaded || playersLoading) return
        setPlayersLoading(true)
        try {
            const data = await APIService.getTeamPlayers(teamId)
            const tracked = data?.players ?? (Array.isArray(data) ? data : [])
            setPlayers(tracked)
        } catch (err) {
            console.error('Failed to load squad:', err)
            setPlayers([])
        } finally {
            setPlayersLoading(false)
            setPlayersLoaded(true)
        }
    }, [teamId, playersLoaded, playersLoading])

    // Load newsletters data
    const loadNewsletters = useCallback(async () => {
        if (newslettersLoaded || newslettersLoading) return
        setNewslettersLoading(true)
        try {
            const data = await APIService.getNewsletters({ team: team.id, published_only: 'true' })
            const items = Array.isArray(data) ? data : data?.items || data?.newsletters || []
            setNewsletters(items)
        } catch (err) {
            console.error('Failed to load newsletters:', err)
            setNewsletters([])
        } finally {
            setNewslettersLoading(false)
            setNewslettersLoaded(true)
        }
    }, [team, newslettersLoaded, newslettersLoading])

    // Load squad on mount (default tab)
    useEffect(() => {
        if (team && !playersLoaded) loadSquad()
    }, [team, playersLoaded, loadSquad])

    // Lazy-load tab data when tab changes
    useEffect(() => {
        if (activeTab === 'squad' && !playersLoaded) loadSquad()
        if (activeTab === 'newsletters' && !newslettersLoaded) loadNewsletters()
    }, [activeTab, playersLoaded, newslettersLoaded, loadSquad, loadNewsletters])

    // Tracking request handlers
    const openRequestTracking = () => {
        setTrackingRequestState({ open: true, reason: '', email: '' })
    }
    const closeRequestTracking = () => setTrackingRequestState(prev => ({ ...prev, open: false }))
    const submitTrackingRequest = async () => {
        setSubmittingTrackingRequest(true)
        try {
            await APIService.submitTrackingRequest(teamId, {
                reason: trackingRequestState.reason || undefined,
                email: trackingRequestState.email || undefined,
            })
            setMessage({ type: 'success', text: `Tracking request submitted for ${team?.name}. We'll review it soon!` })
            closeRequestTracking()
        } catch (error) {
            console.error('Tracking request failed', error)
            if (error.message?.includes('already pending')) {
                setMessage({ type: 'info', text: 'A tracking request for this team is already pending.' })
                closeRequestTracking()
            } else if (error.message?.includes('already being tracked')) {
                setMessage({ type: 'info', text: 'Good news - this team is already being tracked!' })
                closeRequestTracking()
            } else {
                setMessage({ type: 'error', text: 'Failed to submit tracking request. Please try again.' })
            }
        } finally {
            setSubmittingTrackingRequest(false)
        }
    }

    const handleBack = () => {
        if (window.history.length > 1) {
            navigate(-1)
        } else {
            navigate('/teams')
        }
    }

    // Filter players by status
    const filteredPlayers = statusFilter === 'all'
        ? players
        : players.filter(p => {
            const status = p.current_status || p.status
            return status === statusFilter
        })

    // Compute status counts for filter badges
    const statusCounts = players.reduce((acc, p) => {
        const status = p.current_status || p.status || 'unknown'
        acc[status] = (acc[status] || 0) + 1
        return acc
    }, {})

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-secondary to-background">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
                    <p className="text-muted-foreground">Loading team...</p>
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
                            Back to Teams
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
            {/* Header */}
            <div className="bg-card border-b sticky top-0 z-10">
                <div className="max-w-6xl mx-auto px-4 py-4">
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="sm" onClick={handleBack}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Teams
                        </Button>
                        <div className="flex items-center gap-4">
                            {team?.logo ? (
                                <img
                                    src={team.logo}
                                    alt={team.name}
                                    className="w-12 h-12 object-contain"
                                />
                            ) : (
                                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary to-primary/80 flex items-center justify-center shadow-md">
                                    <Users className="h-6 w-6 text-primary-foreground" />
                                </div>
                            )}
                            <div>
                                <h1 className="text-2xl font-bold text-foreground">{team?.name}</h1>
                                <div className="flex flex-wrap items-center gap-2 mt-1">
                                    {team?.league_name && (
                                        <Badge variant="secondary">{team.league_name}</Badge>
                                    )}
                                    {team?.country && (
                                        <Badge variant="outline" className="text-muted-foreground">{team.country}</Badge>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Message banner */}
            {message && (
                <div className="max-w-6xl mx-auto px-4 mt-4">
                    <div className={`p-3 rounded-lg text-sm flex items-center justify-between ${
                        message.type === 'error' ? 'bg-rose-50 text-rose-700 border border-rose-200' :
                        message.type === 'info' ? 'bg-primary/5 text-primary border border-primary/20' :
                        'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    }`}>
                        <span>{message.text}</span>
                        <button onClick={() => setMessage(null)} className="ml-2 hover:opacity-70">
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="max-w-6xl mx-auto px-4 py-6">
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList>
                        {!team?._isExternalTeam && (
                            <TabsTrigger value="squad">
                                <Users className="h-4 w-4 mr-1.5" />
                                Squad
                            </TabsTrigger>
                        )}
                        <TabsTrigger value="alumni">
                            <Share2 className="h-4 w-4 mr-1.5" />
                            Academy Network
                        </TabsTrigger>
                        {!team?._isExternalTeam && (
                            <TabsTrigger value="newsletters">
                                <FileText className="h-4 w-4 mr-1.5" />
                                Newsletters
                            </TabsTrigger>
                        )}
                    </TabsList>

                    {/* Squad Tab */}
                    <TabsContent value="squad" className="mt-4">
                        {playersLoading ? (
                            <div className="flex items-center justify-center py-16">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70 mr-2" />
                                <span className="text-sm text-muted-foreground">Loading players...</span>
                            </div>
                        ) : players.length === 0 ? (
                            <Card>
                                <CardContent className="py-12 text-center">
                                    <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                                    <p className="text-muted-foreground mb-4">No tracked academy players yet</p>
                                    <p className="text-xs text-muted-foreground/70 max-w-md mx-auto">Academy data for this team is limited. We are working with our data provider to improve coverage.</p>
                                    {team?.is_tracked === false && (
                                        <Button variant="outline" onClick={openRequestTracking}>
                                            Request Tracking
                                        </Button>
                                    )}
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="space-y-4">
                                {/* Limited data disclaimer */}
                                {players.length < 10 && (
                                    <p className="text-xs text-muted-foreground/70 text-center py-1">
                                        Academy data for this team is limited. We are working with our data provider to improve coverage.
                                    </p>
                                )}
                                {/* Status filter chips */}
                                {Object.keys(statusCounts).length > 1 && (
                                    <div className="flex flex-wrap gap-2">
                                        <button
                                            onClick={() => setStatusFilter('all')}
                                            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                                                statusFilter === 'all'
                                                    ? 'bg-foreground text-primary-foreground border-foreground'
                                                    : 'bg-card border-border text-muted-foreground hover:bg-secondary'
                                            }`}
                                        >
                                            All ({players.length})
                                        </button>
                                        {Object.entries(statusCounts).map(([status, count]) => (
                                            <button
                                                key={status}
                                                onClick={() => setStatusFilter(status)}
                                                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                                                    statusFilter === status
                                                        ? 'bg-foreground text-primary-foreground border-foreground'
                                                        : `${STATUS_BADGE_CLASSES[status] || 'bg-secondary text-foreground/80 border-border'} hover:opacity-80`
                                                }`}
                                            >
                                                {getStatusLabel(status, team?.name)} ({count})
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {/* Player rows */}
                                <div className="space-y-1">
                                    {filteredPlayers.map((player, idx) => {
                                        const playerId = player.player_id || player.api_football_id || player.id
                                        const name = player.player_name || player.name
                                        const photo = player.player_photo || player.photo
                                        const status = player.current_status || player.status
                                        const loanTeam = player.loan_team_name || player.current_team_name
                                        const loanTeamLogo = player.loan_team_logo || player.current_team_logo
                                        const position = player.position
                                        const isGK = position === 'G' || position === 'Goalkeeper'

                                        return (
                                            <Link
                                                key={`${playerId}-${idx}`}
                                                to={`/players/${playerId}`}
                                                className="flex items-center gap-3 p-3 rounded-lg hover:bg-card hover:shadow-sm transition-all group border border-transparent hover:border-border"
                                            >
                                                <Avatar className="h-10 w-10 shrink-0">
                                                    {photo ? <AvatarImage src={photo} alt={name} /> : null}
                                                    <AvatarFallback className="text-xs bg-primary/5 text-primary">
                                                        {name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                                                    </AvatarFallback>
                                                </Avatar>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                                                            {name}
                                                        </span>
                                                        {status && (
                                                            <StatusIndicator status={status} teamName={team?.name} />
                                                        )}
                                                    </div>
                                                    {loanTeam && (
                                                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
                                                            {status === 'on_loan' && <span className="text-muted-foreground/70">at</span>}
                                                            {loanTeamLogo && (
                                                                <img src={loanTeamLogo} alt="" className="w-4 h-4 rounded-full" />
                                                            )}
                                                            <span className="truncate">{loanTeam}</span>
                                                            {player.is_active === false && <span className="text-muted-foreground/70">(ended)</span>}
                                                        </div>
                                                    )}
                                                    {player.international_team && !loanTeam && (
                                                        <div className="flex items-center gap-1 text-xs text-muted-foreground/70 mt-0.5">
                                                            {player.international_logo && <img src={player.international_logo} alt="" className="w-3.5 h-3.5 rounded-sm" />}
                                                            <span>{player.international_team}</span>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
                                                    {(() => {
                                                        const apps = status === 'first_team' ? (player.parent_club_appearances ?? player.appearances) : player.appearances
                                                        return apps > 0 ? <span>{apps} apps</span> : null
                                                    })()}
                                                    {isGK ? (
                                                        <>
                                                            {player.clean_sheets != null && player.clean_sheets > 0 && (
                                                                <span className="text-emerald-600">{player.clean_sheets} CS</span>
                                                            )}
                                                        </>
                                                    ) : (
                                                        <>
                                                            {player.goals != null && player.goals > 0 && (
                                                                <span className="text-emerald-600">{player.goals}G</span>
                                                            )}
                                                            {player.assists != null && player.assists > 0 && (
                                                                <span className="text-amber-600">{player.assists}A</span>
                                                            )}
                                                        </>
                                                    )}
                                                </div>
                                                <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-primary shrink-0" />
                                            </Link>
                                        )
                                    })}
                                </div>
                            </div>
                        )}
                    </TabsContent>

                    {/* Academy Network Tab */}
                    <TabsContent value="alumni" className="mt-4">
                        <div className="bg-slate-950 rounded-xl p-4 sm:p-6 space-y-5">
                            <ToggleGroup
                                type="single"
                                value={academyView}
                                onValueChange={(v) => v && setAcademyView(v)}
                                variant="outline"
                                className="gap-1"
                            >
                                <ToggleGroupItem value="outbound" className="px-3 data-[state=on]:bg-slate-700 data-[state=on]:text-white text-slate-400 border-slate-700 hover:bg-slate-800 hover:text-slate-200">
                                    <Share2 className="h-3.5 w-3.5 mr-1.5" />
                                    Where They Play
                                </ToggleGroupItem>
                                <ToggleGroupItem value="origins" className="px-3 data-[state=on]:bg-slate-700 data-[state=on]:text-white text-slate-400 border-slate-700 hover:bg-slate-800 hover:text-slate-200">
                                    <Globe className="h-3.5 w-3.5 mr-1.5" />
                                    Where They Trained
                                </ToggleGroupItem>
                            </ToggleGroup>

                            <AnimatePresence mode="wait">
                                {academyView === 'outbound' ? (
                                    <motion.div
                                        key="outbound"
                                        initial={{ opacity: 0, x: -30 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: -30 }}
                                        transition={{ duration: 0.2, ease: 'easeInOut' }}
                                    >
                                        <AcademyConstellation teamApiId={teamId} />
                                    </motion.div>
                                ) : (
                                    <motion.div
                                        key="origins"
                                        initial={{ opacity: 0, x: 30 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: 30 }}
                                        transition={{ duration: 0.2, ease: 'easeInOut' }}
                                    >
                                        <SquadOriginsView
                                            teamApiId={team?.team_id || teamId}
                                            teamLogo={team?.logo}
                                            teamName={team?.name}
                                            initialSeason={urlSeason}
                                        />
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </TabsContent>

                    {/* Newsletters Tab */}
                    <TabsContent value="newsletters" className="mt-4">
                        {newslettersLoading ? (
                            <div className="flex items-center justify-center py-16">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70 mr-2" />
                                <span className="text-sm text-muted-foreground">Loading newsletters...</span>
                            </div>
                        ) : newsletters.length === 0 ? (
                            <Card>
                                <CardContent className="py-12 text-center">
                                    <FileText className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                                    <p className="text-muted-foreground mb-4">No newsletters published yet</p>
                                    <Button variant="outline" asChild>
                                        <Link to="/newsletters">Browse all newsletters</Link>
                                    </Button>
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="space-y-3">
                                {newsletters.map((nl) => {
                                    const date = nl.published_at || nl.target_date || nl.created_at
                                    const formattedDate = date ? new Date(date).toLocaleDateString('en-GB', {
                                        day: 'numeric', month: 'short', year: 'numeric'
                                    }) : null

                                    return (
                                        <Link
                                            key={nl.id}
                                            to={`/newsletters/${nl.id}`}
                                            className="block p-4 bg-card rounded-lg border border-border hover:border-primary/20 hover:shadow-sm transition-all group"
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="flex-1 min-w-0">
                                                    <h3 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                                                        {nl.title || nl.subject || `Newsletter #${nl.id}`}
                                                    </h3>
                                                    {nl.excerpt && (
                                                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{nl.excerpt}</p>
                                                    )}
                                                    {formattedDate && (
                                                        <p className="text-xs text-muted-foreground/70 mt-1.5">{formattedDate}</p>
                                                    )}
                                                </div>
                                                <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-primary shrink-0 mt-1" />
                                            </div>
                                        </Link>
                                    )
                                })}
                            </div>
                        )}
                    </TabsContent>
                </Tabs>
            </div>

            {/* Tracking Request Dialog */}
            <Dialog open={trackingRequestState.open} onOpenChange={(open) => !open && closeRequestTracking()}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <TrendingUp className="h-5 w-5 text-primary" />
                            Request Team Tracking
                        </DialogTitle>
                        <DialogDescription>
                            {team && (
                                <span>Request to track academy players for <strong>{team.name}</strong></span>
                            )}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                            {team?.logo && (
                                <Avatar className="h-12 w-12">
                                    <AvatarImage src={team.logo} alt={team.name} />
                                    <AvatarFallback className="bg-muted text-xs">
                                        {team?.name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                                    </AvatarFallback>
                                </Avatar>
                            )}
                            <div>
                                <p className="font-medium">{team?.name}</p>
                                <p className="text-sm text-muted-foreground">{team?.league_name || team?.country}</p>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="tracking-reason">Why are you interested in this team? (optional)</Label>
                            <Textarea
                                id="tracking-reason"
                                placeholder="e.g., I'm a fan of this club and want to follow their academy players..."
                                value={trackingRequestState.reason}
                                onChange={(e) => setTrackingRequestState(prev => ({ ...prev, reason: e.target.value }))}
                                rows={3}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="tracking-email">Your email (optional)</Label>
                            <Input
                                id="tracking-email"
                                type="email"
                                placeholder="you@example.com"
                                value={trackingRequestState.email}
                                onChange={(e) => setTrackingRequestState(prev => ({ ...prev, email: e.target.value }))}
                            />
                            <p className="text-xs text-muted-foreground">We'll notify you when we start tracking this team.</p>
                        </div>
                    </div>
                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button variant="outline" onClick={closeRequestTracking}>Cancel</Button>
                        <Button onClick={submitTrackingRequest} disabled={submittingTrackingRequest}>
                            {submittingTrackingRequest ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    Submitting...
                                </>
                            ) : (
                                'Submit Request'
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

export default TeamDetailPage
