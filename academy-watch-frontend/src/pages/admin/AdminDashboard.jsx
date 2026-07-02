import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Mail, Users, Shield, GraduationCap, Inbox, Sprout, ArrowRight, Activity, BarChart3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { APIService } from '@/lib/api'
import { fetchInboxCounts } from './AdminInbox'

const QUICK_ACTIONS = [
    {
        title: 'Inbox',
        description: 'Review pending submissions, takes, flags, and requests',
        icon: Inbox,
        href: '/admin/inbox',
        iconBg: 'bg-rose-100',
        iconColor: 'text-rose-600',
    },
    {
        title: 'Manage Players',
        description: 'View and manage all tracked academy players',
        icon: Users,
        href: '/admin/players',
        iconBg: 'bg-blue-100',
        iconColor: 'text-blue-600',
    },
    {
        title: 'Manage Teams',
        description: 'Track/untrack teams and configure data',
        icon: Shield,
        href: '/admin/teams',
        iconBg: 'bg-indigo-100',
        iconColor: 'text-indigo-600',
    },
    {
        title: 'Seeding & Rebuild',
        description: 'Seed players per team, all tracked, cohorts, or full rebuild',
        icon: Sprout,
        href: '/admin/seeding',
        iconBg: 'bg-green-100',
        iconColor: 'text-green-600',
    },
    {
        title: 'Generate Newsletter',
        description: 'Create newsletters for selected teams',
        icon: Mail,
        href: '/admin/newsletters',
        iconBg: 'bg-orange-100',
        iconColor: 'text-orange-600',
    },
    {
        title: 'Users & Writers',
        description: 'Manage users, invite writers, and assign team coverage',
        icon: GraduationCap,
        href: '/admin/users',
        iconBg: 'bg-purple-100',
        iconColor: 'text-purple-600',
    },
]

function StatTile({ label, value, ok, okLabel = 'OK', warnLabel = 'needs repair', testId }) {
    return (
        <div className="border rounded-lg p-3 space-y-1" data-testid={testId}>
            <p className="text-xs text-muted-foreground">{label}</p>
            <div className="flex items-center gap-2">
                <span className="text-xl font-bold">{value}</span>
                {ok !== undefined && (
                    ok
                        ? <Badge className="bg-emerald-50 text-emerald-800 border-emerald-200">{okLabel}</Badge>
                        : <Badge className="bg-amber-50 text-amber-800 border-amber-200">{warnLabel}</Badge>
                )}
            </div>
        </div>
    )
}

// Product analytics — counts by event + a simple daily sparkline (7/30-day toggle).
const ANALYTICS_EVENTS = [
    ['pageview', 'Pageviews'],
    ['search_performed', 'Searches'],
    ['follow_added', 'Follows'],
    ['shadow_minted', 'Shadows minted'],
    ['list_created', 'Lists created'],
    ['claim_submitted', 'Claims'],
]

