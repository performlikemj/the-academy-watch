import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
    Download, Loader2, CheckCircle2, AlertCircle, X, RotateCcw,
    GraduationCap, Sprout, Play, ArrowRight, Newspaper, Settings2,
} from 'lucide-react'
import TeamSelect from '@/components/ui/TeamSelect'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect'
import { APIService } from '@/lib/api'
import { useBackgroundJobs } from '@/context/BackgroundJobsContext'
import { ConfirmGate } from '@/components/admin/ConfirmGate'
import { buildSeedTeamRequest } from './admin-newsletters-api.js'
import { seedSelectedButtonLabel } from './admin-newsletters-seeding.js'

// ============================================================
// Decision tree — when to use which seeding path
// ============================================================
const SEEDING_PATHS = [
    {
        title: 'Seed one team',
        anchor: '#seed-one-team',
        when: 'You just tracked a club and want its academy players discovered from journeys, squad data, and cohorts.',
        cost: 'Moderate API usage (squad fetch + journey syncs).',
    },
    {
        title: 'Seed all tracked',
        anchor: '#seed-all-tracked',
        when: 'Several tracked teams have zero players (e.g. after tracking a batch of clubs). Only seeds teams with no active players — never touches existing data.',
        cost: 'Background job; moderate API usage per empty team.',
    },
    {
        title: 'Cohort seeding',
        anchor: '#cohort-seeding',
        when: 'You want historical academy cohorts (team + league + season graduate groups) — the foundation for journey discovery.',
        cost: 'Big 6 run is a long background job.',
    },
    {
        title: 'Full rebuild',
        anchor: '#full-rebuild',
        when: 'Academy data is wrong beyond piecemeal repair. Nukes tracked players, journeys, cohorts, loans, and locations, then rebuilds from API-Football.',
        cost: 'DESTRUCTIVE. 2-4 hours, ~1500-2500 API calls.',
        destructive: true,
    },
]

