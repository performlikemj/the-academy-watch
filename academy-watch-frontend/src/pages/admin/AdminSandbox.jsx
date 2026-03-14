import { useState, useEffect, useCallback, useRef } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
    Search, Loader2, AlertCircle, CheckCircle2, ArrowRight,
    ChevronDown, ChevronRight, User,
} from 'lucide-react'
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

export function AdminSandbox() {
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
            team: tp.loan_club_name || (tp.team?.name),
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
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Player Sandbox</h2>
                <p className="text-muted-foreground mt-1">
                    Test the classifier pipeline on any player and see step-by-step reasoning
                </p>
            </div>

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
                                        {cls.loan_club_name && (
                                            <span className="text-sm text-muted-foreground">
                                                at {cls.loan_club_name}
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
