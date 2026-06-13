import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { UserPlus, Search, AlertCircle, CheckCircle2, Trash2, RefreshCw, Pencil, X, Save, Loader2, CheckCircle, XCircle, Clock, User, Shield, Download } from 'lucide-react'
import TeamSelect from '@/components/ui/TeamSelect'
import { STATUS_BADGE_CLASSES } from '../../lib/theme-constants'

const STATUS_OPTIONS = [
    { value: 'academy', label: 'Academy' },
    { value: 'on_loan', label: 'On Loan' },
    { value: 'first_team', label: 'First Team' },
    { value: 'released', label: 'Released' },
    { value: 'sold', label: 'Sold' },
]

const LEVEL_OPTIONS = [
    { value: 'U18', label: 'U18' },
    { value: 'U21', label: 'U21' },
    { value: 'U23', label: 'U23' },
    { value: 'Reserve', label: 'Reserve' },
    { value: 'Senior', label: 'Senior' },
]

const POSITION_OPTIONS = ['Goalkeeper', 'Defender', 'Midfielder', 'Attacker']

function StatusBadge({ status, saleFee }) {
    return (
        <Badge className={STATUS_BADGE_CLASSES[status] || 'bg-secondary text-muted-foreground'}>
            {(status || '').replace('_', ' ')}{saleFee ? ` · ${saleFee}` : ''}
        </Badge>
    )
}