function AnalyticsSummaryCard() {
    const [days, setDays] = useState(7)
    const [summary, setSummary] = useState(null)
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        let cancelled = false
        setSummary(null)
        setFailed(false)
        const load = async () => {
            try {
                const data = await APIService.getAnalyticsSummary(days)
                if (!cancelled) setSummary(data)
            } catch {
                if (!cancelled) setFailed(true)
            }
        }
        load()
        return () => { cancelled = true }
    }, [days])

    const totals = summary?.totals || {}
    const daily = summary?.daily || []
    const maxDaily = daily.reduce((m, d) => Math.max(m, d.count || 0), 0)

    return (
        <Card data-testid="analytics-summary">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base flex items-center gap-2">
                            <BarChart3 className="h-4 w-4" />
                            Product Analytics
                        </CardTitle>
                        <CardDescription>First-party events, last {days} days</CardDescription>
                    </div>
                    <div className="flex gap-1">
                        <Button
                            variant={days === 7 ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setDays(7)}
                            data-testid="analytics-range-7"
                        >
                            7d
                        </Button>
                        <Button
                            variant={days === 30 ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setDays(30)}
                            data-testid="analytics-range-30"
                        >
                            30d
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {failed ? (
                    <p className="text-sm text-muted-foreground">
                        Analytics summary unavailable.
                    </p>
                ) : !summary ? (
                    <div className="grid gap-3 grid-cols-2 md:grid-cols-3">
                        {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="grid gap-3 grid-cols-2 md:grid-cols-3">
                            {ANALYTICS_EVENTS.map(([key, label]) => (
                                <StatTile
                                    key={key}
                                    label={label}
                                    value={totals[key] ?? 0}
                                    testId={`analytics-tile-${key}`}
                                />
                            ))}
                        </div>
                        <div>
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-muted-foreground">Events per day</p>
                                <p className="text-xs text-muted-foreground" data-testid="analytics-sessions">
                                    {summary.distinct_sessions ?? 0} sessions
                                </p>
                            </div>
                            {daily.length === 0 ? (
                                <p className="text-xs text-muted-foreground">No activity in this window.</p>
                            ) : (
                                <div className="flex items-end gap-0.5 h-16" data-testid="analytics-sparkline">
                                    {daily.map((d) => (
                                        <div
                                            key={d.date}
                                            className="flex-1 bg-primary/70 rounded-sm min-h-[2px]"
                                            style={{ height: `${maxDaily > 0 ? Math.round(((d.count || 0) / maxDaily) * 100) : 0}%` }}
                                            title={`${d.date}: ${d.count}`}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

function OpsSnapshotStrip() {
    const [ops, setOps] = useState(null)
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            try {
                const data = await APIService.adminOpsOverview()
                if (!cancelled) setOps(data)
            } catch {
                if (!cancelled) setFailed(true)
            }
        }
        load()
        return () => { cancelled = true }
    }, [])

    return (
        <Card data-testid="ops-snapshot">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Ops Snapshot
                        </CardTitle>
                        <CardDescription>Data health at a glance</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" asChild data-testid="ops-snapshot-link">
                        <Link to="/admin/operations">
                            Open Operations
                            <ArrowRight className="h-4 w-4 ml-1" />
                        </Link>
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {failed ? (
                    <p className="text-sm text-muted-foreground">
                        Ops overview unavailable — open <Link to="/admin/operations" className="underline">Operations</Link> for details.
                    </p>
                ) : !ops ? (
                    <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
                        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
                    </div>
                ) : (
                    <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
                        <StatTile
                            label="Active tracked players"
                            value={ops.tracked?.active ?? 0}
                            testId="ops-tile-active"
                        />
                        <StatTile
                            label="Placeholder names"
                            value={ops.tracked?.placeholder_names ?? 0}
                            ok={(ops.tracked?.placeholder_names ?? 0) === 0}
                            testId="ops-tile-placeholders"
                        />
                        <StatTile
                            label="Owning-club actives"
                            value={ops.tracked?.owning_club_active ?? 0}
                            ok={(ops.tracked?.owning_club_active ?? 0) === 0}
                            testId="ops-tile-owning-club"
                        />
                        <StatTile
                            label="Active jobs"
                            value={ops.jobs?.active ?? 0}
                            testId="ops-tile-jobs"
                        />
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

function prettyTabLabel(key) {
    return String(key)
        .replace(/[_-]+/g, ' ')
        .replace(/^\w/, (c) => c.toUpperCase())
}

function InboxPendingStrip() {
    const [counts, setCounts] = useState(null)
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            try {
                const data = await fetchInboxCounts()
                if (!cancelled) setCounts(data)
            } catch {
                if (!cancelled) setFailed(true)
            }
        }
        load()
        return () => { cancelled = true }
    }, [])

    const entries = counts && typeof counts === 'object'
        ? Object.entries(counts).filter(([, v]) => typeof v === 'number')
        : []
    const total = typeof counts === 'number'
        ? counts
        : entries.reduce((sum, [, v]) => sum + v, 0)

    return (
        <Card data-testid="inbox-pending">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base flex items-center gap-2">
                            <Inbox className="h-4 w-4" />
                            Inbox
                            {counts !== null && !failed && (
                                <Badge className={total > 0 ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-emerald-50 text-emerald-800 border-emerald-200'}>
                                    {total} pending
                                </Badge>
                            )}
                        </CardTitle>
                        <CardDescription>Items waiting on a decision</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" asChild data-testid="inbox-pending-link">
                        <Link to="/admin/inbox">
                            Open Inbox
                            <ArrowRight className="h-4 w-4 ml-1" />
                        </Link>
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {failed ? (
                    <p className="text-sm text-muted-foreground">
                        Inbox counts unavailable — open the <Link to="/admin/inbox" className="underline">Inbox</Link> directly.
                    </p>
                ) : counts === null ? (
                    <Skeleton className="h-6 w-2/3" />
                ) : entries.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nothing pending. Inbox zero.</p>
                ) : (
                    <div className="flex flex-wrap gap-2">
                        {entries.map(([key, value]) => (
                            <Badge
                                key={key}
                                variant="outline"
                                className={value > 0 ? 'border-amber-300 bg-amber-50 text-amber-900' : 'text-muted-foreground'}
                            >
                                {prettyTabLabel(key)}: {value}
                            </Badge>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

export function AdminDashboard() {
    const [stats, setStats] = useState(null)

    useEffect(() => {
        let cancelled = false
        const loadStats = async () => {
            try {
                const data = await APIService.request('/admin/dashboard-stats', {}, { admin: true })
                if (!cancelled) setStats(data)
            } catch (error) {
                console.error('Failed to load dashboard stats:', error)
                if (!cancelled) {
                    setStats({
                        players: { total: 0, academy: 0, on_loan: 0, first_team: 0, released: 0 },
                        teams: { tracked: 0 },
                        newsletters: { total: 0, published: 0, drafts: 0 },
                    })
                }
            }
        }
        loadStats()
        return () => { cancelled = true }
    }, [])

    return (
        <div className="space-y-6">
            <header>
                <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
                <p className="text-muted-foreground mt-1">
                    Overview of your academy tracking system
                </p>
            </header>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Tracked Players</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {stats === null ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">{stats.players.total}</div>
                                <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground mt-1">
                                    <span>{stats.players.academy} academy</span>
                                    <span>{stats.players.on_loan} on loan</span>
                                    <span>{stats.players.first_team} first team</span>
                                    {stats.players.released > 0 && <span>{stats.players.released} released</span>}
                                </div>
                            </>
                        )}
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Tracked Teams</CardTitle>
                        <Shield className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {stats === null ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">{stats.teams.tracked}</div>
                                <p className="text-xs text-muted-foreground">
                                    Teams with academy tracking enabled
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Newsletters</CardTitle>
                        <Mail className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {stats === null ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">{stats.newsletters.total}</div>
                                <p className="text-xs text-muted-foreground">
                                    {stats.newsletters.published} published, {stats.newsletters.drafts} drafts
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Ops snapshot + Inbox pending */}
            <div className="grid gap-4 lg:grid-cols-2">
                <OpsSnapshotStrip />
                <InboxPendingStrip />
            </div>

            {/* Product analytics summary */}
            <AnalyticsSummaryCard />

            {/* Seeding & Rebuild pointer (Full Rebuild moved to /admin/seeding) */}
            <Card className="border-amber-200 bg-amber-50/30" data-testid="seeding-pointer">
                <CardHeader>
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Sprout className="h-5 w-5" />
                                Seeding &amp; Rebuild
                            </CardTitle>
                            <CardDescription>
                                Per-team seeding, seed-all backfill, cohort seeding, and the Full Academy Rebuild now live on their own page.
                            </CardDescription>
                        </div>
                        <Button asChild data-testid="seeding-pointer-link">
                            <Link to="/admin/seeding">
                                Open Seeding &amp; Rebuild
                                <ArrowRight className="h-4 w-4 ml-2" />
                            </Link>
                        </Button>
                    </div>
                </CardHeader>
            </Card>

            {/* Quick Actions */}
            <div>
                <h3 className="text-xl font-semibold mb-4">Quick Actions</h3>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {QUICK_ACTIONS.map((action) => (
                        <Link key={action.title} to={action.href}>
                            <Card className="hover:bg-accent hover:shadow-md transition-all cursor-pointer h-full">
                                <CardHeader>
                                    <div className="flex items-center gap-3">
                                        <div className={`p-2 rounded-lg ${action.iconBg}`}>
                                            <action.icon className={`h-5 w-5 ${action.iconColor}`} />
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
                            Use Seeding &amp; Rebuild to discover academy players for your tracked teams, or add one-offs manually on the Players page
                        </p>
                    </div>
                    <div className="border-l-4 border-purple-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">3. Generate Newsletters</h4>
                        <p className="text-sm text-muted-foreground">
                            Create newsletters for tracked teams with recent player activity
                        </p>
                    </div>
                    <div className="border-l-4 border-orange-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">4. Assign Writers & Curate</h4>
                        <p className="text-sm text-muted-foreground">
                            Invite writers and assign them to teams in Users &amp; Writers; review community takes, flags, and submissions in the Inbox
                        </p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
