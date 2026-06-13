import { useState, useEffect, useCallback, useRef } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
    Search, Loader2, AlertCircle, ArrowRight,
    ChevronDown, ChevronRight, User,
} from 'lucide-react'
import {
    buildSelectUpdates,
    mergeCollapseState,
    toggleCollapseState,
    sandboxCardHeaderClasses,
    sofascoreRowKey,
    buildSofascoreUpdatePayload,
} from '@/lib/admin-sandbox.js'
import { STATUS_BADGE_CLASSES } from '../../lib/theme-constants'

const RESULT_COLORS = {
    match: 'bg-emerald-50 text-emerald-700 border-emerald-300',
    pass: 'bg-secondary text-muted-foreground border-border',
}

function StatusBadge({ status }) {
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE_CLASSES[status] || 'bg-secondary text-muted-foreground'}`}>
            {status}
        </span>
    )
}

function ClassifierTester() {
    // Search state
    const [searchQuery, setSearchQuery] = useState('')
    const [searchResults, setSearchResults] = useState([])
    const [searching, setSearching] = useState(false)
    const [showResults, setShowResults] = useState(false)
    const searchRef = useRef(null)
    const debounceRef = useRef(null)

    // Tracked player picker
    const [trackedPlayers, setTrackedPlayers] = useState([])
    const [trackedTeamFilter, setTrackedTeamFilter] = useState('')

    // Selected player
    const [selectedPlayer, setSelectedPlayer] = useState(null)
    const [parentOverride, setParentOverride] = useState('')
    const [forceSync, setForceSync] = useState(false)

    // Results
    const [classifying, setClassifying] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)
    const [expandedClassification, setExpandedClassification] = useState(null)

    // Load tracked players for picker
    useEffect(() => {
        APIService.request('/admin/tracked-players?per_page=500', {}, { admin: true })
            .then((data) => setTrackedPlayers(data?.items || []))
            .catch(() => {})
    }, [])

    // Debounced API search
    const handleSearch = useCallback((query) => {
        setSearchQuery(query)
        if (debounceRef.current) clearTimeout(debounceRef.current)
        if (!query || query.length < 2) {
            setSearchResults([])
            setShowResults(false)
            return
        }
        debounceRef.current = setTimeout(async () => {
            setSearching(true)
            try {
                const data = await APIService.request(
                    `/admin/players/search-api?q=${encodeURIComponent(query)}`,
                    {},
                    { admin: true }
                )
                setSearchResults(data?.results || [])
                setShowResults(true)
            } catch {
                setSearchResults([])
            } finally {
                setSearching(false)
            }
        }, 400)
    }, [])

    const selectPlayer = (player) => {
        setSelectedPlayer(player)
        setShowResults(false)
        setSearchQuery(player.name || '')
        setResult(null)
        setError(null)
    }

    const selectTrackedPlayer = (tp) => {
        setSelectedPlayer({
            id: tp.player_api_id,
            name: tp.player_name,
            photo: tp.photo_url,
            team: tp.current_club_name || (tp.team?.name),
        })
        setSearchQuery(tp.player_name || '')
        setResult(null)
        setError(null)
    }

    const runClassification = async () => {
        if (!selectedPlayer?.id) return
        setClassifying(true)
        setError(null)
        setResult(null)
        try {
            const body = {
                player_api_id: selectedPlayer.id,
                force_sync: forceSync,
            }
            if (parentOverride) body.parent_api_id = parseInt(parentOverride)
            const data = await APIService.request('/admin/players/test-classify', {
                method: 'POST',
                body: JSON.stringify(body),
            }, { admin: true })
            setResult(data)
            if (data.classifications?.length > 0) {
                setExpandedClassification(0)
            }
        } catch (e) {
            setError(e.message || 'Classification failed')
        } finally {
            setClassifying(false)
        }
    }

    // Close search dropdown on outside click
    useEffect(() => {
        const handler = (e) => {
            if (searchRef.current && !searchRef.current.contains(e.target)) {
                setShowResults(false)
            }
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    // Unique teams from tracked players
    const trackedTeams = [...new Map(
        trackedPlayers
            .filter((tp) => tp.team?.name)
            .map((tp) => [tp.team?.id, tp.team])
    ).values()].sort((a, b) => (a.name || '').localeCompare(b.name || ''))

    const filteredTracked = trackedTeamFilter
        ? trackedPlayers.filter((tp) => tp.team?.id === parseInt(trackedTeamFilter))
        : trackedPlayers

    return (
        <div className="space-y-6">
            {/* Player Selection */}
            <Card>
                <CardHeader>
                    <CardTitle>Select Player</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* API Search */}
                    <div ref={searchRef} className="relative">
                        <Label className="text-sm font-medium">Search API-Football</Label>
                        <div className="relative mt-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70" />
                            <Input
                                value={searchQuery}
                                onChange={(e) => handleSearch(e.target.value)}
                                placeholder="Search by player name..."
                                className="pl-9"
                            />
                            {searching && (
                                <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground/70" />
                            )}
                        </div>
                        {showResults && searchResults.length > 0 && (
                            <div className="absolute z-10 w-full mt-1 bg-card border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                                {searchResults.map((p) => (
                                    <button
                                        key={p.id}
                                        className="flex items-center gap-3 w-full px-3 py-2 hover:bg-secondary text-left"
                                        onClick={() => selectPlayer(p)}
                                    >
                                        {p.photo ? (
                                            <img src={p.photo} alt="" className="h-8 w-8 rounded-full object-cover" />
                                        ) : (
                                            <User className="h-8 w-8 p-1.5 rounded-full bg-secondary text-muted-foreground/70" />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <div className="text-sm font-medium truncate">{p.name}</div>
                                            <div className="text-xs text-muted-foreground">{p.team} | {p.nationality} | ID: {p.id}</div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Tracked Player Picker */}
                    <div className="border-t pt-4">
                        <Label className="text-sm font-medium">Or select from tracked players</Label>
                        <div className="flex gap-2 mt-1">
                            <select
                                value={trackedTeamFilter}
                                onChange={(e) => setTrackedTeamFilter(e.target.value)}
                                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                            >
                                <option value="">All teams</option>
                                {trackedTeams.map((t) => (
                                    <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                            </select>
                            <select
                                value=""
                                onChange={(e) => {
                                    const tp = trackedPlayers.find((p) => p.id === parseInt(e.target.value))
                                    if (tp) selectTrackedPlayer(tp)
                                }}
                                className="h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm"
                            >
                                <option value="">Choose player...</option>
                                {filteredTracked.map((tp) => (
                                    <option key={tp.id} value={tp.id}>
                                        {tp.player_name} ({tp.status}) — {tp.team?.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* Selected Player + Options */}
                    {selectedPlayer && (
                        <div className="border-t pt-4 space-y-3">
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
                                {selectedPlayer.photo ? (
                                    <img src={selectedPlayer.photo} alt="" className="h-10 w-10 rounded-full object-cover" />
                                ) : (
                                    <User className="h-10 w-10 p-2 rounded-full bg-primary/10 text-primary" />
                                )}
                                <div>
                                    <div className="font-medium">{selectedPlayer.name}</div>
                                    <div className="text-xs text-muted-foreground">
                                        API ID: {selectedPlayer.id}
                                        {selectedPlayer.team && ` | ${selectedPlayer.team}`}
                                    </div>
                                </div>
                            </div>

                            <div className="flex flex-wrap items-end gap-4">
                                <div className="space-y-1">
                                    <Label className="text-xs">Parent Club Override (optional)</Label>
                                    <Input
                                        value={parentOverride}
                                        onChange={(e) => setParentOverride(e.target.value)}
                                        placeholder="API team ID e.g. 33"
                                        className="w-48"
                                    />
                                </div>
                                <label className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={forceSync}
                                        onChange={(e) => setForceSync(e.target.checked)}
                                        className="rounded border-border"
                                    />
                                    Re-fetch from API
                                </label>
                                <Button onClick={runClassification} disabled={classifying}>
                                    {classifying ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Classifying...
                                        </>
                                    ) : (
                                        'Run Classification'
                                    )}
                                </Button>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {error && (
                <Alert className="border-rose-500 bg-rose-50">
                    <AlertCircle className="h-4 w-4 text-rose-600" />
                    <AlertDescription className="text-rose-800">{error}</AlertDescription>
                </Alert>
            )}

            {/* Results */}
            {result && (
                <>
                    {/* Player Info */}
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-4">
                                {result.player.photo ? (
                                    <img src={result.player.photo} alt="" className="h-16 w-16 rounded-full object-cover" />
                                ) : (
                                    <User className="h-16 w-16 p-4 rounded-full bg-secondary text-muted-foreground/70" />
                                )}
                                <div>
                                    <h3 className="text-xl font-bold">{result.player.name}</h3>
                                    <div className="text-sm text-muted-foreground">
                                        {result.player.nationality}
                                        {result.player.birth_date && ` | Born: ${result.player.birth_date}`}
                                    </div>
                                    <div className="text-sm text-muted-foreground mt-0.5">
                                        Current: <span className="font-medium">{result.journey.current_club || 'Unknown'}</span>
                                        {result.journey.current_level && (
                                            <span className="text-xs ml-1 text-muted-foreground">({result.journey.current_level})</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Existing Tracked Status Diff */}
                    {result.existing_tracked?.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Tracked Player Status</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {result.existing_tracked.map((et, i) => (
                                        <div key={i} className="flex items-center gap-3 text-sm">
                                            <span className="text-muted-foreground">{et.parent_club_name}:</span>
                                            <StatusBadge status={et.current_status} />
                                            {et.would_change ? (
                                                <>
                                                    <ArrowRight className="h-4 w-4 text-orange-500" />
                                                    <StatusBadge status={et.new_status} />
                                                    <span className="text-xs text-orange-600 font-medium">CHANGED</span>
                                                </>
                                            ) : (
                                                <span className="text-xs text-emerald-600">no change</span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Classifications */}
                    {result.classifications?.map((cls, idx) => (
                        <Card key={idx}>
                            <CardHeader
                                className="cursor-pointer"
                                onClick={() => setExpandedClassification(expandedClassification === idx ? null : idx)}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <CardTitle className="text-base">
                                            Classification: {cls.parent_club_name}
                                        </CardTitle>
                                        <StatusBadge status={cls.status} />
                                        {cls.current_club_name && (
                                            <span className="text-sm text-muted-foreground">
                                                at {cls.current_club_name}
                                            </span>
                                        )}
                                    </div>
                                    {expandedClassification === idx
                                        ? <ChevronDown className="h-4 w-4 text-muted-foreground/70" />
                                        : <ChevronRight className="h-4 w-4 text-muted-foreground/70" />}
                                </div>
                            </CardHeader>
                            {expandedClassification === idx && (
                                <CardContent>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="border-b text-left">
                                                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Step</th>
                                                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Rule</th>
                                                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Check</th>
                                                    <th className="pb-2 pr-4 font-medium text-muted-foreground">Result</th>
                                                    <th className="pb-2 font-medium text-muted-foreground">Detail</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {cls.reasoning.map((r, ri) => (
                                                    <tr key={ri} className="border-b last:border-0">
                                                        <td className="py-2 pr-4 text-muted-foreground/70">{ri + 1}</td>
                                                        <td className="py-2 pr-4 font-mono text-xs">{r.rule}</td>
                                                        <td className="py-2 pr-4 text-muted-foreground text-xs max-w-[200px] truncate" title={r.check}>{r.check}</td>
                                                        <td className="py-2 pr-4">
                                                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${RESULT_COLORS[r.result] || ''}`}>
                                                                {r.result}
                                                            </span>
                                                        </td>
                                                        <td className="py-2 text-foreground/80 text-xs">{r.detail}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </CardContent>
                            )}
                        </Card>
                    ))}

                    {/* Journey Timeline */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">
                                Journey ({result.journey.entries?.length || 0} entries, {result.journey.total_clubs} clubs)
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b text-left">
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground">Season</th>
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground">Club</th>
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground">League</th>
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground">Level</th>
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground">Type</th>
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground text-right">Apps</th>
                                            <th className="pb-2 pr-3 font-medium text-muted-foreground text-right">Goals</th>
                                            <th className="pb-2 font-medium text-muted-foreground text-right">Mins</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(result.journey.entries || []).map((e, i) => (
                                            <tr key={i} className="border-b last:border-0">
                                                <td className="py-1.5 pr-3 font-mono text-xs">{e.season}</td>
                                                <td className="py-1.5 pr-3">
                                                    <div className="flex items-center gap-2">
                                                        {e.club_logo && <img src={e.club_logo} alt="" className="h-4 w-4" />}
                                                        <span className="truncate max-w-[150px]">{e.club_name}</span>
                                                    </div>
                                                </td>
                                                <td className="py-1.5 pr-3 text-muted-foreground text-xs truncate max-w-[120px]">{e.league_name}</td>
                                                <td className="py-1.5 pr-3">
                                                    <span className={`text-xs ${e.is_youth ? 'text-primary' : e.is_international ? 'text-purple-600' : 'text-emerald-700'}`}>
                                                        {e.level}
                                                    </span>
                                                </td>
                                                <td className="py-1.5 pr-3 text-xs text-muted-foreground">{e.entry_type}</td>
                                                <td className="py-1.5 pr-3 text-right font-mono text-xs">{e.appearances || 0}</td>
                                                <td className="py-1.5 pr-3 text-right font-mono text-xs">{e.goals || 0}</td>
                                                <td className="py-1.5 text-right font-mono text-xs">{e.minutes || 0}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Transfer History */}
                    {result.transfer_summary?.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Transfer History</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="border-b text-left">
                                                <th className="pb-2 pr-4 font-medium text-muted-foreground">Date</th>
                                                <th className="pb-2 pr-4 font-medium text-muted-foreground">From</th>
                                                <th className="pb-2 pr-4 font-medium text-muted-foreground">To</th>
                                                <th className="pb-2 font-medium text-muted-foreground">Type</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {result.transfer_summary.map((t, i) => (
                                                <tr key={i} className="border-b last:border-0">
                                                    <td className="py-1.5 pr-4 font-mono text-xs">{t.date || '—'}</td>
                                                    <td className="py-1.5 pr-4">{t.from || '—'}</td>
                                                    <td className="py-1.5 pr-4">{t.to || '—'}</td>
                                                    <td className="py-1.5 text-xs text-muted-foreground">{t.type || '—'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </>
            )}
        </div>
    )
}

// Diagnostics — generic admin sandbox-task runner (ported from the legacy
// admin sandbox page). Tasks are registered server-side in
// src/admin/sandbox_tasks.py and listed via adminSandboxTasks().
function DiagnosticsPanel() {
    const [tasks, setTasks] = useState([])
    const [collapsedTasks, setCollapsedTasks] = useState({})
    const [formValues, setFormValues] = useState({})
    const [results, setResults] = useState({})
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [runningTaskId, setRunningTaskId] = useState(null)
    const [sofascorePlayers, setSofascorePlayers] = useState([])
    const [sofascoreInputs, setSofascoreInputs] = useState({})
    const [sofascoreUpdatingKey, setSofascoreUpdatingKey] = useState(null)
    const [sofascoreStatus, setSofascoreStatus] = useState(null)

    const buildDefaults = useCallback((taskList) => {
        const defaults = {}
        for (const task of taskList) {
            const params = task?.parameters || []
            defaults[task.task_id] = params.reduce((acc, param) => {
                if (param.type === 'checkbox') {
                    acc[param.name] = false
                } else {
                    acc[param.name] = ''
                }
                return acc
            }, {})
        }
        return defaults
    }, [])

    const loadTasks = useCallback(async () => {
        setLoading(true)
        setError('')
        try {
            let payload
            try {
                payload = await APIService.adminSandboxTasks()
            } catch (err) {
                if (err?.status === 401) {
                    await APIService.refreshProfile()
                    payload = await APIService.adminSandboxTasks()
                } else {
                    throw err
                }
            }
            const taskList = Array.isArray(payload?.tasks) ? payload.tasks : []
            setTasks(taskList)
            setCollapsedTasks((prev) => mergeCollapseState(prev, taskList))
            setFormValues((prev) => ({ ...buildDefaults(taskList), ...prev }))
        } catch (err) {
            setError(err?.message || 'Failed to load sandbox tasks')
        } finally {
            setLoading(false)
        }
    }, [buildDefaults])

    useEffect(() => {
        loadTasks()
    }, [loadTasks])

    const toggleTaskCollapsed = useCallback((taskId) => {
        setCollapsedTasks((prev) => toggleCollapseState(prev, taskId))
    }, [])

    const handleInputChange = useCallback((taskId, fieldName, fieldType) => (event) => {
        const value = fieldType === 'checkbox' ? event.target.checked : event.target.value
        setFormValues((prev) => ({
            ...prev,
            [taskId]: {
                ...(prev[taskId] || {}),
                [fieldName]: value,
            },
        }))
    }, [])

    const handleSelectChange = useCallback((taskId, param, option, params) => {
        setFormValues((prev) => {
            const updates = buildSelectUpdates(param, option, params)
            if (!updates || Object.keys(updates).length === 0) {
                return prev
            }
            const nextTaskValues = { ...(prev[taskId] || {}) }
            for (const [key, value] of Object.entries(updates)) {
                nextTaskValues[key] = value
            }
            return { ...prev, [taskId]: nextTaskValues }
        })
    }, [])

    const buildPayload = useCallback((task) => {
        const params = task?.parameters || []
        const currentValues = formValues[task.task_id] || {}
        const payload = {}
        for (const param of params) {
            const rawValue = currentValues[param.name]
            if (param.type === 'checkbox') {
                payload[param.name] = !!rawValue
                continue
            }
            if (rawValue === '' || typeof rawValue === 'undefined' || rawValue === null) {
                continue
            }
            if (param.type === 'number') {
                const numeric = Number(rawValue)
                if (!Number.isNaN(numeric)) {
                    payload[param.name] = numeric
                }
            } else {
                payload[param.name] = rawValue
            }
        }
        return payload
    }, [formValues])

    const runTask = useCallback(async (task) => {
        if (!task?.task_id) return
        setRunningTaskId(task.task_id)
        try {
            const payload = buildPayload(task)
            let result
            try {
                result = await APIService.adminSandboxRun(task.task_id, payload)
            } catch (err) {
                if (err?.status === 401) {
                    await APIService.refreshProfile()
                    result = await APIService.adminSandboxRun(task.task_id, payload)
                } else {
                    throw err
                }
            }
            if (task.task_id === 'list-missing-sofascore-ids') {
                const players = Array.isArray(result?.payload?.players) ? result.payload.players : []
                const enriched = players.map((player, index) => ({
                    ...player,
                    __row_key: sofascoreRowKey(player, index),
                }))
                const inputDefaults = {}
                for (const player of enriched) {
                    const rowKey = player.__row_key
                    inputDefaults[rowKey] = player?.sofascore_id ? String(player.sofascore_id) : ''
                }
                setSofascorePlayers(enriched)
                setSofascoreInputs(inputDefaults)
                setSofascoreStatus(null)
                setSofascoreUpdatingKey(null)
            }
            if (task.task_id === 'update-player-sofascore-id') {
                setSofascoreStatus({ type: 'success', message: result?.summary || 'Sofascore id updated.' })
            }
            setResults((prev) => ({
                ...prev,
                [task.task_id]: { status: 'ok', result },
            }))
        } catch (err) {
            if (task?.task_id === 'update-player-sofascore-id') {
                setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to update Sofascore id.' })
            }
            setResults((prev) => ({
                ...prev,
                [task.task_id]: {
                    status: 'error',
                    message: err?.message || 'Task execution failed',
                    detail: err?.body,
                },
            }))
        } finally {
            setRunningTaskId(null)
        }
    }, [buildPayload])

    const handleSofascoreAssign = useCallback(async (row, inputValue) => {
        const payload = buildSofascoreUpdatePayload(row, typeof inputValue === 'string' ? inputValue.trim() : inputValue)
        if (!payload) {
            setSofascoreStatus({ type: 'error', message: 'Unable to update Sofascore id for this row.' })
            return
        }

        const rowKey = row?.__row_key || sofascoreRowKey(row)
        setSofascoreStatus(null)
        setSofascoreUpdatingKey(rowKey)
        try {
            const result = await APIService.adminSandboxRun('update-player-sofascore-id', payload)
            setSofascoreStatus({ type: 'success', message: result?.summary || 'Sofascore id updated.' })
            setSofascorePlayers((prev) => prev.filter((item) => (item.__row_key || sofascoreRowKey(item)) !== rowKey))
            setSofascoreInputs((prev) => {
                const next = { ...prev }
                delete next[rowKey]
                return next
            })
        } catch (err) {
            setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to update Sofascore id.' })
        } finally {
            setSofascoreUpdatingKey(null)
        }
    }, [])

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between gap-2">
                <p className="text-sm text-muted-foreground">
                    Server-side diagnostic tasks (registered in <span className="font-mono">admin/sandbox_tasks.py</span>).
                    Results render inline; nothing here is scheduled — every run is manual.
                </p>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={loadTasks}
                    disabled={loading}
                    data-testid="sandbox-refresh-tasks"
                >
                    {loading ? 'Refreshing…' : 'Refresh tasks'}
                </Button>
            </div>

            {error && (
                <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            {loading && !tasks.length ? (
                <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
                    Loading sandbox tasks…
                </div>
            ) : null}

            {!loading && !tasks.length && !error ? (
                <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
                    No sandbox tasks are currently registered.
                </div>
            ) : null}

            <div className="grid gap-4">
                {tasks.map((task) => {
                    const params = task?.parameters || []
                    const values = formValues[task.task_id] || {}
                    const outcome = results[task.task_id]
                    const isRunning = runningTaskId === task.task_id
                    const isCollapsed = (collapsedTasks && Object.prototype.hasOwnProperty.call(collapsedTasks, task.task_id))
                        ? !!collapsedTasks[task.task_id]
                        : true
                    const ToggleIcon = isCollapsed ? ChevronRight : ChevronDown

                    return (
                        <div key={task.task_id} className="rounded-xl border bg-card shadow-sm">
                            <div className={sandboxCardHeaderClasses('shadow-sm')}>
                                <div className="space-y-1">
                                    <h2 className="text-lg font-semibold">{task.label}</h2>
                                    <p className="text-sm text-muted-foreground">{task.description}</p>
                                </div>
                                <div className="flex items-center gap-2">
                                    {outcome?.status === 'ok' ? (
                                        <span className="text-xs font-medium text-emerald-600">Success</span>
                                    ) : null}
                                    {outcome?.status === 'error' ? (
                                        <span
                                            className="max-w-[12rem] truncate text-xs font-medium text-rose-600"
                                            title={outcome.message}
                                        >
                                            {outcome.message}
                                        </span>
                                    ) : null}
                                    <button
                                        type="button"
                                        onClick={() => toggleTaskCollapsed(task.task_id)}
                                        aria-expanded={!isCollapsed}
                                        data-testid={`sandbox-toggle-${task.task_id}`}
                                        className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2 py-1 text-xs font-medium text-foreground/80 transition hover:bg-muted"
                                    >
                                        <ToggleIcon className="h-4 w-4" />
                                        {isCollapsed ? 'Expand' : 'Collapse'}
                                    </button>
                                </div>
                            </div>
                            {!isCollapsed && (
                                <>
                                    <form
                                        className="px-4 py-4 space-y-4"
                                        onSubmit={(event) => {
                                            event.preventDefault()
                                            runTask(task)
                                        }}
                                    >
                                        {params.length > 0 ? (
                                            <div className="grid gap-3 md:grid-cols-2">
                                                {params.map((param) => {
                                                    const selectOptions = Array.isArray(param.options) ? param.options : []
                                                    const hasSelect = param.type === 'select' && selectOptions.length > 0
                                                    const currentValue = values[param.name] ?? ''
                                                    const selectValue = hasSelect ? String(currentValue ?? '') : ''
                                                    const selectLookup = hasSelect
                                                        ? new Map(selectOptions.map((option, index) => {
                                                            const optValue = option?.value ?? option?.label ?? index
                                                            return [String(optValue), option]
                                                        }))
                                                        : null

                                                    return (
                                                        <label key={param.name} className="flex flex-col gap-2 text-sm font-medium text-foreground/80">
                                                            <span>{param.label}</span>
                                                            {param.type === 'checkbox' ? (
                                                                <div className="flex items-center gap-2 text-sm font-normal">
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={!!values[param.name]}
                                                                        onChange={handleInputChange(task.task_id, param.name, param.type)}
                                                                    />
                                                                    {param.help ? <span className="text-muted-foreground">{param.help}</span> : null}
                                                                </div>
                                                            ) : hasSelect ? (
                                                                <Select
                                                                    value={selectValue}
                                                                    onValueChange={(newValue) => {
                                                                        if (!selectLookup) {
                                                                            handleSelectChange(task.task_id, param, newValue ? { value: newValue } : null, params)
                                                                            return
                                                                        }
                                                                        const option = selectLookup.get(newValue)
                                                                        handleSelectChange(
                                                                            task.task_id,
                                                                            param,
                                                                            option || (newValue ? { value: newValue } : null),
                                                                            params
                                                                        )
                                                                    }}
                                                                >
                                                                    <SelectTrigger>
                                                                        <SelectValue placeholder={param.placeholder || 'Select option…'} />
                                                                    </SelectTrigger>
                                                                    <SelectContent>
                                                                        {selectOptions.map((option, index) => {
                                                                            const optionValue = String(option?.value ?? option?.label ?? index)
                                                                            const optionLabel = option?.label ?? option?.value ?? optionValue
                                                                            return (
                                                                                <SelectItem key={`${optionValue}-${index}`} value={optionValue}>
                                                                                    {optionLabel}
                                                                                </SelectItem>
                                                                            )
                                                                        })}
                                                                    </SelectContent>
                                                                </Select>
                                                            ) : (
                                                                <Input
                                                                    type={param.type || 'text'}
                                                                    value={values[param.name] ?? ''}
                                                                    placeholder={param.placeholder || ''}
                                                                    onChange={handleInputChange(task.task_id, param.name, param.type)}
                                                                />
                                                            )}
                                                            {param.type !== 'checkbox' && param.help ? (
                                                                <span className="text-xs font-normal text-muted-foreground">{param.help}</span>
                                                            ) : null}
                                                        </label>
                                                    )
                                                })}
                                            </div>
                                        ) : (
                                            <p className="text-sm text-muted-foreground">No parameters required.</p>
                                        )}
                                        <div className="flex items-center gap-3">
                                            <Button type="submit" size="sm" disabled={isRunning} data-testid={`sandbox-run-${task.task_id}`}>
                                                {isRunning ? 'Running…' : 'Run task'}
                                            </Button>
                                            {outcome?.status === 'ok' && (
                                                <span className="text-sm text-emerald-600">Success</span>
                                            )}
                                            {outcome?.status === 'error' && (
                                                <span className="text-sm text-rose-600">{outcome.message}</span>
                                            )}
                                        </div>
                                        {task.task_id !== 'list-missing-sofascore-ids' && outcome?.status === 'ok' && outcome.result && (
                                            <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-foreground p-3 text-xs text-card">
                                                {JSON.stringify(outcome.result, null, 2)}
                                            </pre>
                                        )}
                                        {outcome?.status === 'error' && outcome.detail && (
                                            <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-rose-900/80 p-3 text-xs text-rose-100">
                                                {typeof outcome.detail === 'string'
                                                    ? outcome.detail
                                                    : JSON.stringify(outcome.detail, null, 2)}
                                            </pre>
                                        )}
                                    </form>
                                    {task.task_id === 'list-missing-sofascore-ids' && (
                                        <div className="border-t px-4 py-4 space-y-4">
                                            {sofascoreStatus && (
                                                <Alert variant={sofascoreStatus.type === 'error' ? 'destructive' : 'default'}>
                                                    <AlertDescription>{sofascoreStatus.message}</AlertDescription>
                                                </Alert>
                                            )}
                                            {sofascorePlayers.length === 0 ? (
                                                <p className="text-sm text-muted-foreground">
                                                    Run the task to load players missing Sofascore ids.
                                                </p>
                                            ) : (
                                                <div className="overflow-auto">
                                                    <table className="min-w-full text-sm">
                                                        <thead>
                                                            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                                                                <th className="pb-2 pr-4">Player</th>
                                                                <th className="pb-2 pr-4">Parent Club</th>
                                                                <th className="pb-2 pr-4">Loan Club</th>
                                                                <th className="pb-2 pr-4">Sofascore ID</th>
                                                                <th className="pb-2 pr-4">Actions</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {sofascorePlayers.map((player, index) => {
                                                                const rowKey = player?.__row_key || sofascoreRowKey(player, index)
                                                                const apiLabel = player?.player_id ? `API #${player.player_id}` : '—'
                                                                const value = sofascoreInputs[rowKey] ?? (player?.sofascore_id ? String(player.sofascore_id) : '')
                                                                return (
                                                                    <tr key={rowKey} className="border-t border-border last:border-b">
                                                                        <td className="py-2 pr-4 align-top">
                                                                            <div className="font-medium text-foreground">{player?.player_name || (player?.player_id ? `Player #${player.player_id}` : 'Unknown player')}</div>
                                                                            <div className="text-xs text-muted-foreground">{apiLabel}</div>
                                                                        </td>
                                                                        <td className="py-2 pr-4 align-top text-muted-foreground">{player?.primary_team || '—'}</td>
                                                                        <td className="py-2 pr-4 align-top text-muted-foreground">{player?.loan_team || '—'}</td>
                                                                        <td className="py-2 pr-4 align-top">
                                                                            <Input
                                                                                aria-label={`Sofascore id for ${player?.player_name || apiLabel}`}
                                                                                value={value}
                                                                                placeholder="e.g. 1101989"
                                                                                onChange={(event) => {
                                                                                    const next = event.target.value
                                                                                    setSofascoreInputs((prev) => ({ ...prev, [rowKey]: next }))
                                                                                }}
                                                                                className="w-36"
                                                                            />
                                                                        </td>
                                                                        <td className="py-2 pr-4 align-top">
                                                                            <div className="flex flex-wrap gap-2">
                                                                                <Button
                                                                                    size="sm"
                                                                                    disabled={sofascoreUpdatingKey === rowKey || !(value && value.trim())}
                                                                                    onClick={() => handleSofascoreAssign(player, (value || '').trim())}
                                                                                >
                                                                                    {sofascoreUpdatingKey === rowKey ? 'Saving…' : 'Save'}
                                                                                </Button>
                                                                                <Button
                                                                                    size="sm"
                                                                                    variant="outline"
                                                                                    disabled={sofascoreUpdatingKey === rowKey}
                                                                                    onClick={() => handleSofascoreAssign(player, '')}
                                                                                >
                                                                                    Clear
                                                                                </Button>
                                                                            </div>
                                                                        </td>
                                                                    </tr>
                                                                )
                                                            })}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

export function AdminSandbox() {
    return (
        <div className="space-y-6">
            <header>
                <h2 className="text-3xl font-bold tracking-tight">Classifier Tester &amp; Diagnostics</h2>
                <p className="text-muted-foreground mt-1">
                    Test the classifier pipeline on any player, or run server-side diagnostic tasks
                </p>
            </header>

            <Tabs defaultValue="classifier" className="space-y-6">
                <TabsList>
                    <TabsTrigger value="classifier" data-testid="sandbox-tab-classifier">Classifier Tester</TabsTrigger>
                    <TabsTrigger value="diagnostics" data-testid="sandbox-tab-diagnostics">Diagnostics</TabsTrigger>
                </TabsList>
                <TabsContent value="classifier">
                    <ClassifierTester />
                </TabsContent>
                <TabsContent value="diagnostics">
                    <DiagnosticsPanel />
                </TabsContent>
            </Tabs>
        </div>
    )
}

export default AdminSandbox
