import { useState, useEffect, useCallback } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    AlertCircle,
    CheckCircle2,
    Loader2,
    Plus,
    Trash2,
    RefreshCw,
    GraduationCap,
    Calendar,
    Users,
    ArrowRight
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { LEVEL_BADGE_CLASSES } from '../../lib/theme-constants'

export function AdminAcademy() {
    // Stats
    const [stats, setStats] = useState(null)
    const [statsLoading, setStatsLoading] = useState(true)

    // Leagues
    const [leagues, setLeagues] = useState([])
    const [loading, setLoading] = useState(false)

    // Messages
    const [message, setMessage] = useState(null)

    // Add dialog
    const [addDialogOpen, setAddDialogOpen] = useState(false)
    const [addLoading, setAddLoading] = useState(false)
    const [newLeague, setNewLeague] = useState({
        api_league_id: '',
        name: '',
        country: '',
        level: 'U21',
        season: new Date().getFullYear(),
    })

    // Sync state
    const [syncingLeagueId, setSyncingLeagueId] = useState(null)
    const [syncAllLoading, setSyncAllLoading] = useState(false)

    // Delete confirmation
    const [deleteTarget, setDeleteTarget] = useState(null)
    const [deleteLoading, setDeleteLoading] = useState(false)

    // Load stats
    const loadStats = useCallback(async () => {
        try {
            setStatsLoading(true)
            const data = await APIService.adminAcademyStatsSummary()
            setStats(data)
        } catch (err) {
            console.error('Failed to load stats', err)
        } finally {
            setStatsLoading(false)
        }
    }, [])

    // Load leagues
    const loadLeagues = useCallback(async () => {
        try {
            setLoading(true)
            const data = await APIService.adminListAcademyLeagues()
            setLeagues(data?.leagues || [])
        } catch (err) {
            console.error('Failed to load leagues', err)
            setMessage({ type: 'error', text: 'Failed to load academy leagues' })
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        loadStats()
        loadLeagues()
    }, [loadStats, loadLeagues])

    // Add league
    const handleAddLeague = async () => {
        if (!newLeague.api_league_id || !newLeague.name.trim() || !newLeague.level) {
            setMessage({ type: 'error', text: 'League ID, name, and level are required' })
            return
        }

        setAddLoading(true)
        try {
            await APIService.adminCreateAcademyLeague({
                api_league_id: parseInt(newLeague.api_league_id),
                name: newLeague.name.trim(),
                country: newLeague.country.trim() || null,
                level: newLeague.level,
                season: parseInt(newLeague.season) || null,
            })
            setMessage({ type: 'success', text: 'League added' })
            setAddDialogOpen(false)
            setNewLeague({
                api_league_id: '',
                name: '',
                country: '',
                level: 'U21',
                season: new Date().getFullYear(),
            })
            loadLeagues()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to add league' })
        } finally {
            setAddLoading(false)
        }
    }

    // Toggle active
    const toggleActive = async (league) => {
        try {
            await APIService.adminUpdateAcademyLeague(league.id, {
                is_active: !league.is_active
            })
            loadLeagues()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to update league' })
        }
    }

    // Sync single league
    const handleSyncLeague = async (leagueId) => {
        setSyncingLeagueId(leagueId)
        try {
            const result = await APIService.adminSyncAcademyLeague(leagueId)
            const r = result.result || {}
            setMessage({
                type: 'success',
                text: `Synced ${r.fixtures_processed || 0} fixtures, ${r.appearances_created || 0} new appearances`
            })
            loadLeagues()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Sync failed' })
        } finally {
            setSyncingLeagueId(null)
        }
    }

    // Sync all leagues
    const handleSyncAll = async () => {
        setSyncAllLoading(true)
        try {
            const result = await APIService.adminSyncAllAcademyLeagues()
            const s = result.summary || {}
            setMessage({
                type: 'success',
                text: `Synced ${s.leagues_synced || 0} leagues, ${s.fixtures_processed || 0} fixtures, ${s.appearances_created || 0} appearances`
            })
            loadLeagues()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Sync failed' })
        } finally {
            setSyncAllLoading(false)
        }
    }

    // Delete league
    const handleDelete = async () => {
        if (!deleteTarget) return
        setDeleteLoading(true)
        try {
            await APIService.adminDeleteAcademyLeague(deleteTarget.id)
            setMessage({ type: 'success', text: 'League deleted' })
            setDeleteTarget(null)
            loadLeagues()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to delete league' })
        } finally {
            setDeleteLoading(false)
        }
    }

    const formatDate = (dateStr) => {
        if (!dateStr) return 'Never'
        return new Date(dateStr).toLocaleDateString('en-GB', {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        })
    }

    const getLevelBadge = (level) => {
        return (
            <Badge className={LEVEL_BADGE_CLASSES[level] || 'bg-secondary text-muted-foreground'}>
                {level}
            </Badge>
        )
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Academy Tracking</h2>
                <p className="text-muted-foreground mt-1">Manage youth league configurations and sync academy player appearances</p>
            </div>

            {/* Message Display */}
            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Active Leagues</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.leagues?.active || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Appearances</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.appearances?.total || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Last 7 Days</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.appearances?.last_7_days || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Tracked Players</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.tracked_players_with_appearances || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Leagues Card */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Academy Leagues</CardTitle>
                            <CardDescription>
                                Configure which youth leagues to track for player appearances
                            </CardDescription>
                        </div>
                        <div className="flex items-center gap-2">
                            <Button
                                variant="outline"
                                onClick={handleSyncAll}
                                disabled={syncAllLoading || leagues.length === 0}
                            >
                                {syncAllLoading ? (
                                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                ) : (
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                )}
                                Sync All
                            </Button>
                            <Button onClick={() => setAddDialogOpen(true)}>
                                <Plus className="h-4 w-4 mr-2" />
                                Add League
                            </Button>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                            Loading leagues...
                        </div>
                    ) : leagues.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <GraduationCap className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>No academy leagues configured</p>
                            <p className="text-sm mt-1">Add youth leagues to start tracking academy player appearances</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {leagues.map((league) => (
                                <div key={league.id} className="border rounded-lg p-4">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div>
                                                <div className="flex items-center gap-2">
                                                    <span className="font-medium">{league.name}</span>
                                                    {getLevelBadge(league.level)}
                                                    <Badge variant={league.is_active ? 'default' : 'secondary'}>
                                                        {league.is_active ? 'Active' : 'Inactive'}
                                                    </Badge>
                                                </div>
                                                <div className="text-sm text-muted-foreground mt-1">
                                                    {league.country && `${league.country} · `}
                                                    API ID: {league.api_league_id}
                                                    {league.season && ` · Season ${league.season}`}
                                                </div>
                                                <div className="text-xs text-muted-foreground mt-1">
                                                    <Calendar className="h-3 w-3 inline mr-1" />
                                                    Last synced: {formatDate(league.last_synced_at)}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => handleSyncLeague(league.id)}
                                                disabled={syncingLeagueId === league.id}
                                            >
                                                {syncingLeagueId === league.id ? (
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    <RefreshCw className="h-4 w-4" />
                                                )}
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => toggleActive(league)}
                                            >
                                                {league.is_active ? 'Disable' : 'Enable'}
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="destructive"
                                                onClick={() => setDeleteTarget(league)}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Cohorts Link */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Users className="h-5 w-5" />
                                Alumni Cohorts
                            </CardTitle>
                            <CardDescription>
                                Seed and manage academy player cohorts — track where youth players end up
                            </CardDescription>
                        </div>
                        <Link to="/admin/cohorts">
                            <Button>
                                Manage Cohorts
                                <ArrowRight className="h-4 w-4 ml-2" />
                            </Button>
                        </Link>
                    </div>
                </CardHeader>
            </Card>

            {/* Add League Dialog */}
            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add Academy League</DialogTitle>
                        <DialogDescription>
                            Configure a youth league to track player appearances
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>API League ID</Label>
                                <Input
                                    type="number"
                                    value={newLeague.api_league_id}
                                    onChange={(e) => setNewLeague({ ...newLeague, api_league_id: e.target.value })}
                                    placeholder="e.g., 711"
                                />
                                <p className="text-xs text-muted-foreground">
                                    Find IDs at api-football.com
                                </p>
                            </div>
                            <div className="space-y-2">
                                <Label>Level</Label>
                                <Select
                                    value={newLeague.level}
                                    onValueChange={(value) => setNewLeague({ ...newLeague, level: value })}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="U18">U18</SelectItem>
                                        <SelectItem value="U21">U21</SelectItem>
                                        <SelectItem value="U23">U23</SelectItem>
                                        <SelectItem value="Reserve">Reserve</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>League Name</Label>
                            <Input
                                value={newLeague.name}
                                onChange={(e) => setNewLeague({ ...newLeague, name: e.target.value })}
                                placeholder="e.g., Premier League 2"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Country (optional)</Label>
                                <Input
                                    value={newLeague.country}
                                    onChange={(e) => setNewLeague({ ...newLeague, country: e.target.value })}
                                    placeholder="e.g., England"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Season</Label>
                                <Input
                                    type="number"
                                    value={newLeague.season}
                                    onChange={(e) => setNewLeague({ ...newLeague, season: e.target.value })}
                                    placeholder="2026"
                                />
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleAddLeague} disabled={addLoading}>
                            {addLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Add League
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Academy League?</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete <strong>{deleteTarget?.name}</strong>?
                            This will also delete all associated player appearances.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteTarget(null)}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={handleDelete} disabled={deleteLoading}>
                            {deleteLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
