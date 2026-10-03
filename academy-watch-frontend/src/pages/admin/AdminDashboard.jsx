import { useState, useEffect } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { Link } from 'react-router-dom'
import { CalmDetails, CalmHeader, CalmSection, StatusDot } from '@/components/admin/ControlRoom'
import { APIService } from '@/lib/api'
import { useControlFlags, useControlData } from '@/components/admin/B3Control'
import { clearLine, todayRows } from '@/lib/admin-today'
import { cn } from '@/lib/utils'
import { fetchInboxCounts, INBOX_TABS } from './AdminInbox'

// A small number with its label in plain words; `ok` adds "OK" / "needs repair".
function StatTile({ label, value, ok, okLabel = 'OK', warnLabel = 'needs repair', testId }) {
    return (
        <div className="flex min-w-0 flex-col gap-1 py-3 pr-4" data-testid={testId}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-xl font-semibold tabular-nums text-chalk">{value}</span>
                {ok !== undefined && <span className={cn('text-[13px]', ok ? 'text-[#8FBFA4]' : 'text-[#E07A5F]')}>{ok ? okLabel : warnLabel}</span>}
            </div>
            <p className="text-[13px] text-muted-dark">{label}</p>
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
        <span className="flex flex-col items-start gap-1 text-base font-medium">
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
                'h-8 rounded-full px-3.5 text-[13px] transition-colors',
                days === value ? 'bg-chalk text-night' : 'text-muted-dark hover:text-chalk'
            )}
        >
            {value} days
        </button>
    )

    return (
        <section data-testid="analytics-summary" aria-label="Product analytics" className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[13px] text-muted-dark">First-party events, last {days} days</p>
                <div className="flex gap-1 rounded-full border border-chalk/20 p-1" role="group" aria-label="Analytics window">
                    {rangeButton(7)}
                    {rangeButton(30)}
                </div>
            </div>
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
                        <div className="mb-2 flex items-center justify-between text-[13px] text-muted-dark">
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
                                    <span className="absolute -top-1 right-0 text-[11px] tabular-nums text-muted-dark">{maxDaily.toLocaleString()}</span>
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
                                <figcaption className="mt-2 flex justify-between text-[12px] text-muted-dark">
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

// Best-effort read: `null` = no answer (the row or number it feeds is left out).
function useOptional(load, enabled = true) {
    const [value, setValue] = useState(undefined)
    useEffect(() => {
        if (!enabled) return
        let cancelled = false
        load().then(data => { if (!cancelled) setValue(data ?? null) }).catch(() => { if (!cancelled) setValue(null) })
        return () => { cancelled = true }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- each loader is a fixed request for the page's lifetime
    }, [enabled])
    return value
}

const loadStats = () => APIService.request('/admin/dashboard-stats', {}, { admin: true })
const loadOps = () => APIService.adminOpsOverview()
const loadClaims = () => APIService.adminFundingClaims({ status: 'pending' })
const loadPendingScouts = () => APIService.adminListScoutVerifications({ status: 'pending', limit: 3 })
const loadVerifiedScouts = () => APIService.adminListScoutVerifications({ status: 'approved', limit: 1 })
const loadBilling = () => APIService.getAdminBillingSummary()
const INBOX_LABELS = Object.fromEntries(INBOX_TABS.map(tab => [tab.value, tab.label]))
const todayDate = () => new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
const whole = value => Number.isFinite(value) ? value.toLocaleString('en-GB') : null
const hasMrr = summary => Number.isFinite(summary?.mrr_cents) || Object.values(summary?.mrr_by_currency || {}).some(Number.isFinite)

function DecisionRow({ row, last }) {
    const body = (
        <>
            <StatusDot tone={row.tone} />
            <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium text-chalk [overflow-wrap:anywhere]">{row.title}</span>
                <span className="mt-0.5 block text-[13px] text-muted-dark [overflow-wrap:anywhere]">{row.summary}</span>
            </span>
            <span className="flex-none text-[13px] text-muted-dark">{row.area}</span>
        </>
    )
    const rowClass = cn('flex items-center gap-4 px-5 py-4', !last && 'border-b border-chalk/[0.08]')
    return (
        <li>
            {row.href
                ? <Link to={row.href} className={cn(rowClass, 'no-underline transition-colors hover:bg-chalk/[0.04] hover:no-underline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-gold')}>{body}</Link>
                : <div className={rowClass}>{body}</div>}
        </li>
    )
}

function HeadlineNumber({ label, value, testId }) {
    return (
        <div className="min-w-0" data-testid={testId}>
            <div className="min-h-9 text-[28px] font-semibold leading-9 tabular-nums text-chalk">{value}</div>
            <div className="mt-1 text-[13px] text-muted-dark">{label}</div>
        </div>
    )
}

export function AdminDashboard() {
    const flags = useControlFlags()
    const flagsReady = flags !== null
    const businessEnabled = !!flags?.admin_business
    const controlEnabled = !!(flags?.admin_programs || flags?.admin_people || flags?.admin_safety || flags?.admin_business)
    const overview = useControlData(controlEnabled ? '/admin/control/overview' : null)
    const clubs = useControlData(flags?.admin_programs ? '/admin/programs?limit=1' : null)
    const stats = useOptional(loadStats)
    const ops = useOptional(loadOps)
    const claimData = useOptional(loadClaims)
    const pendingScouts = useOptional(loadPendingScouts)
    const verifiedScouts = useOptional(loadVerifiedScouts)
    // With every control-room flag off the page asks exactly what it asked before: the inbox counts and the billing summary.
    const inbox = useOptional(fetchInboxCounts, flagsReady && !controlEnabled)
    const billing = useOptional(loadBilling, flagsReady && !businessEnabled)
    const [analyticsOpen, setAnalyticsOpen] = useState(false)

    const revenue = businessEnabled ? overview.data?.revenue : billing
    const unavailable = controlEnabled ? !!overview.error : inbox === null
    const loading = !flagsReady || (controlEnabled ? !overview.data && !overview.error : inbox === undefined)
    const queues = controlEnabled
        ? overview.data?.queues || []
        : INBOX_TABS.map(tab => ({ key: tab.value, label: INBOX_LABELS[tab.value], href: `/admin/inbox?tab=${tab.value}`, count: inbox?.[tab.value] }))
    const claims = Array.isArray(claimData?.claims) ? claimData.claims : null
    const scouts = Array.isArray(pendingScouts?.verifications) ? { rows: pendingScouts.verifications, total: pendingScouts.total ?? pendingScouts.verifications.length } : null
    const today = todayRows({ queues, claims, scouts, overdue: controlEnabled ? overview.data?.overdue_safeguarding : 0, revenue, ops, businessHref: businessEnabled ? '/admin/business' : null })
    const waiting = today.rows.length
    const safetyRows = today.rows.filter(row => row.key === 'reports' || row.key === 'safeguarding').length
    const line = clearLine(today)

    const numbers = [
        stats === undefined ? { label: 'Tracked players', pending: true } : Number.isFinite(stats?.players?.total) && { label: 'Tracked players', value: whole(stats.players.total) },
        flags?.admin_programs
            ? (!clubs.data && !clubs.error ? { label: 'Clubs', pending: true } : Number.isFinite(clubs.data?.total) && { label: 'Clubs', value: whole(clubs.data.total) })
            : stats === undefined ? { label: 'Tracked teams', pending: true } : Number.isFinite(stats?.teams?.tracked) && { label: 'Tracked teams', value: whole(stats.teams.tracked) },
        verifiedScouts === undefined ? { label: 'Verified scouts', pending: true } : Number.isFinite(verifiedScouts?.total) && { label: 'Verified scouts', value: whole(verifiedScouts.total) },
        revenue === undefined && !(businessEnabled && overview.error) ? { label: 'Monthly recurring revenue', pending: true } : hasMrr(revenue) && { label: 'Monthly recurring revenue', value: <MonthlyRecurringRevenue summary={revenue} />, testId: 'revenue-summary' },
    ].filter(Boolean)
    const more = stats ? [
        ['In the academy', stats.players?.academy], ['Out on loan', stats.players?.on_loan], ['First team', stats.players?.first_team],
        ['Released', stats.players?.released], ...(flags?.admin_programs ? [['Tracked teams', stats.teams?.tracked]] : []),
        ['Newsletters published', stats.newsletters?.published], ['Newsletter drafts', stats.newsletters?.drafts],
        ...(Number.isFinite(revenue?.active_subscriptions) ? [['Active subscriptions', revenue.active_subscriptions]] : []),
    ].filter(([, value]) => Number.isFinite(value)) : []

    return (
        <div className="flex max-w-[920px] flex-col gap-8">
            <CalmHeader title="Today" aside={todayDate()} />

            <CalmSection title="Needs a decision" count={!loading && !unavailable && waiting ? waiting : null} data-testid="inbox-pending" aria-label="Needs a decision">
                {unavailable ? (
                    <p className="text-sm text-muted-dark">
                        {controlEnabled ? 'Review' : 'Inbox'} counts unavailable — open the <Link to="/admin/inbox" className="underline">review queue</Link> directly.
                    </p>
                ) : loading ? (
                    <div className="flex flex-col gap-2" role="status" aria-label="Loading what is waiting">
                        {[0, 1, 2].map(index => <Skeleton key={index} className="h-[72px] w-full rounded-2xl" />)}
                    </div>
                ) : (
                    <>
                        {waiting > 0 && (
                            <ul className="m-0 list-none overflow-hidden rounded-2xl border border-chalk/[0.12] p-0">
                                {today.rows.map((row, index) => <DecisionRow key={row.key} row={row} last={index === waiting - 1} />)}
                            </ul>
                        )}
                        {line && <p className="text-[13px] text-muted-dark" data-testid="today-clear">{line}</p>}
                        {safetyRows === 2 && <p className="text-[13px] text-muted-dark">A report also appears as a safeguarding case; one decision clears both.</p>}
                    </>
                )}
            </CalmSection>

            {numbers.length > 0 && (
                <CalmSection title="The numbers" data-testid="today-numbers">
                    <div className="grid grid-cols-2 gap-6 border-t border-chalk/[0.12] py-5 sm:grid-cols-4">
                        {numbers.map(number => number.pending
                            ? <div key={number.label}><Skeleton className="h-9 w-20" /><div className="mt-1 text-[13px] text-muted-dark">{number.label}</div></div>
                            : <HeadlineNumber key={number.label} {...number} />)}
                    </div>
                </CalmSection>
            )}

            <div className="border-b border-chalk/[0.12]">
                {more.length > 0 && (
                    <CalmDetails summary="More numbers">
                        <div className="grid grid-cols-2 sm:grid-cols-4">{more.map(([label, value]) => <StatTile key={label} label={label} value={whole(value)} />)}</div>
                    </CalmDetails>
                )}
                {ops !== null && (
                    <CalmDetails summary="Data health" note={ops ? (ops.tracked?.placeholder_names || ops.tracked?.owning_club_active ? 'needs repair' : 'all good') : null} noteTone={ops?.tracked?.placeholder_names || ops?.tracked?.owning_club_active ? 'warn' : undefined}>
                        <div data-testid="ops-snapshot">
                            {ops ? (
                                <div className="grid grid-cols-2 sm:grid-cols-4">
                                    <StatTile label="Active tracked players" value={whole(ops.tracked?.active ?? 0)} testId="ops-tile-active" />
                                    <StatTile label="Placeholder names" value={whole(ops.tracked?.placeholder_names ?? 0)} ok={(ops.tracked?.placeholder_names ?? 0) === 0} testId="ops-tile-placeholders" />
                                    <StatTile label="Tracked at their own club" value={whole(ops.tracked?.owning_club_active ?? 0)} ok={(ops.tracked?.owning_club_active ?? 0) === 0} testId="ops-tile-owning-club" />
                                    <StatTile label="Jobs running" value={whole(ops.jobs?.active ?? 0)} testId="ops-tile-jobs" />
                                </div>
                            ) : <Skeleton className="h-14 w-full" />}
                            <Link to="/admin/operations" data-testid="ops-snapshot-link" className="mt-2 inline-block text-sm text-chalk underline underline-offset-4">Open Operations</Link>
                        </div>
                    </CalmDetails>
                )}
                <CalmDetails summary="Product analytics" onToggle={event => { if (event.currentTarget.open) setAnalyticsOpen(true) }}>
                    {analyticsOpen && <AnalyticsSummaryCard />}
                </CalmDetails>
            </div>
        </div>
    )
}
