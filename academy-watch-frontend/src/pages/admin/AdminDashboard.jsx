import { useState, useEffect, useRef, useCallback } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Mail, Users, Shield, Settings, GraduationCap, UserPlus, FileText, Loader2, RotateCcw, AlertCircle, CheckCircle2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { APIService } from '@/lib/api'
import { useBackgroundJobs } from '@/context/BackgroundJobsContext'

export function AdminDashboard() {
    const [stats, setStats] = useState({
        players: { total: 0, academy: 0, on_loan: 0, first_team: 0, released: 0 },
        teams: { tracked: 0 },
        newsletters: { total: 0, published: 0, drafts: 0 },
    })

    const { isBlocking, refresh: refreshJobs } = useBackgroundJobs()

    // Full rebuild state
    const [rebuildJobId, setRebuildJobId] = useState(null)
    const [rebuildMessage, setRebuildMessage] = useState(null)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const wasBlockingRef = useRef(false)

    const rebuildRunning = isBlocking

    const loadStats = useCallback(async () => {
        try {
            const data = await APIService.request('/admin/dashboard-stats', {}, { admin: true })
            setStats(data)
        } catch (error) {
            console.error('Failed to load dashboard stats:', error)
        }
    }, [])

    useEffect(() => {
        loadStats()
    }, [loadStats])

    // Detect when a rebuild completes and fetch final results
    useEffect(() => {
        if (isBlocking) {
            wasBlockingRef.current = true
            return
        }
        if (!wasBlockingRef.current || !rebuildJobId) return
        wasBlockingRef.current = false

        // Rebuild just finished - fetch final status
        APIService.adminGetJobStatus(rebuildJobId).then(job => {
            setRebuildJobId(null)
            if (!job) return
            if (job.status === 'completed') {
                const r = job.results || {}
                setRebuildMessage({
                    type: 'success',
                    text: `Rebuild complete! Created ${r.total_created || 0} tracked players, synced ${r.players_synced || 0} journeys, linked ${r.journeys_linked || 0} orphans.`
                })
                loadStats()
            } else if (job.status === 'failed') {
                setRebuildMessage({
                    type: 'error',
                    text: `Rebuild failed: ${job.error || 'Unknown error'}`
                })
            }
        }).catch(() => {
            setRebuildJobId(null)
        })
    }, [isBlocking, rebuildJobId, loadStats])

    const handleRebuild = async (skipClean = false) => {
        setConfirmOpen(false)
        setRebuildMessage(null)

        try {
            const res = await APIService.adminFullRebuild({ skip_clean: skipClean })
            if (res.job_id) {
                setRebuildJobId(res.job_id)
                refreshJobs()
            }
        } catch (error) {
            console.error('Failed to start rebuild:', error)
            setRebuildMessage({ type: 'error', text: `Failed to start: ${error.message || 'Unknown error'}` })
        }
    }

    const quickActions = [
        {
            title: 'Manage Players',
            description: 'View and manage all tracked academy players',
            icon: Users,
            href: '/admin/players',
            color: 'blue'
        },
        {
            title: 'Seed Players',
            description: 'Import players for a tracked team from API data',
            icon: UserPlus,
            href: '/admin/players',
            color: 'green'
        },
        {
            title: 'Academy Config',
            description: 'Configure academy leagues and tracking',
            icon: GraduationCap,
            href: '/admin/academy',
            color: 'purple'
        },
        {
            title: 'Generate Newsletter',
            description: 'Create newsletters for selected teams',
            icon: Mail,
            href: '/admin/newsletters',
            color: 'orange'
        },
        {
            title: 'Manage Teams',
            description: 'Track/untrack teams and configure data',
            icon: Shield,
            href: '/admin/teams',
            color: 'indigo'
        },
        {
            title: 'Manage Users',
            description: 'View all users and their subscriptions',
            icon: Users,
            href: '/admin/users',
            color: 'gray'
        },
    ]

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
                <p className="text-muted-foreground mt-1">
                    Overview of your academy tracking system
                </p>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Tracked Players</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.players.total}</div>
                        <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground mt-1">
                            <span>{stats.players.academy} academy</span>
                            <span>{stats.players.on_loan} on loan</span>
                            <span>{stats.players.first_team} first team</span>
                            {stats.players.released > 0 && <span>{stats.players.released} released</span>}
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Tracked Teams</CardTitle>
                        <Shield className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.teams.tracked}</div>
                        <p className="text-xs text-muted-foreground">
                            Teams with academy tracking enabled
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Newsletters</CardTitle>
                        <Mail className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.newsletters.total}</div>
                        <p className="text-xs text-muted-foreground">
                            {stats.newsletters.published} published, {stats.newsletters.drafts} drafts
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Full Rebuild Card */}
            <Card className="border-amber-200 bg-amber-50/30">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <RotateCcw className="h-5 w-5" />
                                Full Academy Rebuild
                            </CardTitle>
                            <CardDescription>
                                Nuke all academy data and rebuild from scratch — seeds cohorts, syncs journeys, creates tracked players for all Big 6 teams. Takes 2-4 hours.
                            </CardDescription>
                        </div>
                        {!rebuildRunning && !confirmOpen && (
                            <Button
                                variant="destructive"
                                onClick={() => setConfirmOpen(true)}
                            >
                                <RotateCcw className="h-4 w-4 mr-2" />
                                Full Rebuild
                            </Button>
                        )}
                    </div>
                </CardHeader>

                {confirmOpen && !rebuildRunning && (
                    <CardContent>
                        <div className="border rounded-lg p-4 bg-card space-y-3">
                            <p className="text-sm font-medium text-rose-700">
                                This will delete all TrackedPlayers, journeys, cohorts, loans, and locations, then rebuild everything from API-Football data.
                            </p>
                            <p className="text-sm text-muted-foreground">
                                Uses ~1500-2500 API calls. Teams, users, newsletters, and fixtures are preserved.
                            </p>
                            <div className="flex gap-2">
                                <Button variant="destructive" onClick={() => handleRebuild(false)}>
                                    Yes, nuke and rebuild
                                </Button>
                                <Button variant="outline" onClick={() => handleRebuild(true)}>
                                    Rebuild (keep existing data)
                                </Button>
                                <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
                                    Cancel
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                )}

                {rebuildRunning && (
                    <CardContent>
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>Rebuild in progress — see overlay for details</span>
                        </div>
                    </CardContent>
                )}

                {rebuildMessage && (
                    <CardContent>
                        <Alert className={rebuildMessage.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                            {rebuildMessage.type === 'error'
                                ? <AlertCircle className="h-4 w-4 text-rose-600" />
                                : <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                            }
                            <AlertDescription className={rebuildMessage.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                                {rebuildMessage.text}
                            </AlertDescription>
                        </Alert>
                    </CardContent>
                )}
            </Card>

            {/* Quick Actions */}
            <div>
                <h3 className="text-xl font-semibold mb-4">Quick Actions</h3>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {quickActions.map((action) => (
                        <Link key={action.title} to={action.href}>
                            <Card className="hover:bg-accent hover:shadow-md transition-all cursor-pointer h-full">
                                <CardHeader>
                                    <div className="flex items-center gap-3">
                                        <div className={`p-2 rounded-lg bg-${action.color}-100`}>
                                            <action.icon className={`h-5 w-5 text-${action.color}-600`} />
                                        </div>
                                        <div>
                                            <CardTitle className="text-base">{action.title}</CardTitle>
                                            <CardDescription>{action.description}</CardDescription>
                                        </div>
                                    </div>
                                </CardHeader>
                            </Card>
                        </Link>
                    ))}
                </div>
            </div>

            {/* Getting Started */}
            <Card>
                <CardHeader>
                    <CardTitle>Getting Started</CardTitle>
                    <CardDescription>Common admin tasks and workflows</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="border-l-4 border-primary pl-4 py-2">
                        <h4 className="font-semibold text-sm">1. Track a Team</h4>
                        <p className="text-sm text-muted-foreground">
                            Go to Teams and enable tracking for the clubs whose academies you want to follow
                        </p>
                    </div>
                    <div className="border-l-4 border-emerald-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">2. Seed Players</h4>
                        <p className="text-sm text-muted-foreground">
                            Use the Players page to seed academy players from API data or add them manually
                        </p>
                    </div>
                    <div className="border-l-4 border-purple-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">3. Generate Newsletters</h4>
                        <p className="text-sm text-muted-foreground">
                            Create newsletters for tracked teams with recent player activity
                        </p>
                    </div>
                    <div className="border-l-4 border-orange-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">4. Curate Content</h4>
                        <p className="text-sm text-muted-foreground">
                            Assign writers to teams and manage their commentaries via the Curation page
                        </p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
