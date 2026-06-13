import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
    Activity,
    AlertCircle,
    CheckCircle2,
    Database,
    Globe2,
    ListChecks,
    Loader2,
    Mail,
    Play,
    RefreshCw,
    Wrench,
} from 'lucide-react'

import { APIService } from '@/lib/api'
import { ConfirmGate } from '@/components/admin/ConfirmGate'
import { CursorRunner } from '@/components/admin/CursorRunner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CURRENT_SEASON = (() => {
    const now = new Date()
    return now.getMonth() + 1 >= 8 ? now.getFullYear() : now.getFullYear() - 1
})()
const SEASON_OPTIONS = [0, 1, 2, 3, 4].map((i) => CURRENT_SEASON - i)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function formatTimestamp(ts) {
    if (!ts) return null
    const parsed = Date.parse(ts)
    if (Number.isNaN(parsed)) return String(ts)
    return new Date(parsed).toLocaleString()
}

// Unknown-tolerant last-run matching against /admin/runs/history events.
// Events are loosely-shaped dicts; we match keywords against kind + message
// and prefer the most recent parseable timestamp.
function findLastRun(history, keywords) {
    if (!Array.isArray(history)) return null
    const matches = history.filter((event) => {
        if (!event || typeof event !== 'object') return false
        const hay = `${event.kind || ''} ${event.message || ''}`.toLowerCase()
        return keywords.some((k) => hay.includes(k))
    })
    if (!matches.length) return null
    let best = matches[0]
    let bestTs = Date.parse(best?.ts || '')
    for (const event of matches.slice(1)) {
        const ts = Date.parse(event?.ts || '')
        if (!Number.isNaN(ts) && (Number.isNaN(bestTs) || ts > bestTs)) {
            best = event
            bestTs = ts
        }
    }
    return best
}

