import { useState, useEffect } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { Mail, Users, Shield, GraduationCap, Inbox, Sprout, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { AdminPageHeader, BigStat, SectionTitle, textLinkClass } from '@/components/admin/ControlRoom'
import { APIService } from '@/lib/api'
import { useControlFlags, useControlData } from '@/components/admin/B3Control'
import { cn } from '@/lib/utils'
import { fetchInboxCounts, INBOX_TABS } from './AdminInbox'

const QUICK_ACTIONS = [
    {
        title: 'Inbox',
        description: 'Review pending submissions, takes, flags, and requests',
        icon: Inbox,
        href: '/admin/inbox',
    },
    {
        title: 'Manage Players',
        description: 'View and manage all tracked academy players',
        icon: Users,
        href: '/admin/players',
    },
    {
        title: 'Manage Teams',
        description: 'Track/untrack teams and configure data',
        icon: Shield,
        href: '/admin/teams',
    },
    {
        title: 'Seeding & Rebuild',
        description: 'Seed players per team, all tracked, cohorts, or full rebuild',
        icon: Sprout,
        href: '/admin/seeding',
    },
    {
        title: 'Generate Newsletter',
        description: 'Create newsletters for selected teams',
        icon: Mail,
        href: '/admin/newsletters',
    },
    {
        title: 'Users & Writers',
        description: 'Manage users, invite writers, and assign team coverage',
        icon: GraduationCap,
        href: '/admin/users',
    },
]

function StatTile({ label, value, ok, okLabel = 'OK', warnLabel = 'needs repair', testId }) {
    return (
        <div className="flex min-w-0 flex-col gap-1.5 border-t border-hairline-dark py-4 pr-4" data-testid={testId}>
            <p className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#8C9791]">{label}</p>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="display text-[2.25rem] leading-none tabular-nums text-chalk">{value}</span>
                {ok !== undefined && (
                    <span className={cn('font-mono text-[10.5px] uppercase tracking-[0.12em]', ok ? 'text-[#8FBFA4]' : 'text-[#E9C46A]')}>
                        {ok ? okLabel : warnLabel}
                    </span>
                )}
            </div>
        </div>
    )
}

function formatMinorCurrency(amount, currency) {
    if (!Number.isFinite(amount)) return null
    const code = typeof currency === 'string' ? currency.trim() : ''
    if (!code) return (amount / 100).toFixed(2)
    try {
        return new Intl.NumberFormat(undefined, { style: 'currency', currency: code }).format(amount / 100)
    } catch {
        return `${code.toUpperCase()} ${(amount / 100).toFixed(2)}`
    }
}

function MonthlyRecurringRevenue({ summary }) {
    if (Number.isFinite(summary?.mrr_cents)) {
        return formatMinorCurrency(summary.mrr_cents, summary.currency) || '—'
    }
    const byCurrency = summary?.mrr_by_currency && typeof summary.mrr_by_currency === 'object'
        ? Object.entries(summary.mrr_by_currency)
            .filter(([currency, amount]) => currency && Number.isFinite(amount))
            .sort(([left], [right]) => left.localeCompare(right))
        : []
    if (!byCurrency.length) return '—'
    return (
        <span className="flex flex-col items-start gap-1 text-base">
            {byCurrency.map(([currency, amount]) => <span key={currency}>{currency.toUpperCase()} · {formatMinorCurrency(amount, currency)}</span>)}
        </span>
    )
}

// Product analytics — counts by event + a simple daily sparkline (7/30-day toggle).
const ANALYTICS_EVENTS = [
    ['pageview', 'Pageviews'],
    ['profile_view', 'Profile views'],
    ['search_performed', 'Searches'],
    ['follow_added', 'Follows'],
    ['fan_follow_added', 'Fan follows'],
    ['fan_follow_removed', 'Fan unfollows'],
    ['shadow_minted', 'Shadows minted'],
    ['list_created', 'Lists created'],
    ['claim_submitted', 'Claims'],
]

// One slot per day of the window (missing days count as zero) so a quiet week
// reads as quiet days rather than a single full-width bar.
function dailySeries(daily, days) {
    const counts = new Map(daily.map((d) => [String(d.date).slice(0, 10), Number(d.count) || 0]))
    const latest = daily.reduce((max, d) => (String(d.date) > max ? String(d.date).slice(0, 10) : max), new Date().toISOString().slice(0, 10))
    const end = new Date(`${latest}T00:00:00Z`)
    return Array.from({ length: days }, (_, i) => {
        const day = new Date(end)
        day.setUTCDate(end.getUTCDate() - (days - 1 - i))
        const key = day.toISOString().slice(0, 10)
        return { date: key, count: counts.get(key) || 0 }
    })
}

function shortDay(date) {
    if (!date) return ''
    return new Date(`${date}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

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
    const series = dailySeries(daily, days)
    const maxDaily = series.reduce((m, d) => Math.max(m, d.count), 0)

    const rangeButton = (value) => (
        <button
            type="button"
            onClick={() => setDays(value)}
            data-testid={`analytics-range-${value}`}
            aria-pressed={days === value}
            className={cn(
                'h-8 rounded-full px-3.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors',
                days === value ? 'bg-chalk text-night' : 'text-muted-dark hover:text-chalk'
            )}
        >
            {value}d
        </button>
    )

    return (
        <section data-testid="analytics-summary" aria-labelledby="analytics-heading" className="flex flex-col gap-2">
            <SectionTitle
                title={<span id="analytics-heading">Product analytics</span>}
                action={(
                    <div className="flex gap-1 rounded-full border border-chalk/20 p-1" role="group" aria-label="Analytics window">
                        {rangeButton(7)}
                        {rangeButton(30)}
                    </div>
                )}
            />
            <p className="pt-2 text-[13px] text-[#8C9791]">First-party events, last {days} days</p>
            {failed ? (
                <p className="py-4 text-sm text-muted-dark">
                    Analytics summary unavailable.
                </p>
            ) : !summary ? (
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                    {ANALYTICS_EVENTS.map(([key]) => <Skeleton key={key} className="h-16 rounded-lg" />)}
                </div>
            ) : (
                <div className="flex flex-col gap-6">
                    <div className="grid grid-cols-2 md:grid-cols-3">
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
                        <div className="mb-2 flex items-center justify-between font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#8C9791]">
                            <p>Events per day</p>
                            <p data-testid="analytics-sessions">
                                {summary.distinct_sessions ?? 0} sessions
                            </p>
                        </div>
                        {daily.length === 0 ? (
                            <p className="text-xs text-muted-dark">No activity in this window.</p>
                        ) : (
                            <figure className="m-0">
                                <div className="relative">
                                    <span className="absolute -top-1 right-0 font-mono text-[10px] tabular-nums text-[#8C9791]">{maxDaily.toLocaleString()}</span>
                                    <div
                                        className={cn('flex h-24 items-end border-b border-chalk/25 pt-4', days > 7 ? 'gap-[3px]' : 'gap-3')}
                                        data-testid="analytics-sparkline"
                                        role="img"
                                        aria-label={`Events per day, last ${days} days, peak ${maxDaily.toLocaleString()}`}
                                    >
                                        {series.map((d) => (
                                            <div
                                                key={d.date}
                                                className={cn('flex-1 rounded-t-[2px]', d.count > 0 ? 'bg-gold' : 'bg-chalk/15')}
                                                style={{ height: d.count > 0 && maxDaily > 0 ? `${Math.max(4, Math.round((d.count / maxDaily) * 100))}%` : '2px' }}
                                                title={`${d.date}: ${d.count.toLocaleString()}`}
                                            />
                                        ))}
                                    </div>
                                </div>
                                <figcaption className="mt-2 flex justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-[#8C9791]">
                                    <span>{shortDay(series[0]?.date)}</span>
                                    <span>{shortDay(series[series.length - 1]?.date)}</span>
                                </figcaption>
                            </figure>
                        )}
                    </div>
                </div>
            )}
        </section>
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
        <section data-testid="ops-snapshot" aria-labelledby="ops-heading" className="flex flex-col">
            <div className="flex items-baseline justify-between gap-3 pb-2">
                <h2 id="ops-heading" className="font-mono text-[11.5px] font-medium uppercase tracking-[0.2em] text-[#8C9791]">Data health</h2>
                <Link to="/admin/operations" data-testid="ops-snapshot-link" className={textLinkClass}>
                    Open Operations
                </Link>
            </div>
            {failed ? (
                <p className="border-t border-hairline-dark py-4 text-sm text-muted-dark">
                    Ops overview unavailable — open <Link to="/admin/operations" className="underline">Operations</Link> for details.
                </p>
            ) : !ops ? (
                <div className="grid grid-cols-2 gap-3">
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
                </div>
            ) : (
                <div className="grid grid-cols-2">
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
        </section>
    )
}

const INBOX_TAB_LABELS = Object.fromEntries(INBOX_TABS.map((tab) => [tab.value, tab.label]))

function prettyTabLabel(key) {
    if (INBOX_TAB_LABELS[key]) return INBOX_TAB_LABELS[key]
    return String(key)
        .replace(/[_-]+/g, ' ')
        .replace(/^\w/, (c) => c.toUpperCase())
}

function InboxPendingStrip({ overview, controlEnabled, flagsReady }) {
    const [counts, setCounts] = useState(null)
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        if (!flagsReady || controlEnabled) return
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
    }, [controlEnabled, flagsReady])

    const entries = counts && typeof counts === 'object'
        ? Object.entries(counts).filter(([key, v]) => key !== 'total' && typeof v === 'number')
        : []
    const total = typeof counts === 'number'
        ? counts
        : entries.reduce((sum, [, v]) => sum + v, 0)

    const queues = controlEnabled ? (overview.data?.queues ? [...overview.data.queues].sort((a, b) => Number(b.count > 0) - Number(a.count > 0)) : []) : entries.map(([key, count]) => ({ key, count, label: prettyTabLabel(key), href: `/admin/inbox?tab=${encodeURIComponent(key)}` }))
    const pending = controlEnabled ? overview.data?.total : total
    const unavailable = controlEnabled ? !!overview.error : failed
    const loading = !flagsReady || (controlEnabled ? !overview.data : counts === null)

    return (
        <section data-testid="inbox-pending" aria-labelledby="inbox-heading" className="flex flex-col">
            <SectionTitle
                title={<span id="inbox-heading">Waiting for a human</span>}
                count={!loading && !unavailable ? `${pending} ${controlEnabled ? 'queue items' : 'pending'}` : null}
                action={(
                    <Link to="/admin/inbox" data-testid="inbox-pending-link" className={cn(textLinkClass, 'hidden sm:inline')}>
                        Open review queue
                    </Link>
                )}
            />
            {unavailable ? (
                <p className="py-5 text-sm text-muted-dark">
                    {controlEnabled ? 'Review' : 'Inbox'} counts unavailable — open the <Link to="/admin/inbox" className="underline">Inbox</Link> directly.
                </p>
            ) : loading ? (
                <div className="flex flex-col gap-3 pt-4">
                    {[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
                </div>
            ) : queues?.length === 0 || pending === 0 ? (
                <p className="py-6 text-[15px] text-muted-dark">Nothing pending. Inbox zero.</p>
            ) : (
                <ul className="flex flex-col">
                    {queues.map(({ key, count: value, label, href }) => (
                        <li key={key}>
                            <Link
                                to={href}
                                className="grid grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-4 border-b border-hairline-dark px-1.5 py-4 text-chalk no-underline transition-colors hover:bg-chalk/[0.04] hover:no-underline sm:grid-cols-[76px_minmax(0,1fr)_auto]"
                            >
                                <span className={cn('display text-[2.75rem] leading-[.9] tabular-nums', value > 0 ? 'text-chalk' : 'text-chalk/35')}>{value}</span>
                                <span className="text-base">{label}</span>
                                <span className={cn('font-mono text-[11px] uppercase tracking-[0.1em]', value > 0 ? 'text-[#E9C46A]' : 'text-[#8C9791]')}>
                                    {value > 0 ? 'Needs review' : 'Clear'}
                                </span>
                            </Link>
                        </li>
                    ))}
                </ul>
            )}
            {controlEnabled && overview.data?.overdue_safeguarding > 0 && <p className="mt-4 text-sm text-gold">{overview.data.overdue_safeguarding} safeguarding first action overdue</p>}
            {controlEnabled && <p className="mt-3 text-xs text-muted-dark">Counts show items in each review queue. A report and its safeguarding case can need separate decisions.</p>}
        </section>
    )
}

function Funnel({ stats }) {
    if (stats === null) {
        return (
            <div className="grid grid-cols-2 gap-4 border-y border-chalk/20 py-6 md:grid-cols-3 xl:grid-cols-6">
                {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-20" />)}
            </div>
        )
    }
    const tiles = [
        { label: 'Tracked players', value: stats.players.total, sub: stats.players.released > 0 ? `${stats.players.released} released` : 'across tracked academies' },
        { label: 'In the academy', value: stats.players.academy, sub: 'still at their club' },
        { label: 'Out on loan', value: stats.players.on_loan, sub: 'playing elsewhere' },
        { label: 'First team', value: stats.players.first_team, sub: 'made the step', subTone: 'gold' },
        { label: 'Tracked teams', value: stats.teams.tracked, sub: 'Teams with academy tracking enabled' },
        { label: 'Newsletters', value: stats.newsletters.total, sub: `${stats.newsletters.published} published, ${stats.newsletters.drafts} drafts` },
    ]
    return (
        <section aria-label="Platform totals" className="grid grid-cols-2 border-y border-chalk/20 md:grid-cols-3 xl:grid-cols-6">
            {tiles.map((tile) => (
                <BigStat
                    key={tile.label}
                    label={tile.label}
                    value={tile.value}
                    sub={tile.sub}
                    subTone={tile.subTone}
                    className="border-hairline-dark py-6 pr-4 xl:border-r xl:last:border-r-0 [&:not(:first-child)]:xl:pl-5"
                />
            ))}
        </section>
    )
}

export function AdminDashboard() {
    const [stats, setStats] = useState(null)
    const [revenue, setRevenue] = useState(undefined)
    const flags = useControlFlags()
    const flagsReady = flags !== null
    const businessEnabled = !!flags?.admin_business
    const controlEnabled = !!(flags?.admin_programs || flags?.admin_people || flags?.admin_safety || flags?.admin_business)
    const overview = useControlData(controlEnabled ? '/admin/control/overview' : null)

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

    useEffect(() => {
        if (!flagsReady || businessEnabled) return
        let cancelled = false
        APIService.getAdminBillingSummary()
            .then((data) => { if (!cancelled) setRevenue(data) })
            .catch(() => { if (!cancelled) setRevenue(null) })
        return () => { cancelled = true }
    }, [flagsReady, businessEnabled])

    const shownRevenue = flags?.admin_business ? overview.data?.revenue : revenue
    return (
        <div className="flex flex-col gap-11">
            <AdminPageHeader
                eyebrow="Overview · Today"
                title="The game,"
                accent="at a glance"
                lede="Everything the platform is tracking, and everything waiting on an admin decision."
            />

            <Funnel stats={stats} />

            <div className="grid gap-12 xl:grid-cols-[minmax(0,1fr)_380px]">
                <InboxPendingStrip overview={overview} controlEnabled={controlEnabled} flagsReady={flagsReady} />

                <aside className="flex flex-col gap-10">
                    <OpsSnapshotStrip />

                    {shownRevenue ? (
                        <section data-testid="revenue-summary" aria-labelledby="revenue-heading" className="flex flex-col">
                            <div className="pb-2">
                                <h2 id="revenue-heading" className="font-mono text-[11.5px] font-medium uppercase tracking-[0.2em] text-[#8C9791]">Revenue</h2>
                                <p className="mt-1 text-[13px] text-[#8C9791]">Stripe subscriptions and rail health</p>
                            </div>
                            <div className="grid grid-cols-2">
                                <StatTile label="Active subscriptions" value={shownRevenue.active_subscriptions ?? 0} />
                                <StatTile label="Monthly recurring revenue" value={<MonthlyRecurringRevenue summary={shownRevenue} />} />
                                <StatTile label="Past due" value={shownRevenue.past_due ?? 0} ok={(shownRevenue.past_due ?? 0) === 0} />
                                <StatTile label="Webhook failures · 24h" value={shownRevenue.webhook_failed_last_24h ?? 0} ok={(shownRevenue.webhook_failed_last_24h ?? 0) === 0} />
                            </div>
                        </section>
                    ) : null}

                    {/* Seeding & Rebuild pointer (Full Rebuild moved to /admin/seeding) */}
                    <section className="flex flex-col gap-3 rounded-[10px] border border-chalk/15 p-6" data-testid="seeding-pointer">
                        <span className="eyebrow flex items-center gap-2"><Sprout className="h-3.5 w-3.5" aria-hidden="true" />Seeding &amp; Rebuild</span>
                        <p className="text-[14.5px] leading-relaxed text-[#C9CFCB]">
                            Per-team seeding, seed-all backfill, cohort seeding, and the Full Academy Rebuild now live on their own page.
                        </p>
                        <Button asChild variant="on-dark" size="sm" className="self-start" data-testid="seeding-pointer-link">
                            <Link to="/admin/seeding">
                                Open Seeding &amp; Rebuild
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                    </section>
                </aside>
            </div>

            <AnalyticsSummaryCard />

            <div className="grid gap-12 xl:grid-cols-2">
                <section aria-labelledby="shortcuts-heading" className="flex flex-col">
                    <SectionTitle title={<span id="shortcuts-heading">Shortcuts</span>} count={`${QUICK_ACTIONS.length} tools`} />
                    <ul className="flex flex-col">
                        {QUICK_ACTIONS.map((action) => (
                            <li key={action.title}>
                                <Link
                                    to={action.href}
                                    className="group grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-4 border-b border-hairline-dark px-1.5 py-4 text-chalk no-underline transition-colors hover:bg-chalk/[0.04] hover:no-underline"
                                >
                                    <action.icon className="h-4 w-4 text-gold" aria-hidden="true" />
                                    <span className="min-w-0">
                                        <span className="block text-[15px]">{action.title}</span>
                                        <span className="block text-[13px] text-[#8C9791]">{action.description}</span>
                                    </span>
                                    <ArrowRight className="h-4 w-4 text-muted-dark transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
                                </Link>
                            </li>
                        ))}
                    </ul>
                </section>

                <section aria-labelledby="getting-started-heading" className="flex flex-col">
                    <SectionTitle title={<span id="getting-started-heading">Getting started</span>} count="4 steps" />
                    <ol className="flex flex-col">
                        {GETTING_STARTED.map((step, index) => (
                            <li key={step.title} className="grid grid-cols-[28px_minmax(0,1fr)] gap-4 border-b border-hairline-dark px-1.5 py-4">
                                <span className="font-mono text-[12px] text-gold">{String(index + 1).padStart(2, '0')}</span>
                                <span>
                                    <span className="block text-[15px] text-chalk">{step.title}</span>
                                    <span className="block text-[13px] leading-relaxed text-[#8C9791]">{step.body}</span>
                                </span>
                            </li>
                        ))}
                    </ol>
                </section>
            </div>
        </div>
    )
}

const GETTING_STARTED = [
    { title: 'Track a Team', body: 'Go to Teams and enable tracking for the clubs whose academies you want to follow' },
    { title: 'Seed Players', body: 'Use Seeding & Rebuild to discover academy players for your tracked teams, or add one-offs manually on the Players page' },
    { title: 'Generate Newsletters', body: 'Create newsletters for tracked teams with recent player activity' },
    { title: 'Assign Writers & Curate', body: 'Invite writers and assign them to teams in Users & Writers; review community takes, flags, and submissions in the Inbox' },
]
