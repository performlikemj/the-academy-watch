import { useState, useEffect, useCallback, useRef } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Loader2, RefreshCw, GraduationCap, Users, Play, Trash2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { STATUS_BADGE_CLASSES } from '../../lib/theme-constants'

export function AdminCohorts() {
    // Message
    const [message, setMessage] = useState(null)

    // Big 6 seeding
    const [big6Loading, setBig6Loading] = useState(false)
    const [, setBig6JobId] = useState(null)
    const [big6Progress, setBig6Progress] = useState(null)
    const big6PollRef = useRef(null)

    // Single cohort seed
    const [cohortForm, setCohortForm] = useState({ team_api_id: '', league_api_id: '', season: '' })
    const [cohortSeedLoading, setCohortSeedLoading] = useState(false)

    // Cohort list
    const [cohorts, setCohorts] = useState([])
    const [cohortsLoading, setCohortsLoading] = useState(true)
    const [actionLoading, setActionLoading] = useState(null)

    // Load cohorts
    const loadCohorts = useCallback(async () => {
        try {
            setCohortsLoading(true)
            const data = await APIService.adminGetCohortSeedStatus()
            setCohorts(Array.isArray(data) ? data : data?.cohorts || [])
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to load cohorts' })
        } finally {
            setCohortsLoading(false)
        }
    }, [])

    useEffect(() => {
        loadCohorts()
    }, [loadCohorts])

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (big6PollRef.current) {
                clearInterval(big6PollRef.current)
            }
        }
    }, [])

    // Seed Big 6
    const handleSeedBig6 = async () => {
        setBig6Loading(true)
        setBig6Progress(null)
        setMessage(null)

        try {
            const result = await APIService.adminSeedBig6()
            const jobId = result.job_id

            if (!jobId) {
                setMessage({ type: 'success', text: 'Big 6 seeding completed' })
                setBig6Loading(false)
                loadCohorts()
                return
            }

            setBig6JobId(jobId)

            big6PollRef.current = setInterval(async () => {
                try {
                    const job = await APIService.adminGetJobStatus(jobId)
                    if (job) {
                        setBig6Progress(job)

                        if (job.status === 'completed' || job.status === 'failed') {
                            clearInterval(big6PollRef.current)
                            big6PollRef.current = null
                            setBig6Loading(false)
                            setBig6JobId(null)

                            if (job.status === 'completed') {
                                setMessage({ type: 'success', text: 'Big 6 seeding completed successfully' })
                            } else {
                                setMessage({ type: 'error', text: `Big 6 seeding failed: ${job.error || 'Unknown error'}` })
                            }

                            loadCohorts()
                        }
                    }
                } catch (err) {
                    console.error('Failed to poll job status:', err)
                }
            }, 3000)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to start Big 6 seeding' })
            setBig6Loading(false)
        }
    }

    // Seed single cohort
    const handleSeedCohort = async () => {
        if (!cohortForm.team_api_id || !cohortForm.league_api_id || !cohortForm.season) {
            setMessage({ type: 'error', text: 'All fields are required' })
            return
        }

        setCohortSeedLoading(true)
        setMessage(null)

        try {
            await APIService.adminSeedCohort({
                team_api_id: parseInt(cohortForm.team_api_id),
                league_api_id: parseInt(cohortForm.league_api_id),
                season: parseInt(cohortForm.season),
            })
            setMessage({ type: 'success', text: 'Cohort seeded successfully' })
            setCohortForm({ team_api_id: '', league_api_id: '', season: '' })
            loadCohorts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to seed cohort' })
        } finally {
            setCohortSeedLoading(false)
        }
    }

    // Sync journeys for a cohort
    const handleSyncJourneys = async (cohort) => {
        setActionLoading(`sync-${cohort.id}`)
        try {
            await APIService.adminSyncCohortJourneys(cohort.id)
            setMessage({ type: 'success', text: `Journeys synced for ${cohort.team_name}` })
            loadCohorts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to sync journeys' })
        } finally {
            setActionLoading(null)
        }
    }

    // Refresh stats for a cohort
    const handleRefreshStats = async (cohort) => {
        setActionLoading(`refresh-${cohort.id}`)
        try {
            await APIService.adminRefreshCohortStats(cohort.id)
            setMessage({ type: 'success', text: `Stats refreshed for ${cohort.team_name}` })
            loadCohorts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to refresh stats' })
        } finally {
            setActionLoading(null)
        }
    }

    // Delete a cohort
    const handleDeleteCohort = async (cohort) => {
        if (!confirm(`Are you sure you want to delete the cohort for ${cohort.team_name}?`)) return

        setActionLoading(`delete-${cohort.id}`)
        try {
            await APIService.adminDeleteCohort(cohort.id)
            setMessage({ type: 'success', text: `Cohort deleted for ${cohort.team_name}` })
            loadCohorts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to delete cohort' })
        } finally {
            setActionLoading(null)
        }
    }

    const COHORT_STATUS_COLORS = {
        pending: 'bg-amber-50 text-amber-800 border-amber-200',
        seeding: 'bg-primary/10 text-primary border-primary/20',
        syncing_journeys: 'bg-primary/10 text-primary border-primary/20',
        complete: 'bg-emerald-50 text-emerald-800 border-emerald-200',
        partial: 'bg-amber-50 text-amber-800 border-amber-200',
        no_data: 'bg-stone-100 text-stone-700 border-stone-200',
        failed: 'bg-rose-50 text-rose-800 border-rose-200',
    }

    const getStatusBadge = (status) => {
        return (
            <Badge className={COHORT_STATUS_COLORS[status] || 'bg-secondary text-muted-foreground'}>
                {status}
            </Badge>
        )
    }

    const big6ProgressPercent = big6Progress && big6Progress.total > 0
        ? Math.round((big6Progress.progress / big6Progress.total) * 100)
        : 0

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Academy Cohorts</h2>
                <p className="text-muted-foreground mt-1">Seed and manage academy player cohorts by team and season</p>
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

            <div className="grid gap-6 lg:grid-cols-2">
                {/* Big 6 Seeding */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <GraduationCap className="h-5 w-5" />
                            Seed Big 6
                        </CardTitle>
                        <CardDescription>
                            Seed academy cohorts for all Big 6 Premier League clubs
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <Button
                            onClick={handleSeedBig6}
                            disabled={big6Loading}
                            className="w-full"
                        >
                            {big6Loading ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            ) : (
                                <Play className="h-4 w-4 mr-2" />
                            )}
                            Seed Big 6
                        </Button>

                        {big6Loading && big6Progress && (
                            <div className="space-y-2">
                                <div className="flex items-center justify-between text-sm text-muted-foreground">
                                    <span>{big6Progress.current_item || 'Processing...'}</span>
                                    <span>{big6Progress.progress || 0} / {big6Progress.total || 0}</span>
                                </div>
                                <div className="w-full bg-muted rounded-full h-2.5">
                                    <div
                                        className="bg-primary h-2.5 rounded-full transition-all duration-300"
                                        style={{ width: `${big6ProgressPercent}%` }}
                                    />
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Single Cohort Seed */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Users className="h-5 w-5" />
                            Seed Single Cohort
                        </CardTitle>
                        <CardDescription>
                            Seed a cohort for a specific team, league, and season
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-3 gap-3">
                            <div className="space-y-2">
                                <Label>Team API ID</Label>
                                <Input
                                    type="number"
                                    value={cohortForm.team_api_id}
                                    onChange={(e) => setCohortForm({ ...cohortForm, team_api_id: e.target.value })}
                                    placeholder="e.g., 33"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>League API ID</Label>
                                <Input
                                    type="number"
                                    value={cohortForm.league_api_id}
                                    onChange={(e) => setCohortForm({ ...cohortForm, league_api_id: e.target.value })}
                                    placeholder="e.g., 39"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Season</Label>
                                <Input
                                    type="number"
                                    value={cohortForm.season}
                                    onChange={(e) => setCohortForm({ ...cohortForm, season: e.target.value })}
                                    placeholder="e.g., 2024"
                                />
                            </div>
                        </div>
                        <Button
                            onClick={handleSeedCohort}
                            disabled={cohortSeedLoading}
                            className="w-full"
                        >
                            {cohortSeedLoading ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            ) : (
                                <Play className="h-4 w-4 mr-2" />
                            )}
                            Seed Cohort
                        </Button>
                    </CardContent>
                </Card>
            </div>

            {/* Cohort List */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Cohorts</CardTitle>
                            <CardDescription>
                                All seeded academy cohorts and their current status
                            </CardDescription>
                        </div>
                        <Button variant="outline" onClick={loadCohorts} disabled={cohortsLoading}>
                            {cohortsLoading ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            ) : (
                                <RefreshCw className="h-4 w-4 mr-2" />
                            )}
                            Refresh
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    {cohortsLoading ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                            Loading cohorts...
                        </div>
                    ) : cohorts.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <GraduationCap className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>No cohorts seeded yet</p>
                            <p className="text-sm mt-1">Use the forms above to seed academy cohorts</p>
                        </div>
                    ) : (
                        <div className="border rounded-lg overflow-auto">
                            <table className="w-full text-sm">
                                <thead className="bg-muted/50">
                                    <tr className="text-left">
                                        <th className="px-4 py-3 font-medium">Team</th>
                                        <th className="px-4 py-3 font-medium">League</th>
                                        <th className="px-4 py-3 font-medium">Season</th>
                                        <th className="px-4 py-3 font-medium">Players</th>
                                        <th className="px-4 py-3 font-medium">Status</th>
                                        <th className="px-4 py-3 font-medium">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {cohorts.map((cohort) => (
                                        <tr key={cohort.id} className="border-t hover:bg-muted/30">
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
                                                    {cohort.team_logo && (
                                                        <img
                                                            src={cohort.team_logo}
                                                            alt={cohort.team_name}
                                                            className="h-6 w-6 object-contain"
                                                        />
                                                    )}
                                                    <span className="font-medium">{cohort.team_name}</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-muted-foreground">
                                                {cohort.league_name}
                                            </td>
                                            <td className="px-4 py-3">
                                                {cohort.season}
                                            </td>
                                            <td className="px-4 py-3">
                                                {cohort.analytics?.total_players ?? 0}
                                            </td>
                                            <td className="px-4 py-3">
                                                {getStatusBadge(cohort.sync_status)}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() => handleSyncJourneys(cohort)}
                                                        disabled={actionLoading === `sync-${cohort.id}`}
                                                        title="Sync Journeys"
                                                    >
                                                        {actionLoading === `sync-${cohort.id}` ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <Play className="h-4 w-4" />
                                                        )}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() => handleRefreshStats(cohort)}
                                                        disabled={actionLoading === `refresh-${cohort.id}`}
                                                        title="Refresh Stats"
                                                    >
                                                        {actionLoading === `refresh-${cohort.id}` ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <RefreshCw className="h-4 w-4" />
                                                        )}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="destructive"
                                                        onClick={() => handleDeleteCohort(cohort)}
                                                        disabled={actionLoading === `delete-${cohort.id}`}
                                                        title="Delete Cohort"
                                                    >
                                                        {actionLoading === `delete-${cohort.id}` ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <Trash2 className="h-4 w-4" />
                                                        )}
                                                    </Button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