function scalarEntries(data, omit = []) {
    if (!data || typeof data !== 'object') return []
    return Object.entries(data).filter(
        ([key, value]) =>
            !omit.includes(key) &&
            (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean')
    )
}

function CounterChips({ data, omit = [], testId }) {
    const entries = scalarEntries(data, omit)
    if (!entries.length) return null
    return (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2" data-testid={testId}>
            {entries.map(([key, value]) => (
                <div key={key} className="rounded-lg border bg-muted/30 p-2">
                    <div className="text-base font-semibold break-all">{String(value)}</div>
                    <div className="text-xs text-muted-foreground break-all">{key.replaceAll('_', ' ')}</div>
                </div>
            ))}
        </div>
    )
}

function StatusBadge({ count }) {
    const ok = (Number(count) || 0) === 0
    return (
        <Badge
            variant="outline"
            className={
                ok
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-amber-200 bg-amber-50 text-amber-800'
            }
        >
            {ok ? 'OK' : 'needs repair'}
        </Badge>
    )
}

// ---------------------------------------------------------------------------
// Duties registry — static. No scheduler exists anywhere; this page is the
// manual cockpit. Last-run is derived defensively from run history.
// ---------------------------------------------------------------------------

const DUTIES = [
    {
        id: 'newsletter-weekly',
        duty: 'Weekly newsletter generation',
        cadence: 'Weekly, after the weekend fixtures',
        keywords: ['newsletter-run'],
        action: { type: 'link', to: '/admin/newsletters', label: 'Newsletters' },
    },
    {
        id: 'deadline-processing',
        duty: 'Monday deadline processing (publishes & charges writers)',
        cadence: 'Mondays 23:59 GMT',
        keywords: ['deadline'],
        action: { type: 'link', to: '/admin/newsletters', label: 'Newsletters' },
    },
    {
        id: 'scout-digests',
        duty: 'Scout digest emails',
        cadence: 'Weekly',
        keywords: ['scout'],
        action: { type: 'anchor', href: '#scout-digests', label: 'Runner below' },
    },
    {
        id: 'transfer-window-heal',
        duty: 'Transfer-window heal (refresh tracked-player statuses)',
        cadence: 'Each transfer window (Jan / summer)',
        keywords: ['refresh-status', 'refresh_status', 'refresh statuses'],
        action: { type: 'link', to: '/admin/players', label: 'Players' },
    },
    {
        id: 'video-reaper',
        duty: 'Video stale-job reaper',
        cadence: 'As needed (stuck GPU jobs)',
        keywords: ['reap', 'stale-job', 'stale job'],
        action: { type: 'link', to: '/admin/video', label: 'Film Room' },
    },
    {
        id: 'provenance-repair',
        duty: 'Provenance repair (recompute-academy + backfill-names)',
        cadence: 'After data incidents / new-region syncs',
        keywords: ['recompute-academy', 'recompute_academy', 'backfill-names', 'backfill_names'],
        action: { type: 'anchor', href: '#provenance-repair', label: 'Runners below' },
    },
]

// ---------------------------------------------------------------------------
// Generic backfill tool card (section 6)
// ---------------------------------------------------------------------------

function BackfillCard({ id, title, description, quotaNote, fields = [], run, confirmWord, pollsJob = false }) {
    const [values, setValues] = useState(() =>
        Object.fromEntries(fields.map((f) => [f.key, f.defaultValue ?? '']))
    )
    const [dryRun, setDryRun] = useState(true)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const [busy, setBusy] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)
    const [job, setJob] = useState(null)
    const mountedRef = useRef(true)

    useEffect(() => {
        mountedRef.current = true
        return () => {
            mountedRef.current = false
        }
    }, [])

    const pollJob = useCallback(async (jobId) => {
        setJob({ id: jobId, status: 'running', data: null })
        for (;;) {
            await sleep(3000)
            if (!mountedRef.current) return
            let data
            try {
                data = await APIService.adminGetJobStatus(jobId)
            } catch (err) {
                if (mountedRef.current) setJob((j) => ({ ...(j || {}), status: 'unknown', error: err?.message }))
                return
            }
            const status = data?.status || data?.job?.status || 'running'
            if (!mountedRef.current) return
            setJob({ id: jobId, status, data })
            if (['completed', 'failed', 'cancelled'].includes(status)) return
        }
    }, [])

    const execute = async () => {
        setBusy(true)
        setError(null)
        setResult(null)
        setJob(null)
        try {
            const response = await run(values, dryRun)
            if (!mountedRef.current) return
            setResult(response)
            if (pollsJob && response?.job_id) {
                await pollJob(response.job_id)
            }
        } catch (err) {
            if (mountedRef.current) setError(err?.message || 'Request failed')
        } finally {
            if (mountedRef.current) setBusy(false)
        }
    }

    const onRunClick = () => {
        if (dryRun) {
            execute()
        } else {
            setConfirmOpen(true)
        }
    }

    const jobResults = job?.data?.results || job?.data?.job?.results || null

    return (
        <Card data-testid={`backfill-${id}`}>
            <CardHeader>
                <CardTitle className="text-base">{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {quotaNote && (
                    <Alert className="border-amber-300 bg-amber-50">
                        <AlertCircle className="h-4 w-4 text-amber-600" />
                        <AlertDescription className="text-amber-800">{quotaNote}</AlertDescription>
                    </Alert>
                )}

                <div className="flex flex-wrap items-end gap-3">
                    {fields.map((field) => (
                        <div key={field.key} className="space-y-1">
                            <Label htmlFor={`backfill-${id}-${field.key}`} className="text-xs">
                                {field.label}
                            </Label>
                            <Input
                                id={`backfill-${id}-${field.key}`}
                                data-testid={`backfill-${id}-${field.key}`}
                                type={field.type || 'text'}
                                className="w-36"
                                value={values[field.key]}
                                placeholder={field.placeholder}
                                onChange={(e) =>
                                    setValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                                }
                            />
                        </div>
                    ))}

                    <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
                        <Switch
                            checked={dryRun}
                            onCheckedChange={setDryRun}
                            disabled={busy}
                            data-testid={`backfill-${id}-dryrun`}
                            aria-label="Dry run"
                        />
                        <span className="text-sm">{dryRun ? 'Dry run' : <span className="text-destructive font-medium">LIVE</span>}</span>
                    </div>

                    <Button
                        size="sm"
                        variant={dryRun ? 'outline' : 'destructive'}
                        disabled={busy}
                        onClick={onRunClick}
                        data-testid={`backfill-${id}-run`}
                    >
                        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                        Run
                    </Button>
                </div>

                {error && (
                    <Alert className="border-rose-500 bg-rose-50">
                        <AlertCircle className="h-4 w-4 text-rose-600" />
                        <AlertDescription className="text-rose-800">{error}</AlertDescription>
                    </Alert>
                )}

                {result && (
                    <div className="space-y-2">
                        {result.message && <p className="text-sm text-muted-foreground">{result.message}</p>}
                        <CounterChips data={result} omit={['message', 'kind', 'job_id']} testId={`backfill-${id}-result`} />
                    </div>
                )}

                {job && (
                    <div className="space-y-2 rounded-lg border bg-muted/20 p-3" data-testid={`backfill-${id}-job`}>
                        <div className="flex items-center gap-2 text-sm">
                            {job.status === 'running' && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
                            {job.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                            {(job.status === 'failed' || job.status === 'cancelled') && (
                                <AlertCircle className="h-4 w-4 text-rose-600" />
                            )}
                            <span className="font-medium">Background job</span>
                            <Badge variant="secondary">{job.status}</Badge>
                            <code className="text-xs text-muted-foreground break-all">{job.id}</code>
                        </div>
                        {job.error && <p className="text-xs text-rose-700">{job.error}</p>}
                        {jobResults && <CounterChips data={jobResults} />}
                    </div>
                )}
            </CardContent>

            <ConfirmGate
                open={confirmOpen}
                onOpenChange={setConfirmOpen}
                title={`Run live: ${title}`}
                description={`${quotaNote ? `${quotaNote}\n\n` : ''}This run will write changes (dry_run: false).`}
                confirmWord={confirmWord}
                confirmLabel="Run live"
                destructive
                onConfirm={execute}
            />
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AdminOperations() {
    // System status / overview
    const [overview, setOverview] = useState(null)
    const [overviewLoading, setOverviewLoading] = useState(true)
    const [overviewError, setOverviewError] = useState(null)
    const [baseline, setBaseline] = useState(null)
    const [verifyAfter, setVerifyAfter] = useState(null)
    const [verifying, setVerifying] = useState(false)
    const [pauseSaving, setPauseSaving] = useState(false)
    const [notice, setNotice] = useState(null)

    // Duties registry
    const [runsHistory, setRunsHistory] = useState(null)

    // Force-fail-all
    const [forceFailOpen, setForceFailOpen] = useState(false)
    const [forceFailResult, setForceFailResult] = useState(null)

    // Backfill-names runner
    const [bnDryRun, setBnDryRun] = useState(true)
    const [bnConfirmOpen, setBnConfirmOpen] = useState(false)
    const [bnFetchMissing, setBnFetchMissing] = useState(false)
    const [bnFetchLimit, setBnFetchLimit] = useState('50')
    const [bnBusy, setBnBusy] = useState(false)
    const [bnResult, setBnResult] = useState(null)
    const [bnError, setBnError] = useState(null)

    // Global footprint
    const [syncLeaguesOpen, setSyncLeaguesOpen] = useState(false)
    const [syncLeaguesBusy, setSyncLeaguesBusy] = useState(false)
    const [syncLeaguesResult, setSyncLeaguesResult] = useState(null)
    const [syncTeamsOpen, setSyncTeamsOpen] = useState(false)
    const [syncTeamsBusy, setSyncTeamsBusy] = useState(false)
    const [syncTeamsSeason, setSyncTeamsSeason] = useState(String(CURRENT_SEASON))
    const [syncTeamsResult, setSyncTeamsResult] = useState(null)

    const loadOverview = useCallback(async ({ asBaseline = false } = {}) => {
        try {
            const data = await APIService.adminOpsOverview()
            setOverview(data)
            setOverviewError(null)
            if (asBaseline) setBaseline(data)
            return data
        } catch (err) {
            setOverviewError(err?.message || 'Failed to load operations overview')
            return null
        } finally {
            setOverviewLoading(false)
        }
    }, [])

    useEffect(() => {
        ;(async () => {
            await loadOverview({ asBaseline: true })
            try {
                const history = await APIService.adminRunsHistory()
                setRunsHistory(Array.isArray(history) ? history : history?.items || [])
            } catch {
                setRunsHistory([])
            }
        })()
    }, [loadOverview])

    const togglePaused = async (next) => {
        setPauseSaving(true)
        try {
            await APIService.adminSetRunStatus(next)
            setOverview((prev) => (prev ? { ...prev, runs_paused: next } : prev))
            setNotice({ type: 'success', text: next ? 'Runs paused.' : 'Runs resumed.' })
        } catch (err) {
            setNotice({ type: 'error', text: `Failed to update run status: ${err?.message || err}` })
        } finally {
            setPauseSaving(false)
        }
    }

    const forceFailAll = async () => {
        try {
            const result = await APIService.adminJobsForceFailAll()
            setForceFailResult(result)
            setNotice({ type: 'success', text: result?.message || 'Force-fail complete.' })
            loadOverview()
        } catch (err) {
            setNotice({ type: 'error', text: `Force-fail failed: ${err?.message || err}` })
        }
    }

    const runBackfillNames = async () => {
        setBnBusy(true)
        setBnError(null)
        setBnResult(null)
        try {
            const fetchLimit = Number.parseInt(bnFetchLimit, 10)
            const result = await APIService.adminBackfillPlayerNames({
                dryRun: bnDryRun,
                fetchMissing: bnFetchMissing,
                fetchLimit: Number.isFinite(fetchLimit) && fetchLimit > 0 ? fetchLimit : 50,
            })
            setBnResult(result)
        } catch (err) {
            setBnError(err?.message || 'Backfill failed')
        } finally {
            setBnBusy(false)
        }
    }

    const runVerify = async () => {
        setVerifying(true)
        const data = await loadOverview()
        if (data) setVerifyAfter(data)
        setVerifying(false)
    }

    const syncLeagues = async () => {
        setSyncLeaguesBusy(true)
        setSyncLeaguesResult(null)
        try {
            const result = await APIService.adminSyncLeagues()
            setSyncLeaguesResult(result)
            setNotice({ type: 'success', text: 'League sync finished.' })
        } catch (err) {
            setNotice({ type: 'error', text: `League sync failed: ${err?.message || err}` })
        } finally {
            setSyncLeaguesBusy(false)
        }
    }

    const syncTeams = async () => {
        setSyncTeamsBusy(true)
        setSyncTeamsResult(null)
        try {
            const result = await APIService.adminSyncTeams(Number(syncTeamsSeason))
            setSyncTeamsResult(result)
            setNotice({ type: 'success', text: `Team sync for ${syncTeamsSeason} finished.` })
        } catch (err) {
            setNotice({ type: 'error', text: `Team sync failed: ${err?.message || err}` })
        } finally {
            setSyncTeamsBusy(false)
        }
    }

    const tracked = overview?.tracked || {}
    const crawl = overview?.crawl || {}
    const crawlIds = new Set(crawl.crawl_league_ids || [])
    const bnApplied = bnResult ? (bnResult.applied ?? bnResult.dry_run === false) : null

    const verifyMetrics = [
        ['active', 'Active tracked'],
        ['placeholder_names', 'Placeholder names'],
        ['null_position', 'NULL position'],
        ['null_birth_date', 'NULL birth date'],
        ['null_age', 'NULL age'],
        ['owning_club_active', 'Owning-club active'],
    ]

    return (
        <div className="space-y-6">
            <header>
                <h2 className="text-3xl font-bold tracking-tight">Operations</h2>
                <p className="text-muted-foreground mt-1">
                    Manual cockpit for periodic duties, provenance repairs, and data backfills — there is no
                    scheduler, so nothing here runs unless you run it.
                </p>
            </header>

            {notice && (
                <Alert className={notice.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {notice.type === 'error'
                        ? <AlertCircle className="h-4 w-4 text-rose-600" />
                        : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={notice.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {notice.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* 1 — System status */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5" /> System status
                    </CardTitle>
                    <CardDescription>Tracked-player data health, run pause flag, API quota, and active jobs</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {overviewLoading ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <Skeleton key={i} className="h-20 rounded-lg" />
                            ))}
                        </div>
                    ) : overviewError ? (
                        <Alert className="border-rose-500 bg-rose-50">
                            <AlertCircle className="h-4 w-4 text-rose-600" />
                            <AlertDescription className="text-rose-800">
                                {overviewError}
                                <Button size="sm" variant="outline" className="ml-3" onClick={() => loadOverview({ asBaseline: true })}>
                                    Retry
                                </Button>
                            </AlertDescription>
                        </Alert>
                    ) : (
                        <>
                            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="ops-tracked-grid">
                                <div className="rounded-lg border bg-muted/30 p-3 space-y-1">
                                    <div className="text-2xl font-semibold">{tracked.active ?? '—'}</div>
                                    <div className="text-xs text-muted-foreground">Active tracked</div>
                                    <Badge variant="outline">info</Badge>
                                </div>
                                {[
                                    ['placeholder_names', 'Placeholder names'],
                                    ['null_position', 'NULL position'],
                                    ['null_birth_date', 'NULL birth date'],
                                    ['null_age', 'NULL age'],
                                    ['owning_club_active', 'Owning-club active'],
                                ].map(([key, label]) => (
                                    <div key={key} className="rounded-lg border bg-muted/30 p-3 space-y-1">
                                        <div className="text-2xl font-semibold">{tracked[key] ?? '—'}</div>
                                        <div className="text-xs text-muted-foreground">{label}</div>
                                        <StatusBadge count={tracked[key]} />
                                    </div>
                                ))}
                            </div>

                            <p className="text-xs text-muted-foreground">
                                Journeys: {overview?.journeys?.total ?? '—'} total, {overview?.journeys?.with_entries ?? '—'} with entries
                                {' · '}Inactive tracked rows: {tracked.inactive ?? '—'}
                            </p>

                            <div className="flex flex-wrap items-center gap-4 pt-2 border-t">
                                <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
                                    <Switch
                                        checked={Boolean(overview?.runs_paused)}
                                        onCheckedChange={togglePaused}
                                        disabled={pauseSaving}
                                        data-testid="ops-runs-paused-toggle"
                                        aria-label="Pause runs"
                                    />
                                    <span className="text-sm font-medium">
                                        {overview?.runs_paused ? 'Runs PAUSED' : 'Runs enabled'}
                                    </span>
                                    {pauseSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                                </div>

                                <div className="text-sm text-muted-foreground">
                                    API calls today:{' '}
                                    <span className="font-semibold text-foreground">
                                        {overview?.api_usage_today ?? 'n/a'}
                                    </span>
                                </div>

                                <div className="flex items-center gap-2 text-sm">
                                    <span className="text-muted-foreground">Active jobs:</span>
                                    <Badge variant={(overview?.jobs?.active || 0) > 0 ? 'default' : 'secondary'}>
                                        {overview?.jobs?.active ?? 0}
                                    </Badge>
                                    <Button
                                        size="sm"
                                        variant="destructive"
                                        data-testid="ops-force-fail-all"
                                        onClick={() => setForceFailOpen(true)}
                                    >
                                        Force-fail all jobs
                                    </Button>
                                </div>
                            </div>
                            {forceFailResult && (
                                <p className="text-xs text-muted-foreground">
                                    Last force-fail: {forceFailResult.message} (count: {forceFailResult.count ?? 0})
                                </p>
                            )}
                        </>
                    )}
                </CardContent>
            </Card>

            {/* 2 — Duties */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <ListChecks className="h-5 w-5" /> Duties
                    </CardTitle>
                    <CardDescription>
                        Every periodic duty the platform expects. No scheduler exists — this table is the manual
                        cockpit: each duty only happens when an admin runs it.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Table data-testid="ops-duties-table">
                        <TableHeader>
                            <TableRow>
                                <TableHead>Duty</TableHead>
                                <TableHead>Intended cadence</TableHead>
                                <TableHead>Last run</TableHead>
                                <TableHead>Action</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {DUTIES.map((duty) => {
                                const lastRun = runsHistory === null ? undefined : findLastRun(runsHistory, duty.keywords)
                                return (
                                    <TableRow key={duty.id} data-testid={`ops-duty-${duty.id}`}>
                                        <TableCell className="font-medium whitespace-normal">{duty.duty}</TableCell>
                                        <TableCell className="text-muted-foreground whitespace-normal">{duty.cadence}</TableCell>
                                        <TableCell>
                                            {runsHistory === null ? (
                                                <Skeleton className="h-4 w-28" />
                                            ) : lastRun ? (
                                                <span title={lastRun.message || lastRun.kind}>
                                                    {formatTimestamp(lastRun.ts) || 'unknown'}
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground">unknown</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            {duty.action.type === 'link' ? (
                                                <Button asChild size="sm" variant="outline">
                                                    <Link to={duty.action.to}>{duty.action.label}</Link>
                                                </Button>
                                            ) : (
                                                <Button asChild size="sm" variant="outline">
                                                    <a href={duty.action.href}>{duty.action.label}</a>
                                                </Button>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>

            {/* 3 — Provenance repair */}
            <section id="provenance-repair" className="space-y-4 scroll-mt-20">
                <div className="flex items-center gap-2">
                    <Wrench className="h-5 w-5" />
                    <h3 className="text-xl font-semibold">Provenance repair</h3>
                </div>

                <CursorRunner
                    title="Provenance repair (recompute-academy)"
                    description="Re-types stored journey entries, recomputes academy_club_ids, and deactivates tracked rows that contradict academy provenance (deprecated owning-club rows, non-academy parents, outside the tracking window). Cursor-paged; the owning-club sweep only runs on the first page, so run the full loop at least once."
                    dryRunDefault={true}
                    confirmWord="APPLY"
                    runPage={async ({ dryRun, cursor }) => {
                        const r = await APIService.adminRecomputeAcademy({ dryRun, cursor, limit: 100 })
                        return {
                            nextCursor: r?.next_cursor ?? null,
                            counters: {
                                processed: r?.journeys_processed,
                                changed: r?.journeys_changed,
                                deactivated: r?.rows_deactivated,
                                errors: r?.errors,
                            },
                            examples: r?.examples,
                            applied: r?.applied,
                        }
                    }}
                />

                {/* Backfill names — single-shot */}
                <Card data-testid="ops-backfill-names">
                    <CardHeader>
                        <CardTitle className="text-base">Backfill placeholder names & profiles</CardTitle>
                        <CardDescription>
                            Resolves &ldquo;Player NNNN&rdquo; placeholder names from local sources (cohorts, season
                            stats, players, journeys) and fills NULL position / birth date / age / nationality.
                            Single-shot — one call covers the whole population.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex flex-wrap items-end gap-3">
                            <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
                                <Switch
                                    checked={bnDryRun}
                                    onCheckedChange={(next) => {
                                        if (next) setBnDryRun(true)
                                        else setBnConfirmOpen(true)
                                    }}
                                    disabled={bnBusy}
                                    data-testid="ops-backfill-names-dryrun"
                                    aria-label="Dry run"
                                />
                                <span className="text-sm">
                                    {bnDryRun ? 'Dry run' : <span className="text-destructive font-medium">LIVE</span>}
                                </span>
                            </div>

                            <label className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={bnFetchMissing}
                                    onChange={(e) => setBnFetchMissing(e.target.checked)}
                                    className="h-4 w-4 rounded border-border"
                                    data-testid="ops-backfill-names-fetch-missing"
                                />
                                <span className="text-sm">Fetch missing from API-Football</span>
                            </label>

                            {bnFetchMissing && (
                                <div className="space-y-1">
                                    <Label htmlFor="ops-bn-fetch-limit" className="text-xs">Fetch limit (max 200)</Label>
                                    <Input
                                        id="ops-bn-fetch-limit"
                                        data-testid="ops-backfill-names-fetch-limit"
                                        type="number"
                                        min="1"
                                        max="200"
                                        className="w-28"
                                        value={bnFetchLimit}
                                        onChange={(e) => setBnFetchLimit(e.target.value)}
                                    />
                                </div>
                            )}

                            <Button
                                size="sm"
                                variant={bnDryRun ? 'outline' : 'destructive'}
                                disabled={bnBusy}
                                onClick={runBackfillNames}
                                data-testid="ops-backfill-names-run"
                            >
                                {bnBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                                Run backfill
                            </Button>
                        </div>

                        {bnFetchMissing && (
                            <Alert className="border-amber-300 bg-amber-50">
                                <AlertCircle className="h-4 w-4 text-amber-600" />
                                <AlertDescription className="text-amber-800">
                                    Quota warning: fetching missing profiles spends API-Football quota (one call per
                                    player, capped by the fetch limit). The fetch only happens on a LIVE run — it is
                                    skipped under dry-run.
                                </AlertDescription>
                            </Alert>
                        )}

                        {bnError && (
                            <Alert className="border-rose-500 bg-rose-50">
                                <AlertCircle className="h-4 w-4 text-rose-600" />
                                <AlertDescription className="text-rose-800">{bnError}</AlertDescription>
                            </Alert>
                        )}

                        {bnResult && (
                            <div className="space-y-2">
                                <Badge variant={bnApplied ? 'default' : 'secondary'}>
                                    {bnApplied ? 'applied' : 'not applied (dry run)'}
                                </Badge>
                                <CounterChips
                                    data={bnResult}
                                    omit={['dry_run', 'applied']}
                                    testId="ops-backfill-names-result"
                                />
                                {Array.isArray(bnResult.examples) && bnResult.examples.length > 0 && (
                                    <ul className="max-h-48 overflow-y-auto rounded-md border bg-muted/20 divide-y text-xs">
                                        {bnResult.examples.map((example, idx) => (
                                            <li key={idx} className="px-3 py-1.5 font-mono break-all">
                                                {example && typeof example === 'object'
                                                    ? `${example.player_api_id ?? ''}: ${example.old ?? ''} → ${example.new ?? ''}`
                                                    : String(example)}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        )}
                    </CardContent>

                    <ConfirmGate
                        open={bnConfirmOpen}
                        onOpenChange={setBnConfirmOpen}
                        title="Disable dry-run for name/profile backfill"
                        description="The next run will WRITE name and profile changes to tracked players, players, and journeys."
                        confirmWord="APPLY"
                        confirmLabel="Enable live mode"
                        destructive
                        onConfirm={() => setBnDryRun(false)}
                    />
                </Card>

                {/* Verify applied state */}
                <Card data-testid="ops-verify-panel">
                    <CardHeader>
                        <CardTitle className="text-base">Verify applied state</CardTitle>
                        <CardDescription>
                            The dry-run trap is real: dry and live runs return identical counters, and a believed-applied
                            repair has silently rolled back in production before. Re-fetching live DB counts and comparing
                            against the page-load baseline is the only proof a repair actually committed.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={runVerify}
                            disabled={verifying || overviewLoading}
                            data-testid="ops-verify-refetch"
                        >
                            {verifying ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                            Re-fetch & compare
                        </Button>

                        {baseline && verifyAfter && (
                            <Table data-testid="ops-verify-table">
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Metric</TableHead>
                                        <TableHead>Before (page load)</TableHead>
                                        <TableHead>After (re-fetch)</TableHead>
                                        <TableHead>Delta</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {verifyMetrics.map(([key, label]) => {
                                        const before = baseline?.tracked?.[key]
                                        const after = verifyAfter?.tracked?.[key]
                                        const delta =
                                            typeof before === 'number' && typeof after === 'number' ? after - before : null
                                        return (
                                            <TableRow key={key}>
                                                <TableCell className="font-medium">{label}</TableCell>
                                                <TableCell>{before ?? '—'}</TableCell>
                                                <TableCell>{after ?? '—'}</TableCell>
                                                <TableCell>
                                                    {delta === null ? '—' : (
                                                        <span className={delta === 0 ? 'text-muted-foreground' : delta < 0 ? 'text-emerald-700 font-medium' : 'text-amber-700 font-medium'}>
                                                            {delta > 0 ? `+${delta}` : delta}
                                                        </span>
                                                    )}
                                                </TableCell>
                                            </TableRow>
                                        )
                                    })}
                                </TableBody>
                            </Table>
                        )}
                        {baseline && !verifyAfter && (
                            <p className="text-sm text-muted-foreground">
                                Baseline captured at page load. Run a repair above, then re-fetch to see what actually changed.
                            </p>
                        )}
                    </CardContent>
                </Card>
            </section>

            {/* 4 — Scout digests */}
            <section id="scout-digests" className="space-y-4 scroll-mt-20">
                <div className="flex items-center gap-2">
                    <Mail className="h-5 w-5" />
                    <h3 className="text-xl font-semibold">Scout digests</h3>
                </div>
                <CursorRunner
                    title="Scout digest emails (send-digests)"
                    description="Builds and sends the scout digest to opted-in watchlist users. Cursor-paged over user accounts (50 per page). Dry pages render a recipient preview without sending or mutating snapshots; live pages SEND EMAIL."
                    dryRunDefault={true}
                    confirmWord="SEND"
                    runPage={async ({ dryRun, cursor }) => {
                        const r = await APIService.adminSendScoutDigests({ dryRun, limit: 50, cursor })
                        return {
                            nextCursor: r?.next_cursor ?? null,
                            counters: {
                                sent: r?.sent,
                                skipped: r?.skipped,
                                users_considered: r?.users_considered,
                            },
                            // Recipient preview — drop the bulky rendered html.
                            examples: (r?.previews || []).map((p) => ({
                                email: p?.email,
                                subject: p?.subject,
                                players: p?.players,
                            })),
                            applied: r?.applied,
                        }
                    }}
                />
            </section>

            {/* 5 — Global footprint */}
            <Card data-testid="ops-global-footprint">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Globe2 className="h-5 w-5" /> Global footprint
                    </CardTitle>
                    <CardDescription>
                        Supported leagues (metadata/browse) vs the actively-crawled set. Crawling is env-gated
                        (CRAWL_LEAGUE_IDS) — widening it spends API quota on every fixture sweep.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {overviewLoading ? (
                        <Skeleton className="h-24 rounded-lg" />
                    ) : (
                        <div className="flex flex-wrap gap-2" data-testid="ops-league-chips">
                            {(crawl.supported_leagues || []).map((league) => {
                                const isCrawled = crawlIds.has(league.id)
                                return (
                                    <Badge
                                        key={league.id}
                                        variant="outline"
                                        className={
                                            isCrawled
                                                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                                                : 'bg-muted/40 text-muted-foreground'
                                        }
                                        title={`${league.region || ''} · league ${league.id}${isCrawled ? ' · crawled' : ' · metadata only'}`}
                                    >
                                        {league.name}
                                        {isCrawled && <CheckCircle2 className="h-3 w-3" />}
                                    </Badge>
                                )
                            })}
                            {!(crawl.supported_leagues || []).length && (
                                <p className="text-sm text-muted-foreground">No league data in overview.</p>
                            )}
                        </div>
                    )}

                    <div className="flex flex-wrap items-end gap-3 pt-2 border-t">
                        <Button
                            size="sm"
                            variant="outline"
                            disabled={syncLeaguesBusy}
                            onClick={() => setSyncLeaguesOpen(true)}
                            data-testid="ops-sync-leagues"
                        >
                            {syncLeaguesBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                            Sync leagues
                        </Button>

                        <div className="flex items-end gap-2">
                            <div className="space-y-1">
                                <Label className="text-xs">Season</Label>
                                <Select value={syncTeamsSeason} onValueChange={setSyncTeamsSeason}>
                                    <SelectTrigger className="w-28" data-testid="ops-sync-teams-season">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {SEASON_OPTIONS.map((season) => (
                                            <SelectItem key={season} value={String(season)}>
                                                {season}/{String(season + 1).slice(-2)}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <Button
                                size="sm"
                                variant="outline"
                                disabled={syncTeamsBusy}
                                onClick={() => setSyncTeamsOpen(true)}
                                data-testid="ops-sync-teams"
                            >
                                {syncTeamsBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                                Sync teams
                            </Button>
                        </div>
                    </div>

                    {syncLeaguesResult && <CounterChips data={syncLeaguesResult} testId="ops-sync-leagues-result" />}
                    {syncTeamsResult && <CounterChips data={syncTeamsResult} testId="ops-sync-teams-result" />}
                </CardContent>
            </Card>

            {/* 6 — Backfills & data tools */}
            <section className="space-y-4">
                <div className="flex items-center gap-2">
                    <Database className="h-5 w-5" />
                    <h3 className="text-xl font-semibold">Backfills & data tools</h3>
                </div>

                <BackfillCard
                    id="sync-all-fixtures"
                    title="Sync all player fixtures (background job)"
                    description="Batch-syncs fixture stats for ALL active tracked players, grouped by club to share API calls. Runs as a background job — progress is polled below."
                    quotaNote="Quota-heavy: one API call per finished fixture across every tracked player. There is no spend cap once started."
                    confirmWord="SYNC"
                    pollsJob
                    fields={[
                        { key: 'season', label: 'Season (optional)', type: 'number', placeholder: String(CURRENT_SEASON) },
                    ]}
                    run={(values, dryRun) => {
                        const season = Number.parseInt(values.season, 10)
                        return APIService.adminSyncAllPlayerFixtures({
                            dry_run: dryRun,
                            ...(Number.isFinite(season) ? { season } : {}),
                        })
                    }}
                />

                <BackfillCard
                    id="raw-json"
                    title="Backfill fixture raw JSON"
                    description="Fetches full fixture payloads for fixtures missing raw_json (enables team-name extraction for old fixtures). Optional player/team scope."
                    quotaNote="One API call per fixture, capped by the limit (max 200)."
                    confirmWord="APPLY"
                    fields={[
                        { key: 'limit', label: 'Limit (max 200)', type: 'number', defaultValue: '50' },
                        { key: 'team_api_id', label: 'Team API ID (optional)', type: 'number', placeholder: 'any' },
                        { key: 'player_id', label: 'Player API ID (optional)', type: 'number', placeholder: 'any' },
                    ]}
                    run={(values, dryRun) => {
                        const limit = Number.parseInt(values.limit, 10)
                        const teamApiId = Number.parseInt(values.team_api_id, 10)
                        const playerId = Number.parseInt(values.player_id, 10)
                        return APIService.adminBackfillRawJson({
                            dry_run: dryRun,
                            ...(Number.isFinite(limit) ? { limit } : {}),
                            ...(Number.isFinite(teamApiId) ? { team_api_id: teamApiId } : {}),
                            ...(Number.isFinite(playerId) ? { player_id: playerId } : {}),
                        })
                    }}
                />

                <BackfillCard
                    id="ages"
                    title="Backfill ages & birth dates"
                    description="Phase A copies birth dates from linked journeys (free); phase B fetches remaining gaps from API-Football. Optional parent-club scope."
                    quotaNote="Phase B spends quota: one API call per player still missing data, capped by the limit."
                    confirmWord="APPLY"
                    fields={[
                        { key: 'limit', label: 'API fetch limit', type: 'number', defaultValue: '500' },
                        { key: 'team_api_id', label: 'Team API ID (optional)', type: 'number', placeholder: 'any' },
                    ]}
                    run={(values, dryRun) => {
                        const limit = Number.parseInt(values.limit, 10)
                        const teamApiId = Number.parseInt(values.team_api_id, 10)
                        return APIService.adminBackfillAges({
                            dry_run: dryRun,
                            ...(Number.isFinite(limit) ? { limit } : {}),
                            ...(Number.isFinite(teamApiId) ? { team_api_id: teamApiId } : {}),
                        })
                    }}
                />

                <BackfillCard
                    id="formations"
                    title="Backfill formations"
                    description="Fills formation, grid, and formation position on existing fixture stats rows (one lineup fetch per fixture)."
                    quotaNote="One API call per fixture needing formation data, capped by the limit (max 1000)."
                    confirmWord="APPLY"
                    fields={[
                        { key: 'limit', label: 'Fixture limit', type: 'number', defaultValue: '200' },
                    ]}
                    run={(values, dryRun) => {
                        const limit = Number.parseInt(values.limit, 10)
                        return APIService.adminBackfillFormations({
                            dry_run: dryRun,
                            ...(Number.isFinite(limit) ? { limit } : {}),
                        })
                    }}
                />
            </section>

            {/* Gates */}
            <ConfirmGate
                open={forceFailOpen}
                onOpenChange={setForceFailOpen}
                title="Force-fail ALL running jobs"
                description="Marks every running or cancelled background job as failed. Only use this for jobs that are genuinely stuck — running jobs are killed mid-flight."
                confirmWord="FAIL"
                confirmLabel="Force-fail all"
                destructive
                onConfirm={forceFailAll}
            />
            <ConfirmGate
                open={syncLeaguesOpen}
                onOpenChange={setSyncLeaguesOpen}
                title="Sync leagues from API-Football"
                description="Refreshes metadata for every supported league. Quota note: roughly one or two API calls per league (cached). Safe but not free."
                confirmLabel="Sync leagues"
                onConfirm={syncLeagues}
            />
            <ConfirmGate
                open={syncTeamsOpen}
                onOpenChange={setSyncTeamsOpen}
                title={`Sync teams for ${syncTeamsSeason}`}
                description="Syncs all teams across every supported league for the chosen season. Quota note: one API call per league page — this is how new regions enter the platform."
                confirmLabel="Sync teams"
                onConfirm={syncTeams}
            />
        </div>
    )
}

export default AdminOperations