// ============================================================
// Tab 1: All Players
// ============================================================
function AllPlayersTab({ teams, setMessage }) {
    const [players, setPlayers] = useState([])
    const [loading, setLoading] = useState(false)
    const [page, setPage] = useState(1)
    const [pageSize] = useState(20)
    const [totalPages, setTotalPages] = useState(1)
    const [editingId, setEditingId] = useState(null)
    const [editForm, setEditForm] = useState({})
    const [saving, setSaving] = useState(false)
    const [deletingId, setDeletingId] = useState(null)
    const [refreshingStatuses, setRefreshingStatuses] = useState(false)

    const [filters, setFilters] = useState({
        search: '',
        team_id: '',
        status: '',
        current_level: '',
        data_source: '',
    })

    const loadPlayers = useCallback(async (nextPage) => {
        setLoading(true)
        try {
            const params = { page: nextPage || page, page_size: pageSize }
            if (filters.search.trim()) params.search = filters.search.trim()
            if (filters.team_id) params.team_id = Number(filters.team_id)
            if (filters.status) params.status = filters.status
            if (filters.current_level) params.current_level = filters.current_level
            if (filters.data_source) params.data_source = filters.data_source

            const res = await APIService.adminTrackedPlayersList(params)
            setPlayers(res.items || [])
            setPage(res.page || 1)
            setTotalPages(res.total_pages || 1)
        } catch (error) {
            setMessage({ type: 'error', text: `Failed to load players: ${error?.body?.error || error.message}` })
        } finally {
            setLoading(false)
        }
    }, [page, pageSize, filters, setMessage])

    useEffect(() => {
        loadPlayers(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters.search, filters.team_id, filters.status, filters.current_level, filters.data_source])

    const startEdit = (player) => {
        setEditingId(player.id)
        setEditForm({
            status: player.status || 'academy',
            current_level: player.current_level || '',
            current_club_api_id: player.current_club_api_id || '',
            current_club_name: player.current_club_name || '',
            notes: player.notes || '',
            position: player.position || '',
            sale_fee: player.sale_fee || '',
        })
    }

    const saveEdit = async () => {
        setSaving(true)
        try {
            await APIService.adminTrackedPlayerUpdate(editingId, editForm)
            setEditingId(null)
            setMessage({ type: 'success', text: 'Player updated' })
            loadPlayers()
        } catch (error) {
            setMessage({ type: 'error', text: `Update failed: ${error?.body?.error || error.message}` })
        } finally {
            setSaving(false)
        }
    }

    const deletePlayer = async (id, name) => {
        if (!window.confirm(`Remove "${name}" from tracking?`)) return
        setDeletingId(id)
        try {
            await APIService.adminTrackedPlayerDelete(id)
            setMessage({ type: 'success', text: `Removed ${name}` })
            setPlayers((prev) => prev.filter((p) => p.id !== id))
        } catch (error) {
            setMessage({ type: 'error', text: `Delete failed: ${error?.body?.error || error.message}` })
        } finally {
            setDeletingId(null)
        }
    }

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className="flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[180px]">
                    <Input
                        placeholder="Search player name..."
                        value={filters.search}
                        onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                    />
                </div>
                <TeamSelect
                    teams={teams}
                    value={filters.team_id}
                    placeholder="Filter by team..."
                    onChange={(id) => setFilters({ ...filters, team_id: id })}
                    className="min-w-[180px]"
                />
                <select
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                    value={filters.status}
                    onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                >
                    <option value="">All statuses</option>
                    {STATUS_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                </select>
                <select
                    className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                    value={filters.current_level}
                    onChange={(e) => setFilters({ ...filters, current_level: e.target.value })}
                >
                    <option value="">All levels</option>
                    {LEVEL_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                </select>
                <Button variant="outline" size="sm" onClick={() => loadPlayers(1)} disabled={loading}>
                    <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    disabled={refreshingStatuses}
                    onClick={async () => {
                        setRefreshingStatuses(true)
                        try {
                            const payload = filters.team_id ? { team_id: Number(filters.team_id) } : {}
                            const res = await APIService.adminRefreshTrackedPlayerStatuses(payload)
                            setMessage({ type: 'success', text: `Refreshed statuses: ${res.updated} of ${res.total} updated` })
                            loadPlayers()
                        } catch (error) {
                            setMessage({ type: 'error', text: `Refresh failed: ${error?.body?.error || error.message}` })
                        } finally {
                            setRefreshingStatuses(false)
                        }
                    }}
                >
                    {refreshingStatuses ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Shield className="h-4 w-4 mr-1" />}
                    Re-classify
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    disabled={refreshingStatuses}
                    title="Re-syncs journey data from API-Football then re-classifies. Use this to fix stale statuses (e.g. international teams showing as loans)."
                    onClick={async () => {
                        if (!filters.team_id) {
                            setMessage({ type: 'error', text: 'Select a team first — re-sync is too slow for all teams at once' })
                            return
                        }
                        setRefreshingStatuses(true)
                        try {
                            const payload = { team_id: Number(filters.team_id), resync_journeys: true }
                            const res = await APIService.adminRefreshTrackedPlayerStatuses(payload)
                            const parts = [`${res.updated} of ${res.total} updated`]
                            if (res.journeys_resynced) parts.push(`${res.journeys_resynced} journeys re-synced`)
                            setMessage({ type: 'success', text: `Re-sync complete: ${parts.join(', ')}` })
                            loadPlayers()
                        } catch (error) {
                            setMessage({ type: 'error', text: `Re-sync failed: ${error?.body?.error || error.message}` })
                        } finally {
                            setRefreshingStatuses(false)
                        }
                    }}
                >
                    {refreshingStatuses ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                    Re-sync & Re-classify
                </Button>
            </div>

            {/* Players Table */}
            {loading && <p className="text-sm text-muted-foreground">Loading players...</p>}
            {!loading && players.length === 0 && (
                <p className="text-sm text-muted-foreground py-8 text-center">No tracked players found.</p>
            )}
            {!loading && players.length > 0 && (
                <div className="space-y-2">
                    {players.map((p) => (
                        <div key={p.id} className="rounded-md border px-4 py-3 bg-card">
                            {editingId === p.id ? (
                                /* Edit form */
                                <div className="space-y-3">
                                    <div className="font-medium">{p.player_name}</div>
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                        <div>
                                            <Label className="text-xs">Status</Label>
                                            <select
                                                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                                                value={editForm.status}
                                                onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                                            >
                                                {STATUS_OPTIONS.map((opt) => (
                                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div>
                                            <Label className="text-xs">Level</Label>
                                            <select
                                                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                                                value={editForm.current_level}
                                                onChange={(e) => setEditForm({ ...editForm, current_level: e.target.value })}
                                            >
                                                <option value="">None</option>
                                                {LEVEL_OPTIONS.map((opt) => (
                                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div>
                                            <Label className="text-xs">Position</Label>
                                            <select
                                                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                                                value={editForm.position}
                                                onChange={(e) => setEditForm({ ...editForm, position: e.target.value })}
                                            >
                                                <option value="">None</option>
                                                {POSITION_OPTIONS.map((pos) => (
                                                    <option key={pos} value={pos}>{pos}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>
                                    {editForm.status === 'on_loan' && (
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            <div>
                                                <Label className="text-xs">Loan Club Name</Label>
                                                <Input
                                                    value={editForm.current_club_name}
                                                    onChange={(e) => setEditForm({ ...editForm, current_club_name: e.target.value })}
                                                    placeholder="e.g. Sheffield Wednesday"
                                                />
                                            </div>
                                            <div>
                                                <Label className="text-xs">Loan Club API ID</Label>
                                                <Input
                                                    type="number"
                                                    value={editForm.current_club_api_id}
                                                    onChange={(e) => setEditForm({ ...editForm, current_club_api_id: e.target.value })}
                                                    placeholder="Optional"
                                                />
                                            </div>
                                        </div>
                                    )}
                                    {editForm.status === 'sold' && (
                                        <div>
                                            <Label className="text-xs">Sale Fee</Label>
                                            <Input
                                                value={editForm.sale_fee}
                                                onChange={(e) => setEditForm({ ...editForm, sale_fee: e.target.value })}
                                                placeholder="e.g. €50M, Free"
                                            />
                                        </div>
                                    )}
                                    <div>
                                        <Label className="text-xs">Notes</Label>
                                        <Textarea
                                            value={editForm.notes}
                                            onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                                            rows={2}
                                        />
                                    </div>
                                    <div className="flex gap-2">
                                        <Button size="sm" onClick={saveEdit} disabled={saving}>
                                            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
                                            Save
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                                            <X className="h-4 w-4 mr-1" /> Cancel
                                        </Button>
                                    </div>
                                </div>
                            ) : (
                                /* Display row */
                                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                    <div className="flex items-center gap-3">
                                        {p.photo_url ? (
                                            <img src={p.photo_url} alt="" className="w-8 h-8 rounded-full object-cover bg-secondary" />
                                        ) : (
                                            <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs text-muted-foreground">
                                                {(p.player_name || '?')[0]}
                                            </div>
                                        )}
                                        <div>
                                            <div className="font-medium">{p.player_name}</div>
                                            <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                                                <span>{p.team_name || '—'}</span>
                                                {p.position && <span>{p.position}</span>}
                                                {p.current_level && <span>{p.current_level}</span>}
                                                {p.current_club_name && <span>@ {p.current_club_name}</span>}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <StatusBadge status={p.status} saleFee={p.sale_fee} />
                                        <Badge variant="outline" className="text-xs">{p.data_source}</Badge>
                                        <Button variant="ghost" size="sm" onClick={() => startEdit(p)}>
                                            <Pencil className="h-4 w-4" />
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="text-rose-600 hover:text-rose-700"
                                            disabled={deletingId === p.id}
                                            onClick={() => deletePlayer(p.id, p.player_name)}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Pagination */}
            {!loading && players.length > 0 && (
                <div className="flex items-center justify-between pt-2">
                    <div className="text-xs text-muted-foreground">Page {page} of {totalPages}</div>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => { setPage(page - 1); loadPlayers(page - 1) }}>Prev</Button>
                        <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => { setPage(page + 1); loadPlayers(page + 1) }}>Next</Button>
                    </div>
                </div>
            )}
        </div>
    )
}

// ============================================================
// Tab 2: Submissions — moved to the unified Inbox
// ============================================================
function SubmissionsTab() {
    return (
        <Card data-testid="submissions-moved-card">
            <CardHeader>
                <CardTitle>Submissions have moved</CardTitle>
                <CardDescription>
                    Writer-submitted players are now reviewed in the unified admin Inbox,
                    alongside community takes, flags, and tracking requests.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <Button asChild>
                    <Link to="/admin/inbox?tab=manual">Open the Inbox</Link>
                </Button>
            </CardContent>
        </Card>
    )
}

// ============================================================
// Tab 3: Add Player (seeding moved to Seeding & Rebuild)
// ============================================================
function SeedTab({ teams, setMessage }) {
    return (
        <div className="space-y-6">
            <Card data-testid="seeding-moved-card">
                <CardHeader>
                    <CardTitle>Seeding has moved</CardTitle>
                    <CardDescription>
                        Discovering academy players (per team, all tracked teams, cohorts, or a full
                        rebuild) now lives on the Seeding &amp; Rebuild page — one home for every
                        seeding path, with the right guardrails.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Button asChild>
                        <Link to="/admin/seeding">Open Seeding &amp; Rebuild</Link>
                    </Button>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Add Player Manually</CardTitle>
                    <CardDescription>Add a player who isn't in the API data</CardDescription>
                </CardHeader>
                <CardContent>
                    <ManualAddForm teams={teams} setMessage={setMessage} />
                </CardContent>
            </Card>
        </div>
    )
}

// ============================================================
// Manual Add Player Form
// ============================================================
function ManualAddForm({ teams, setMessage }) {
    const [form, setForm] = useState({
        player_name: '',
        position: '',
        nationality: '',
        age: '',
        team_id: '',
        status: 'academy',
        current_level: '',
        current_club_name: '',
        notes: '',
    })

    const handleSubmit = async () => {
        if (!form.player_name.trim()) {
            setMessage({ type: 'error', text: 'Player name is required' })
            return
        }
        if (!form.team_id) {
            setMessage({ type: 'error', text: 'Team is required' })
            return
        }

        try {
            const payload = {
                player_name: form.player_name.trim(),
                team_id: Number(form.team_id),
                status: form.status,
                data_source: 'manual',
            }
            if (form.position) payload.position = form.position
            if (form.nationality) payload.nationality = form.nationality
            if (form.age) payload.age = parseInt(form.age)
            if (form.current_level) payload.current_level = form.current_level
            if (form.current_club_name) payload.current_club_name = form.current_club_name
            if (form.notes) payload.notes = form.notes

            await APIService.adminTrackedPlayerCreate(payload)
            setMessage({ type: 'success', text: `Added ${form.player_name}` })
            setForm({ player_name: '', position: '', nationality: '', age: '', team_id: '', status: 'academy', current_level: '', current_club_name: '', notes: '' })
        } catch (error) {
            setMessage({ type: 'error', text: `Create failed: ${error?.body?.error || error.message}` })
        }
    }

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                    <Label>Player Name *</Label>
                    <Input value={form.player_name} onChange={(e) => setForm({ ...form, player_name: e.target.value })} placeholder="Full name" />
                </div>
                <div>
                    <Label>Parent Team *</Label>
                    <TeamSelect teams={teams} value={form.team_id} onChange={(id) => setForm({ ...form, team_id: id })} placeholder="Select team..." />
                </div>
                <div>
                    <Label>Status</Label>
                    <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                        {STATUS_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                </div>
                <div>
                    <Label>Position</Label>
                    <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}>
                        <option value="">Select...</option>
                        {POSITION_OPTIONS.map((pos) => <option key={pos} value={pos}>{pos}</option>)}
                    </select>
                </div>
                <div>
                    <Label>Level</Label>
                    <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={form.current_level} onChange={(e) => setForm({ ...form, current_level: e.target.value })}>
                        <option value="">None</option>
                        {LEVEL_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                </div>
                <div>
                    <Label>Nationality</Label>
                    <Input value={form.nationality} onChange={(e) => setForm({ ...form, nationality: e.target.value })} placeholder="e.g. England" />
                </div>
                <div>
                    <Label>Age</Label>
                    <Input type="number" value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value })} placeholder="Age" />
                </div>
                {form.status === 'on_loan' && (
                    <div className="md:col-span-2">
                        <Label>Loan Club Name</Label>
                        <Input value={form.current_club_name} onChange={(e) => setForm({ ...form, current_club_name: e.target.value })} placeholder="e.g. Sheffield Wednesday" />
                    </div>
                )}
                <div className="md:col-span-2">
                    <Label>Notes</Label>
                    <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={2} />
                </div>
            </div>
            <Button onClick={handleSubmit}>
                <UserPlus className="h-4 w-4 mr-2" />
                Create Player
            </Button>
        </div>
    )
}

// ============================================================
// Main export
// ============================================================
export function AdminPlayers() {
    const [teams, setTeams] = useState([])
    const [message, setMessage] = useState(null)

    useEffect(() => {
        const loadTeams = async () => {
            try {
                const data = await APIService.getTeams()
                setTeams(Array.isArray(data) ? data : [])
            } catch (error) {
                console.error('Failed to load teams', error)
            }
        }
        loadTeams()
    }, [])

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Players</h2>
                <p className="text-muted-foreground mt-1">Manage tracked academy players</p>
            </div>

            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                        <Button variant="ghost" size="sm" className="ml-2 h-6 px-2" onClick={() => setMessage(null)}>
                            <X className="h-3 w-3" />
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            <Tabs defaultValue="all" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="all">All Players</TabsTrigger>
                    <TabsTrigger value="submissions">Submissions</TabsTrigger>
                    <TabsTrigger value="seed">Seed</TabsTrigger>
                </TabsList>

                <TabsContent value="all">
                    <AllPlayersTab teams={teams} setMessage={setMessage} />
                </TabsContent>

                <TabsContent value="submissions">
                    <SubmissionsTab setMessage={setMessage} />
                </TabsContent>

                <TabsContent value="seed">
                    <SeedTab teams={teams} setMessage={setMessage} />
                </TabsContent>
            </Tabs>
        </div>
    )
}