function DecisionTreeHeader() {
    return (
        <Card data-testid="seeding-decision-tree">
            <CardHeader>
                <CardTitle>Which path do I need?</CardTitle>
                <CardDescription>
                    Four ways to populate academy data, from surgical to scorched-earth. Start at the top — the full rebuild is the last resort.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {SEEDING_PATHS.map((path, idx) => (
                        <a key={path.title} href={path.anchor} className="block h-full">
                            <div className={`border rounded-lg p-3 h-full space-y-1 hover:bg-accent transition-colors ${path.destructive ? 'border-rose-200 bg-rose-50/40' : ''}`}>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-mono text-muted-foreground">{idx + 1}</span>
                                    <span className="font-semibold text-sm">{path.title}</span>
                                    {path.destructive && <Badge className="bg-rose-100 text-rose-800 border-rose-200">destructive</Badge>}
                                </div>
                                <p className="text-xs text-muted-foreground">{path.when}</p>
                                <p className={`text-xs ${path.destructive ? 'text-rose-700 font-medium' : 'text-muted-foreground'}`}>{path.cost}</p>
                            </div>
                        </a>
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}

// ============================================================
// Shared: background job polling
// ============================================================
function useJobPolling(onFinished) {
    const [job, setJob] = useState(null)
    const timerRef = useRef(null)
    const onFinishedRef = useRef(onFinished)

    useEffect(() => {
        onFinishedRef.current = onFinished
    }, [onFinished])

    useEffect(() => () => {
        if (timerRef.current) clearInterval(timerRef.current)
    }, [])

    const start = useCallback((jobId) => {
        if (timerRef.current) clearInterval(timerRef.current)
        setJob(null)
        timerRef.current = setInterval(async () => {
            try {
                const j = await APIService.adminGetJobStatus(jobId)
                if (!j) return
                setJob(j)
                if (j.status === 'completed' || j.status === 'failed') {
                    clearInterval(timerRef.current)
                    timerRef.current = null
                    onFinishedRef.current?.(j)
                }
            } catch (err) {
                console.error('Failed to poll job status:', err)
            }
        }, 3000)
    }, [])

    return { job, start }
}

function JobProgressBar({ job }) {
    if (!job) return null
    const pct = job.total > 0 ? Math.round(((job.progress || 0) / job.total) * 100) : 0
    return (
        <div className="space-y-2" data-testid="seeding-job-progress">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{job.current_item || 'Processing...'}</span>
                <span>{job.progress || 0} / {job.total || 0}</span>
            </div>
            <div className="w-full bg-muted rounded-full h-2.5">
                <div
                    className="bg-primary h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    )
}

// ============================================================
// Section 1: Per-team seed (ported from AdminPlayers Seed tab)
// ============================================================
function PerTeamSeedCard({ teams, setMessage }) {
    const [selectedTeam, setSelectedTeam] = useState('')
    const [maxAge, setMaxAge] = useState('23')
    const [seeding, setSeeding] = useState(false)
    const [seedResult, setSeedResult] = useState(null)

    const handleSeed = async () => {
        if (!selectedTeam) {
            setMessage({ type: 'error', text: 'Select a team first' })
            return
        }
        setSeeding(true)
        setSeedResult(null)
        try {
            const payload = { team_id: Number(selectedTeam) }
            if (maxAge) payload.max_age = parseInt(maxAge)
            const result = await APIService.adminSeedTeamPlayers(payload)
            setSeedResult(result)
            setMessage({ type: 'success', text: `Seeded ${result.created || 0} players for ${result.team_name}` })
        } catch (error) {
            setMessage({ type: 'error', text: `Seed failed: ${error?.body?.error || error.message}` })
        } finally {
            setSeeding(false)
        }
    }

    const trackedTeams = teams.filter((t) => t.is_tracked)

    return (
        <Card id="seed-one-team">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Download className="h-5 w-5" />
                    Seed One Team
                </CardTitle>
                <CardDescription>
                    Identify academy products for a team using journey data, squad analysis, and cohort records.
                    Only players confirmed as academy products of this club will be added. Additive — never removes data.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div data-testid="seed-team-select">
                        <Label>Select Team</Label>
                        <TeamSelect
                            teams={trackedTeams.length > 0 ? trackedTeams : teams}
                            value={selectedTeam}
                            onChange={setSelectedTeam}
                            placeholder="Select a tracked team..."
                        />
                        {trackedTeams.length === 0 && teams.length > 0 && (
                            <p className="text-xs text-muted-foreground mt-1">No tracked teams found. Showing all teams.</p>
                        )}
                    </div>
                    <div>
                        <Label>Max Age</Label>
                        <Input
                            type="number"
                            value={maxAge}
                            onChange={(e) => setMaxAge(e.target.value)}
                            placeholder="23"
                            className="w-24"
                            data-testid="seed-team-max-age"
                        />
                        <p className="text-xs text-muted-foreground mt-1">Only sync journeys for squad players at or below this age</p>
                    </div>
                </div>
                <Button onClick={handleSeed} disabled={seeding || !selectedTeam} data-testid="seed-team-run">
                    {seeding ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Download className="h-4 w-4 mr-2" />}
                    Discover Academy Players
                </Button>

                {seedResult && (
                    <div className={`mt-4 p-4 rounded-md border text-sm space-y-1 ${seedResult.created > 0 ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`} data-testid="seed-team-result">
                        <div className="flex items-center gap-2 font-medium">
                            <CheckCircle2 className={`h-4 w-4 ${seedResult.created > 0 ? 'text-emerald-600' : 'text-amber-600'}`} />
                            Seed Complete — {seedResult.team_name}
                        </div>
                        <div className="text-muted-foreground space-y-0.5">
                            <div>Created: {seedResult.created || 0} • Skipped (already tracked): {seedResult.skipped || 0}</div>
                            <div>Academy players identified: {seedResult.candidates_found || 0} • Squad checked: {seedResult.squad_size || 0}</div>
                            {seedResult.journeys_synced > 0 && (
                                <div>Journeys synced: {seedResult.journeys_synced} • Not academy: {seedResult.not_academy || 0}</div>
                            )}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

// ============================================================
// Section 2: Seed all tracked (ported from AdminTeams)
// ============================================================
function SeedAllTrackedCard({ setMessage }) {
    const [seeding, setSeeding] = useState(false)
    const [startInfo, setStartInfo] = useState(null)

    const { job, start } = useJobPolling(useCallback((finished) => {
        setSeeding(false)
        if (finished.status === 'completed') {
            setMessage({ type: 'success', text: 'Seed-all-tracked job completed.' })
        } else {
            setMessage({ type: 'error', text: `Seed-all-tracked failed: ${finished.error || 'Unknown error'}` })
        }
    }, [setMessage]))

    const handleSeedAll = async () => {
        setSeeding(true)
        setStartInfo(null)
        setMessage(null)
        try {
            const res = await APIService.adminSeedAllTrackedPlayers()
            if (res.empty_teams === 0) {
                setMessage({ type: 'success', text: 'All tracked teams already have players seeded.' })
                setSeeding(false)
                return
            }
            setStartInfo(res)
            if (res.job_id) {
                start(res.job_id)
            } else {
                setSeeding(false)
            }
        } catch (err) {
            setMessage({ type: 'error', text: `Seed failed: ${err.message}` })
            setSeeding(false)
        }
    }

    return (
        <Card id="seed-all-tracked">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Sprout className="h-5 w-5" />
                    Seed All Tracked Teams
                </CardTitle>
                <CardDescription>
                    Backfill: finds every tracked team with zero active players and seeds each one in a single background job.
                    Teams that already have players are left untouched.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <Button onClick={handleSeedAll} disabled={seeding} data-testid="seed-all-run">
                    {seeding ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Sprout className="h-4 w-4 mr-2" />}
                    {seeding ? 'Seeding unseeded teams...' : 'Seed Unseeded Teams'}
                </Button>

                {startInfo && (
                    <p className="text-sm text-muted-foreground" data-testid="seed-all-start-info">
                        Seeding {startInfo.teams_to_seed} of {startInfo.tracked_teams} tracked team(s)
                        {Array.isArray(startInfo.team_names) && startInfo.team_names.length > 0 && (
                            <>: {startInfo.team_names.join(', ')}</>
                        )}
                    </p>
                )}

                {seeding && <JobProgressBar job={job} />}
            </CardContent>
        </Card>
    )
}

// ============================================================
// Section 3: Cohorts quick links (thin wrapper over AdminCohorts APIs)
// ============================================================
function CohortsCard({ setMessage }) {
    const [big6Loading, setBig6Loading] = useState(false)

    const { job, start } = useJobPolling(useCallback((finished) => {
        setBig6Loading(false)
        if (finished.status === 'completed') {
            setMessage({ type: 'success', text: 'Big 6 cohort seeding completed successfully' })
        } else {
            setMessage({ type: 'error', text: `Big 6 seeding failed: ${finished.error || 'Unknown error'}` })
        }
    }, [setMessage]))

    const handleSeedBig6 = async () => {
        setBig6Loading(true)
        setMessage(null)
        try {
            const result = await APIService.adminSeedBig6()
            if (!result.job_id) {
                setMessage({ type: 'success', text: 'Big 6 seeding completed' })
                setBig6Loading(false)
                return
            }
            start(result.job_id)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to start Big 6 seeding' })
            setBig6Loading(false)
        }
    }

    return (
        <Card id="cohort-seeding">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <GraduationCap className="h-5 w-5" />
                    Cohort Seeding
                </CardTitle>
                <CardDescription>
                    Academy cohorts are team + league + season graduate groups — the raw material journey discovery feeds on.
                    Long background job; uses API quota per cohort.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                    <Button onClick={handleSeedBig6} disabled={big6Loading} data-testid="seed-big6-run">
                        {big6Loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
                        Seed Big 6 Cohorts
                    </Button>
                    <Button variant="outline" asChild data-testid="seed-cohorts-link">
                        <Link to="/admin/cohorts">
                            Single cohort & cohort management
                            <ArrowRight className="h-4 w-4 ml-2" />
                        </Link>
                    </Button>
                </div>

                {big6Loading && <JobProgressBar job={job} />}
            </CardContent>
        </Card>
    )
}

// ============================================================
// Section 4: Newsletter loan-data seeding
// (reuses admin-newsletters-seeding.js + admin-newsletters-api.js)
// ============================================================
function LoanDataSeedingCard({ teams, setMessage }) {
    const [season, setSeason] = useState(new Date().getFullYear().toString())
    const [selectedTeamIds, setSelectedTeamIds] = useState([])
    const [seeding, setSeeding] = useState(false)
    const [results, setResults] = useState(null)

    const trackedTeams = teams.filter((t) => t.is_tracked)

    const handleSeedSelected = async () => {
        if (selectedTeamIds.length === 0) {
            setMessage({ type: 'error', text: 'Please select teams to seed' })
            return
        }
        const numericSeason = parseInt(season, 10)
        if (!Number.isFinite(numericSeason)) {
            setMessage({ type: 'error', text: 'Please enter a valid season year before seeding' })
            return
        }

        setSeeding(true)
        setResults(null)
        try {
            const settled = await Promise.allSettled(selectedTeamIds.map(async (teamId) => {
                const req = buildSeedTeamRequest({ teamId, season: numericSeason })
                // The current seed endpoint expects `team_id` (db id); the legacy
                // builder still emits `team_db_id` — remap so the request succeeds.
                const body = JSON.parse(req.options.body)
                if (body.team_db_id != null && body.team_id == null) {
                    body.team_id = body.team_db_id
                    delete body.team_db_id
                }
                return APIService.request(
                    req.endpoint,
                    { ...req.options, body: JSON.stringify(body) },
                    { admin: req.admin }
                )
            }))

            const successes = settled.filter((r) => r.status === 'fulfilled')
            const failures = settled.filter((r) => r.status === 'rejected')
            const created = successes.reduce((sum, r) => sum + (r.value?.created || 0), 0)
            const skipped = successes.reduce((sum, r) => sum + (r.value?.skipped || 0), 0)
            setResults({ teams: successes.length, created, skipped, failures: failures.length })

            if (failures.length > 0) {
                const detail = failures.map((f) => f.reason?.message || 'unknown error').slice(0, 3).join('; ')
                setMessage({ type: 'error', text: `Seeding completed with ${failures.length} failure(s): ${detail}` })
            } else {
                setMessage({ type: 'success', text: `Seeded ${successes.length} team(s) for ${numericSeason}` })
            }
        } catch (error) {
            setMessage({ type: 'error', text: `Seeding failed: ${error.message}` })
        } finally {
            setSeeding(false)
        }
    }

    return (
        <Card id="loan-data-seeding">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Newspaper className="h-5 w-5" />
                    Newsletter Loan-Data Seeding
                </CardTitle>
                <CardDescription>
                    Populate loan data for specific teams before generating newsletters. Runs the same academy
                    discovery as Seed One Team, scoped to the season below. This endpoint has no dry-run.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <Label htmlFor="loan-seed-season">Season Year</Label>
                        <Input
                            id="loan-seed-season"
                            type="number"
                            value={season}
                            onChange={(e) => setSeason(e.target.value)}
                            placeholder="2025"
                            data-testid="loan-seed-season"
                        />
                    </div>
                    <div data-testid="loan-seed-teams">
                        <Label>Teams</Label>
                        <TeamMultiSelect
                            teams={trackedTeams.length > 0 ? trackedTeams : teams}
                            value={selectedTeamIds}
                            onChange={setSelectedTeamIds}
                            placeholder="Select teams to seed..."
                        />
                    </div>
                </div>
                <Button onClick={handleSeedSelected} disabled={seeding || selectedTeamIds.length === 0} data-testid="loan-seed-run">
                    {seeding && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    {seedSelectedButtonLabel({ isSeeding: seeding, selectionCount: selectedTeamIds.length })}
                </Button>

                {results && (
                    <div className="p-4 rounded-md border bg-muted/30 text-sm text-muted-foreground" data-testid="loan-seed-result">
                        Seeded {results.teams} team(s) — created {results.created}, skipped {results.skipped} already tracked
                        {results.failures > 0 && <span className="text-rose-700"> • {results.failures} failed</span>}
                    </div>
                )}

                <p className="text-xs text-muted-foreground">
                    Top-5 league bulk seeding was removed with the legacy loans endpoints — use Seed All Tracked Teams above to backfill every tracked club.
                </p>
            </CardContent>
        </Card>
    )
}

// ============================================================
// Section 5: Full Rebuild (ported from AdminDashboard, + config select)
// ============================================================
function FullRebuildCard({ setMessage }) {
    const { isBlocking, refresh: refreshJobs } = useBackgroundJobs()

    // Config selection (same API calls as AdminTools)
    const [configs, setConfigs] = useState([])
    const [configsLoading, setConfigsLoading] = useState(true)
    const [selectedConfigId, setSelectedConfigId] = useState(null)
    const [configDetail, setConfigDetail] = useState(null)

    // Rebuild job state
    const [rebuildJobId, setRebuildJobId] = useState(null)
    const [rebuildMessage, setRebuildMessage] = useState(null)
    const [confirmVariant, setConfirmVariant] = useState(null) // 'nuke' | 'keep' | null
    const wasBlockingRef = useRef(false)

    const rebuildRunning = isBlocking

    useEffect(() => {
        let cancelled = false
        const loadConfigs = async () => {
            try {
                const data = await APIService.request('/admin/rebuild-configs', {}, { admin: true })
                if (cancelled) return
                const list = data || []
                setConfigs(list)
                const active = list.find((c) => c.is_active)
                if (active) setSelectedConfigId(active.id)
            } catch (e) {
                if (!cancelled) setMessage({ type: 'error', text: `Failed to load rebuild configs: ${e.message}` })
            } finally {
                if (!cancelled) setConfigsLoading(false)
            }
        }
        loadConfigs()
        return () => { cancelled = true }
    }, [setMessage])

    useEffect(() => {
        if (!selectedConfigId) return
        let cancelled = false
        const loadDetail = async () => {
            try {
                const data = await APIService.request(`/admin/rebuild-configs/${selectedConfigId}`, {}, { admin: true })
                if (!cancelled) setConfigDetail(data)
            } catch (err) {
                console.error('Failed to load rebuild config detail:', err)
            }
        }
        loadDetail()
        return () => { cancelled = true }
    }, [selectedConfigId])

    // Detect when a rebuild completes and fetch final results
    useEffect(() => {
        if (isBlocking) {
            wasBlockingRef.current = true
            return
        }
        if (!wasBlockingRef.current || !rebuildJobId) return
        wasBlockingRef.current = false

        APIService.adminGetJobStatus(rebuildJobId).then((job) => {
            setRebuildJobId(null)
            if (!job) return
            if (job.status === 'completed') {
                const r = job.results || {}
                setRebuildMessage({
                    type: 'success',
                    text: `Rebuild complete! Created ${r.total_created || 0} tracked players, synced ${r.players_synced || 0} journeys, linked ${r.journeys_linked || 0} orphans.`,
                })
            } else if (job.status === 'failed') {
                setRebuildMessage({
                    type: 'error',
                    text: `Rebuild failed: ${job.error || 'Unknown error'}`,
                })
            }
        }).catch(() => {
            setRebuildJobId(null)
        })
    }, [isBlocking, rebuildJobId])

    const handleRebuild = async () => {
        const skipClean = confirmVariant === 'keep'
        setConfirmVariant(null)
        setRebuildMessage(null)

        try {
            const payload = { skip_clean: skipClean }
            // Pass the selected config explicitly — the endpoint accepts config_id
            // (falls back to the active config server-side when omitted).
            if (selectedConfigId) payload.config_id = selectedConfigId
            const res = await APIService.adminFullRebuild(payload)
            if (res.job_id) {
                setRebuildJobId(res.job_id)
                refreshJobs()
            }
        } catch (error) {
            console.error('Failed to start rebuild:', error)
            setRebuildMessage({ type: 'error', text: `Failed to start: ${error.message || 'Unknown error'}` })
        }
    }

    const selectedConfig = configs.find((c) => c.id === selectedConfigId)
    // Only trust the detail when it matches the current selection (avoids
    // showing a stale summary while the next config detail loads).
    const detail = configDetail && configDetail.id === selectedConfigId ? configDetail : null
    const cfg = detail?.config || {}
    const teamCount = cfg.team_ids ? Object.keys(cfg.team_ids).length : 0
    const seasons = Array.isArray(cfg.seasons) ? cfg.seasons : []
    const leagueIds = Array.isArray(cfg.league_ids) ? cfg.league_ids : []

    return (
        <Card id="full-rebuild" className="border-rose-200 bg-rose-50/30">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <RotateCcw className="h-5 w-5" />
                    Full Academy Rebuild
                </CardTitle>
                <CardDescription>
                    Last resort. Deletes all tracked players, journeys, cohorts, loans, and locations, then rebuilds
                    everything from API-Football. Takes 2-4 hours and ~1500-2500 API calls. Teams, users, newsletters,
                    and fixtures are preserved.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Config selection */}
                <div className="space-y-2">
                    <Label>Rebuild Configuration</Label>
                    {configsLoading ? (
                        <Skeleton className="h-9 w-full max-w-md" />
                    ) : configs.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                            No saved rebuild configs — the rebuild will use built-in defaults (Big 6).
                            Create one in{' '}
                            <Link to="/admin/tools" className="underline">API &amp; Configs</Link>.
                        </p>
                    ) : (
                        <div className="flex flex-wrap items-center gap-2">
                            <Select
                                value={selectedConfigId ? String(selectedConfigId) : undefined}
                                onValueChange={(v) => setSelectedConfigId(Number(v))}
                                disabled={rebuildRunning}
                            >
                                <SelectTrigger className="w-full max-w-md" data-testid="rebuild-config-select">
                                    <SelectValue placeholder="Select a rebuild config..." />
                                </SelectTrigger>
                                <SelectContent>
                                    {configs.map((c) => (
                                        <SelectItem key={c.id} value={String(c.id)}>
                                            {c.name}{c.is_active ? ' (active)' : ''}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <Button variant="outline" size="sm" asChild data-testid="rebuild-config-edit-link">
                                <Link to="/admin/tools">
                                    <Settings2 className="h-4 w-4 mr-1" />
                                    Edit configs
                                </Link>
                            </Button>
                        </div>
                    )}

                    {selectedConfig && (
                        <div className="text-xs text-muted-foreground space-y-0.5" data-testid="rebuild-config-summary">
                            <div>
                                Selected: <span className="font-medium text-foreground">{selectedConfig.name}</span>
                                {selectedConfig.is_active && <Badge className="ml-2 bg-emerald-50 text-emerald-800 border-emerald-200">active</Badge>}
                                <span className="ml-2">— passed explicitly to the job as config_id</span>
                            </div>
                            {detail && (
                                <div>
                                    {teamCount} team(s)
                                    {seasons.length > 0 && <> • seasons {seasons.join(', ')}</>}
                                    {leagueIds.length > 0 && <> • {leagueIds.length} league(s) expanded to all active teams</>}
                                    {cfg.rate_limit_per_day != null && <> • {cfg.rate_limit_per_day} calls/day cap</>}
                                </div>
                            )}
                            {selectedConfig.notes && <div className="italic">{selectedConfig.notes}</div>}
                        </div>
                    )}
                </div>

                {/* Variant launchers */}
                {!rebuildRunning && (
                    <div className="flex flex-wrap gap-2">
                        <Button
                            variant="destructive"
                            onClick={() => setConfirmVariant('nuke')}
                            data-testid="rebuild-variant-nuke"
                        >
                            <RotateCcw className="h-4 w-4 mr-2" />
                            Nuke and rebuild (destructive)
                        </Button>
                        <Button
                            variant="outline"
                            onClick={() => setConfirmVariant('keep')}
                            data-testid="rebuild-variant-keep"
                        >
                            Rebuild keeping existing data
                        </Button>
                    </div>
                )}

                {rebuildRunning && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="rebuild-running">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Rebuild in progress — see overlay for details</span>
                    </div>
                )}

                {rebuildMessage && (
                    <Alert className={rebuildMessage.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'} data-testid="rebuild-message">
                        {rebuildMessage.type === 'error'
                            ? <AlertCircle className="h-4 w-4 text-rose-600" />
                            : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                        <AlertDescription className={rebuildMessage.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                            {rebuildMessage.text}
                        </AlertDescription>
                    </Alert>
                )}

                <ConfirmGate
                    open={confirmVariant !== null}
                    onOpenChange={(open) => { if (!open) setConfirmVariant(null) }}
                    title={confirmVariant === 'keep' ? 'Run Rebuild (keep existing data)' : 'Run Full Rebuild'}
                    description={confirmVariant === 'keep'
                        ? `Re-runs the rebuild pipeline WITHOUT the clean-slate step — existing tracked players, journeys, and cohorts are kept and topped up. Config: ${selectedConfig ? selectedConfig.name : 'built-in defaults'}. Takes 2-4 hours, ~1500-2500 API calls.`
                        : `This DELETES all tracked players, journeys, cohorts, loans, and locations, then rebuilds from API-Football. Config: ${selectedConfig ? selectedConfig.name : 'built-in defaults'}. Takes 2-4 hours, ~1500-2500 API calls. Teams, users, newsletters, and fixtures are preserved.`}
                    confirmWord="REBUILD"
                    confirmLabel="Run it"
                    destructive={confirmVariant !== 'keep'}
                    onConfirm={handleRebuild}
                />
            </CardContent>
        </Card>
    )
}

// ============================================================
// Page
// ============================================================
export function AdminSeeding() {
    const [teams, setTeams] = useState([])
    const [message, setMessage] = useState(null)

    useEffect(() => {
        let cancelled = false
        const loadTeams = async () => {
            try {
                const data = await APIService.getTeams()
                if (!cancelled) setTeams(Array.isArray(data) ? data : [])
            } catch (error) {
                console.error('Failed to load teams', error)
            }
        }
        loadTeams()
        return () => { cancelled = true }
    }, [])

    return (
        <div className="space-y-6">
            <header>
                <h2 className="text-3xl font-bold tracking-tight">Seeding &amp; Rebuild</h2>
                <p className="text-muted-foreground mt-1">
                    Every way to populate academy data — from seeding a single team to the full nuclear rebuild
                </p>
            </header>

            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'} data-testid="seeding-message">
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                        <Button variant="ghost" size="sm" className="ml-2 h-6 px-2" onClick={() => setMessage(null)} data-testid="seeding-message-dismiss">
                            <X className="h-3 w-3" />
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            <DecisionTreeHeader />
            <PerTeamSeedCard teams={teams} setMessage={setMessage} />
            <SeedAllTrackedCard setMessage={setMessage} />
            <CohortsCard setMessage={setMessage} />
            <LoanDataSeedingCard teams={teams} setMessage={setMessage} />
            <FullRebuildCard setMessage={setMessage} />
        </div>
    )
}
